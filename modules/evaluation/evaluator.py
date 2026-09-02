"""
Module 3 — Evaluation & Feedback.

Supports dual-mode scoring:
  1. Trained ML Scorer (m3_upgrade/scorer/scorer_model.joblib) when available
  2. Rule-based keyword-overlap rubric fallback when ML model isn't trained yet

MCQ: exact match (0 or 100).
Signature remains strictly (score: float 0-100, feedback: str).
"""

import os
import sys
import importlib.util
from pathlib import Path

# Fix Windows PyTorch DLL loading issue — must load torch BEFORE numpy/scipy/joblib
if sys.platform == "win32":
    spec = importlib.util.find_spec("torch")
    if spec and spec.origin:
        torch_lib = Path(spec.origin).parent / "lib"
        if torch_lib.exists():
            os.environ["PATH"] = str(torch_lib) + os.pathsep + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(str(torch_lib))
            except Exception:
                pass
    try:
        import torch
    except Exception:
        pass

import joblib

# Try loading trained ML model lazily
_ML_MODEL_DATA = None
_ML_LOADED = False


def _get_ml_model():
    global _ML_MODEL_DATA, _ML_LOADED
    if _ML_LOADED:
        return _ML_MODEL_DATA

    _ML_LOADED = True
    model_dir = Path(__file__).parent.parent.parent / "m3_upgrade" / "scorer"
    model_path = model_dir / "scorer_model.joblib"

    if model_path.exists():
        try:
            data = joblib.load(model_path)
            backend = data.get("backend", "tfidf")
            if backend == "tfidf":
                vec_path = model_dir / "scorer_model_vectorizer.joblib"
                if vec_path.exists():
                    data["vectorizer"] = joblib.load(vec_path)
                    _ML_MODEL_DATA = data
            elif backend == "embeddings":
                from sentence_transformers import SentenceTransformer
                data["encoder"] = SentenceTransformer("all-MiniLM-L6-v2")
                _ML_MODEL_DATA = data
        except Exception as e:
            print(f"[evaluator] Note: Failed loading ML model, using keyword rubric fallback. Error: {e}")

    return _ML_MODEL_DATA


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

    # Try trained ML model first
    ml_data = _get_ml_model()
    score = None

    if ml_data:
        try:
            model = ml_data["model"]
            backend = ml_data.get("backend", "tfidf")
            text = f"{question['prompt']} [SEP] {answer_text}"

            if backend == "tfidf" and "vectorizer" in ml_data:
                vec = ml_data["vectorizer"]
                X = vec.transform([text])
                raw_score = float(model.predict(X)[0])
                # Scale 0-10 score to 0-100
                score = round(max(0.0, min(100.0, raw_score * 10.0)), 1)
            elif backend == "embeddings" and "encoder" in ml_data:
                encoder = ml_data["encoder"]
                X = encoder.encode([text])
                raw_score = float(model.predict(X)[0])
                score = round(max(0.0, min(100.0, raw_score * 10.0)), 1)
        except Exception as e:
            score = None

    # Fallback to keyword-overlap rubric if ML score is unavailable
    answer_lower = answer_text.lower()
    keywords = question.get("keywords", [])
    matched = [kw for kw in keywords if kw.lower() in answer_lower]
    missing = [kw for kw in keywords if kw not in matched]

    if score is None:
        score = round(100 * len(matched) / len(keywords), 1) if keywords else 50.0

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

