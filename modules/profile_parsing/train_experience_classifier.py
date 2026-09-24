"""Reproducible experience-classifier training and evaluation workflow."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "master_resumes.jsonl"
OUTPUT = ROOT / "models" / "experience_classifier"
LABELS = ["work", "internship", "contract", "research", "other"]
LABEL_MAPPING = {
    "full-time": "work",
    "full time": "work",
    "part-time": "work",
    "part time": "work",
    "internship": "internship",
    "contract": "contract",
}


def clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\n", " ")).strip()


def build_text(entry: dict[str, Any], section: str = "EXPERIENCE") -> str:
    dates = entry.get("dates") or {}
    technical = entry.get("technical_environment") or {}
    descriptions = entry.get("responsibilities") or []
    parts = [
        f"SECTION: {clean(section)}",
        f"ROLE: {clean(entry.get('title'))}",
        f"ORGANIZATION: {clean(entry.get('company'))}",
        f"DATE: {clean(dates.get('start'))} - {clean(dates.get('end'))} ({clean(dates.get('duration'))})",
        f"DESCRIPTION: {' '.join(clean(item) for item in descriptions)}",
        f"TECHNICAL ENVIRONMENT: {' '.join(clean(item) for key in ('technologies', 'methodologies', 'tools') for item in (technical.get(key) or []))}",
    ]
    return " ".join(part for part in parts if part.split(":", 1)[-1].strip())


def normalize_label(value: Any) -> str | None:
    raw = clean(value).lower()
    if raw in LABEL_MAPPING:
        return LABEL_MAPPING[raw]
    return None


def load_records() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records = []
    source_labels = Counter()
    with SOURCE.open(encoding="utf-8") as handle:
        for resume_id, line in enumerate(handle):
            if not line.strip():
                continue
            resume = json.loads(line)
            for entry_id, entry in enumerate(resume.get("experience") or []):
                if not isinstance(entry, dict):
                    continue
                raw_label = clean(entry.get("employment_type"))
                source_labels[raw_label] += 1
                label = normalize_label(raw_label)
                records.append({
                    "resume_id": str(resume_id),
                    "entry_id": entry_id,
                    "text": build_text(entry),
                    "label": label,
                    "source_label": raw_label,
                    "title": clean(entry.get("title")),
                })
    return records, {"source_label_distribution": dict(source_labels)}


def split_records(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    usable = [record for record in records if record["label"] in LABELS]
    by_resume: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in usable:
        by_resume[record["resume_id"]].append(record)
    resume_ids = sorted(by_resume)
    strata = [Counter(item["label"] for item in by_resume[resume_id]).most_common(1)[0][0] for resume_id in resume_ids]
    train_ids, temp_ids = train_test_split(resume_ids, test_size=0.2, random_state=42, stratify=strata)
    temp_strata = [Counter(item["label"] for item in by_resume[resume_id]).most_common(1)[0][0] for resume_id in temp_ids]
    valid_ids, test_ids = train_test_split(temp_ids, test_size=0.5, random_state=42, stratify=temp_strata)
    return {"train": sorted(train_ids), "validation": sorted(valid_ids), "test": sorted(test_ids)}


def train(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], TfidfVectorizer]:
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=20000, sublinear_tf=True)
    features = vectorizer.fit_transform([row["text"] for row in rows])
    model = LogisticRegression(max_iter=3000, class_weight="balanced")
    model.fit(features, [row["label"] for row in rows])
    return {"model": model, "vectorizer": vectorizer, "labels": LABELS}, vectorizer


def metrics(bundle: dict[str, Any], rows: list[dict[str, Any]], masked: bool = False) -> dict[str, Any]:
    texts = [re.sub(r"\b(intern(?:ship|ed)?|trainee)\b", "[MASKED]", row["text"], flags=re.IGNORECASE) if masked else row["text"] for row in rows]
    predicted = bundle["model"].predict(bundle["vectorizer"].transform(texts))
    actual = [row["label"] for row in rows]
    report = classification_report(actual, predicted, labels=LABELS, output_dict=True, zero_division=0)
    return {
        "accuracy": accuracy_score(actual, predicted),
        "macro_f1": f1_score(actual, predicted, labels=LABELS, average="macro", zero_division=0),
        "weighted_f1": f1_score(actual, predicted, labels=LABELS, average="weighted", zero_division=0),
        "per_class": {label: report.get(label, {}) for label in LABELS},
        "confusion_matrix": confusion_matrix(actual, predicted, labels=LABELS).tolist(),
    }


def main() -> None:
    records, source_report = load_records()
    splits = split_records(records)
    rows_by_split = {name: [record for record in records if record["resume_id"] in ids and record["label"] in LABELS] for name, ids in splits.items()}
    bundle, _ = train(rows_by_split["train"])
    old_bundle = joblib.load(OUTPUT / "experience_classifier.joblib")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUTPUT / "experience_classifier.joblib", OUTPUT / "experience_classifier_legacy.joblib")
    joblib.dump(bundle, OUTPUT / "experience_classifier_baseline.joblib")
    for name in ("label_mapping.json", "training_config.json", "metrics.json", "dataset_report.json", "split_manifest.json"):
        (OUTPUT / name).unlink(missing_ok=True)
    normal_test = metrics(bundle, rows_by_split["test"])
    masked_test = metrics(bundle, rows_by_split["test"], masked=True)
    old_test = metrics(old_bundle, rows_by_split["test"])
    shutil.copy2(OUTPUT / "experience_classifier_baseline.joblib", OUTPUT / "experience_classifier.joblib")
    dataset_report = {
        "source": str(SOURCE.name),
        "resumes": len({record["resume_id"] for record in records}),
        "experience_entries": len(records),
        "usable_entries": sum(record["label"] in LABELS for record in records),
        "ambiguous_entries": sum(record["label"] is None for record in records),
        "class_distribution": dict(Counter(record["label"] for record in records if record["label"])),
        **source_report,
        "generated_examples": [{key: record[key] for key in ("resume_id", "entry_id", "text", "label")} for record in records if record["label"]],
    }
    parquet_report = inspect_parquet()
    external_report = evaluate_external(bundle)
    (OUTPUT / "label_mapping.json").write_text(json.dumps(LABEL_MAPPING, indent=2), encoding="utf-8")
    (OUTPUT / "training_config.json").write_text(json.dumps({"seed": 42, "split": "80/10/10 by resume", "model": "tfidf_logistic_regression", "input_excludes": ["employment_type"]}, indent=2), encoding="utf-8")
    (OUTPUT / "dataset_report.json").write_text(json.dumps(dataset_report, indent=2), encoding="utf-8")
    (OUTPUT / "split_manifest.json").write_text(json.dumps(splits, indent=2), encoding="utf-8")
    (OUTPUT / "metrics.json").write_text(json.dumps({"old_model": old_test, "new_model": normal_test, "keyword_ablation": {"normal": normal_test, "masked": masked_test}}, indent=2), encoding="utf-8")
    (OUTPUT / "parquet_dataset_report.json").write_text(json.dumps(parquet_report, indent=2), encoding="utf-8")
    (OUTPUT / "external_resume_report.json").write_text(json.dumps(external_report, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(records), "splits": {key: len(value) for key, value in rows_by_split.items()}, "old": old_test, "new": normal_test, "masked": masked_test, "external": external_report, "parquet": parquet_report}, indent=2))


def inspect_parquet() -> dict[str, Any]:
    path = ROOT / "train-00000-of-00001.parquet"
    if not path.exists():
        return {"exists": False, "decision": "not available"}
    try:
        import pyarrow.parquet as pq
        table = pq.read_table(path)
        columns = table.column_names
        sample = table.slice(0, 2).to_pylist()
        return {
            "exists": True,
            "rows": table.num_rows,
            "columns": columns,
            "label_columns": [column for column in columns if any(token in column.lower() for token in ("label", "ner", "tag", "entity"))],
            "text_columns": [column for column in columns if "text" in column.lower() or "message" in column.lower() or "content" in column.lower()],
            "possible_ner_columns": [column for column in columns if any(token in column.lower() for token in ("ner", "tag", "entity", "tokens"))],
            "sample_schema": str(table.schema),
            "sample": sample,
            "decision": "excluded: chat messages with system/user/assistant roles, no token-level resume NER annotations",
        }
    except Exception as exc:
        return {"exists": True, "error": f"{type(exc).__name__}: {exc}", "decision": "excluded because it could not be read"}


def evaluate_external(bundle: dict[str, Any]) -> dict[str, Any]:
    from extract_text import extract_text
    from parser import parse_resume
    results = {}
    for filename in ("Siyon_AIML_optpdf.pdf", "GOKUL_REDDY (1).pdf", "resume.pdf"):
        path = ROOT / "uploads" / filename
        if not path.exists():
            continue
        profile = parse_resume(extract_text(str(path)), filename)
        entries = []
        for entry in profile.experience + profile.internships:
            text = " ".join(["experience", clean(entry.get("role")), clean(entry.get("organization")), clean(entry.get("duration")), " ".join(clean(item) for item in entry.get("description") or [])])
            features = bundle["vectorizer"].transform([text])
            probabilities = bundle["model"].predict_proba(features)[0]
            entries.append({"role": entry.get("role"), "prediction": str(bundle["model"].predict(features)[0]), "confidence": round(float(max(probabilities)), 3)})
        results[filename] = {"education_count": len(profile.education), "work_count": len(profile.experience), "internship_count": len(profile.internships), "entries": entries}
    return results


if __name__ == "__main__":
    main()