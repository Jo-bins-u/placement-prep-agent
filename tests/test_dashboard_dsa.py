import unittest

import database as db
from app import app
from modules.coding.problem_generator import generate_dsa_problem
from modules.profile_parsing.schema import CandidateProfile, ContactInfo


class DashboardDsaTests(unittest.TestCase):
    def test_submission_updates_dashboard_metrics(self):
        profile = CandidateProfile(contact=ContactInfo(name="Dashboard Test", email="dashboard@example.com"))
        candidate_id = db.save_candidate(profile)
        problem = generate_dsa_problem({"skills": ["Python"]}, "medium", "arrays", "Python")
        db.save_coding_problem(problem["id"], candidate_id, problem)
        db.save_coding_submission(
            candidate_id,
            problem["id"],
            "def solution(nums): return sum(nums)",
            passed_tests=2,
            total_tests=3,
            score=66.7,
            execution_time_ms=12.0,
            memory_usage_mb=8.0,
            status="partially_correct",
            feedback="One test failed.",
        )

        client = app.test_client()
        response = client.get(f"/api/dashboard/{candidate_id}")
        self.assertEqual(response.status_code, 200)
        dsa = response.get_json()["dsa"]
        self.assertEqual(dsa["attempted"], 1)
        self.assertEqual(dsa["solved"], 0)
        self.assertEqual(dsa["average_score"], 66.7)
        self.assertEqual(dsa["topic_scores"]["arrays"], 66.7)
        self.assertEqual(len(dsa["trend"]), 1)


if __name__ == "__main__":
    unittest.main()
