import copy
import unittest

from modules.coding import problem_generator as pg
from modules.coding.dsa_bank import PROBLEMS
from modules.coding.runner import evaluate_submission


class DsaBankTests(unittest.TestCase):
    def test_every_topic_and_difficulty_has_a_problem(self):
        covered = {(p["topic"], p["difficulty"]) for p in PROBLEMS}
        missing = [(t, d) for t in pg.TOPICS for d in pg.DIFFICULTIES if (t, d) not in covered]
        self.assertEqual(missing, [])

    def test_reference_solutions_pass_their_tests(self):
        for entry in PROBLEMS:
            namespace = {}
            exec(entry["solution"], namespace)
            fn = namespace[entry["name"]]
            for args, expected in entry["visible"] + entry["hidden"]:
                with self.subTest(problem=entry["name"], args=args):
                    got = fn(*copy.deepcopy(args))
                    if isinstance(expected, float):
                        self.assertAlmostEqual(got, expected)
                    else:
                        self.assertEqual(got, expected)

    def test_judge_accepts_reference_through_the_real_runner(self):
        for entry in PROBLEMS[::6]:  # a spread of problems through the subprocess judge
            with self.subTest(problem=entry["name"]):
                result = evaluate_submission(pg._from_bank_entry(entry), entry["solution"])
                self.assertEqual(result["status"], "correct")

    def test_fallback_matches_requested_topic(self):
        for topic in ("graphs", "stacks", "heap", "bit_manipulation"):
            problem = pg.generate_dsa_problem({}, "easy", topic, "python")
            self.assertEqual(problem["source"], "curated_bank")
            bank_entry = next(p for p in PROBLEMS if p["name"] == problem["function_signature"]["name"])
            self.assertEqual(bank_entry["topic"], topic)
            self.assertTrue(pg.validate_problem_schema(problem))


class LlmProblemVerificationTests(unittest.TestCase):
    def raw(self, name="fib"):
        good = pg._from_bank_entry(next(p for p in PROBLEMS if p["name"] == name))
        return {k: copy.deepcopy(good[k]) for k in ("title", "description", "constraints", "function_signature",
                                                   "visible_test_cases", "hidden_test_cases", "reference_solution")}

    def test_correct_problem_is_accepted(self):
        problem, reason = pg.verify_llm_problem(self.raw(), "dynamic_programming", "easy")
        self.assertIsNotNone(problem, reason)
        self.assertEqual(problem["source"], "llm_verified")

    def test_wrong_expected_output_is_rejected(self):
        raw = self.raw()
        raw["hidden_test_cases"][0]["expected"] += 1
        problem, reason = pg.verify_llm_problem(raw, "dynamic_programming", "easy")
        self.assertIsNone(problem)
        self.assertTrue(reason.startswith("reference_"))

    def test_structural_problems_are_rejected(self):
        raw = self.raw()
        raw["hidden_test_cases"] = raw["hidden_test_cases"][:1]
        self.assertEqual(pg.verify_llm_problem(raw, "dynamic_programming", "easy")[1], "too_few_hidden_tests")
        raw = self.raw()
        raw["reference_solution"] = {"python": "print('hi')"}
        self.assertEqual(pg.verify_llm_problem(raw, "dynamic_programming", "easy")[1], "missing_python_reference")
        self.assertEqual(pg.verify_llm_problem("not json", "dynamic_programming", "easy")[1], "not_json_object")


if __name__ == "__main__":
    unittest.main()
