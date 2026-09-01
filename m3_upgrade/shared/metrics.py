"""
Standard evaluation metrics for this kind of task — use these to report
results, not just "loss went down." Pearson r and QWK are the two
metrics you'll see in every published ASAG paper (including the ASAP
and Mohler dataset benchmarks), so using them signals you know the
field and lets you compare your numbers to published baselines.
"""

from scipy.stats import pearsonr
from sklearn.metrics import cohen_kappa_score
import numpy as np


def pearson_correlation(y_true, y_pred) -> float:
    """How well predicted scores track true scores, linearly. Ranges -1 to 1;
    published ASAG systems on the Mohler dataset typically land around 0.5-0.6."""
    r, _ = pearsonr(y_true, y_pred)
    return round(float(r), 4)


def quadratic_weighted_kappa(y_true, y_pred, min_rating=0, max_rating=10) -> float:
    """
    Agreement between predicted and true scores, penalizing large
    misses more than small ones. This is THE standard metric for
    automated scoring tasks (used in the Kaggle ASAP competition).
    Needs integer-ish ratings — round continuous scores first.
    """
    y_true_r = np.clip(np.round(y_true), min_rating, max_rating).astype(int)
    y_pred_r = np.clip(np.round(y_pred), min_rating, max_rating).astype(int)
    return round(
        cohen_kappa_score(y_true_r, y_pred_r, weights="quadratic",
                           labels=list(range(min_rating, max_rating + 1))),
        4,
    )


def rouge_l(reference: str, hypothesis: str) -> float:
    """
    Lightweight ROUGE-L (longest common subsequence based F1) with no
    external dependency, for evaluating generated feedback text against
    reference feedback. Not a full ROUGE implementation — good enough
    to report a number in your report, not for a leaderboard.
    """
    ref_tokens = reference.lower().split()
    hyp_tokens = hypothesis.lower().split()
    if not ref_tokens or not hyp_tokens:
        return 0.0

    lcs = _lcs_length(ref_tokens, hyp_tokens)
    if lcs == 0:
        return 0.0

    precision = lcs / len(hyp_tokens)
    recall = lcs / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def _lcs_length(a, b):
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]
