import unittest

from modules.profile_parsing.schema import CandidateProfile, ContactInfo
from services.resume_feedback import analyze_resume_feedback


class ResumeFeedbackTests(unittest.TestCase):
    def test_resume_feedback_is_scored_from_canonical_profile(self):
        profile = CandidateProfile(
            contact=ContactInfo(name="Ava Patel", email="ava@example.com", phone="9999999999"),
            skills=["Python", "Flask", "PostgreSQL", "Docker", "Machine Learning"],
            education=[],
            projects=[],
            experience_raw=[
                "Built analytics dashboards using Python, SQL, and Flask.",
                "Owned end-to-end deployment for a service used by 200+ users.",
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


if __name__ == "__main__":
    unittest.main()
