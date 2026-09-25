import unittest

from modules.profile_parsing.parser import parse_resume


class InternshipExtractionTests(unittest.TestCase):
    def test_role_company_and_dates_on_separate_lines(self):
        text = '''
        Bob Candidate
        INTERNSHIPS
        Machine Learning Intern
        Cognifyz Technologies
        Mar 2025 - Apr 2025
        - Developed a restaurant rating prediction model.
        - Built a recommendation system.
        '''
        profile = parse_resume(text, source_file='internships.txt')
        self.assertEqual(len(profile.internships), 1)
        item = profile.internships[0]
        self.assertEqual(item.role, "Machine Learning Intern")
        self.assertEqual(item.company, "Cognifyz Technologies")
        self.assertEqual(item.duration, "Mar 2025 - Apr 2025")
        self.assertEqual(len(item.description_points), 2)

    def test_single_line_role_company_dates(self):
        text = '''
        Siya Candidate
        EXPERIENCE
        Machine Learning Intern | Cognifyz Technologies | Mar–Apr 2025
        - Built NLP features.
        '''
        item = parse_resume(text).internships[0]
        self.assertEqual(item.role, "Machine Learning Intern")
        self.assertEqual(item.company, "Cognifyz Technologies")
        self.assertEqual(item.duration, "Mar–Apr 2025")

    def test_company_first_then_role_with_location(self):
        text = '''
        Joy Candidate
        Work Experience & Internships
        Cezen Technologies Pvt. Ltd., Bengaluru April 2026 – May 2026
        Cybersecurity AI Intern
        - Built a threat detection pipeline.
        '''
        item = parse_resume(text).internships[0]
        self.assertEqual(item.role, "Cybersecurity AI Intern")
        self.assertEqual(item.company, "Cezen Technologies Pvt. Ltd.")
        self.assertEqual(item.location, "Bengaluru")
        self.assertEqual(item.duration, "April 2026 – May 2026")

    def test_multiple_internships_stay_separate(self):
        text = '''
        Carol Candidate
        INTERNSHIPS
        Data Science Intern
        Acme Labs
        Jun 2024 - Aug 2024
        - Built forecasting models.
        Web Development Intern
        Beta Corp
        Jan 2024 - Mar 2024
        - Built a React dashboard.
        '''
        profile = parse_resume(text)
        self.assertEqual([i.role for i in profile.internships], ["Data Science Intern", "Web Development Intern"])
        self.assertEqual([i.company for i in profile.internships], ["Acme Labs", "Beta Corp"])

    def test_wrapped_bullets_group_into_single_point(self):
        text = '''
        Esha Candidate
        INTERNSHIPS
        Machine Learning Intern
        Cognifyz Technologies
        Mar 2025 - Apr 2025
        - Developed a restaurant rating prediction model
          using gradient boosting.
        - Built a recommendation system.
        - Implemented cuisine classification.
        '''
        item = parse_resume(text).internships[0]
        self.assertEqual(len(item.description_points), 3)
        self.assertIn("gradient boosting", item.description_points[0])

    def test_internships_are_not_counted_as_projects(self):
        text = '''
        Dana Candidate
        PROJECTS
        Campus Event Portal
        - Built with React.
        EXPERIENCE
        Summer Intern, Software Development — TechCorp
        Worked on backend REST APIs using FastAPI.
        '''
        profile = parse_resume(text)
        self.assertEqual([p.title for p in profile.projects], ["Campus Event Portal"])
        self.assertEqual(profile.internships[0].company, "TechCorp")

    def test_project_titled_internship_is_not_a_heading(self):
        text = '''
        Eli Candidate
        PROJECTS
        Internship Portal
        - Built a job board with Flask.
        '''
        profile = parse_resume(text)
        self.assertEqual([p.title for p in profile.projects], ["Internship Portal"])
        self.assertEqual(profile.internships, [])


if __name__ == "__main__":
    unittest.main()
