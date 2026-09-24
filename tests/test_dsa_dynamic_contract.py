import unittest

from modules.coding.problem_generator import generate_dsa_problem, validate_problem_schema
from modules.coding.runner import evaluate_submission, run_candidate_code


class DynamicDsaContractTests(unittest.TestCase):
    def test_topic_and_difficulty_change_problem_contract(self):
        arrays = generate_dsa_problem({}, "easy", "arrays", "python")
        graph = generate_dsa_problem({}, "medium", "graphs", "python")

        self.assertNotEqual(arrays["canonical_hash"], graph["canonical_hash"])
        self.assertEqual(arrays["topic"], "arrays")
        self.assertEqual(graph["topic"], "graphs")
        self.assertNotEqual(arrays["function_signature"]["name"], graph["function_signature"]["name"])
        self.assertTrue(validate_problem_schema(arrays))
        self.assertTrue(validate_problem_schema(graph))

    def test_structured_args_execute_without_scalar_iteration(self):
        problem = generate_dsa_problem({}, "medium", "sliding_window", "python")
        code = "def max_window_sum(nums, k):\n    return max(sum(nums[i:i+k]) for i in range(len(nums)-k+1))\n"
        result = run_candidate_code(problem, code)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["passed_tests"], result["total_tests"])
        self.assertTrue(all("input" in test and "expected" in test and "actual" in test for test in result["tests"]))

    def test_empty_tests_cannot_be_reported_as_passed(self):
        problem = generate_dsa_problem({}, "easy", "arrays", "python")
        problem["visible_test_cases"] = []
        result = run_candidate_code(problem, "def sum_array(nums): return sum(nums)")
        self.assertNotEqual(result["status"], "passed")
        self.assertEqual(result["total_tests"], 0)

    def test_submission_uses_hidden_tests_and_deterministic_score(self):
        problem = generate_dsa_problem({}, "easy", "hashing", "python")
        result = evaluate_submission(problem, "def contains_duplicate(nums): return len(nums) != len(set(nums))")
        self.assertEqual(result["status"], "correct")
        self.assertEqual(result["passed_tests"], result["total_tests"])
        self.assertEqual(result["coding_score"], 100.0)


if __name__ == "__main__":
    unittest.main()