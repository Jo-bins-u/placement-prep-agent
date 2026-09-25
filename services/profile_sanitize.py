"""Whitelist + size limits for candidate profiles coming from the browser (profile edit form
and PUT /api/profile). Unknown keys are dropped, strings are trimmed and length-capped, lists
are capped, and links keep only http(s) URLs."""

from __future__ import annotations

import re
from typing import Any

MAX_PROFILE_JSON_BYTES = 200_000

SHORT, MEDIUM, LONG = 200, 1000, 4000
MAX_ITEMS, MAX_SKILLS, MAX_POINTS = 30, 100, 40

_CONTACT = {"name": SHORT, "email": SHORT, "phone": 40}
_EDUCATION = {"institution": SHORT, "degree": SHORT, "field_of_study": SHORT, "specialization": SHORT,
              "cgpa_or_percentage": 40, "scale": 40, "raw_text": MEDIUM}
_PROJECT = {"title": SHORT, "name": SHORT, "description": LONG, "raw_text": LONG, "source": 40, "id": 64}
_INTERNSHIP = {"role": SHORT, "company": SHORT, "duration": 100, "location": SHORT, "description": LONG,
               "raw_text": LONG, "id": 64}
_TOP_STRINGS = {"source_file": SHORT, "parser_version": 20, "preferred_language": 40}


def _text(value: Any, limit: int):
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text[:limit] or None


def _texts(values: Any, limit: int, max_items: int) -> list:
    if not isinstance(values, list):
        return []
    out = [_text(v, limit) for v in values[:max_items]]
    return [v for v in out if v]


def clean_link(value: Any):
    """http(s) URL or bare domain, else None."""
    link = _text(value, 300)
    if not link or re.search(r"[\s\"'<>\\]", link):
        return None
    if "://" in link:
        return link if re.match(r"^https?://[^/\s]+", link, re.I) else None
    if link.startswith("/") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:(?!\d)", link):
        return None
    return link


def _number(value: Any):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(max(number, 0.0), 1.0)


def _record(raw: Any, fields: dict) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {key: _text(raw.get(key), limit) for key, limit in fields.items()}


def sanitize_profile(raw: Any) -> dict:
    """Return a safe copy of a candidate profile dict."""
    raw = raw if isinstance(raw, dict) else {}
    contact = _record(raw.get("contact"), _CONTACT)
    contact["confidence"] = _number((raw.get("contact") or {}).get("confidence") if isinstance(raw.get("contact"), dict) else 0)

    projects = []
    for item in (raw.get("projects") or [])[:MAX_ITEMS] if isinstance(raw.get("projects"), list) else []:
        if not isinstance(item, dict):
            continue
        project = _record(item, _PROJECT)
        project["description_points"] = _texts(item.get("description_points"), MEDIUM, MAX_POINTS)
        project["tech_stack"] = _texts(item.get("tech_stack"), 60, MAX_ITEMS)
        project["technologies"] = _texts(item.get("technologies"), 60, MAX_ITEMS)
        project["links"] = [link for link in (clean_link(v) for v in (item.get("links") or [])[:10]
                                              if isinstance(item.get("links"), list)) if link]
        project["llm_extracted"] = bool(item.get("llm_extracted"))
        project["confidence"] = _number(item.get("confidence"))
        projects.append(project)

    internships = []
    for item in (raw.get("internships") or [])[:MAX_ITEMS] if isinstance(raw.get("internships"), list) else []:
        if not isinstance(item, dict):
            continue
        internship = _record(item, _INTERNSHIP)
        internship["description_points"] = _texts(item.get("description_points"), MEDIUM, MAX_POINTS)
        internship["tech_stack"] = _texts(item.get("tech_stack"), 60, MAX_ITEMS)
        internships.append(internship)

    education = [_record(item, _EDUCATION) for item in (raw.get("education") or [])[:MAX_ITEMS]
                 if isinstance(item, dict)] if isinstance(raw.get("education"), list) else []

    profile = {
        "contact": contact,
        "skills": _texts(raw.get("skills"), 60, MAX_SKILLS),
        "education": education,
        "projects": projects,
        "internships": internships,
        "needs_review": _texts(raw.get("needs_review"), SHORT, MAX_ITEMS),
        "verified": bool(raw.get("verified")),
    }
    for key, limit in _TOP_STRINGS.items():
        if raw.get(key) is not None:
            profile[key] = _text(raw.get(key), limit)
    return profile
