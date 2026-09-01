"""
Module 4 stand-in — Analytics & Recommendation.

Aggregates attempt scores per topic to find weak areas (FR4.1, FR4.2)
and suggests what to practice next (FR4.3). Pure functions over data
passed in — no DB access here, so this stays easy to unit test.
"""

WEAK_THRESHOLD = 50.0  # avg score below this = flagged weak (tune this with real usage data)


def compute_topic_scores(attempts) -> dict:
    """attempts: rows with .topic and .score. Returns {topic: avg_score}."""
    totals = {}
    counts = {}
    for a in attempts:
        totals[a["topic"]] = totals.get(a["topic"], 0) + a["score"]
        counts[a["topic"]] = counts.get(a["topic"], 0) + 1
    return {topic: round(totals[topic] / counts[topic], 1) for topic in totals}


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
