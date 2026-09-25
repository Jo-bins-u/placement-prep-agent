"""M3 — answer evaluation.

Written answers are scored in up to three ways, strongest available first:

1. AI grading (Groq, when GROQ_API_KEY is set): judges concepts rather than exact
   wording, blended 70/30 with the rubric score below. If the AI score is wildly
   above the rubric for a very short answer (e.g. an answer that tries to talk the
   grader into a high score) the rubric score is used instead.
2. A trained scorer model, if its files are present (m3_upgrade/ — optional).
3. Rubric keyword coverage: the share of the question's key concepts that appear
   in the answer as whole words (light stemming, multi-word phrases need all their
   words). Answers that are mostly a list of the keywords are capped at 50, because
   listing terms is not explaining them.

MCQ answers are exact matches.
"""

import re

try:
    from .ml_adapter import generate_feedback, load_or_train_scorer, score_answer
except ImportError:  # pragma: no cover - direct-module runtime used by the target app
    from modules.evaluation.ml_adapter import generate_feedback, load_or_train_scorer, score_answer

try:
    from services.llm_service import grade_answer
except Exception:  # pragma: no cover
    grade_answer = None

AI_WEIGHT = 0.7
# Text that demands a score from the grader, or talks to the grader directly. An answer with
# this is scored by the rubric only (the AI's opinion is not trusted). Deliberately narrow:
# honest answers that merely *mention* instructions, prompts or points must not be flagged -
# anything subtler is left to the AI grader's own "manipulation" flag and the 30% rubric weight.
_GRADER_MANIPULATION = re.compile(
    r"\b(give|award|assign|grant)\s+(me|this( answer)?|it|my answer)\b.{0,25}?\b(100|full marks|full score|full points|perfect score|maximum score|max score|high score|top marks)\b"
    r"|\b(score|grade|rate|mark)\s+(this( answer)?|me|my answer)\s+(as\s+|with\s+|a\s+)?(100|10\s*/\s*10|highly|perfect|full marks|correct)\b"
    r"|\b(this answer|my answer|it|this)\s+deserves?\s+(a\s+)?(100\s*/\s*100|100 ?points|full marks|10\s*/\s*10|a perfect score|the maximum score|maximum marks)"
    r"|\b(set|output|return|make|put)\s+(the\s+|my\s+|its\s+)?(score|grade|mark)\s*(to|=|:|as|at)?\s*100\b"
    r"|\bscore\s*[:=]\s*100\b"
    r"|(^|[.!?\n]\s*)(note to (the )?)?(grader|evaluator|examiner|assessor)\s*(note|instructions?|message)?\s*:"  # addressed at sentence start
    r"|\byou are (an?|the) (ai |llm )?(grader|evaluator|examiner|assessor)\b"
    r"|</?candidate_answer>",
    re.IGNORECASE | re.DOTALL,
)
STUFFING_CAP = 50.0
_STOP = {"the", "a", "an", "of", "to", "in", "and", "or", "is", "are", "it", "on", "for", "with", "by", "as", "be", "that", "this"}


def _stem(word: str) -> str:
    """Very light suffix stripping (two passes): 'contiguously' and 'contiguous' -> 'contiguou'."""
    for _ in range(2):
        for suffix in ("ations", "ation", "ings", "ing", "ies", "ied", "ers", "er", "es", "ed", "ly", "s"):
            if len(word) > len(suffix) + 2 and word.endswith(suffix):
                word = word[: -len(suffix)] + ("y" if suffix in ("ies", "ied") else "")
                break
    return word


def _stems(text: str) -> list:
    return [_stem(w) for w in re.findall(r"[a-z0-9+#]+", str(text or "").lower()) if w not in _STOP]


def rubric_score(question: dict, answer_text: str):
    """Return (score 0-100, matched keywords, missing keywords, stuffing_capped)."""
    keywords = [str(k) for k in question.get("keywords", []) if str(k).strip()]
    if not keywords:
        return 0.0, [], [], False
    answer_stems = _stems(answer_text)
    answer_set = set(answer_stems)
    matched, missing, keyword_stems = [], [], set()
    for kw in keywords:
        kw_stems = [s for s in _stems(kw)] or [_stem(kw.lower())]
        keyword_stems.update(kw_stems)
        (matched if all(s in answer_set for s in kw_stems) else missing).append(kw)
    score = round(100 * len(matched) / len(keywords), 1)

    # "Buzzword list" detection: most of the answer is just the rubric terms.
    capped = False
    if answer_stems and score > STUFFING_CAP:
        keyword_share = sum(1 for s in answer_stems if s in keyword_stems) / len(answer_stems)
        if keyword_share >= 0.6 or len(answer_stems) < len(matched) + 4:
            score, capped = STUFFING_CAP, True
    return score, matched, missing, capped


def _rubric_feedback(score: float, missing: list, capped: bool) -> str:
    if capped:
        return "You named the right concepts but didn't explain them. Describe how and why each one matters."
    verdict = "Strong answer." if score >= 75 else ("Partially correct." if score >= 40 else "Missing most of the key concepts.")
    if missing:
        verdict += f" Consider covering: {', '.join(missing[:4])}."
    return verdict


def evaluate_answer_detailed(question: dict, answer_text: str) -> dict:
    """Score an answer and explain how. Keys: score, feedback, method, matched, missing."""
    if question.get("type") == "mcq":
        correct = (answer_text or "").strip().lower() == str(question.get("answer", "")).strip().lower()
        return {"score": 100.0 if correct else 0.0, "method": "exact_match", "matched": [], "missing": [],
                "feedback": "Correct." if correct else f"Not quite — the correct answer is '{question.get('answer')}'."}

    if not answer_text or not answer_text.strip():
        return {"score": 0.0, "feedback": "No answer submitted.", "method": "empty", "matched": [], "missing": list(question.get("keywords", []))}

    rubric, matched, missing, capped = rubric_score(question, answer_text)

    # Strip zero-width/invisible characters first so they can't be used to split trigger words.
    visible = re.sub(r"[\u00ad\u200b-\u200f\u2060-\u2064\ufeff]", "", answer_text)
    manipulation = bool(_GRADER_MANIPULATION.search(visible))
    ai = grade_answer(question, answer_text) if grade_answer and not manipulation else None
    if ai is not None:
        words = len(answer_text.split())
        if ai.get("manipulation"):
            manipulation, ai = True, None  # the grader itself flagged instructions aimed at it
        elif ai["score"] - rubric > 60 and words < 12:
            ai = None  # implausible: tiny answer, huge AI score — don't trust it
    if manipulation:
        return {"score": min(rubric, STUFFING_CAP), "method": "rubric", "rubric_score": rubric,
                "matched": matched, "missing": missing, "flagged": "grader_manipulation",
                "feedback": "Your answer included instructions to the grader, so it was scored on key concepts only. "
                            "Just explain the concepts."}
    if ai is not None:
        score = round(AI_WEIGHT * ai["score"] + (1 - AI_WEIGHT) * rubric, 1)
        if capped:
            score = min(score, STUFFING_CAP)
        feedback = ai["feedback"]
        if ai["missing"]:
            feedback += " Missing: " + ", ".join(ai["missing"][:4]) + "."
        return {"score": score, "feedback": feedback, "method": "ai+rubric", "ai_score": ai["score"], "rubric_score": rubric,
                "matched": ai["covered"] or matched, "missing": ai["missing"] or missing}

    if load_or_train_scorer():
        model_score = score_answer(question, answer_text)
        score = round((model_score + rubric) / 2, 1)
        return {"score": min(score, STUFFING_CAP) if capped else score, "feedback": generate_feedback(question, answer_text, score),
                "method": "model+rubric", "rubric_score": rubric, "matched": matched, "missing": missing}

    return {"score": rubric, "feedback": _rubric_feedback(rubric, missing, capped), "method": "rubric",
            "rubric_score": rubric, "matched": matched, "missing": missing}


def evaluate_answer(question: dict, answer_text: str):
    """Returns (score: float 0-100, feedback: str)."""
    result = evaluate_answer_detailed(question, answer_text)
    return result["score"], result["feedback"]
