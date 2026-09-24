import json
import tempfile
import unittest
from pathlib import Path

from modules.profile_parsing.experience_classifier import (
    predict_experience_type,
    train_experience_classifier,
)


class ExperienceClassifierTests(unittest.TestCase):
    def test_train_and_predict_internship_examples(self):
        rows = [
            {
                "text": "Machine Learning Intern | Cognifyz Technologies | Mar-Apr 2025\nDeveloped end-to-end ML pipelines using Python and scikit-learn.",
                "label": "internship",
            },
            {
                "text": "Software Engineer | ABC Technologies | 2023-Present\nBuilt backend APIs and production services.",
                "label": "work",
            },
            {
                "text": "Artificial Intelligence Research Assistant | University of Delhi | May-Jul 2025\nConducted computer vision experiments and evaluated baselines.",
                "label": "research",
            },
            {
                "text": "Information Technology Support Specialist | City College | 2022-2023\nHandled troubleshooting and hardware support.",
                "label": "other",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = Path(tmpdir) / "experience_dataset.jsonl"
            with data_path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")

            model_dir = Path(tmpdir) / "model"
            model = train_experience_classifier(str(data_path), str(model_dir), prefer_transformer=False)
            self.assertIn("labels", model)
            self.assertEqual(set(model["labels"]), {"work", "internship", "research", "other"})

            internship_prediction = predict_experience_type(
                "Machine Learning Intern | Cognifyz Technologies | Mar-Apr 2025\nBuilt model evaluation workflows.",
                model_dir=str(model_dir),
            )
            self.assertEqual(internship_prediction["label"], "internship")

            research_prediction = predict_experience_type(
                "Undergraduate Research Assistant | AI Lab | May-Jul 2025\nStudied retrieval systems and published experiments.",
                model_dir=str(model_dir),
            )
            self.assertEqual(research_prediction["label"], "research")


if __name__ == "__main__":
    unittest.main()
