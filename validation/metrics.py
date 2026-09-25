"""Small, dependency-free metric helpers used by the validation suites."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, Sequence


def normalise(text) -> str:
    return re.sub(r"[^a-z0-9+#]+", " ", str(text or "").lower()).strip()


def prf(predicted: Iterable, expected: Iterable) -> dict:
    """Set-based precision / recall / F1 (items are normalised strings)."""
    pred = {normalise(p) for p in predicted if normalise(p)}
    gold = {normalise(g) for g in expected if normalise(g)}
    tp = len(pred & gold)
    precision = tp / len(pred) if pred else (1.0 if not gold else 0.0)
    recall = tp / len(gold) if gold else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": len(pred - gold), "fn": len(gold - pred), "precision": precision, "recall": recall, "f1": f1}


def micro_prf(rows: Sequence[dict]) -> dict:
    """Micro-average of prf() dicts (sums tp/fp/fn first)."""
    tp = sum(r["tp"] for r in rows)
    fp = sum(r["fp"] for r in rows)
    fn = sum(r["fn"] for r in rows)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def token_similarity(a, b) -> float:
    """Jaccard similarity of word sets — used for fuzzy title matching."""
    sa, sb = set(normalise(a).split()), set(normalise(b).split())
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb) if sa | sb else 0.0


def fuzzy_prf(predicted: Sequence[str], expected: Sequence[str], threshold: float = 0.6) -> dict:
    """Greedy one-to-one matching on token similarity (for titles that may differ slightly)."""
    unmatched = list(expected)
    tp = 0
    for p in predicted:
        best = max(unmatched, key=lambda g: token_similarity(p, g), default=None)
        if best is not None and token_similarity(p, best) >= threshold:
            tp += 1
            unmatched.remove(best)
    fp = len(predicted) - tp
    fn = len(expected) - tp
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def mean(values: Sequence[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def mae(pred: Sequence[float], gold: Sequence[float]) -> float:
    return mean([abs(p - g) for p, g in zip(pred, gold)])


def rmse(pred: Sequence[float], gold: Sequence[float]) -> float:
    return math.sqrt(mean([(p - g) ** 2 for p, g in zip(pred, gold)]))


def _ranks(values: Sequence[float]) -> list:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def pearson(x: Sequence[float], y: Sequence[float]) -> float:
    mx, my = mean(x), mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    return num / den if den else 0.0


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    return pearson(_ranks(x), _ranks(y))


def percentile(values: Sequence[float], q: float) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    k = (len(values) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def confusion(labels_true: Sequence[str], labels_pred: Sequence[str]) -> dict:
    classes = sorted(set(labels_true) | set(labels_pred))
    matrix = {t: {p: 0 for p in classes} for t in classes}
    for t, p in zip(labels_true, labels_pred):
        matrix[t][p] += 1
    return matrix


def binary_scores(y_true: Sequence[bool], y_pred: Sequence[bool]) -> dict:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t and p)
    fp = sum(1 for t, p in zip(y_true, y_pred) if not t and p)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t and not p)
    tn = sum(1 for t, p in zip(y_true, y_pred) if not t and not p)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / max(1, tp + fp + fn + tn)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy}


def chi_square_uniform(counts: Counter, categories: Iterable) -> float:
    categories = list(categories)
    total = sum(counts[c] for c in categories)
    expected = total / len(categories)
    return sum((counts[c] - expected) ** 2 / expected for c in categories)


def chi_square_p_value(chi2: float, dof: int) -> float:
    """Upper-tail p-value of the chi-square distribution (regularised gamma, series/continued fraction)."""
    a, x = dof / 2.0, chi2 / 2.0
    if x <= 0:
        return 1.0
    gln = math.lgamma(a)
    if x < a + 1:  # series for P(a, x)
        term = total = 1.0 / a
        n = a
        for _ in range(500):
            n += 1
            term *= x / n
            total += term
            if abs(term) < abs(total) * 1e-12:
                break
        return max(0.0, 1.0 - total * math.exp(-x + a * math.log(x) - gln))
    b = x + 1 - a  # continued fraction for Q(a, x)
    c = 1.0 / 1e-300
    d = 1.0 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-12:
            break
    return min(1.0, math.exp(-x + a * math.log(x) - gln) * h)


def shannon_entropy_bits(counts: Counter) -> float:
    total = sum(counts.values())
    return -sum((c / total) * math.log2(c / total) for c in counts.values() if c)
