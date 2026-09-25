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


# ---------------------------------------------------------------------------
# Practice modes: Technical (core concepts by topic) and Interview (resume + behavioural)
# ---------------------------------------------------------------------------
import hashlib

INTERVIEW_BANK_PATH = Path(__file__).parent.parent.parent / "data" / "interview_bank.json"
TOPIC_ORDER = ["Data Structures", "Algorithms", "Dynamic Programming", "DBMS", "Operating Systems",
               "Computer Networks", "OOP", "System Design", "Python", "Machine Learning", "Web Development"]


def load_interview_bank() -> dict:
    with open(INTERVIEW_BANK_PATH, encoding="utf-8") as f:
        return json.load(f)


def technical_topics() -> list:
    """Topics offered in Technical mode, in a sensible study order."""
    try:
        present = {q["topic"] for q in load_question_bank()}
    except Exception:
        present = set()
    return [t for t in TOPIC_ORDER if t in present] + sorted(present - set(TOPIC_ORDER))


def _items(profile: dict, key: str) -> list:
    return [item for item in (profile.get(key) or []) if isinstance(item, dict)]


def interview_focus_options(profile: dict) -> list:
    """[(value, label, group)] for the Interview topic picker, built from the candidate's resume."""
    options = [("mixed", "Mixed - a bit of everything", "General"), ("behavioral", "Behavioral & HR", "General")]
    if profile.get("skills"):
        options.append(("skills", "Skills on my resume", "General"))
    for index, project in enumerate(_items(profile, "projects")):
        title = (project.get("title") or project.get("name") or "").strip()
        if title:
            options.append((f"project:{index}", title[:70], "My projects"))
    for index, internship in enumerate(_items(profile, "internships")):
        role, company = (internship.get("role") or "").strip(), (internship.get("company") or "").strip()
        if role or company:
            label = f"{role} at {company}" if role and company else (role or company)
            options.append((f"internship:{index}", label[:70], "My internships"))
    return options


def resolve_focus(profile: dict, value: str) -> dict:
    """Turn a picker value into {"kind", "label", "item"}; unknown values fall back to mixed."""
    value = str(value or "mixed")
    kind, _, index = value.partition(":")
    if kind in ("project", "internship") and index.isdigit():
        items = _items(profile, "projects" if kind == "project" else "internships")
        if int(index) < len(items):
            labels = {v: label for v, label, _ in interview_focus_options(profile)}
            return {"kind": kind, "value": value, "label": labels.get(value, kind.title()), "item": items[int(index)]}
    if kind in ("behavioral", "skills"):
        return {"kind": kind, "value": kind, "label": "Behavioral & HR" if kind == "behavioral" else "Skills on my resume"}
    return {"kind": "mixed", "value": "mixed", "label": "Mixed"}


def _techs(item: dict) -> list:
    techs = item.get("tech_stack") or item.get("technologies") or []
    return [str(t).strip() for t in techs if str(t).strip()][:6]


def _fill(template: dict, subject: str, values: dict, topic: str, focus_label: str) -> dict | None:
    keywords = []
    for keyword in template["keywords"]:
        if "{tech}" in keyword:
            if not values.get("techs"):
                continue
            keyword = "|".join(values["techs"])
        elif "{tech_first}" in keyword:
            if not values.get("tech_first"):
                return None
            keyword = values["tech_first"]
        elif "{skill}" in keyword:
            keyword = values.get("skill", "")
        if keyword.strip():
            keywords.append(keyword)
    fmt = {"title": values.get("title", ""), "tech": ", ".join(values.get("techs") or []) or "the technologies you used",
           "tech_first": values.get("tech_first", ""), "company": values.get("company", "the company"),
           "role": values.get("role", "an intern"), "skill": values.get("skill", "")}
    digest = hashlib.sha1(f"{template['tid']}|{subject}".encode("utf-8"), usedforsecurity=False).hexdigest()[:10]  # stable id, not security
    return {"id": f"iv-{digest}", "topic": topic, "type": "short_answer", "difficulty": template["difficulty"],
            "prompt": template["prompt"].format(**fmt), "keywords": keywords,
            "ideal_answer": template["ideal_answer"].format(**fmt), "source": "bank", "mode": "interview",
            "category": "resume_interview", "reason": f"About {focus_label}"}


def _interview_pool(profile: dict, focus: dict) -> list:
    bank = load_interview_bank()
    pool = []
    kinds = [focus["kind"]] if focus["kind"] != "mixed" else ["behavioral", "project", "internship", "skills"]
    if "behavioral" in kinds:
        pool += [dict(q, source="bank", mode="interview", category="behavioral") for q in bank["behavioral"]]
    if "project" in kinds:
        projects = [focus["item"]] if focus.get("item") else _items(profile, "projects")
        for project in projects:
            title = (project.get("title") or project.get("name") or "").strip()
            if not title:
                continue
            techs = _techs(project)
            values = {"title": title, "techs": techs, "tech_first": techs[0] if techs else ""}
            pool += [q for q in (_fill(t, title, values, "Projects", title) for t in bank["project_templates"]) if q]
    if "internship" in kinds:
        internships = [focus["item"]] if focus.get("item") else _items(profile, "internships")
        for internship in internships:
            company, role = (internship.get("company") or "").strip(), (internship.get("role") or "").strip()
            if not (company or role):
                continue
            values = {"company": company or "your internship", "role": role or "an intern", "techs": _techs(internship)}
            pool += [q for q in (_fill(t, f"{role}@{company}", values, "Internships", company or role)
                                 for t in bank["internship_templates"]) if q]
    if "skills" in kinds:
        for skill in [str(s).strip() for s in (profile.get("skills") or []) if str(s).strip()][:25]:
            pool += [q for q in (_fill(t, skill, {"skill": skill}, "Resume Skills", skill) for t in bank["skill_templates"]) if q]
    return pool


def pick_interview_question(profile: dict, focus: dict, answered_ids: set, *, difficulty: str | None = None,
                            previous_prompts: list | None = None):
    """Interview mode: questions about the candidate's own resume or behavioural/HR questions."""
    llm_question = generate_interview_question(profile, [], set(answered_ids), difficulty=difficulty,
                                               previous_prompts=previous_prompts, mode="interview", focus=focus)
    if llm_question:
        llm_question["topic"] = {"behavioral": "Behavioral", "project": "Projects", "internship": "Internships",
                                 "skills": "Resume Skills"}.get(focus["kind"], llm_question["topic"])
        return llm_question
    pool = _interview_pool(profile, focus)
    if not pool:
        pool = [dict(q, source="bank", mode="interview") for q in load_interview_bank()["behavioral"]]
    asked = {p.strip().lower() for p in (previous_prompts or [])}
    fresh = [q for q in pool if q["id"] not in answered_ids and q["prompt"].strip().lower() not in asked]
    if fresh:
        return random.choice(fresh)
    # Everything in this area has been asked: offer one again for more practice.
    return dict(random.choice(pool), repeat=True)


def pick_technical_question(profile: dict, topic: str | None, weak_topics: list, answered_ids: set, *,
                            difficulty: str | None = None, previous_prompts: list | None = None):
    """Technical mode: core concept questions. topic=None means "recommended" (weak areas first)."""
    focus = {"topic": topic} if topic else {}
    llm_question = generate_interview_question(profile, weak_topics, set(answered_ids), difficulty=difficulty,
                                               previous_prompts=previous_prompts, mode="technical", focus=focus)
    if llm_question:
        if topic:
            llm_question["topic"] = topic
        return llm_question
    try:
        bank = [dict(q, source="bank", mode="technical") for q in load_question_bank()]
    except Exception:
        return None
    if topic:
        bank = [q for q in bank if q["topic"].lower() == topic.lower()] or bank
    asked = {p.strip().lower() for p in (previous_prompts or [])}
    fresh = [q for q in bank if q["id"] not in answered_ids and q["prompt"].strip().lower() not in asked]
    if not fresh:
        return dict(random.choice(bank), repeat=True) if bank else None
    weak = {str(t).lower() for t in weak_topics}
    skills = {str(s).lower() for s in (profile.get("skills") or [])}

    def matches_skill(name: str) -> bool:
        name = name.lower()
        return any(name == s or name in s or s in name for s in skills if len(s) > 2)

    groups = [fresh] if topic else [[q for q in fresh if q["topic"].lower() in weak],
                                    [q for q in fresh if matches_skill(q["topic"])], fresh]
    for group in groups:
        if group:
            preferred = [q for q in group if q.get("difficulty") == difficulty] if difficulty else []
            return random.choice(preferred or group)
    return None
