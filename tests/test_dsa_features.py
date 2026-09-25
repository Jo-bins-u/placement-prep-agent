import unittest

from app import app
from modules.coding.problem_generator import generate_dsa_problem, public_problem, validate_problem_schema
from modules.coding.runner import evaluate_submission, run_candidate_code


class DsaFeaturesTests(unittest.TestCase):
    def test_generate_problem_has_required_schema(self):
        problem = generate_dsa_problem({"skills": ["Python", "Arrays"]}, "medium", "arrays", "python")
        self.assertTrue(validate_problem_schema(problem))
        self.assertEqual(problem["difficulty"], "medium")
        self.assertEqual(problem["topic"], "arrays")
        self.assertNotIn("hidden_tests", public_problem(problem))

    def test_run_code_against_examples_returns_stdout(self):
        problem = generate_dsa_problem({"skills": ["Python", "Arrays"]}, "medium", "arrays", "python")
        code = "def max_subarray_sum(nums):\n    best = current = nums[0]\n    for value in nums[1:]:\n        current = max(value, current + value)\n        best = max(best, current)\n    return best\n"
        result = run_candidate_code(problem, code)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["passed_tests"], result["total_tests"])

    def test_submit_code_uses_hidden_tests(self):
        problem = generate_dsa_problem({"skills": ["Python", "Arrays"]}, "medium", "arrays", "python")
        code = "def max_subarray_sum(nums):\n    best = current = nums[0]\n    for value in nums[1:]:\n        current = max(value, current + value)\n        best = max(best, current)\n    return best\n"
        result = evaluate_submission(problem, code)
        self.assertGreaterEqual(result["passed_tests"], 0)
        self.assertGreaterEqual(result["coding_score"], 0.0)
        self.assertIn(result["status"], {"correct", "partially_correct", "incorrect"})

    def test_api_routes_exist_for_dsa_operations(self):
        import auth
        import database as db
        client = app.test_client()
        self.assertEqual(client.post('/coding/problems/generate', json={}).status_code, 401)  # login required
        user = db.get_user_by_email("dsa-api@example.com")
        uid = user["id"] if user else db.create_user("dsa-api@example.com", auth.hash_password("secret123"))
        db.mark_user_verified(uid)
        from modules.profile_parsing.schema import CandidateProfile, ContactInfo
        cid = db.save_candidate(uid, CandidateProfile(contact=ContactInfo(name="d", email="dsa-api@example.com"), skills=["Python", "Arrays"]))
        client.post("/login", data={"email": "dsa-api@example.com", "password": "secret123"})
        # The problem is generated from the server's copy of the profile; client profile text is ignored.
        self.assertEqual(client.post('/coding/problems/generate', json={"profile": {"skills": ["x"]}}).status_code, 400)
        generate = client.post('/coding/problems/generate', json={"candidate_id": cid, "difficulty": "medium", "topic": "arrays", "language": "python", "profile": {"skills": ["ignored"]}})
        self.assertEqual(generate.status_code, 200)
        body = generate.get_json()
        self.assertIn("problem", body)
        self.assertNotIn("hidden_tests", body["problem"])
        self.assertNotIn("hidden_test_cases", body["problem"])
        self.assertNotIn("reference_solution", body["problem"])


if __name__ == '__main__':
    unittest.main()
