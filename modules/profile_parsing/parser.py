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

try:
    from .schema import CandidateProfile, ContactInfo, Education, Project
    from .skills_taxonomy import ALL_SKILLS
except ImportError:  # pragma: no cover - supports legacy direct-script execution
    from schema import CandidateProfile, ContactInfo, Education, Project
    from skills_taxonomy import ALL_SKILLS

# --- Section headings we look for to split the resume into blocks ---
SECTION_HEADERS = {
    "education": ["education", "academic background", "academics"],
    "skills": ["skills", "technical skills", "core competencies"],
    "projects": ["projects", "academic projects", "personal projects"],
}

NON_SECTION_HEADERS = {
    "achievements & certifications",
    "achievements and certifications",
    "certifications",
    "certificates",
    "awards",
    "languages",
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

    if not sections.get("education"):
        _extract_education_fallback(lines, profile)

    _extract_skills(text, profile)
    _extract_education(sections.get("education", []), profile)
    _extract_projects(sections.get("projects", []), text, profile)

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
        if line.lower().strip(" :-") in NON_SECTION_HEADERS:
            current = None
            continue
        if current:
            sections[current].append(line)

    return sections


def _match_header(line: str) -> str:
    normalized = re.sub(r"\s+", " ", line.lower()).strip(" :-")
    for key, variants in SECTION_HEADERS.items():
        if normalized in variants:
            return key
        if any(normalized == variant or normalized.startswith(f"{variant} ") or normalized.endswith(f" {variant}") for variant in variants):
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
    if not edu_lines:
        return

    records = []
    current = []
    for raw_line in edu_lines:
        line = re.sub(r"^\s*[•●▪‣\-*–—]\s*", "", raw_line).strip()
        if not line:
            continue
        starts_with_qualification = bool(re.match(r"(?:b\.?\s?tech|b\.?\s?e\.?|m\.?\s?tech|bachelor|master|associate|diploma|pre-university|sslc|class\s+(?:x|xii|10|12))\b", line, re.IGNORECASE))
        starts_institution = bool(re.search(r"\b(?:university|college|school|institute|academy)\b", line, re.IGNORECASE)) and not starts_with_qualification
        if starts_institution and current:
            records.append(current)
            current = []
        current.append(line)
    if current:
        records.append(current)

    seen_institutions = set()
    for record in records:
        raw_text = " | ".join(record)
        lower = raw_text.lower()
        if not any(token in lower for token in ("b.", "m.", "degree", "diploma", "class ", "school", "college", "university", "gpa", "cgpa", "percentage", "sslc", "puc", "pre-university")):
            continue
        if "christuniversity.in" in lower:
            continue
        education = _education_from_text(raw_text)
        institution_key = re.sub(r"\W+", " ", education.institution or "").strip().lower()
        if institution_key and any(institution_key in existing or existing in institution_key for existing in seen_institutions):
            continue
        if institution_key:
            seen_institutions.add(institution_key)
        profile.education.append(education)


def _education_from_text(raw_text: str) -> Education:
    value = raw_text.strip()
    segments = [segment.strip() for segment in value.split("|") if segment.strip()]
    score_match = re.search(r"(?:(?:CGPA|GPA|Percentage)\s*[:\-]?\s*)?([\d.]+%)(?:\s*/\s*([\d.]+))?|(?:CGPA|GPA|Percentage)\s*[:\-]?\s*([\d.]+)(?:\s*/\s*([\d.]+))?", value, re.IGNORECASE)
    qualification_re = re.compile(r"(?:B\.?\s?Tech|B\.?\s?E\.?|M\.?\s?Tech|Bachelor|Master|Associate|Diploma|Pre-University|SSLC|Class\s+(?:X|XII|10|12))\b", re.IGNORECASE)
    first_is_institution = bool(segments and re.search(r"\b(?:university|college|school|institute|academy)\b", segments[0], re.IGNORECASE) and not qualification_re.match(segments[0]))
    degree_segments = segments[1:] if first_is_institution else segments
    degree_segment = next((segment for segment in degree_segments if qualification_re.search(segment)), "")
    institution_candidates = [
        segment for segment in segments
        if re.search(r"\b(?:university|college|school|institute|academy)\b", segment, re.IGNORECASE)
        and not qualification_re.match(segment)
    ]
    if institution_candidates:
        institution = institution_candidates[0].strip(" -," )
    else:
        inline_match = re.search(r"(?:,\s*)([^,|]*(?:University|College|School|Institute|Academy)[^,|]*)", value, re.IGNORECASE)
        institution = inline_match.group(1).strip(" -," ) if inline_match else None
    degree = degree_segment.strip(" -") if degree_segment else None
    field = None
    specialization = None
    if degree:
        field_match = re.search(r"\b(?:in|of)\s+([^|,]+)", degree, re.IGNORECASE)
        field = field_match.group(1).strip() if field_match else None
        specialization_match = re.search(r"\(([^)]*(?:AI|ML|speciali)[^)]*)\)", degree, re.IGNORECASE)
        specialization = specialization_match.group(1).strip() if specialization_match else None
    return Education(
        institution=institution,
        degree=degree,
        field_of_study=field,
        specialization=specialization,
        cgpa_or_percentage=(score_match.group(1) or score_match.group(3)) if score_match else None,
        scale=(score_match.group(2) or score_match.group(4)) if score_match else None,
        raw_text=value,
    )


def _extract_education_fallback(lines: List[str], profile: CandidateProfile) -> None:
    if profile.education:
        return

    education_candidates = []
    for line in lines[:40]:
        lower = line.lower()
        if any(token in lower for token in ["b.tech", "bachelor", "master", "degree", "university", "college", "gpa", "cgpa", "percentage", "class xii", "class x"]):
            education_candidates.append(line.strip())

    if not education_candidates:
        return

    deduped = []
    seen = set()
    for line in education_candidates:
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(line)

    for line in deduped:
        if any(segment in line.lower() for segment in ["christ", "university", "college", "school", "institute"]):
            profile.education.append(_education_from_text(line))

    if not profile.education:
        for line in deduped:
            profile.education.append(_education_from_text(line))

    for edu_item in profile.education:
        if not edu_item.cgpa_or_percentage:
            score_match = re.search(r"(?:CGPA|GPA|Percentage)\s*[:\-]?\s*([\d.]+%?)", edu_item.raw_text or "", re.IGNORECASE)
            if score_match:
                edu_item.cgpa_or_percentage = score_match.group(1)


# ---------------------------------------------------------------------------
# Project extraction — static heuristic + optional LLM upgrade
# ---------------------------------------------------------------------------
def _extract_projects(proj_lines: List[str], full_resume_text: str, profile: CandidateProfile) -> None:
    # Deterministic grouping owns project boundaries. LLM extraction must not
    # be allowed to turn arbitrary bullet fragments into project titles.
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
    """Group title-like lines and preserve wrapped bullets as one project."""
    projects = []
    current_title = None
    current_bullets = []
    current_bullet = None

    def flush_bullet():
        nonlocal current_bullet
        if current_bullet:
            current_bullets.append(current_bullet.strip())
            current_bullet = None

    def flush_project():
        nonlocal current_title, current_bullets
        flush_bullet()
        if not current_title:
            return
        description = " ".join(current_bullets).strip()
        tech = _technologies_in(" ".join([current_title, description]))
        projects.append(Project(
            title=current_title,
            description=description or None,
            description_points=list(current_bullets),
            tech_stack=tech,
            technologies=tech,
            raw_text="\n".join([current_title] + current_bullets),
            confidence=0.95 if current_bullets else 0.65,
        ))
        current_title = None
        current_bullets = []

    for raw_line in proj_lines:
        line = raw_line.strip()
        if not line:
            continue
        if _is_project_title(line, has_existing_project=bool(current_title)):
            flush_project()
            current_title = line.rstrip(" :")
            continue
        bullet = _strip_bullet(line)
        if bullet is not None:
            flush_bullet()
            current_bullet = bullet
        elif current_title:
            if current_bullet:
                current_bullet = f"{current_bullet} {line}"
            else:
                current_bullet = line

    flush_project()
    profile.projects.extend(projects)



def _extract_projects(proj_lines: List[str], full_resume_text: str, profile: CandidateProfile) -> None:
    _heuristic_extract_projects(proj_lines, profile)


BULLET_RE = re.compile(r"^\s*[•●▪‣\-*–—]\s+(.*)$")
VERB_FRAGMENT_RE = re.compile(
    r"^(architected|built|designed|implemented|engineered|developed|integrated|optimized|created|managed|led|used|deployed|configured|added|worked)\b",
    re.IGNORECASE,
)


def _strip_bullet(line: str):
    match = BULLET_RE.match(line)
    return match.group(1).strip() if match else None


def _is_project_title(line: str, has_existing_project: bool = False) -> bool:
    text = line.strip()
    if _strip_bullet(text) is not None or not text:
        return False
    if text[-1:] in ".,;:!?" or len(text.split()) > 12 or len(text) > 110:
        return False
    if VERB_FRAGMENT_RE.match(text):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z0-9+.#/-]*", text)
    if not words:
        return False
    capitalized = sum(word[0].isupper() or word.isupper() for word in words)
    title_like = capitalized >= max(1, len(words) - 1)
    return title_like and (not has_existing_project or len(words) >= 2)


def _technologies_in(text: str) -> List[str]:
    return [
        skill for skill in ALL_SKILLS
        if re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", text, re.IGNORECASE)
    ]


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
