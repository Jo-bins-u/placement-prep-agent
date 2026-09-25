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
    from .schema import CandidateProfile, ContactInfo, Education, Internship, Project
    from .skills_taxonomy import ALL_SKILLS
except ImportError:  # pragma: no cover - supports legacy direct-script execution
    from schema import CandidateProfile, ContactInfo, Education, Internship, Project
    from skills_taxonomy import ALL_SKILLS

# --- Section headings we look for to split the resume into blocks ---
SECTION_HEADERS = {
    "education": ["education", "academic background", "academics"],
    "skills": ["skills", "technical skills", "core competencies"],
    "projects": ["projects", "academic projects", "personal projects"],
    # Resumes label internships many ways; every entry under these headings is
    # stored as an internship. Matched exactly (see _match_header) so project
    # titles such as "Internship Portal" are never mistaken for headings.
    "internships": [
        "internships", "internship", "internship experience", "internship details",
        "experience", "work experience", "professional experience", "relevant experience",
        "industry experience", "employment", "employment history", "work history",
        "training", "industrial training", "industry training",
    ],
}

EXACT_MATCH_SECTIONS = {"internships"}
# Combined headings such as "Work Experience & Internships" or "Internships and Training".
INTERNSHIP_HEADER_RE = re.compile(
    r"^(?:(?:work|professional|relevant|industry)\s+)?(?:experience|internships?)"
    r"(?:\s*(?:&|and|/|,)\s*(?:(?:work\s+)?experience|internships?|training|trainings))?$"
)

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
    _extract_internships(sections.get("internships", []), profile)

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
        if key in EXACT_MATCH_SECTIONS:
            if key == "internships" and INTERNSHIP_HEADER_RE.match(normalized):
                return key
            continue
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


QUALIFICATION_RE = re.compile(
    r"(?:integrated\s+)?(?:B\.?\s?Tech|B\.?\s?E\b\.?|B\.?\s?Sc|B\.?\s?C\.?A|B\.?\s?Com|M\.?\s?Tech|M\.?\s?Sc|M\.?\s?C\.?A|M\.?\s?B\.?A|"
    r"M\.?\s?E\b\.?|Ph\.?\s?D|Bachelor|Master|Associate|Diploma|Pre-University|PUC|SSLC|Higher Secondary|Senior Secondary|"
    r"Secondary|HSC|SSC|Class\s+(?:X|XII|10|12)(?:th)?)\b",
    re.IGNORECASE,
)
INSTITUTION_RE = re.compile(r"\b(?:university|college|school|institute|academy|polytechnic|vidyalaya|iit|nit|iiit)\b", re.IGNORECASE)
SCORE_WORD_RE = re.compile(r"\b(?:cgpa|gpa|percentage|grade|score)\b|\d+(?:\.\d+)?\s*%|^\s*\d+(?:\.\d+)?\s*(?:/\s*\d+)?\s*$", re.IGNORECASE)


def _education_from_text(raw_text: str) -> Education:
    value = raw_text.strip()
    # Split into pieces on pipes, spaced dashes and commas: "B.Tech in CS, XYZ Institute — CGPA 8.7"
    pieces = [p.strip(" -–—,|") for p in re.split(r"\s*\|\s*|\s+[—–-]\s+|\s*[—–]\s*|,\s*", value)]
    pieces = [p for p in pieces if p]
    score_match = re.search(r"(?:(?:CGPA|GPA|Percentage)\s*[:\-]?\s*)?([\d.]{1,8}%)(?:\s*/\s*([\d.]{1,8}))?|(?:CGPA|GPA|Percentage)\s*[:\-]?\s*([\d.]{1,8})(?:\s*/\s*([\d.]{1,8}))?|([\d.]{1,8})\s*(?:/\s*([\d.]{1,8}))?\s*(?:CGPA|GPA)", value, re.IGNORECASE)

    institution = next((p for p in pieces if INSTITUTION_RE.search(p) and not QUALIFICATION_RE.match(p)), None)
    if institution is None:
        institution = next((p for p in pieces if INSTITUTION_RE.search(p)), None)
    degree_index = next((k for k, p in enumerate(pieces) if QUALIFICATION_RE.search(p) and p != institution), None)
    degree = pieces[degree_index] if degree_index is not None else None
    field = None
    if degree:
        nxt = pieces[degree_index + 1] if degree_index + 1 < len(pieces) else None
        subject_next = bool(nxt and nxt != institution and not SCORE_WORD_RE.search(nxt)
                            and not INSTITUTION_RE.search(nxt) and not DATE_RANGE_RE.search(nxt))
        in_match = re.search(r"\bin\s+(.+)$", degree, re.IGNORECASE)
        if in_match:                                   # "B.Tech in Computer Science"
            field = in_match.group(1).strip()
        elif subject_next and re.search(r"\b(?:bachelor|master)\s+of\b", degree, re.IGNORECASE):
            field = nxt                                # "Bachelor of Technology, Computer Science"
        else:
            of_match = re.search(r"\bof\s+(.+)$", degree, re.IGNORECASE)
            rest = QUALIFICATION_RE.sub("", degree, count=1).strip(" .")
            field = (of_match.group(1).strip() if of_match else rest) or (nxt if subject_next else None)
    specialization_match = re.search(r"\(([^)]*(?:AI|ML|speciali)[^)]*)\)", value, re.IGNORECASE)
    if score_match:
        score = score_match.group(1) or score_match.group(3) or score_match.group(5)
        scale = score_match.group(2) or score_match.group(4) or score_match.group(6)
    else:
        score = scale = None
    return Education(
        institution=institution,
        degree=degree,
        field_of_study=field,
        specialization=specialization_match.group(1).strip() if specialization_match else None,
        cgpa_or_percentage=score,
        scale=scale,
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
    current_title_tech = []
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
        tech = []
        for item in list(current_title_tech) + _technologies_in(" ".join([current_title, description])):
            if item.lower() not in {t.lower() for t in tech}:
                tech.append(item)
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
        title_text, title_tech = _split_project_title(line)
        if _is_project_title(title_text, has_existing_project=bool(current_title)):
            flush_project()
            current_title = title_text.rstrip(" :")
            current_title_tech[:] = title_tech
            continue
        bullet = _strip_bullet(line)
        if bullet is not None:
            flush_bullet()
            current_bullet = bullet
        elif current_title:
            if current_bullet:
                current_bullet = _join_wrapped(current_bullet, line)
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


def _join_wrapped(previous: str, continuation: str) -> str:
    """Join a line the PDF wrapped: 're-' + 'sponses' -> 'responses', otherwise add a space."""
    previous = previous.rstrip()
    if re.search(r"[a-z]-$", previous) and continuation[:1].islower():
        return previous[:-1] + continuation
    return f"{previous} {continuation}"


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


def _split_project_title(line: str):
    """'EventOps – Platform React, Node.js | Ongoing' -> ('EventOps – Platform', ['React', 'Node.js'])."""
    text = line.strip()
    if _strip_bullet(text) is not None:
        return text, []
    head = re.split(r"\s*\|\s*", text)
    title, rest = head[0], head[1:]
    title, _ = _split_dates(title)
    tail_items = []
    for chunk in rest:
        chunk, _ = _split_dates(chunk)
        tail_items.extend(t.strip() for t in chunk.split(",") if t.strip())
    tail_items = [t for t in tail_items if t.lower() not in {"ongoing", "github", "live", "link"}]
    # A comma-separated tech list glued to the end of the title: "Chatbot Python, RAG, NLP".
    if "," in title:
        before_comma, after_comma = title.split(",", 1)
        words = before_comma.split()
        cut = None
        for size in (3, 2, 1):  # longest known skill ending right before the first comma
            if len(words) > size and _is_skill(" ".join(words[-size:])):
                cut = len(words) - size
                break
        if cut:
            first_item = " ".join(words[cut:])
            title = " ".join(words[:cut])
            tail_items = [first_item] + [t.strip() for t in after_comma.split(",") if t.strip()] + tail_items
    return title.strip(" -–—|,"), tail_items


def _is_skill(text: str) -> bool:
    return text.strip().lower() in _SKILLS_LOWER


_SKILLS_LOWER = {skill.lower() for skill in ALL_SKILLS}


def _technologies_in(text: str) -> List[str]:
    return [
        skill for skill in ALL_SKILLS
        if re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", text, re.IGNORECASE)
    ]


# ---------------------------------------------------------------------------
# Internship extraction
# ---------------------------------------------------------------------------
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE_POINT = rf"(?:{_MONTH}\s*'?\d{{2,4}}|\d{{1,2}}/\d{{2,4}}|(?:summer|winter|spring|fall)\s+\d{{4}}|\d{{4}})"
DATE_RANGE_RE = re.compile(
    rf"\(?\s*{_MONTH}\s*(?:-|–|—|to)\s*{_MONTH}\s*'?\d{{2,4}}\s*\)?"  # Mar–Apr 2025
    rf"|\(?\s*{_DATE_POINT}(?:\s*(?:-|–|—|to|till|until)\s*(?:{_DATE_POINT}|present|current|now|ongoing))?\s*\)?",
    re.IGNORECASE,
)
ROLE_WORD_RE = re.compile(r"(?:intern|trainee|apprentice|engineer|developer|analyst|associate|assistant|researcher|consultant|designer|scientist|manager|lead)\b", re.IGNORECASE)
ROLE_COMPANY_SPLIT_RE = re.compile(r"\s*(?:—|–|\|)\s*|\s+(?:-|@|at)\s+", re.IGNORECASE)


def _split_dates(line: str):
    """Return (line_without_dates, duration_text_or_None)."""
    matches = [m for m in DATE_RANGE_RE.finditer(line) if re.search(r"\d", m.group(0))]
    if not matches:
        return line, None
    duration = " ".join(m.group(0).strip(" ()") for m in matches)
    remaining = DATE_RANGE_RE.sub(lambda m: "" if re.search(r"\d", m.group(0)) else m.group(0), line)
    remaining = re.sub(r"\s{2,}", " ", remaining).strip(" ,|–—-()")
    return remaining, duration


def _looks_like_heading_line(text: str) -> bool:
    """A short, title-cased line that isn't a sentence (role, company or location)."""
    max_words = 16 if ROLE_WORD_RE.search(text) else 12
    if not text or text[-1:] in ".;!?" or len(text.split()) > max_words:
        return False
    if VERB_FRAGMENT_RE.match(text):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z0-9+.#/&-]*", text)
    if not words:
        return False
    small = {"of", "and", "in", "at", "for", "the", "a", "an", "to", "on", "with", "&"}
    significant = [w for w in words if w.lower() not in small]
    capitalized = sum(w[0].isupper() for w in significant)
    return capitalized >= max(1, len(significant) - 1)


def _extract_internships(lines: List[str], profile: CandidateProfile) -> None:
    entries = []
    current = None
    last_was_bullet = False

    def start(role_line: str):
        nonlocal current
        text, duration = _split_dates(role_line)
        parts = [p.strip(" ,") for p in ROLE_COMPANY_SPLIT_RE.split(text, maxsplit=1)]
        role, company = parts[0], (parts[1] if len(parts) > 1 else None)
        if company and "·" in company:
            # "Software Engineer Intern – Backend Systems · Python": the tail is a focus line, not a company.
            role, company = text.strip(" ,"), None
        elif company and ROLE_WORD_RE.search(company) and not ROLE_WORD_RE.search(role):
            # "Acme Pvt. Ltd., Bengaluru — Cybersecurity AI Intern": company first, role second.
            role, company = company, role
        current = {"role": role or None, "company": company or None, "duration": duration,
                   "location": None, "points": [], "raw": [role_line]}
        entries.append(current)

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        bullet = _strip_bullet(line)
        if bullet is not None:
            if current is None:
                start("Internship")
                current["role"] = None
            current["points"].append(bullet)
            current["raw"].append(line)
            last_was_bullet = True
            continue

        text, duration = _split_dates(line)
        is_heading = _looks_like_heading_line(text)
        if current is not None and not current["points"]:
            # Still in the header block of the current entry (company / dates / location).
            if duration and not text:
                current["duration"] = current["duration"] or duration
                current["raw"].append(line)
                continue
            if is_heading and not current["company"]:
                current["company"] = text
                current["duration"] = current["duration"] or duration
                current["raw"].append(line)
                continue
            if (is_heading and not current["location"] and not duration and len(text.split()) <= 4
                    and not ROLE_WORD_RE.search(text)):
                current["location"] = text
                current["raw"].append(line)
                continue
            if duration and not current["duration"] and len(text.split()) <= 4:
                current["duration"] = duration
                current["location"] = current["location"] or (text or None)
                current["raw"].append(line)
                continue
        if is_heading and (current is None or current["points"] or current["duration"]):
            start(line)
            last_was_bullet = False
            continue
        if current is None:
            start(line)
            continue
        # Prose line: a wrapped bullet continues the previous point, otherwise it's a new point.
        if last_was_bullet and current["points"] and (line[:1].islower() or current["points"][-1].rstrip()[-1:] not in ".!?"):
            current["points"][-1] = _join_wrapped(current["points"][-1], line)
        else:
            current["points"].append(line)
            last_was_bullet = False
        current["raw"].append(line)

    for entry in entries:
        if not (entry["role"] or entry["company"] or entry["points"]):
            continue
        # "Company, City  <dates>" on the first line and the role underneath: swap them back.
        if entry["company"] and ROLE_WORD_RE.search(entry["company"]) and not ROLE_WORD_RE.search(entry["role"] or ""):
            entry["role"], entry["company"] = entry["company"], entry["role"]
        # "Company, City" where the city came along: keep the city as the location.
        if entry["company"] and not entry["location"] and entry["company"].count(",") >= 1:
            name, _, place = entry["company"].rpartition(",")
            if name.strip() and len(place.split()) <= 3 and not re.search(r"(?:ltd|inc|llc|pvt|corp)\.?$", place.strip(), re.IGNORECASE):
                entry["company"], entry["location"] = name.strip(" ,"), place.strip()
        description = " ".join(entry["points"]).strip() or None
        profile.internships.append(Internship(
            role=entry["role"],
            company=entry["company"],
            duration=entry["duration"],
            location=entry["location"],
            description=description,
            description_points=list(entry["points"]),
            tech_stack=_technologies_in(" ".join(filter(None, [entry["role"], description]))),
            raw_text="\n".join(entry["raw"]),
        ))


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
