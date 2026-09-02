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
import os
import random
import re
import time
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Static bank (fallback)
# ---------------------------------------------------------------------------
QUESTION_BANK_PATH = Path(__file__).parent.parent.parent / "data" / "question_bank.json"


def load_question_bank():
    with open(QUESTION_BANK_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Groq client (lazy init so the module loads even without the package / key)
# ---------------------------------------------------------------------------
_groq_client = None


def _get_groq_client():
    global _groq_client
    if _groq_client is not None:
        return _groq_client

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        # Try loading from a .env file in the project root
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("GROQ_API_KEY=") and not line.startswith("#"):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not api_key:
        return None  # No key available — will fall back to static bank

    try:
        from groq import Groq  # type: ignore
        _groq_client = Groq(api_key=api_key)
        return _groq_client
    except ImportError:
        return None  # groq package not installed


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are an expert technical interview question generator for placement preparation.
Your job is to create ONE high-quality interview question that is:
- Specifically tailored to the candidate's skills and weak areas
- Appropriate difficulty (not too easy, not impossibly hard)
- Practical and relevant to real placement interviews

You MUST respond with ONLY a valid JSON object (no markdown, no explanation).
"""

_USER_PROMPT_TEMPLATE = """\
Generate one technical interview question for a candidate with the following profile:

Skills from resume: {skills}
Topics where the candidate is weak (prioritise these): {weak_topics}
Topics already practised: {answered_topics}

Return EXACTLY this JSON shape (nothing else):
{{
  "id": "gen-<unique_id>",
  "topic": "<topic name>",
  "type": "short_answer",
  "difficulty": "<easy|medium|hard>",
  "prompt": "<the interview question text>",
  "keywords": ["<key concept 1>", "<key concept 2>", "<key concept 3>", "<key concept 4>", "<key concept 5>"]
}}

Rules:
- "topic" must match one of the candidate's skills or weak topics when possible.
- "keywords" must be 4-7 concepts an evaluator would look for in a good answer.
- Make the prompt specific and thought-provoking, not generic.
- Do NOT wrap the JSON in markdown code fences.
"""


def _build_user_prompt(profile_skills: list, weak_topics: list, answered_topics: list) -> str:
    skills_str = ", ".join(profile_skills) if profile_skills else "General CS"
    weak_str = ", ".join(weak_topics) if weak_topics else "None identified yet"
    answered_str = ", ".join(set(answered_topics)) if answered_topics else "None"
    return _USER_PROMPT_TEMPLATE.format(
        skills=skills_str,
        weak_topics=weak_str,
        answered_topics=answered_str,
    )


# ---------------------------------------------------------------------------
# LLM question generation
# ---------------------------------------------------------------------------
def generate_llm_question(profile_skills: list, weak_topics: list, answered_topics: list):
    """
    Calls Groq to generate a personalised question.
    Returns a question dict on success, None on any failure.
    """
    client = _get_groq_client()
    if client is None:
        return None

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(
                    profile_skills, weak_topics, answered_topics
                )},
            ],
            temperature=0.8,
            max_tokens=512,
        )

        raw = response.choices[0].message.content.strip()

        # Strip accidental markdown fences if the model adds them
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        question = json.loads(raw)

        # Ensure a unique ID so it doesn't collide with the static bank
        question["id"] = f"gen-{uuid.uuid4().hex[:8]}-{int(time.time())}"

        # Validate required fields
        required = {"id", "topic", "type", "difficulty", "prompt", "keywords"}
        if not required.issubset(question.keys()):
            return None

        return question

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public interface (unchanged signature — rest of app uses only these two)
# ---------------------------------------------------------------------------
def pick_next_question(profile_skills: list, weak_topics: list, answered_ids: set):
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

    llm_question = generate_llm_question(profile_skills, weak_topics, answered_topics)
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
