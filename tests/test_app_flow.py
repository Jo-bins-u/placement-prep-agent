import io
import json
import os
import unittest

from app import app


class AppFlowTests(unittest.TestCase):
    def test_homepage_and_upload_flow(self):
        client = app.test_client()

        home = client.get('/')
        self.assertEqual(home.status_code, 200)

        sample_path = os.path.join(os.getcwd(), 'sample_resume.pdf')
        with open(sample_path, 'rb') as fh:
            upload = client.post(
                '/upload',
                data={'resume': (io.BytesIO(fh.read()), 'sample_resume.pdf')},
                content_type='multipart/form-data',
            )

        self.assertIn(upload.status_code, (200, 302))
        self.assertIn('Location', upload.headers)

        location = upload.headers.get('Location', '')
        self.assertIn('/dashboard/', location)

        candidate_id = int(location.rstrip('/').split('/')[-1])
        dashboard = client.get(f'/dashboard/{candidate_id}')
        self.assertEqual(dashboard.status_code, 200)

        practice = client.get(f'/practice/{candidate_id}')
        self.assertEqual(practice.status_code, 200)
        practice_html = practice.get_data(as_text=True).lower()
        self.assertTrue('question' in practice_html or 'question_json' in practice_html)

        payload = {
            'id': 'Q1',
            'topic': 'data structures',
            'type': 'short_answer',
            'keywords': ['hash function', 'collision', 'index', 'lookup'],
            'prompt': 'Explain how a hash table achieves average O(1) lookup time.',
        }
        answer = (
            'A hash table maps keys to indices with a hash function, and collisions are '
            'resolved by probing or chaining, so average lookup stays constant when the '
            'load factor is controlled.'
        )

        submit = client.post(
            f'/practice/{candidate_id}/submit',
            data={
                'question_id': 'Q1',
                'answer_text': answer,
                'question_json': json.dumps(payload),
            },
        )

        self.assertEqual(submit.status_code, 200)
        submit_html = submit.get_data(as_text=True).lower()
        self.assertTrue('score' in submit_html or 'feedback' in submit_html)


if __name__ == '__main__':
    unittest.main()
