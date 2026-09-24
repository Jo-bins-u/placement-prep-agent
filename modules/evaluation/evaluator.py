"""Target app M3 evaluator with ML adapter integration.

This keeps the application contract unchanged while adopting the source project's
trained scorer/feedback behavior when available. The fallback path remains the
original keyword-based heuristic so the app continues to work without a model.
"""

try:
    from .ml_adapter import generate_feedback, score_answer
except ImportError:  # pragma: no cover - direct-module runtime used by the target app
    from modules.evaluation.ml_adapter import generate_feedback, score_answer


def evaluate_answer(question: dict, answer_text: str):
    """Returns (score: float 0-100, feedback: str)."""
    if question.get("type") == "mcq":
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

    score = score_answer(question, answer_text)
    if score == 0.0:
        # Keep the legacy rubric-based logic as a graceful fallback.
        answer_lower = answer_text.lower()
        keywords = question.get("keywords", [])
        matched = [kw for kw in keywords if str(kw).lower() in answer_lower]
        missing = [kw for kw in keywords if str(kw) not in matched]
        score = round(100 * len(matched) / len(keywords), 1) if keywords else 0.0
        if score >= 75:
            verdict = "Strong answer."
        elif score >= 40:
            verdict = "Partially correct."
        else:
            verdict = "Missing most of the key concepts."
        feedback = verdict
        if missing:
            shown = missing[:4]
            feedback += f" Consider mentioning: {', '.join(shown)}."
        return score, feedback

    feedback = generate_feedback(question, answer_text, score)
    return score, feedback
