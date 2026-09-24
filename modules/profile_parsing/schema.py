"""
Candidate Profile Schema — Module 1 output contract.

This is the shared contract every other module (M2 question generation,
M3 evaluation, M4 analytics/dashboard) reads from. Lock this early — the
whole team's Week 3 milestone depends on it (see PRD Section 10).

Design choices:
- Every extracted field carries a `confidence` so downstream modules and
  the dashboard can show "needs review" instead of silently trusting a
  bad parse (PRD FR5.4).
- `skills` is a flat list now; if you later want skill *categories*
  (languages vs frameworks vs tools), extend this — but confirm with
  whoever owns M2, since it consumes this list directly for topic bias.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional
from uuid import uuid4
import json


@dataclass
class ContactInfo:
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    confidence: float = 0.0  # 0-1, how sure the parser is


@dataclass
class Education:
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    specialization: Optional[str] = None
    cgpa_or_percentage: Optional[str] = None
    scale: Optional[str] = None
    raw_text: Optional[str] = None  # keep the source line for manual review


@dataclass
class Project:
    title: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    description_points: List[str] = field(default_factory=list)
    tech_stack: List[str] = field(default_factory=list)
    technologies: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    raw_text: Optional[str] = None
    llm_extracted: bool = False  # True when extracted via Groq LLM
    source: str = "resume"
    confidence: float = 0.0
    id: str = field(default_factory=lambda: f"project-{uuid4().hex[:12]}")

    def __post_init__(self):
        self.name = self.name or self.title
        self.title = self.title or self.name
        if not self.description_points and self.description:
            self.description_points = [self.description]
        if not self.description and self.description_points:
            self.description = " ".join(self.description_points)
        if not self.technologies:
            self.technologies = list(self.tech_stack)
        if not self.tech_stack:
            self.tech_stack = list(self.technologies)
        if not self.confidence:
            self.confidence = 0.9 if self.title and self.description else 0.65



@dataclass
class CandidateProfile:
    contact: ContactInfo = field(default_factory=ContactInfo)
    skills: List[str] = field(default_factory=list)
    education: List[Education] = field(default_factory=list)
    projects: List[Project] = field(default_factory=list)

    # Fields the parser wasn't confident about — dashboard shows these
    # as "needs review" per PRD FR5.4, instead of guessing.
    needs_review: List[str] = field(default_factory=list)

    source_file: Optional[str] = None
    parser_version: str = "0.1"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent)
