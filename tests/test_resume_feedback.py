import unittest

from modules.profile_parsing.schema import CandidateProfile, ContactInfo, Internship
from services.resume_feedback import analyze_resume_feedback


class ResumeFeedbackTests(unittest.TestCase):
    def test_resume_feedback_is_scored_from_canonical_profile(self):
        profile = CandidateProfile(
            contact=ContactInfo(name="Ava Patel", email="ava@example.com", phone="9999999999"),
            skills=["Python", "Flask", "PostgreSQL", "Docker", "Machine Learning"],
            education=[],
            projects=[],
            internships=[
                Internship(
                    role="Backend Intern",
                    company="Acme",
                    duration="May 2025 - Jul 2025",
                    description_points=[
                        "Built analytics dashboards using Python, SQL, and Flask.",
                        "Owned end-to-end deployment for a service used by 200+ users.",
                    ],
                ),
            ],
        )

        result = analyze_resume_feedback(profile)

        self.assertIn("overall_score", result)
        self.assertGreaterEqual(result["overall_score"], 0)
        self.assertLessEqual(result["overall_score"], 100)
        self.assertIn("category_scores", result)
        self.assertIn("strengths", result)
        self.assertIn("weaknesses", result)
        self.assertIn("suggestions", result)
        self.assertIsInstance(result["category_scores"], dict)
        self.assertEqual(set(result["category_scores"]), {"projects", "internships", "skills", "education"})

    def test_missing_internships_are_flagged(self):
        result = analyze_resume_feedback({"skills": ["Python"], "projects": [], "education": [], "internships": []})
        self.assertLess(result["category_scores"]["internships"], 50)
        self.assertTrue(any("internship" in s.lower() for s in result["suggestions"]))


if __name__ == "__main__":
    unittest.main()
