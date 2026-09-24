import json
import os
import unittest

from modules.dsa_engine import (
    generate_dsa_problem,
    run_sample_tests,
    submit_solution,
    validate_problem_schema,
    compute_skill_gap,
)


class DsaFlowTests(unittest.TestCase):
    def test_generate_problem_for_profile(self):
        profile = {
            "skills": ["Python", "SQL", "Data Structures"],
            "experience_raw": ["Built analytics tools using Python."],
        }
        problem = generate_dsa_problem(profile, difficulty="medium", topic="arrays", language="Python")
        self.assertIsInstance(problem, dict)
        self.assertEqual(problem["difficulty"], "medium")
        self.assertEqual(problem["topic"], "arrays")
        self.assertIn("Python", problem["skills"])
        self.assertTrue(validate_problem_schema(problem))

    def test_problem_schema_and_tests_are_valid(self):
        profile = {"skills": ["Python"], "experience_raw": ["Software engineer intern"]}
        problem = generate_dsa_problem(profile, difficulty="easy", topic="strings", language="Python")
        self.assertIn("examples", problem)
        self.assertIn("hidden_tests", problem)
        self.assertGreater(len(problem["hidden_tests"]), 0)
        self.assertGreater(len(problem["constraints"]), 0)

    def test_run_sample_tests_and_submit_success(self):
        profile = {"skills": ["Python"], "experience_raw": ["Python developer"]}
        problem = generate_dsa_problem(profile, difficulty="easy", topic="arrays", language="Python")
        raw_code = """
def solution(nums):
    return sum(nums)
"""
        sample_result = run_sample_tests(problem, raw_code)
        self.assertEqual(sample_result["status"], "success")

        submit_result = submit_solution(problem, raw_code)
        self.assertIn(submit_result["status"], {"success", "partial", "incorrect"})
        self.assertIn("passed_tests", submit_result)

    def test_skill_gap_analysis_uses_profile_and_history(self):
        profile = {"skills": ["Python", "SQL", "DSA", "Machine Learning"]}
        history = [
            {"topic": "arrays", "score": 92},
            {"topic": "graphs", "score": 35},
            {"topic": "dynamic_programming", "score": 28},
        ]
        gaps = compute_skill_gap(profile, history)
        self.assertIn("graphs", gaps)
        self.assertIn("dynamic_programming", gaps)


if __name__ == "__main__":
    unittest.main()
