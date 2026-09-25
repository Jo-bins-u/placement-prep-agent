"""Hand-labelled resumes for measuring the resume parser.

All people and companies are fictional. Each case gives the raw resume text and
the fields a human would extract ("gold" labels). Formats vary on purpose:
different heading styles, bullets, inline vs separate dates, pipes/dashes,
company-first vs role-first internships. Skills include a few technologies that
are NOT in the skills taxonomy so recall is measured honestly.
"""

RESUMES = [
    {
        "id": "R01-classic",
        "text": """Aarav Mehta
aarav.mehta@example.com | +91 98450 11223
EDUCATION
B.Tech in Computer Science, Northfield Institute of Technology — CGPA 8.4
SKILLS
Python, Java, SQL, Flask, Docker, Git, Data Structures, Algorithms
PROJECTS
Smart Attendance System
- Built a face-recognition attendance tracker using Python and OpenCV.
- Stored records in MySQL and exposed a Flask dashboard.
Expense Splitter App
- Developed a React web app to split group expenses with Firebase auth.
INTERNSHIPS
Software Development Intern
Brightpath Labs
Jun 2024 - Aug 2024
- Built REST APIs in Flask for the billing service.
- Wrote unit tests that raised coverage to 85%.
""",
        "gold": {
            "name": "Aarav Mehta", "email": "aarav.mehta@example.com",
            "skills": ["Python", "Java", "SQL", "Flask", "Docker", "Git", "Data Structures", "Algorithms", "OpenCV", "MySQL", "React", "Firebase"],
            "projects": ["Smart Attendance System", "Expense Splitter App"],
            "internships": [{"role": "Software Development Intern", "company": "Brightpath Labs", "duration": "Jun 2024 - Aug 2024"}],
            "education": ["Northfield Institute of Technology"],
        },
    },
    {
        "id": "R02-pipes-inline",
        "text": """Diya Raman
diya.raman@example.org
TECHNICAL SKILLS
Languages: Python, C++, JavaScript
Frameworks: Django, React.js, Node.js
Databases: PostgreSQL, MongoDB
EXPERIENCE
Machine Learning Intern | Nimbus Analytics | Jan 2025 – Apr 2025
• Trained gradient-boosting models to predict customer churn with scikit-learn.
• Reduced inference latency by 40% using batching.
Web Development Intern | Coralwave Media | May 2024 – Jul 2024
• Built a content dashboard in React.js backed by Node.js services.
PROJECTS
Crop Yield Predictor | Python, scikit-learn
• Regression model predicting yield from rainfall and soil data.
Chat Room Server | C++, Linux
• Multi-client chat server using POSIX sockets.
EDUCATION
Riverdale University — B.E. Information Technology — CGPA 9.1
""",
        "gold": {
            "name": "Diya Raman", "email": "diya.raman@example.org",
            "skills": ["Python", "C++", "JavaScript", "Django", "React.js", "Node.js", "PostgreSQL", "MongoDB", "scikit-learn", "Linux"],
            "projects": ["Crop Yield Predictor", "Chat Room Server"],
            "internships": [
                {"role": "Machine Learning Intern", "company": "Nimbus Analytics", "duration": "Jan 2025 – Apr 2025"},
                {"role": "Web Development Intern", "company": "Coralwave Media", "duration": "May 2024 – Jul 2024"},
            ],
            "education": ["Riverdale University"],
        },
    },
    {
        "id": "R03-company-first",
        "text": """Kabir Sethi
kabir.sethi@example.com | 9876501234
Work Experience & Internships
Orchid Systems Pvt. Ltd., Pune   Dec 2024 – Feb 2025
Backend Engineering Intern
- Migrated cron jobs to a Redis-backed task queue.
- Containerised services with Docker and deployed on AWS.
Lumen Health, Remote   Jun 2024 – Aug 2024
Data Analyst Intern
- Automated weekly SQL reports and built Tableau dashboards.
Projects
Parking Spot Finder
- Android app in Kotlin that shows free parking spots using live sensor data.
Resume Ranker
- NLP pipeline ranking resumes against job descriptions using Python.
Education
Bachelor of Engineering in Computer Engineering, Westbrook College — 8.2 CGPA
Skills
Kotlin, Python, SQL, Redis, Docker, AWS, NLP
""",
        "gold": {
            "name": "Kabir Sethi", "email": "kabir.sethi@example.com",
            "skills": ["Kotlin", "Python", "SQL", "Redis", "Docker", "AWS", "NLP", "Tableau"],
            "projects": ["Parking Spot Finder", "Resume Ranker"],
            "internships": [
                {"role": "Backend Engineering Intern", "company": "Orchid Systems Pvt. Ltd.", "duration": "Dec 2024 – Feb 2025"},
                {"role": "Data Analyst Intern", "company": "Lumen Health", "duration": "Jun 2024 – Aug 2024"},
            ],
            "education": ["Westbrook College"],
        },
    },
    {
        "id": "R04-no-internships",
        "text": """Meera Iyer
meera.iyer@example.com
SKILLS
Java, Spring Boot, MySQL, Git, OOP, DBMS
PROJECTS
Library Management System
- Java and Spring Boot application with role-based access for librarians.
Online Quiz Platform
- Timed quizzes with automatic grading, built with Spring Boot and MySQL.
Weather Notifier Bot
- Telegram bot that sends daily forecasts.
EDUCATION
B.Tech in Information Technology, Eastgate University — CGPA 7.9
Higher Secondary, Sunrise Public School — Percentage 88%
""",
        "gold": {
            "name": "Meera Iyer", "email": "meera.iyer@example.com",
            "skills": ["Java", "Spring Boot", "MySQL", "Git", "OOP", "DBMS"],
            "projects": ["Library Management System", "Online Quiz Platform", "Weather Notifier Bot"],
            "internships": [],
            "education": ["Eastgate University", "Sunrise Public School"],
        },
    },
    {
        "id": "R05-at-style",
        "text": """Rohan Das
rohan.das@example.com | +91 90000 55555
PROFESSIONAL EXPERIENCE
Cloud Intern at Stratus Cloudworks (May 2025 - Jul 2025)
Bengaluru, India
Automated infrastructure provisioning with Terraform and Kubernetes on GCP.
Research Intern at Institute of Applied AI (Dec 2024 - Jan 2025)
Built an image-captioning prototype using PyTorch.
PROJECTS
Traffic Sign Classifier
- CNN trained with TensorFlow and Keras on 40k images, 96% accuracy.
EDUCATION
M.Tech in Artificial Intelligence, Lakeside University
SKILLS
Python, PyTorch, TensorFlow, Keras, Kubernetes, GCP, Deep Learning
""",
        "gold": {
            "name": "Rohan Das", "email": "rohan.das@example.com",
            "skills": ["Python", "PyTorch", "TensorFlow", "Keras", "Kubernetes", "GCP", "Deep Learning", "Terraform"],
            "projects": ["Traffic Sign Classifier"],
            "internships": [
                {"role": "Cloud Intern", "company": "Stratus Cloudworks", "duration": "May 2025 - Jul 2025"},
                {"role": "Research Intern", "company": "Institute of Applied AI", "duration": "Dec 2024 - Jan 2025"},
            ],
            "education": ["Lakeside University"],
        },
    },
    {
        "id": "R06-month-range",
        "text": """Sana Qureshi
sana.q@example.com
EXPERIENCE
Frontend Intern | Pixel Forge | Mar–May 2025
- Rebuilt the marketing site in Next.js and TypeScript.
- Cut page load time from 3.2s to 1.1s.
PROJECTS
Portfolio Generator
- Static-site generator in TypeScript that turns markdown into a portfolio.
Recipe Finder
- Vue app that searches recipes by ingredients using a public API.
SKILLS
TypeScript, JavaScript, Next.js, Vue, Node.js, Git
EDUCATION
B.Sc Computer Science, Hillcrest College — CGPA 8.8
""",
        "gold": {
            "name": "Sana Qureshi", "email": "sana.q@example.com",
            "skills": ["TypeScript", "JavaScript", "Next.js", "Vue", "Node.js", "Git"],
            "projects": ["Portfolio Generator", "Recipe Finder"],
            "internships": [{"role": "Frontend Intern", "company": "Pixel Forge", "duration": "Mar–May 2025"}],
            "education": ["Hillcrest College"],
        },
    },
    {
        "id": "R07-projects-with-tech-tail",
        "text": """Vikram Nair
vikram.nair@example.com | 8123456789
Projects
EventHub – Campus Event Platform React, Node.js, MongoDB | Jan 2025 – Apr 2025
• Built a full-stack event platform with role-based access and live updates.
Fraud Detection Engine Python, scikit-learn, FastAPI
• Trained an isolation-forest model and served it through FastAPI.
Internships
Software Engineer Intern – Payments Team
Arcadia Fintech, Mumbai
Jun 2025 – Aug 2025
• Built reconciliation jobs in Python processing 2M transactions a day.
Technical Skills
Python, React, Node.js, MongoDB, FastAPI, scikit-learn, SQL
Education
Bachelor of Technology, Computer Science, Crestview University
""",
        "gold": {
            "name": "Vikram Nair", "email": "vikram.nair@example.com",
            "skills": ["Python", "React", "Node.js", "MongoDB", "FastAPI", "scikit-learn", "SQL"],
            "projects": ["EventHub – Campus Event Platform", "Fraud Detection Engine"],
            "internships": [{"role": "Software Engineer Intern – Payments Team", "company": "Arcadia Fintech", "duration": "Jun 2025 – Aug 2025"}],
            "education": ["Crestview University"],
        },
    },
    {
        "id": "R08-wrapped-bullets",
        "text": """Ananya Bose
ananya.bose@example.com
INTERNSHIP EXPERIENCE
Data Science Intern
Quantum Retail Analytics
Jan 2024 - Jun 2024
- Developed demand-forecasting models in Python that reduced stock-outs
  by 18% across 40 stores.
- Built an internal Streamlit app for planners.
PROJECTS
Sentiment Tracker
- NLP dashboard tracking product sentiment from reviews.
SKILLS
Python, NLP, SQL, Machine Learning, Pandas
EDUCATION
Integrated M.Sc Data Science, Greenfield University — CGPA 9.0
""",
        "gold": {
            "name": "Ananya Bose", "email": "ananya.bose@example.com",
            "skills": ["Python", "NLP", "SQL", "Machine Learning", "Pandas", "Streamlit"],
            "projects": ["Sentiment Tracker"],
            "internships": [{"role": "Data Science Intern", "company": "Quantum Retail Analytics", "duration": "Jan 2024 - Jun 2024"}],
            "education": ["Greenfield University"],
        },
    },
    {
        "id": "R09-training-heading",
        "text": """Farhan Ali
farhan.ali@example.com
INDUSTRIAL TRAINING
Embedded Systems Trainee
Voltline Electronics
Summer 2024
- Programmed microcontrollers in C for motor control.
PROJECTS
Home Automation Hub
- Raspberry Pi hub controlling lights via a Flask API.
Line Follower Robot
- Arduino robot using PID control.
SKILLS
C, Python, Flask, Linux
EDUCATION
B.E. Electronics and Communication, Ridgeway Institute of Engineering
""",
        "gold": {
            "name": "Farhan Ali", "email": "farhan.ali@example.com",
            "skills": ["C", "Python", "Flask", "Linux", "Arduino", "Raspberry Pi"],
            "projects": ["Home Automation Hub", "Line Follower Robot"],
            "internships": [{"role": "Embedded Systems Trainee", "company": "Voltline Electronics", "duration": "Summer 2024"}],
            "education": ["Ridgeway Institute of Engineering"],
        },
    },
    {
        "id": "R10-internship-titled-project",
        "text": """Priya Kulkarni
priya.k@example.com | 9988776655
PROJECTS
Internship Portal
- Job board for campus internships built with Django and PostgreSQL.
User Experience Audit Tool
- Browser extension that scores page accessibility, written in JavaScript.
EXPERIENCE
QA Intern — Sparrow Software
Oct 2024 – Dec 2024
- Automated regression tests with Selenium, cutting release checks from 2 days to 3 hours.
SKILLS
Python, Django, PostgreSQL, JavaScript, Selenium
EDUCATION
B.Tech Computer Science, Maplewood University
""",
        "gold": {
            "name": "Priya Kulkarni", "email": "priya.k@example.com",
            "skills": ["Python", "Django", "PostgreSQL", "JavaScript", "Selenium"],
            "projects": ["Internship Portal", "User Experience Audit Tool"],
            "internships": [{"role": "QA Intern", "company": "Sparrow Software", "duration": "Oct 2024 – Dec 2024"}],
            "education": ["Maplewood University"],
        },
    },
]
