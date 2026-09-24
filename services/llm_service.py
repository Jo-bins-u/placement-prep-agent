"""Centralized, validated Groq integration for placement-prep features."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key.startswith("gsk_your_"):
        return None

    try:
        from groq import Groq
        _client = Groq(api_key=api_key)
    except (ImportError, Exception):
        return None
    return _client


def _parse_json(raw: str) -> Any:
    cleaned = (raw or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def request_json(system_prompt: str, user_prompt: str, *, max_tokens: int = 900) -> Optional[Any]:
    """Request JSON once and return None for unavailable or malformed responses."""
    client = _get_client()
    if client is None:
        return None

    try:
        response = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content if response.choices else ""
        return _parse_json(content)
    except Exception:
        return None


def generate_interview_question(profile: dict, weak_topics: list[str], answered_ids: set[str], *, difficulty: str | None = None) -> Optional[dict]:
    """Generate one resume-grounded question with a validated response shape."""
    contact = profile.get("contact") or {}
    projects = profile.get("projects") or []
    education = profile.get("education") or []
    experience = profile.get("experience_raw") or []
    skills = profile.get("skills") or []
    project_context = [
        {
            "title": item.get("title"),
            "description": item.get("description"),
            "technologies": item.get("tech_stack", []),
        }
        for item in projects
        if isinstance(item, dict)
    ]
    requested_difficulty = difficulty if difficulty in {"easy", "medium", "hard"} else "medium"
    prompt = {
        "skills": skills[:30],
        "projects": project_context[:10],
        "education": education[:10],
        "experience": experience[:10],
        "contact_name": contact.get("name"),
        "weak_topics": weak_topics[:10],
        "previous_question_ids": list(answered_ids)[-30:],
        "difficulty": requested_difficulty,
    }
    system = (
        "You generate one personalized placement interview question. "
        "Use the candidate's projects and technologies when available. "
        "Never infer sensitive traits or invent candidate experience. "
        "Return only valid JSON."
    )
    user = f"""Candidate context:
{json.dumps(prompt, ensure_ascii=True)}

Return exactly:
{{
  "id": "gen-unique",
  "topic": "specific topic",
  "type": "short_answer",
  "category": "resume_interview",
  "difficulty": "{requested_difficulty}",
  "prompt": "one interview question",
  "keywords": ["four to seven expected concepts"],
  "skills": ["resume skills used"],
  "projects": ["resume project titles used"],
  "reason": "why this question is personalized"
}}
"""
    result = request_json(system, user)
    if not isinstance(result, dict):
        return None

    required = {"topic", "type", "difficulty", "prompt", "keywords"}
    if not required.issubset(result) or not isinstance(result.get("prompt"), str):
        return None
    if result["difficulty"] not in {"easy", "medium", "hard"}:
        return None
    if result["type"] != "short_answer" or not isinstance(result.get("keywords"), list):
        return None

    result["id"] = f"gen-{os.urandom(6).hex()}"
    result["category"] = result.get("category") or "resume_interview"
    result["skills"] = result.get("skills") if isinstance(result.get("skills"), list) else []
    result["projects"] = result.get("projects") if isinstance(result.get("projects"), list) else []
    result["reason"] = str(result.get("reason") or "Based on the candidate profile")
    return result
