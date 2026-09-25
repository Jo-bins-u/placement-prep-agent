import math
import re
from typing import Any


def _normalize_text(value):
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


IMPACT_WORDS = ["built", "designed", "developed", "optimized", "led", "improved", "implemented", "architected", "deployed", "automated"]


def _score_internships(profile: dict) -> tuple[int, list[str], list[str], list[str]]:
    internships = [item for item in (profile.get("internships") or []) if isinstance(item, dict)]
    if not internships:
        return 30, [], ["No internships were found on the resume."], [
            "Add any internships or industrial training with the company, dates, and what you built."
        ]

    text = " ".join(
        _normalize_text(" ".join(item.get("description_points") or [item.get("description") or ""]))
        for item in internships
    ).lower()
    detailed = sum(1 for item in internships if len(_normalize_text(item.get("description") or "").split()) >= 12)
    with_dates = sum(1 for item in internships if item.get("duration"))
    with_company = sum(1 for item in internships if item.get("company"))
    impact = sum(1 for word in IMPACT_WORDS if word in text)
    has_numbers = bool(re.search(r"\d+\s*(?:%|x|\+|ms|users|requests|samples)", text))

    score = 45 + min(3, len(internships)) * 10 + detailed * 5 + min(impact, 4) * 3 + (8 if has_numbers else 0)
    strengths, weaknesses, suggestions = [], [], []

    strengths.append(f"{len(internships)} internship{'s' if len(internships) != 1 else ''} listed.")
    if detailed == len(internships):
        strengths.append("Each internship describes the work you did.")
    else:
        weaknesses.append("Some internships have little or no description.")
        suggestions.append("Describe each internship in 2–3 bullets: the problem, what you built, and the tools used.")
    if with_company < len(internships) or with_dates < len(internships):
        weaknesses.append("Some internships are missing the company name or dates.")
        suggestions.append("Show the company and start–end dates for every internship.")
    if not has_numbers:
        suggestions.append("Add measurable results to your internships (accuracy, latency, users, time saved).")
    elif impact >= 2:
        strengths.append("Internship work is described with clear, measurable impact.")

    return min(100, int(score)), strengths, weaknesses, suggestions


def _score_skills(profile: dict) -> tuple[int, list[str], list[str], list[str]]:
    skills = profile.get("skills") or []
    skill_count = len(skills)
    core = {"python", "sql", "java", "javascript", "react", "flask", "aws", "docker", "machine learning", "data structures", "algorithms"}
    overlap = sum(1 for item in skills if item.lower() in core)
    score = 50 + min(30, skill_count * 3) + min(20, overlap * 5)
    score = min(100, int(score))

    strengths = []
    weaknesses = []
    suggestions = []

    if skill_count >= 6:
        strengths.append("Skill breadth is strong and well-aligned with tech roles.")
    else:
        weaknesses.append("Skill inventory is still narrow.")
        suggestions.append("List the frameworks, databases, and tools you actually use in projects and coursework.")

    if overlap >= 2:
        strengths.append("Core technical keywords are clearly visible.")
    else:
        weaknesses.append("The resume does not surface enough core tech keywords.")
        suggestions.append("Add core technologies and stacks that match the roles you want.")

    if not skills:
        weaknesses.append("No explicit skills section was detected.")
        suggestions.append("Create a clean skills section with technologies and tools grouped by category.")

    return score, strengths, weaknesses, suggestions


def _score_projects(profile: dict) -> tuple[int, list[str], list[str], list[str]]:
    projects = profile.get("projects") or []
    if not projects:
        return 35, ["Project signal is missing."], ["No project data was detected in the uploaded resume."], ["Add 2-3 project entries with problem, stack, and outcomes."]

    good_projects = []
    weaker_projects = []
    detailed = 0

    for project in projects:
        description = _normalize_text(project.get("description") or "")
        tech = project.get("tech_stack") or []
        if len(description.split()) >= 20 and tech:
            good_projects.append(project)
            detailed += 1
        else:
            weaker_projects.append(project)

    score = min(100, 50 + detailed * 12 + min(20, len(projects) * 3))
    strengths = []
    weaknesses = []
    suggestions = []

    if detailed >= 1:
        strengths.append("Projects include enough technical detail to read as substantive work.")
    else:
        weaknesses.append("Project descriptions are too brief or generic.")
        suggestions.append("Expand each project description with team scope, problem solved, and tech used.")

    if len(projects) >= 2:
        strengths.append("Multiple projects show breadth of application.")
    else:
        weaknesses.append("Only one project is documented.")
        suggestions.append("Add one more project to better show problem-solving range.")

    return min(100, int(score)), strengths, weaknesses, suggestions


def _score_education(profile: dict) -> tuple[int, list[str], list[str], list[str]]:
    education = profile.get("education") or []
    if not education:
        return 55, [], ["Education details are missing or unstructured."], ["Add degree, institution, and relevant coursework or graduating year."]

    score = 70
    strengths = ["Education information is present."]
    weaknesses = []
    suggestions = []

    if any(item.get("degree") or item.get("institution") for item in education):
        score += 15
        strengths.append("Academic credentials are partially structured.")
    else:
        weaknesses.append("Education is not formatted clearly enough for recruiters.")
        suggestions.append("Write institution, degree, and major explicitly in a standard format.")

    if any(item.get("cgpa_or_percentage") for item in education):
        score += 10
        strengths.append("Academic performance is available.")

    return min(100, int(score)), strengths, weaknesses, suggestions


def analyze_resume_feedback(profile) -> dict:
    """Generate deterministic resume score and recommendations using the canonical profile."""
    profile_data = profile.to_dict() if hasattr(profile, "to_dict") else profile
    if not isinstance(profile_data, dict):
        profile_data = {
            "contact": getattr(profile, "contact", None) and getattr(profile, "contact").__dict__ or {},
            "skills": getattr(profile, "skills", []) or [],
            "education": getattr(profile, "education", []) or [],
            "projects": getattr(profile, "projects", []) or [],
            "internships": getattr(profile, "internships", []) or [],
        }

    category_scores = {}
    strengths = []
    weaknesses = []
    suggestions = []

    for category, fn in [
        ("projects", _score_projects),
        ("internships", _score_internships),
        ("skills", _score_skills),
        ("education", _score_education),
    ]:
        score, cat_strengths, cat_weaknesses, cat_suggestions = fn(profile_data)
        category_scores[category] = score
        strengths.extend(cat_strengths)
        weaknesses.extend(cat_weaknesses)
        suggestions.extend(cat_suggestions)

    overall_score = int(round(sum(category_scores.values()) / len(category_scores)))

    summary = {
        "overall_score": overall_score,
        "category_scores": category_scores,
        "strengths": strengths[:6],
        "weaknesses": weaknesses[:6],
        "suggestions": suggestions[:6],
        "summary": (
            "This resume shows a solid technical foundation with room to sharpen impact language and project depth."
            if overall_score >= 70 else
            "This resume conveys a promising foundation, but it can be strengthened with clearer outcomes, stronger project and internship descriptions, and fuller skill coverage."
        ),
    }
    return summary
