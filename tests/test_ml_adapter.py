import unittest

from modules.evaluation.ml_adapter import SOURCE_DATASET, SOURCE_SCORER_PATH, load_or_train_scorer, score_answer


class MlAdapterTests(unittest.TestCase):
    @unittest.skipUnless(SOURCE_DATASET.exists() or SOURCE_SCORER_PATH.exists(),
                         "m3_upgrade/ seed dataset and scorer model are not in this repository")
    def test_scorer_model_loads_from_seed_dataset(self):
        scorer = load_or_train_scorer()
        self.assertIsNotNone(scorer)

    def test_score_answer_returns_percentage(self):
        score = score_answer(
            question={
                "topic": "python",
                "type": "short_answer",
                "keywords": ["list", "dictionary", "loop", "mutable"],
            },
            answer="A list is mutable and a dictionary stores key-value pairs while loops iterate over data.",
        )
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)


if __name__ == "__main__":
    unittest.main()
