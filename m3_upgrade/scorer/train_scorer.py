"""
train_scorer.py — trains a model to predict a score from (question, answer).

Two backends, chosen with --backend:

  tfidf        Bag-of-words features + regression. No downloads, works
               anywhere, trains in seconds. This is your BASELINE — the
               number you report to show the embedding model is actually
               earning its complexity, not just "the number we got."

  embeddings   Sentence-transformer embeddings (all-MiniLM-L6-v2) +
               regression. Needs internet to download the pretrained
               model the first time (blocked in some sandboxed dev
               environments — run this on your own machine). This is
               your MAIN model — captures meaning, not just word overlap,
               so it should score paraphrased-but-correct answers fairly
               where TF-IDF can't.

Both report Pearson correlation and Quadratic Weighted Kappa on a held-out
test split — the standard metrics for this task (see shared/metrics.py).

Usage:
    python train_scorer.py --data ../data/seed_dataset.jsonl --backend tfidf
    python train_scorer.py --data ../data/feedback_dataset.jsonl --backend embeddings
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import Ridge
from sklearn.feature_extraction.text import TfidfVectorizer
import joblib

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from metrics import pearson_correlation, quadratic_weighted_kappa


def load_dataset(path: str) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def make_text(row: dict) -> str:
    """What the model sees: question gives context, answer is what's graded."""
    return f"{row['question']} [SEP] {row['answer']}"


def train_tfidf(train_rows, val_rows, test_rows):
    vectorizer = TfidfVectorizer(max_features=2000, ngram_range=(1, 2))
    X_train = vectorizer.fit_transform([make_text(r) for r in train_rows])
    X_val = vectorizer.transform([make_text(r) for r in val_rows])
    X_test = vectorizer.transform([make_text(r) for r in test_rows])

    y_train = np.array([r["score"] for r in train_rows])
    y_val = np.array([r["score"] for r in val_rows])
    y_test = np.array([r["score"] for r in test_rows])

    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)

    return model, vectorizer, (X_val, y_val), (X_test, y_test)


def train_embeddings(train_rows, val_rows, test_rows):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("sentence-transformers not installed. Run: pip install sentence-transformers")
        sys.exit(1)

    print("Loading all-MiniLM-L6-v2 (downloads ~90MB the first time)...")
    encoder = SentenceTransformer("all-MiniLM-L6-v2")

    X_train = encoder.encode([make_text(r) for r in train_rows], show_progress_bar=True)
    X_val = encoder.encode([make_text(r) for r in val_rows])
    X_test = encoder.encode([make_text(r) for r in test_rows])

    y_train = np.array([r["score"] for r in train_rows])
    y_val = np.array([r["score"] for r in val_rows])
    y_test = np.array([r["score"] for r in test_rows])

    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)

    return model, encoder, (X_val, y_val), (X_test, y_test)


def evaluate(model, X, y_true, max_score: float, label: str):
    y_pred = model.predict(X)
    y_pred = np.clip(y_pred, 0, max_score)

    r = pearson_correlation(y_true, y_pred)
    qwk = quadratic_weighted_kappa(y_true, y_pred, min_rating=0, max_rating=int(max_score))

    print(f"[{label}] Pearson r = {r:.4f}   QWK = {qwk:.4f}   n = {len(y_true)}")
    return r, qwk


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Path to dataset .jsonl")
    parser.add_argument("--backend", choices=["tfidf", "embeddings"], default="tfidf")
    parser.add_argument("--out", default="scorer_model.joblib")
    args = parser.parse_args()

    rows = load_dataset(args.data)
    if len(rows) < 20:
        print(f"Warning: only {len(rows)} examples. This is fine to test the pipeline "
              f"mechanically, but you'll want 500+ for a real result (see README).")

    max_score = rows[0].get("max_score", 10.0)

    # 70 / 15 / 15 split
    train_rows, temp_rows = train_test_split(rows, test_size=0.3, random_state=42)
    val_rows, test_rows = train_test_split(temp_rows, test_size=0.5, random_state=42)
    print(f"Split: {len(train_rows)} train / {len(val_rows)} val / {len(test_rows)} test")

    if args.backend == "tfidf":
        model, featurizer, (X_val, y_val), (X_test, y_test) = train_tfidf(train_rows, val_rows, test_rows)
    else:
        model, featurizer, (X_val, y_val), (X_test, y_test) = train_embeddings(train_rows, val_rows, test_rows)

    evaluate(model, X_val, y_val, max_score, "validation")
    evaluate(model, X_test, y_test, max_score, "test")

    joblib.dump({"model": model, "backend": args.backend, "max_score": max_score}, args.out)
    print(f"Saved model to {args.out}")
    if args.backend == "tfidf":
        joblib.dump(featurizer, args.out.replace(".joblib", "_vectorizer.joblib"))


if __name__ == "__main__":
    main()
