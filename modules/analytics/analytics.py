"""
Module 4 stand-in — Analytics & Recommendation.

Aggregates attempt scores per topic to find weak areas (FR4.1, FR4.2)
and suggests what to practice next (FR4.3). Pure functions over data
passed in — no DB access here, so this stays easy to unit test.
"""

WEAK_THRESHOLD = 50.0  # avg score below this = flagged weak (tune this with real usage data)
INTERVIEW_WEIGHT = 0.5
DSA_WEIGHT = 0.5


def compute_topic_scores(attempts) -> dict:
    """attempts: rows with .topic and .score. Returns {topic: avg_score}."""
    totals = {}
    counts = {}
    for a in attempts:
        totals[a["topic"]] = totals.get(a["topic"], 0) + a["score"]
        counts[a["topic"]] = counts.get(a["topic"], 0) + 1
    return {topic: round(totals[topic] / counts[topic], 1) for topic in totals}


def combine_practice_scores(interview_scores: dict, dsa_scores: dict) -> dict:
    """Merge live interview and DSA evidence without hardcoding dashboard values."""
    combined = {}
    for topic in set(interview_scores) | set(dsa_scores):
        interview = interview_scores.get(topic)
        dsa = dsa_scores.get(topic)
        if interview is None:
            combined[topic] = round(float(dsa), 1)
        elif dsa is None:
            combined[topic] = round(float(interview), 1)
        else:
            combined[topic] = round(
                float(interview) * INTERVIEW_WEIGHT + float(dsa) * DSA_WEIGHT,
                1,
            )
    return combined


def get_weak_topics(topic_scores: dict) -> list:
    return [topic for topic, score in topic_scores.items() if score < WEAK_THRESHOLD]


def get_strong_topics(topic_scores: dict) -> list:
    return [topic for topic, score in topic_scores.items() if score >= 75]


def recommend_next_steps(weak_topics: list, topic_scores: dict) -> list:
    """Simple rule-based recommendations. Swap for something smarter
    (e.g. resource-mapped recommendations) once you have real usage data
    on what actually helps candidates improve."""
    recs = []
    for topic in weak_topics:
        recs.append({
            "title": f"Practice more {topic} questions",
            "reason": f"Current average: {topic_scores[topic]}% — below the {int(WEAK_THRESHOLD)}% target",
        })
    if not recs:
        recs.append({
            "title": "Keep practicing across topics",
            "reason": "No weak areas flagged yet — try a wider range of topics to build a fuller picture",
        })
    return recs


# ---------------------------------------------------------------------------
# Skill proficiency — evidence-based metric used by the dashboard
# ---------------------------------------------------------------------------
# A single answer should not decide a skill. Each topic's proficiency is a
# Bayesian (shrinkage) estimate over every attempt on that topic, oldest first:
#
#   w_i        = RECENCY_DECAY ** (attempts after i)          (newer attempts count more)
#   mean       = sum(w_i * score_i) / sum(w_i)                 (recency-weighted accuracy)
#   estimate   = (n * mean + PRIOR_STRENGTH * PRIOR_SCORE) / (n + PRIOR_STRENGTH)
#   confidence = n / (n + PRIOR_STRENGTH)
#
# With one attempt the estimate is pulled halfway to a neutral 50%; as attempts
# accumulate it converges to the (recency-weighted) average. A topic is only
# labelled weak/developing/strong after MIN_ATTEMPTS attempts.
#
# Parameters were chosen with the simulation in validation/run.py (suite
# "proficiency"): PRIOR_STRENGTH=1 and RECENCY_DECAY=0.9 gave lower error than the
# plain average at every attempt count for improving learners. Weighting hard
# questions more was tested and rejected (it biased estimates downwards).
from math import sqrt

PRIOR_SCORE = 50.0
PRIOR_STRENGTH = 1.0
RECENCY_DECAY = 0.9
MIN_ATTEMPTS = 3
STRONG_THRESHOLD = 75.0


def _confidence_label(confidence: float, attempts: int) -> str:
    if attempts < MIN_ATTEMPTS:
        return "low"
    if confidence >= 0.85:
        return "high"
    return "medium"


def compute_proficiency(evidence: list, now=None) -> dict:
    """evidence: dicts with topic, score (0-100), created_at, source ('interview'|'dsa') and optional difficulty.
    Returns {topic: profile dict} — see the comment above for the formula. `now` is accepted for API compatibility."""
    by_topic = {}
    for item in evidence:
        topic = item.get("topic")
        if not topic or item.get("score") is None:
            continue
        by_topic.setdefault(topic, []).append(item)

    profiles = {}
    for topic, items in by_topic.items():
        items = sorted(items, key=lambda i: str(i.get("created_at") or ""))
        scores = [max(0.0, min(100.0, float(i["score"]))) for i in items]
        n = len(scores)
        weights = [RECENCY_DECAY ** (n - 1 - k) for k in range(n)]
        weighted_mean = sum(w * s for w, s in zip(weights, scores)) / sum(weights)
        estimate = (n * weighted_mean + PRIOR_STRENGTH * PRIOR_SCORE) / (n + PRIOR_STRENGTH)
        confidence = n / (n + PRIOR_STRENGTH)
        raw_mean = sum(scores) / n
        spread = sqrt(sum((s - raw_mean) ** 2 for s in scores) / n) if n > 1 else 0.0
        recent, earlier = scores[-3:], scores[:-3]
        trend = round(sum(recent) / len(recent) - sum(earlier) / len(earlier), 1) if earlier else None

        if n < MIN_ATTEMPTS:
            status = "needs_data"
        elif estimate < WEAK_THRESHOLD:
            status = "weak"
        elif estimate < STRONG_THRESHOLD:
            status = "developing"
        else:
            status = "strong"

        profiles[topic] = {
            "score": round(estimate, 1),
            "raw_average": round(raw_mean, 1),
            "weighted_average": round(weighted_mean, 1),
            "attempts": n,
            "interview_attempts": sum(1 for i in items if i.get("source") == "interview"),
            "dsa_attempts": sum(1 for i in items if i.get("source") == "dsa"),
            "confidence": round(confidence, 2),
            "confidence_label": _confidence_label(confidence, n),
            "consistency": round(max(0.0, 100.0 - spread), 1),
            "trend": trend,
            "status": status,
            "attempts_needed": max(0, MIN_ATTEMPTS - n),
        }
    return dict(sorted(profiles.items(), key=lambda kv: (kv[1]["status"] == "needs_data", kv[1]["score"])))


def overall_proficiency(profiles: dict) -> float:
    """Confidence-weighted mean of topic estimates (topics with more evidence count more)."""
    total_weight = sum(p["confidence"] for p in profiles.values())
    if not total_weight:
        return 0.0
    return round(sum(p["score"] * p["confidence"] for p in profiles.values()) / total_weight, 1)


def weak_topics_from_profiles(profiles: dict) -> list:
    return [t for t, p in profiles.items() if p["status"] == "weak"]


def strong_topics_from_profiles(profiles: dict) -> list:
    return [t for t, p in profiles.items() if p["status"] == "strong"]


def recommend_from_profiles(profiles: dict) -> list:
    recs = []
    for topic, p in profiles.items():
        if p["status"] == "weak":
            recs.append({
                "title": f"Practice more {topic} questions",
                "reason": f"Proficiency {p['score']}% across {p['attempts']} attempts — below the {int(WEAK_THRESHOLD)}% target",
            })
    for topic, p in profiles.items():
        if p["status"] == "needs_data":
            recs.append({
                "title": f"Measure your {topic} skill",
                "reason": f"Answer {p['attempts_needed']} more {topic} question{'s' if p['attempts_needed'] != 1 else ''} to get a reliable score",
            })
    if not recs:
        recs.append({
            "title": "Keep practicing across topics",
            "reason": "No weak areas flagged — try new topics or harder questions to keep improving",
        })
    return recs[:6]
