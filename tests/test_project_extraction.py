import sys
import unittest

sys.path.insert(0, "modules/profile_parsing")

from parser import parse_resume


class ProjectExtractionTests(unittest.TestCase):
    def test_groups_two_projects_and_keeps_wrapped_bullets(self):
        text = """Alex Candidate
PROJECTS
Qorvexis - AI Infrastructure Intelligence Platform
- Architected a multi-tenant SaaS platform across
multiple LLM providers.
- Designed Business Intelligence systems for spend analytics and
recommendations.
- Implemented JWT Authentication, RBAC, FastAPI, PostgreSQL, OpenAI, Groq, Gemini, OpenRouter.
Distributed Rate Limiter System
- Architected a distributed API rate-limiting system.
- Designed atomic Redis Lua scripts and optimized Redis memory management.
- Developed an asynchronous benchmarking framework and integrated telemetry endpoints.
EDUCATION
University
"""

        profile = parse_resume(text, source_file="fixture.txt")

        self.assertEqual(
            [project.title for project in profile.projects],
            [
                "Qorvexis - AI Infrastructure Intelligence Platform",
                "Distributed Rate Limiter System",
            ],
        )
        self.assertEqual(len(profile.projects), 2)
        self.assertIn("multiple LLM providers.", profile.projects[0].description)
        self.assertIn("recommendations.", profile.projects[0].description)
        self.assertNotIn("recommendations.", [project.title for project in profile.projects])
        self.assertIn("FastAPI", profile.projects[0].technologies)
        self.assertIn("Redis", profile.projects[1].technologies)
        self.assertGreaterEqual(profile.projects[0].confidence, 0.9)


if __name__ == "__main__":
    unittest.main()
