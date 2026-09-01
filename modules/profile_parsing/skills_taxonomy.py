"""
Starter skills taxonomy for keyword-based extraction.

This is intentionally simple (exact/word-boundary match) so it's fast,
explainable, and has no external model dependency. Expand this list as
you test against real resumes — every FN (skill present in resume but
missed here) is a one-line fix.

Grouped so M2 (question generation) can later bias by category if useful,
but the schema currently flattens this to a single `skills` list —
confirm with M2's owner before changing that.
"""

SKILLS_TAXONOMY = {
    "languages": [
        "Python", "Java", "C++", "C", "JavaScript", "TypeScript", "Go", "Rust",
        "SQL", "R", "Kotlin", "Swift", "PHP", "Ruby", "Scala",
    ],
    "frameworks": [
        "React", "React.js", "Angular", "Vue", "Django", "Flask", "FastAPI",
        "Spring", "Spring Boot", "Node.js", "Express", "Next.js", "TensorFlow",
        "PyTorch", "Keras", "scikit-learn",
    ],
    "databases": [
        "MySQL", "PostgreSQL", "MongoDB", "Redis", "SQLite", "Oracle",
        "Firebase", "Cassandra",
    ],
    "tools": [
        "Git", "GitHub", "Docker", "Kubernetes", "AWS", "Azure", "GCP",
        "Jenkins", "Linux", "Postman", "VS Code", "Jira",
    ],
    "cs_fundamentals": [
        "Data Structures", "Algorithms", "OOP", "Object-Oriented Programming",
        "DBMS", "Operating Systems", "Computer Networks", "System Design",
        "Machine Learning", "Deep Learning", "NLP",
    ],
}

# Flat lookup used by the matcher — longer phrases first so "React.js"
# matches before the shorter "React" would grab it.
ALL_SKILLS = sorted(
    {s for group in SKILLS_TAXONOMY.values() for s in group},
    key=len,
    reverse=True,
)
