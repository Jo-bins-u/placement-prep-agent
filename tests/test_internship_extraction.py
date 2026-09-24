import unittest

from modules.profile_parsing.parser import parse_resume


class InternshipExperienceTests(unittest.TestCase):
    def test_resume_with_only_jobs_keeps_empty_internships(self):
        text = '''
        Alice Candidate
        EXPERIENCE
        Software Engineer
        ABC Technologies
        2024 - Present
        - Built internal analytics platform.
        '''
        profile = parse_resume(text, source_file='jobs.txt')
        self.assertEqual(len(profile.experience), 1)
        self.assertEqual(profile.experience[0]["type"], "work")
        self.assertEqual(profile.internships, [])

    def test_resume_with_only_internships_has_empty_experience(self):
        text = '''
        Bob Candidate
        INTERNSHIP EXPERIENCE
        Machine Learning Intern
        Cognifyz Technologies
        Mar 2025 - Apr 2025
        - Developed a restaurant rating prediction model.
        - Built a recommendation system.
        '''
        profile = parse_resume(text, source_file='internships.txt')
        self.assertEqual(profile.experience, [])
        self.assertEqual(len(profile.internships), 1)
        self.assertEqual(profile.internships[0]["type"], "internship")
        self.assertEqual(profile.internships[0]["role"], "Machine Learning Intern")

    def test_resume_with_both_work_and_internships_keeps_separate_collections(self):
        text = '''
        Carol Candidate
        WORK EXPERIENCE
        Software Engineer
        XYZ Corp
        2023 - Present
        - Built API services.

        INTERNSHIPS
        Data Science Intern
        Acme Labs
        Jun 2024 - Aug 2024
        - Built forecasting models.
        '''
        profile = parse_resume(text, source_file='mixed.txt')
        self.assertEqual(len(profile.experience), 1)
        self.assertEqual(len(profile.internships), 1)
        self.assertEqual(profile.experience[0]["type"], "work")
        self.assertEqual(profile.internships[0]["type"], "internship")

    def test_role_name_machine_learning_intern_classifies_as_internship(self):
        text = '''
        Dana Candidate
        EXPERIENCE
        Machine Learning Intern
        Insight Labs
        2025
        - Built NLP features.
        '''
        profile = parse_resume(text, source_file='role.txt')
        self.assertEqual(profile.internships[0]["type"], "internship")
        self.assertEqual(profile.experience, [])

    def test_wrapped_internship_lines_group_into_single_object(self):
        text = '''
        Esha Candidate
        INTERNSHIPS
        Machine Learning Intern
        Cognifyz Technologies
        Mar 2025 - Apr 2025
        - Developed a restaurant rating prediction model.
        - Built a recommendation system.
        - Implemented cuisine classification.
        '''
        profile = parse_resume(text, source_file='wrapped.txt')
        self.assertEqual(len(profile.internships), 1)
        self.assertEqual(len(profile.internships[0]["description"]), 3)
        self.assertEqual(profile.internships[0]["organization"], "Cognifyz Technologies")


if __name__ == "__main__":
    unittest.main()
