"""Adapter for the source M3 ML upgrade.

This keeps the target application's public evaluator interface stable while
loading a real trained scorer model from the source project dataset when one is
available. If no saved model is present, it trains a small TF-IDF Ridge regressor
from the bundled seed dataset so the app still works in a clean environment.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DATASET = PROJECT_ROOT / "m3_upgrade" / "data" / "seed_dataset.jsonl"
SOURCE_SCORER_PATH = PROJECT_ROOT / "m3_upgrade" / "scorer" / "scorer_model.joblib"
SOURCE_VECTORIZER_PATH = PROJECT_ROOT / "m3_upgrade" / "scorer" / "scorer_model_vectorizer.joblib"
FEEDBACK_MODEL_PATH = PROJECT_ROOT / "m3_upgrade" / "feedback_generator" / "feedback_model"


def _make_text(question: Any, answer: Any) -> str:
    question_text = str(question or "")
    answer_text = str(answer or "")
    return f"{question_text} [SEP] {answer_text}"


def _load_seed_rows() -> list[dict]:
    if not SOURCE_DATASET.exists():
        return []
    rows: list[dict] = []
    with SOURCE_DATASET.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


@lru_cache(maxsize=1)
def load_or_train_scorer() -> Optional[Dict[str, Any]]:
    """Return the trained scorer bundle or train it lazily from the bundled seed data."""
    if SOURCE_SCORER_PATH.exists():
        try:
            payload = joblib.load(SOURCE_SCORER_PATH)
            if isinstance(payload, dict) and payload.get("model") is not None:
                if payload.get("backend") == "tfidf" and payload.get("vectorizer") is None:
                    if SOURCE_VECTORIZER_PATH.exists():
                        payload["vectorizer"] = joblib.load(SOURCE_VECTORIZER_PATH)
                return payload
        except Exception:
            pass

    rows = _load_seed_rows()
    if not rows:
        return None

    max_score = max(float(r.get("max_score", 10.0)) for r in rows)
    vectorizer = TfidfVectorizer(max_features=2000, ngram_range=(1, 2))
    texts = [_make_text(r.get("question", ""), r.get("answer", "")) for r in rows]
    X = vectorizer.fit_transform(texts)
    y = np.array([float(r.get("score", 0.0)) for r in rows], dtype=float)

    model = Ridge(alpha=1.0)
    model.fit(X, y)

    payload = {
        "model": model,
        "vectorizer": vectorizer,
        "max_score": max_score,
        "backend": "tfidf",
    }

    try:
        SOURCE_SCORER_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(payload, SOURCE_SCORER_PATH)
    except Exception:
        pass

    return payload


def score_answer(question: Dict[str, Any], answer_text: Optional[str] = None, answer: Optional[str] = None) -> float:
    """Score an answer from 0..100 using the trained model when available.

    Accepts both the target app's `answer_text` parameter and the source-style
    `answer` keyword to remain compatible across code paths.
    """
    if answer_text is None:
        answer_text = answer
    if answer_text is None:
        return 0.0

    payload = load_or_train_scorer()
    if not payload:
        return 0.0

    model = payload.get("model")
    vectorizer = payload.get("vectorizer")
    max_score = float(payload.get("max_score", 10.0))
    if model is None:
        return 0.0

    question_text = str(question.get("prompt") or question.get("question") or question.get("topic") or "")
    text = _make_text(question_text, answer_text)
    if payload.get("backend") == "embeddings":
        encoder = payload.get("encoder")
        if encoder is None:
            return 0.0
        features = encoder.encode([text])
    else:
        if vectorizer is None:
            return 0.0
        features = vectorizer.transform([text])
    predicted = float(model.predict(features)[0])
    predicted = max(0.0, min(predicted, max_score))
    score = (predicted / max_score) * 100.0 if max_score else 0.0
    return round(score, 1)


def generate_feedback(question: Dict[str, Any], answer_text: str, score: Optional[float] = None) -> str:
    """Generate feedback from the saved seq2seq model, with a local fallback."""
    answer_text = (answer_text or "").strip()
    if not answer_text:
        return "No answer submitted. Try to provide a more complete response."

    score = float(score if score is not None else score_answer(question, answer_text))
    generated = _generate_saved_feedback(question, answer_text, score)
    if generated:
        return generated

    return _generate_heuristic_feedback(question, answer_text, score)


@lru_cache(maxsize=1)
def _load_feedback_model():
    if not (FEEDBACK_MODEL_PATH / "config.json").exists():
        return None
    try:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        import torch

        return AutoTokenizer.from_pretrained(FEEDBACK_MODEL_PATH), AutoModelForSeq2SeqLM.from_pretrained(FEEDBACK_MODEL_PATH), torch
    except Exception:
        return None


def _generate_saved_feedback(question: Dict[str, Any], answer_text: str, score: float) -> Optional[str]:
    bundle = _load_feedback_model()
    if bundle is None:
        return None
    tokenizer, model, torch = bundle
    max_score = float(question.get("max_score", 10.0))
    normalized_score = score / 100.0 * max_score if score > max_score else score
    band = "excellent" if normalized_score >= 0.85 * max_score else "good" if normalized_score >= 0.65 * max_score else "needs_improvement" if normalized_score >= 0.4 * max_score else "poor"
    source = f"question: {question.get('prompt') or question.get('question') or ''} answer: {answer_text} score: {normalized_score:g}/{max_score:g} band: {band}"
    try:
        model.eval()
        inputs = tokenizer(source, return_tensors="pt", truncation=True, max_length=256)
        with torch.no_grad():
            output = model.generate(**inputs, max_length=128)
        text = tokenizer.decode(output[0], skip_special_tokens=True).strip()
        return text or None
    except Exception:
        return None


def _generate_heuristic_feedback(question: Dict[str, Any], answer_text: str, score: float) -> str:
    keywords = question.get("keywords") or []
    keyword_list = [str(item).strip() for item in keywords if str(item).strip()]
    lower_answer = answer_text.lower()

    if keyword_list:
        matched = [kw for kw in keyword_list if kw.lower() in lower_answer]
        missing = [kw for kw in keyword_list if kw.lower() not in lower_answer]
        if score >= 75:
            return "Strong answer. You covered the key points well." if not missing else "Strong answer overall. Consider adding: " + ", ".join(missing[:3]) + "."
        if score >= 40:
            return "Partially correct. Consider adding the main points around: " + ", ".join(missing[:3]) + "." if missing else "Partially correct. You are close; expand a bit more on the core concept."
        if missing:
            return "You are missing several core ideas. Focus on: " + ", ".join(missing[:4]) + "."

    if score >= 75:
        return "Strong answer. Your response demonstrates the right core idea and is well aligned to the topic."
    if score >= 40:
        return "Partially correct. Try to explain the concept with a bit more precision and concrete examples."
    return "The answer needs more depth. Explain the main idea, key terms, and why it matters."
