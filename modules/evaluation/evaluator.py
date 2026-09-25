"""M3 — answer evaluation.

Written answers are scored in up to three ways, strongest available first:

1. AI grading (Groq, when GROQ_API_KEY is set): judges concepts rather than exact
   wording, blended 70/30 with the rubric score below. If the AI score is wildly
   above the rubric for a very short answer (e.g. an answer that tries to talk the
   grader into a high score) the rubric score is used instead.
2. A trained scorer model, if its files are present (m3_upgrade/ — optional).
3. Concept rubric: each key concept may list alternative phrasings ("contiguous|next to
   each other"). A concept counts when any phrasing appears in the answer, with light
   stemming and typo tolerance ("conection" ~ "connection"); a multi-word phrasing that is
   half present earns half credit. This is combined with how close the answer's meaning is
   to the question's model answer (character n-gram TF-IDF similarity), so a correct answer
   in the candidate's own words still scores well. Answers that are mostly a list of the
   keywords are capped at 50, because listing terms is not explaining them.

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
SIMILARITY_FLOOR, SIMILARITY_FULL = 0.10, 0.42   # cosine similarity mapped to 0..100 between these
SIMILARITY_WEIGHT = 0.5                          # weight of meaning-similarity when a model answer exists
COVERAGE_CURVE = 0.8                             # exponent applied to the concept-coverage fraction
FUZZY_RATIO = 0.84                               # typo tolerance for words of 5+ letters


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


def concept_alternatives(keyword) -> list:
    """'contiguous|next to each other' -> ['contiguous', 'next to each other']."""
    return [alt.strip() for alt in str(keyword).split("|") if alt.strip()]


def concept_name(keyword) -> str:
    alternatives = concept_alternatives(keyword)
    return alternatives[0] if alternatives else str(keyword)


def display_concept(name: str) -> str:
    """How a concept is shown to the candidate: 'lru' -> 'LRU', 'random access' -> 'Random access'."""
    name = str(name).strip()
    if 2 <= len(name) <= 4 and name.isalpha() and name.islower():
        return name.upper()
    return name[:1].upper() + name[1:] if name[:1].islower() else name


def _word_present(word: str, answer_set: set, long_words: list) -> bool:
    if word in answer_set:
        return True
    if len(word) >= 5:  # tolerate small typos in longer words
        from difflib import SequenceMatcher
        return any(abs(len(w) - len(word)) <= 2 and SequenceMatcher(None, word, w).ratio() >= FUZZY_RATIO
                   for w in long_words)
    return False


def _alternative_credit(alternative: str, answer_text_lower: str, answer_set: set, long_words: list) -> float:
    words = _stems(alternative)
    if not words or all(len(w) <= 2 for w in words):
        # symbols or very short tokens ("[]", "o(1)", "l2"): need the exact phrase
        return 1.0 if alternative.lower() in answer_text_lower else 0.0
    hits = sum(_word_present(w, answer_set, long_words) for w in words)
    if hits == len(words):
        return 1.0
    if len(words) >= 3 and hits >= 2:  # most of a longer phrase: half credit
        return 0.5
    return 0.0


def concept_coverage(question: dict, answer_text: str) -> list:
    """[(concept name, credit 0/0.5/1)] for every key concept of the question."""
    answer_stems = _stems(answer_text)
    answer_set = set(answer_stems)
    long_words = [w for w in answer_set if len(w) >= 4]
    lowered = str(answer_text or "").lower()
    prompt_stems = set(_stems(question.get("prompt", "")))
    out = []
    for keyword in question.get("keywords", []) or []:
        if not str(keyword).strip():
            continue
        # A phrasing made only of the question's own words proves nothing (the answer could just
        # echo the question), so it doesn't earn credit on its own.
        alternatives = [alt for alt in concept_alternatives(keyword)
                        if not (set(_stems(alt)) and set(_stems(alt)) <= prompt_stems)]
        credit = max((_alternative_credit(alt, lowered, answer_set, long_words) for alt in alternatives), default=0.0)
        out.append((display_concept(concept_name(keyword)), credit))
    return out


_VECTORIZER = []


def _vectorizer():
    """Character n-gram TF-IDF fitted once on all model answers in the question banks."""
    if not _VECTORIZER:
        from sklearn.feature_extraction.text import TfidfVectorizer
        corpus = []
        try:
            import json
            from pathlib import Path
            data_dir = Path(__file__).resolve().parents[2] / "data"
            for name in ("question_bank.json", "interview_bank.json"):
                path = data_dir / name
                if path.exists():
                    items = json.loads(path.read_text(encoding="utf-8"))
                    items = items if isinstance(items, list) else items.get("behavioral", [])
                    corpus += [str(q.get("ideal_answer") or "") + " " + str(q.get("prompt") or "") for q in items]
        except Exception:
            pass
        corpus = [c for c in corpus if c.strip()] or ["placeholder text"]
        _VECTORIZER.append(TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True,
                                           lowercase=True).fit(corpus))
    return _VECTORIZER[0]


def _content(text: str, drop: set) -> str:
    """Words that carry meaning: no stop words and none of the question's own words (so merely
    repeating the question - "polymorphism is when..." - doesn't look similar to the answer)."""
    words = re.findall(r"[a-z0-9+#]+", str(text or "").lower())
    return " ".join(w for w in words if w not in _STOP and _stem(w) not in drop and len(w) > 1)


def meaning_similarity(answer_text: str, reference: str, prompt: str = "") -> float:
    """0..100: how close the answer is to the model answer in wording/meaning (not keyword-exact).
    Short answers are damped: a one-liner can't match a full explanation's meaning."""
    if not reference or not str(answer_text or "").strip():
        return 0.0
    drop = {_stem(w) for w in re.findall(r"[a-z0-9+#]+", str(prompt or "").lower())}
    answer, ref = _content(str(answer_text)[:4000], drop), _content(reference, drop)
    if not answer or not ref:
        return 0.0
    try:
        from sklearn.metrics.pairwise import cosine_similarity
        vectors = _vectorizer().transform([answer, ref])
        cosine = float(cosine_similarity(vectors[0], vectors[1])[0][0])
    except Exception:
        return 0.0
    scaled = max(0.0, min(1.0, (cosine - SIMILARITY_FLOOR) / (SIMILARITY_FULL - SIMILARITY_FLOOR)))
    length = min(1.0, len(answer.split()) / max(6.0, 0.3 * len(ref.split())))
    return round(scaled * length * 100, 1)


def rubric_details(question: dict, answer_text: str) -> dict:
    """Rubric score with its parts: concept coverage, meaning similarity and the stuffing cap."""
    concepts = concept_coverage(question, answer_text)
    if not concepts:
        return {"score": 0.0, "coverage": 0.0, "similarity": 0.0, "matched": [], "partial": [], "missing": [], "capped": False}
    # Concave curve: covering the core half of the concepts is a partially-correct answer (~57),
    # not a failing one; full coverage is still required for 100.
    coverage = round(100 * (sum(c for _, c in concepts) / len(concepts)) ** COVERAGE_CURVE, 1)
    similarity = meaning_similarity(answer_text, question.get("ideal_answer"), question.get("prompt", ""))
    score = coverage
    if question.get("ideal_answer"):
        # Take the better of pure concept coverage and a blend with meaning similarity, so a
        # correct answer in different words isn't punished for missing the exact terms.
        score = max(coverage, round((1 - SIMILARITY_WEIGHT) * coverage + SIMILARITY_WEIGHT * similarity, 1))
    matched = [n for n, c in concepts if c == 1.0]
    partial = [n for n, c in concepts if c == 0.5]
    missing = [n for n, c in concepts if c == 0.0]

    # "Buzzword list" detection: most of the answer is just the rubric terms.
    capped = False
    answer_stems = _stems(answer_text)
    keyword_stems = {s for kw in question.get("keywords", []) for alt in concept_alternatives(kw) for s in _stems(alt)}
    if answer_stems and score > STUFFING_CAP:
        # Words that aren't rubric terms are the explanation; a bare list of terms has almost none.
        explaining = sum(1 for s in answer_stems if s not in keyword_stems)
        if explaining < max(3, 0.8 * len(matched)) or len(answer_stems) < len(matched) + 4:
            score, capped = STUFFING_CAP, True
    return {"score": round(score, 1), "coverage": coverage, "similarity": similarity, "matched": matched,
            "partial": partial, "missing": missing, "capped": capped}


def rubric_score(question: dict, answer_text: str):
    """Return (score 0-100, matched concepts, missing concepts, stuffing_capped)."""
    details = rubric_details(question, answer_text)
    return details["score"], details["matched"] + details["partial"], details["missing"], details["capped"]


def _band(score: float) -> str:
    return "Strong answer." if score >= 75 else ("Partially correct." if score >= 40 else "Needs work.")


def _rubric_feedback(details: dict) -> str:
    if details["capped"]:
        return "You named the right concepts but didn't explain them. Describe how and why each one matters."
    parts = [_band(details["score"])]
    if details["matched"]:
        parts.append(f"You covered {', '.join(details['matched'][:4])}.")
    if details["partial"]:
        parts.append(f"You touched on {', '.join(details['partial'][:3])} - explain it more fully.")
    if details["missing"]:
        parts.append(f"To make it complete, add: {', '.join(details['missing'][:4])}.")
    return " ".join(parts)


def _suggestions(details: dict) -> list:
    tips = [f"Add a sentence on {name} and how it applies to this question." for name in details["missing"][:3]]
    tips += [f"Go deeper on {name} — say how it works, not just its name." for name in details["partial"][:2]]
    return tips


def evaluate_answer_detailed(question: dict, answer_text: str) -> dict:
    """Score an answer and explain how. Keys: score, feedback, method, matched, partial, missing,
    strengths, improvements, model_answer (+ ai_score / rubric_score / similarity when used)."""
    model_answer = question.get("ideal_answer") or ""
    if question.get("type") == "mcq":
        correct = (answer_text or "").strip().lower() == str(question.get("answer", "")).strip().lower()
        return {"score": 100.0 if correct else 0.0, "method": "exact_match", "matched": [], "partial": [], "missing": [],
                "strengths": [], "improvements": [], "model_answer": model_answer,
                "feedback": "Correct." if correct else f"Not quite — the correct answer is '{question.get('answer')}'."}

    if not answer_text or not answer_text.strip():
        return {"score": 0.0, "feedback": "No answer submitted.", "method": "empty", "matched": [], "partial": [],
                "missing": [concept_name(k) for k in question.get("keywords", [])], "strengths": [], "improvements": [],
                "model_answer": model_answer}

    details = rubric_details(question, answer_text)
    rubric = details["score"]
    common = {"rubric_score": rubric, "similarity": details["similarity"], "coverage": details["coverage"],
              "model_answer": model_answer, "partial": details["partial"]}

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
        return {**common, "score": min(rubric, STUFFING_CAP), "method": "rubric", "matched": details["matched"],
                "missing": details["missing"], "flagged": "grader_manipulation", "strengths": [], "improvements": [],
                "feedback": "Your answer included instructions to the grader, so it was scored on key concepts only. "
                            "Just explain the concepts."}
    if ai is not None:
        score = round(AI_WEIGHT * ai["score"] + (1 - AI_WEIGHT) * rubric, 1)
        if details["capped"]:
            score = min(score, STUFFING_CAP)
        return {**common, "score": score, "feedback": ai["feedback"], "method": "ai+rubric", "ai_score": ai["score"],
                "matched": ai.get("covered") or details["matched"],
                "partial": ai.get("partial") or details["partial"],
                "missing": ai.get("missing") or details["missing"],
                "strengths": ai.get("strengths") or [], "improvements": ai.get("improvements") or _suggestions(details),
                "model_answer": model_answer or ai.get("model_answer", "")}

    if load_or_train_scorer():
        model_score = score_answer(question, answer_text)
        score = round((model_score + rubric) / 2, 1)
        return {**common, "score": min(score, STUFFING_CAP) if details["capped"] else score,
                "feedback": generate_feedback(question, answer_text, score), "method": "model+rubric",
                "matched": details["matched"], "missing": details["missing"],
                "strengths": [f"Covered {m}" for m in details["matched"][:4]], "improvements": _suggestions(details)}

    return {**common, "score": rubric, "feedback": _rubric_feedback(details), "method": "rubric",
            "matched": details["matched"], "missing": details["missing"],
            "strengths": [f"Covered {m}" for m in details["matched"][:4]], "improvements": _suggestions(details)}


def evaluate_answer(question: dict, answer_text: str):
    """Returns (score: float 0-100, feedback: str)."""
    result = evaluate_answer_detailed(question, answer_text)
    return result["score"], result["feedback"]
