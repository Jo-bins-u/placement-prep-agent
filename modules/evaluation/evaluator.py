"""
Module 3 stand-in — Evaluation & Feedback.

MCQ: exact match, trivial.
Short answer: keyword-overlap against a rubric (each question's
`keywords` list in the question bank IS the rubric). This is
deliberately simple and explainable for the prototype — the real M3
(per the PRD) should layer an LLM-based grader on top of, or instead
of, this for nuance an exact-keyword match misses (e.g. someone
explaining the right concept in different words). Keep this function's
signature stable so that swap doesn't ripple through the app.
"""


def evaluate_answer(question: dict, answer_text: str):
    """Returns (score: float 0-100, feedback: str)."""
    if question["type"] == "mcq":
        return _evaluate_mcq(question, answer_text)
    return _evaluate_short_answer(question, answer_text)


def _evaluate_mcq(question: dict, answer_text: str):
    correct = answer_text.strip().lower() == question["answer"].strip().lower()
    score = 100.0 if correct else 0.0
    feedback = (
        "Correct."
        if correct
        else f"Not quite — the correct answer is '{question['answer']}'."
    )
    return score, feedback


def _evaluate_short_answer(question: dict, answer_text: str):
    if not answer_text or not answer_text.strip():
        return 0.0, "No answer submitted."

    answer_lower = answer_text.lower()
    keywords = question["keywords"]
    matched = [kw for kw in keywords if kw.lower() in answer_lower]
    missing = [kw for kw in keywords if kw not in matched]

    score = round(100 * len(matched) / len(keywords), 1) if keywords else 0.0

    if score >= 75:
        verdict = "Strong answer."
    elif score >= 40:
        verdict = "Partially correct."
    else:
        verdict = "Missing most of the key concepts."

    feedback = verdict
    if missing:
        # Cap how many we show so feedback stays readable
        shown = missing[:4]
        feedback += f" Consider mentioning: {', '.join(shown)}."

    return score, feedback
