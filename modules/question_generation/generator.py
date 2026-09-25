"""
Module 2 — Question Generation (Groq LLM + static bank fallback).

Primary path  : Groq API generates a bespoke question from the candidate's
                resume skills, weak topics, and answered history.
Fallback path : If GROQ_API_KEY is not set or the API call fails, the module
                falls back to picking from data/question_bank.json exactly as
                the original prototype did.

Environment variable (put in a .env file at the project root):
    GROQ_API_KEY=gsk_...

`pick_next_question()` is the single boundary the rest of the app touches.
Its return shape is unchanged so evaluation / dashboard need no edits.
"""

import json
import random
from pathlib import Path

from services.llm_service import generate_interview_question

# ---------------------------------------------------------------------------
# Static bank (fallback)
# ---------------------------------------------------------------------------
QUESTION_BANK_PATH = Path(__file__).parent.parent.parent / "data" / "question_bank.json"


def load_question_bank():
    with open(QUESTION_BANK_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Public interface (unchanged signature — rest of app uses only these two)
# ---------------------------------------------------------------------------
def pick_next_question(profile_skills: list, weak_topics: list, answered_ids: set, profile: dict | None = None,
                       *, difficulty: str | None = None, previous_prompts: list | None = None):
    """
    1. Ask the LLM for a question grounded in the resume (validated in llm_service;
       it sees the text of recent questions so it doesn't repeat them).
    2. Otherwise pick from the static bank, never repeating an answered question:
         weak / focus topics first, then topics matching resume skills, then anything,
         preferring the requested difficulty within each group.
    """
    llm_question = generate_interview_question(
        profile or {"skills": profile_skills},
        weak_topics,
        set(answered_ids),
        difficulty=difficulty,
        previous_prompts=previous_prompts,
    )
    if llm_question:
        return llm_question

    try:
        bank = load_question_bank()
    except Exception:
        return None

    asked_prompts = {p.strip().lower() for p in (previous_prompts or [])}
    unanswered = [q for q in bank if q["id"] not in answered_ids and q["prompt"].strip().lower() not in asked_prompts]
    if not unanswered:
        return None

    weak = {str(t).lower() for t in weak_topics}
    skills = {str(s).lower() for s in profile_skills}

    def matches_skill(topic: str) -> bool:
        t = topic.lower()
        return any(t == s or t in s or s in t for s in skills if len(s) > 2)

    for group in (
        [q for q in unanswered if q["topic"].lower() in weak],
        [q for q in unanswered if matches_skill(q["topic"])],
        unanswered,
    ):
        if group:
            preferred = [q for q in group if q.get("difficulty") == difficulty] if difficulty else []
            return dict(random.choice(preferred or group), source="bank")
    return None


def get_question_by_id(question_id: str):
    """Look up a question from the static bank by ID (LLM questions are ephemeral)."""
    # LLM-generated questions have IDs starting with "gen-"; they aren't stored
    # in the bank, so return None and let the caller handle it gracefully.
    if question_id.startswith("gen-"):
        return None

    try:
        bank = load_question_bank()
    except Exception:
        return None

    for q in bank:
        if q["id"] == question_id:
            return q
    return None
