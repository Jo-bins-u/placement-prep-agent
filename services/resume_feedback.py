import math
import re
from typing import Any


def _normalize_text(value):
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _score_experience(profile: dict) -> tuple[int, list[str], list[str], list[str]]:
    work_entries = profile.get("experience") or []
    internship_entries = profile.get("internships") or []
    experience = profile.get("experience_raw") or []
    text = " ".join(_normalize_text(item) for item in experience if item)
    if not text and not work_entries and not internship_entries:
        return 0, [], [], ["Add concrete work experience to show outcomes and ownership."]

    work_count = len(work_entries)
    internship_count = len(internship_entries)
    metrics = {
        "projects": len(profile.get("projects") or []),
        "skills": len(profile.get("skills") or []),
        "work_items": work_count,
        "internship_items": internship_count,
        "experience_items": len(experience),
        "impact_markers": sum(1 for marker in ["built", "designed", "developed", "optimized", "led", "improved", "implemented", "architected"] if marker.lower() in text.lower()),
    }

    score = min(100, 35 + metrics["work_items"] * 12 + metrics["internship_items"] * 8 + metrics["impact_markers"] * 5 + metrics["projects"] * 8 + min(metrics["skills"], 15))
    strengths = []
    weaknesses = []
    suggestions = []

    if work_count >= 1:
        strengths.append(f"Work experience includes {work_count} role entry(s).")
    elif internship_count >= 1:
        strengths.append(f"Internships provide {internship_count} entry(s) of relevant applied experience.")
    else:
        weaknesses.append("Resume would benefit from more experience detail.")
        suggestions.append("Add 1–2 fuller work entries with scope, tools, and outcomes.")

    if internship_count:
        strengths.append(f"Internships are tracked separately: {internship_count} internship entry(s).")
    elif work_count:
        strengths.append("The experience section is clearly separated from internships.")

    if metrics["impact_markers"] >= 2:
        strengths.append("Your responsibilities read as outcome-oriented and action-based.")
    else:
        weaknesses.append("Impact language is limited.")
        suggestions.append("Add action verbs and measurable business outcomes to highlight ownership.")

    if metrics["projects"] >= 1:
        strengths.append("Project evidence is included.")
    else:
        weaknesses.append("Portfolio depth is light.")
        suggestions.append("Add a few projects with role, stack, and business value.")

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
            "experience": getattr(profile, "experience", []) or [],
            "internships": getattr(profile, "internships", []) or [],
            "experience_raw": getattr(profile, "experience_raw", []) or [],
        }

    category_scores = {}
    strengths = []
    weaknesses = []
    suggestions = []

    for category, fn in [
        ("experience", _score_experience),
        ("skills", _score_skills),
        ("projects", _score_projects),
        ("education", _score_education),
    ]:
        score, cat_strengths, cat_weaknesses, cat_suggestions = fn(profile_data)
        category_scores[category] = score
        strengths.extend(cat_strengths)
        weaknesses.extend(cat_weaknesses)
        suggestions.extend(cat_suggestions)

    work_count = len(profile_data.get("experience") or [])
    internship_count = len(profile_data.get("internships") or [])
    overall_score = int(round(sum(category_scores.values()) / len(category_scores)))

    summary = {
        "overall_score": overall_score,
        "category_scores": category_scores,
        "experience_breakdown": {
            "work_experience": work_count,
            "internships": internship_count,
        },
        "strengths": strengths[:6],
        "weaknesses": weaknesses[:6],
        "suggestions": suggestions[:6],
        "summary": (
            "This resume shows a solid technical foundation with room to sharpen impact language and project depth."
            if overall_score >= 70 else
            "This resume conveys a promising foundation, but it can be strengthened with clearer outcomes, stronger project storytelling, and fuller skill coverage."
        ),
    }
    return summary
