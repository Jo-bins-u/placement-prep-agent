from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = PROJECT_ROOT / "data" / "experience_classifier_dataset.jsonl"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / "experience_classifier"
LABELS = ["work", "internship", "contract", "research", "other"]


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\n", " ")
    text = " ".join(text.split())
    return text.strip()


def _build_entry_text(entry: Any) -> str:
    if isinstance(entry, dict):
        role = _normalize_text(entry.get("role") or entry.get("title") or "")
        organization = _normalize_text(entry.get("organization") or "")
        duration = _normalize_text(entry.get("duration") or "")
        section = _normalize_text(entry.get("section") or entry.get("section_heading") or "experience")
        description = " ".join(_normalize_text(item) for item in (entry.get("description") or []) if _normalize_text(item))
        text = " ".join([section, role, organization, duration, description])
        return text.strip()
    if isinstance(entry, str):
        return _normalize_text(entry)
    return ""


def _default_dataset() -> List[Dict[str, str]]:
    return [
        {
            "text": "EXPERIENCE Machine Learning Intern Cognifyz Technologies Mar-Apr 2025 Developed end-to-end machine learning workflows using Python and scikit-learn and deployed forecasting pipelines.",
            "label": "internship",
        },
        {
            "text": "WORK EXPERIENCE Software Engineer ABC Technologies 2023-Present Built backend APIs and production services with Flask and PostgreSQL.",
            "label": "work",
        },
        {
            "text": "WORK EXPERIENCE & INTERNSHIPS Software Engineer Intern Larsen & Toubro Backend Systems Designed APIs and optimized data transfer flows across services.",
            "label": "internship",
        },
        {
            "text": "INTERNSHIP EXPERIENCE Data Science Intern Acme Labs Jun-Aug 2024 Built recommendation systems and forecasting models for customer analytics.",
            "label": "internship",
        },
        {
            "text": "RESEARCH EXPERIENCE Artificial Intelligence Research Assistant University of Delhi May-Jul 2025 Conducted experiments on computer vision and evaluated baselines.",
            "label": "research",
        },
        {
            "text": "EXPERIENCE Undergraduate Research Assistant AI Lab 2024 Conducted experiments and analyzed model performance in a research setting.",
            "label": "research",
        },
        {
            "text": "EXPERIENCE Information Technology Support Specialist City College 2022-2023 Provided troubleshooting and handled hardware support across campus systems.",
            "label": "other",
        },
        {
            "text": "PROFESSIONAL EXPERIENCE Frontend Engineer QuickCart 2024-Present Improved user flows and built responsive dashboards with React and TypeScript.",
            "label": "work",
        },
        {
            "text": "INTERNSHIPS Cloud Engineering Intern Vertex Systems Jan-Feb 2025 Automated deployment workflows using Docker and AWS.",
            "label": "internship",
        },
        {
            "text": "EXPERIENCE Software Engineer Intern CoreLogic 2025 Designed ETL pipelines and improved data reliability metrics across reporting services.",
            "label": "internship",
        },
        {
            "text": "RESEARCH EXPERIENCE Research Associate Data Science Lab 2024 Evaluated experimental models and machine learning pipelines for multimodal analysis.",
            "label": "research",
        },
        {
            "text": "EXPERIENCE Teaching Assistant Department of Computer Science 2024 Supported practical labs and graded assignments for programming courses.",
            "label": "other",
        },
    ]


def _load_jsonl(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            text = _normalize_text(obj.get("text") or obj.get("raw_text") or "")
            label = _normalize_text(obj.get("label") or "")
            if text and label:
                rows.append({"text": text, "label": label.lower()})
    return rows


def _ensure_dataset(path: Path) -> List[Dict[str, str]]:
    rows = _load_jsonl(path)
    if rows:
        return rows
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = _default_dataset()
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows


def _save_model_bundle(bundle: Dict[str, Any], model_dir: Path) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "experience_classifier.joblib"
    joblib.dump(bundle, model_path)
    with (model_dir / "label_mapping.json").open("w", encoding="utf-8") as handle:
        json.dump({"labels": bundle["labels"]}, handle, indent=2)
    with (model_dir / "metadata.json").open("w", encoding="utf-8") as handle:
        json.dump({
            "model_type": "tfidf_logistic_regression",
            "labels": bundle["labels"],
            "notes": "Offline fallback model for resume experience classification; transformer path is preferred when a local checkpoint is available.",
        }, handle, indent=2)


def train_experience_classifier(dataset_path: Optional[str] = None, model_dir: Optional[str] = None, prefer_transformer: bool = False) -> Dict[str, Any]:
    dataset_file = Path(dataset_path) if dataset_path else DEFAULT_DATASET_PATH
    target_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
    rows = _ensure_dataset(dataset_file)

    valid_labels = {label for label in LABELS}
    filtered = []
    for row in rows:
        label = str(row.get("label", "")).strip().lower()
        if label in valid_labels:
            filtered.append({"text": _normalize_text(row.get("text", "")), "label": label})

    if not filtered:
        raise ValueError("No valid labeled examples could be loaded for the experience classifier.")

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=4000)
    texts = [row["text"] for row in filtered]
    labels = [row["label"] for row in filtered]
    X = vectorizer.fit_transform(texts)

    model = LogisticRegression(max_iter=2000, class_weight="balanced")
    model.fit(X, labels)

    trained_labels = list(dict.fromkeys(labels))
    bundle = {
        "model": model,
        "vectorizer": vectorizer,
        "labels": trained_labels,
        "label_to_index": {label: idx for idx, label in enumerate(trained_labels)},
        "metadata": {
            "training_rows": len(filtered),
            "class_distribution": {label: labels.count(label) for label in trained_labels},
            "preferred_backend": "transformer" if prefer_transformer else "tfidf",
        },
    }
    _save_model_bundle(bundle, target_dir)
    return bundle


def _load_model_bundle(model_dir: Optional[str] = None) -> Dict[str, Any]:
    target_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
    bundle_path = target_dir / "experience_classifier.joblib"
    if bundle_path.exists():
        try:
            return joblib.load(bundle_path)
        except Exception:
            pass
    return train_experience_classifier(model_dir=str(target_dir))


def predict_experience_type(entry: Any, model_dir: Optional[str] = None) -> Dict[str, Any]:
    bundle = _load_model_bundle(model_dir)
    text = _build_entry_text(entry)
    if not text:
        return {"label": "other", "confidence": 0.0, "needs_review": True}

    features = bundle["vectorizer"].transform([text])
    prediction = bundle["model"].predict(features)[0]
    probabilities = bundle["model"].predict_proba(features)[0]
    confidence = float(max(probabilities))
    label = str(prediction).lower()
    if label not in bundle["labels"]:
        label = "other"
    return {
        "label": label,
        "confidence": round(confidence, 3),
        "needs_review": confidence < 0.55,
    }


def classify_entry_text(text: str, model_dir: Optional[str] = None) -> Dict[str, Any]:
    return predict_experience_type({"role": text, "organization": "", "duration": "", "description": [], "section": "experience"}, model_dir=model_dir)
