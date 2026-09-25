import io
import os
import re
import unittest

import auth
import database as db
from app import app


class AppFlowTests(unittest.TestCase):
    def test_homepage_and_upload_flow(self):
        client = app.test_client()
        self.assertEqual(client.get('/').status_code, 200)

        # Signed-in user (uploads now require an account)
        email = "flow-upload@example.com"
        user = db.get_user_by_email(email)
        user_id = user["id"] if user else db.create_user(email, auth.hash_password("secret123"))
        db.mark_user_verified(user_id)
        self.assertEqual(client.post('/login', data={'email': email, 'password': 'secret123'}).status_code, 302)

        sample_path = os.path.join(os.path.dirname(__file__), '..', 'sample_resume.pdf')
        with open(sample_path, 'rb') as fh:
            upload = client.post('/upload', data={'resume': (io.BytesIO(fh.read()), 'sample_resume.pdf')},
                                 content_type='multipart/form-data')
        self.assertEqual(upload.status_code, 302)
        location = upload.headers['Location']
        self.assertIn('/verify-profile/', location)
        candidate_id = int(location.rstrip('/').split('/')[-1])

        profile = client.get(f'/verify-profile/{candidate_id}')
        self.assertEqual(profile.status_code, 200)
        self.assertIn(b'TechCorp', profile.data)  # internship parsed from the sample resume

        dashboard = client.get(f'/dashboard/{candidate_id}')
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b'Where you', dashboard.data)

        practice = client.get(f'/practice/{candidate_id}')
        self.assertEqual(practice.status_code, 200)
        self.assertIn('question', practice.get_data(as_text=True).lower())

        issue_id = re.search(r'name="issue_id" value="([^"]+)"', practice.get_data(as_text=True)).group(1)
        answer = ('A hash table maps keys to an index with a hash function, and collisions are resolved '
                  'by probing or chaining, so lookup stays constant on average.')
        submit = client.post(f'/practice/{candidate_id}/submit', data={'issue_id': issue_id, 'answer_text': answer})
        self.assertEqual(submit.status_code, 200)
        self.assertIn('feedback', submit.get_data(as_text=True).lower())


if __name__ == '__main__':
    unittest.main()
