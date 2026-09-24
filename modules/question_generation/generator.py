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
def pick_next_question(profile_skills: list, weak_topics: list, answered_ids: set, profile: dict | None = None):
    """
    Selection logic:
    1. Try Groq LLM to generate a bespoke question (if API key is present).
    2. If LLM is unavailable / fails, fall back to the static question bank
       using the original priority order:
         a) Weak-topic questions first
         b) Skill-matched questions next
         c) Any unanswered question as a last resort
    """
    # --- Attempt LLM generation ---
    answered_topics = []
    try:
        bank = load_question_bank()
        answered_topics = [q["topic"] for q in bank if q["id"] in answered_ids]
    except Exception:
        pass

    llm_question = generate_interview_question(
        profile or {"skills": profile_skills},
        weak_topics,
        set(answered_ids),
    )
    if llm_question:
        return llm_question

    # --- Fallback: static question bank ---
    try:
        bank = load_question_bank()
    except Exception:
        return None

    unanswered = [q for q in bank if q["id"] not in answered_ids]

    if not unanswered:
        return None  # Candidate has answered everything in the bank

    weak_matches = [q for q in unanswered if q["topic"] in weak_topics]
    if weak_matches:
        return random.choice(weak_matches)

    skill_matches = [q for q in unanswered if q["topic"] in profile_skills]
    if skill_matches:
        return random.choice(skill_matches)

    return random.choice(unanswered)


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
