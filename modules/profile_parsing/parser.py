"""
Step 2 of the pipeline: turn raw resume text into a CandidateProfile.

Approach: section-splitting + regex + keyword matching for fast, explainable
extraction. When a GROQ_API_KEY is present, the project extraction step is
upgraded to use an LLM for more accurate title/description/tech parsing.
The static path runs identically without the key, so the prototype still
works out of the box.
"""

import json
import os
import re
from pathlib import Path
from typing import List

from schema import CandidateProfile, ContactInfo, Education, Project
from skills_taxonomy import ALL_SKILLS

# --- Section headings we look for to split the resume into blocks ---
SECTION_HEADERS = {
    "education": ["education", "academic background", "academics"],
    "skills": ["skills", "technical skills", "core competencies"],
    "projects": ["projects", "academic projects", "personal projects"],
    "experience": ["experience", "work experience", "internship", "internships"],
}

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(\+?\d{1,3}[-.\\s]?)?(?:\d[-.\\s]?){9,12}\d")


# ---------------------------------------------------------------------------
# Groq client (same lazy-init pattern as generator.py)
# ---------------------------------------------------------------------------
_groq_client = None


def _get_groq_client():
    global _groq_client
    if _groq_client is not None:
        return _groq_client

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("GROQ_API_KEY=") and not line.startswith("#"):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not api_key:
        return None

    try:
        from groq import Groq  # type: ignore
        _groq_client = Groq(api_key=api_key)
        return _groq_client
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def parse_resume(text: str, source_file: str = None) -> CandidateProfile:
    profile = CandidateProfile(source_file=source_file)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    _extract_contact(lines, profile)
    sections = _split_sections(lines)

    _extract_skills(text, profile)
    _extract_education(sections.get("education", []), profile)
    _extract_projects(sections.get("projects", []), text, profile)

    if sections.get("experience"):
        profile.experience_raw = sections["experience"]

    _flag_missing_fields(profile)
    return profile


# ---------------------------------------------------------------------------
# Contact extraction
# ---------------------------------------------------------------------------
def _extract_contact(lines: List[str], profile: CandidateProfile) -> None:
    full_text = "\n".join(lines[:15])

    email_match = EMAIL_RE.search(full_text)
    phone_match = PHONE_RE.search(full_text)

    name = None
    for line in lines[:5]:
        if EMAIL_RE.search(line) or PHONE_RE.search(line):
            continue
        if 2 <= len(line.split()) <= 4 and line[0].isupper() and "@" not in line:
            name = line
            break

    confidence = sum([bool(name), bool(email_match), bool(phone_match)]) / 3

    profile.contact = ContactInfo(
        name=name,
        email=email_match.group(0) if email_match else None,
        phone=phone_match.group(0) if phone_match else None,
        confidence=round(confidence, 2),
    )


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------
def _split_sections(lines: List[str]) -> dict:
    sections = {}
    current = None

    for line in lines:
        header_key = _match_header(line)
        if header_key:
            current = header_key
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)

    return sections


def _match_header(line: str) -> str:
    normalized = line.lower().strip(" :-")
    for key, variants in SECTION_HEADERS.items():
        if normalized in variants:
            return key
    return None


# ---------------------------------------------------------------------------
# Skills extraction (keyword match against taxonomy)
# ---------------------------------------------------------------------------
def _extract_skills(full_text: str, profile: CandidateProfile) -> None:
    found = []
    for skill in ALL_SKILLS:
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, full_text, re.IGNORECASE):
            found.append(skill)
    profile.skills = found


# ---------------------------------------------------------------------------
# Education extraction
# ---------------------------------------------------------------------------
def _extract_education(edu_lines: List[str], profile: CandidateProfile) -> None:
    cgpa_re = re.compile(r"(?:CGPA|GPA|Percentage)\s*[:\-]?\s*([\d.]+%?)", re.IGNORECASE)
    for line in edu_lines:
        cgpa_match = cgpa_re.search(line)
        profile.education.append(
            Education(
                raw_text=line,
                cgpa_or_percentage=cgpa_match.group(1) if cgpa_match else None,
            )
        )


# ---------------------------------------------------------------------------
# Project extraction — static heuristic + optional LLM upgrade
# ---------------------------------------------------------------------------
def _extract_projects(proj_lines: List[str], full_resume_text: str, profile: CandidateProfile) -> None:
    """
    Try LLM extraction first (structured, handles messy formatting well).
    Fall back to heuristic block-splitting if LLM is unavailable.
    """
    if proj_lines:
        llm_projects = _llm_extract_projects(proj_lines)
        if llm_projects:
            profile.projects = llm_projects
            return

    # --- Heuristic fallback ---
    _heuristic_extract_projects(proj_lines, profile)


def _llm_extract_projects(proj_lines: List[str]) -> List[Project]:
    """Call Groq to parse project lines into structured Project objects."""
    client = _get_groq_client()
    if client is None:
        return []

    raw_text = "\n".join(proj_lines)

    system_prompt = (
        "You are a resume parser. Extract all projects from the provided resume text. "
        "Return ONLY a valid JSON array (no markdown, no explanation)."
    )

    user_prompt = f"""Extract all projects from this resume section and return a JSON array.

Resume projects section:
\"\"\"
{raw_text}
\"\"\"

Return EXACTLY this JSON array shape (nothing else, no code fences):
[
  {{
    "title": "<project title>",
    "description": "<1-2 sentence summary of what the project does>",
    "tech_stack": ["<tech1>", "<tech2>"]
  }}
]

Rules:
- "title" should be the project name only (no dates, no bullet points).
- "description" should be a clean prose summary, not a raw bullet list.
- "tech_stack" should list technologies, languages, or frameworks mentioned.
- If no clear projects exist, return an empty array [].
- Do NOT include markdown code fences in your response.
"""

    try:
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=1024,
        )

        raw = response.choices[0].message.content.strip()
        # Strip accidental markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []

        projects = []
        for item in parsed:
            if not isinstance(item, dict) or not item.get("title"):
                continue
            projects.append(Project(
                title=item.get("title"),
                description=item.get("description"),
                tech_stack=item.get("tech_stack", []),
                raw_text=item.get("title"),
                llm_extracted=True,
            ))
        return projects

    except Exception:
        return []


def _heuristic_extract_projects(proj_lines: List[str], profile: CandidateProfile) -> None:
    """Original block-splitting heuristic."""
    current_block: List[str] = []

    def flush():
        if not current_block:
            return
        title = current_block[0]
        description = " ".join(current_block[1:])
        tech = [s for s in ALL_SKILLS if re.search(r"\b" + re.escape(s) + r"\b", description, re.IGNORECASE)]
        profile.projects.append(
            Project(title=title, description=description or None, tech_stack=tech,
                    raw_text=" | ".join(current_block))
        )

    for line in proj_lines:
        looks_like_title = len(line.split()) <= 8 and not line.startswith(("-", "•"))
        if looks_like_title and current_block:
            flush()
            current_block = [line]
        else:
            current_block.append(line.lstrip("-• "))
    flush()


# ---------------------------------------------------------------------------
# Missing field flags
# ---------------------------------------------------------------------------
def _flag_missing_fields(profile: CandidateProfile) -> None:
    if not profile.contact.email:
        profile.needs_review.append("contact.email")
    if not profile.contact.name or profile.contact.confidence < 0.5:
        profile.needs_review.append("contact.name")
    if not profile.skills:
        profile.needs_review.append("skills")
    if not profile.education:
        profile.needs_review.append("education")
    if not profile.projects:
        profile.needs_review.append("projects")
