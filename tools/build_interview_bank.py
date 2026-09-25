"""Builds data/interview_bank.json: behavioural/HR questions plus templates for questions about the
candidate's own projects, internships and skills. {title}, {tech}, {company}, {role}, {skill} are
filled from the resume. Keywords use "a|b" alternatives like the technical bank."""
import json
import sys

STAR = ["situation|context|background|when i was|at the time|during",
        "task|goal|responsibility|my role|i had to|needed to",
        "action|i decided|i did|i took|i implemented|i organised|i organized|i spoke|i proposed|steps",
        "result|outcome|impact|in the end|finally|improved|reduced|increased|delivered|succeeded"]
REFLECT = "learned|lesson|takeaway|next time|would do differently|realised|realized"

behavioral = [
    ("Tell me about yourself.", "easy",
     ["background|studying|student|degree|currently", "projects|built|developed|worked on", "skills|experience with|good at|strength",
      "internship|intern|worked at|team", "goal|looking for|interested in|want to|aspire|role"],
     "A strong answer is a 60–90 second story, not a résumé read-out: who you are now (degree, focus), 2–3 highlights that "
     "prove your skills (a project or internship with a concrete result), what you enjoy or are good at, and why you're "
     "interested in this kind of role."),
    ("Describe a challenging bug or problem you solved. How did you approach it?", "medium",
     STAR[:1] + ["debug|investigate|logs|reproduce|root cause|traced", "fix|solution|solved|resolved", STAR[3], REFLECT],
     "Use STAR: set the scene briefly, explain why it was hard, walk through how you investigated (reproducing it, logs, "
     "narrowing down the root cause), what you changed, the measurable result, and what you'd do to prevent it next time."),
    ("Tell me about a time you worked in a team and faced a disagreement. How did you handle it?", "medium",
     STAR[:1] + ["disagree|conflict|different opinion|different views|argument", "listen|discuss|understand|talked|communicate|communicated|communication",
                 "compromise|agreed|consensus|decided together|data|prototype", STAR[3]],
     "A strong answer describes a real disagreement without blaming anyone, shows you listened to understand the other view, "
     "explains how the team decided (data, a quick prototype, a compromise), and ends with the outcome and what you learned "
     "about working with others."),
    ("Tell me about a time you failed or made a mistake. What did you learn?", "medium",
     STAR[:1] + ["mistake|failed|failure|went wrong|error|missed", "own|responsibility|my fault|i should have|accountable|accountability",
                 "fix|recover|corrected|made up|resolved", REFLECT],
     "Pick a real, moderate mistake, take ownership rather than blaming others, explain what you did to fix or limit the "
     "damage, and focus on the concrete lesson and how you've applied it since."),
    ("How do you handle tight deadlines or multiple competing priorities?", "easy",
     ["prioritize|prioritise|priority|most important|urgent", "plan|break down|schedule|list|timeline|estimate",
      "communicate|inform|update|stakeholders|ask for help|flag early", "focus|time management|avoid distractions",
      "example|for instance|once|during|last semester|when i"],
     "Show a method: list and prioritise tasks by impact and urgency, break work into steps with a timeline, communicate "
     "early if something will slip, and back it up with a short real example where it worked."),
    ("Why do you want to work in software engineering / this role?", "easy",
     ["enjoy|passion|interested|love|excited", "build|solve problems|create|impact|users",
      "experience|project|internship|when i", "learn|grow|improve|skills", "company|team|role|product"],
     "Connect genuine motivation to evidence: what you enjoy (building things people use, solving problems), a moment from "
     "a project or internship that confirmed it, and what you hope to learn and contribute in this specific role or company."),
    ("What are your strengths and weaknesses?", "easy",
     ["strength|good at|strong", "weakness|improve|working on|struggle",
      "example|for instance|when i|in my project|once", "steps|improving|practice|course|feedback|habit", "relevant|role|team"],
     "Give one or two strengths backed by a concrete example, and one real (not disguised-strength) weakness together with "
     "the specific steps you're taking to improve it."),
    ("Describe a time you had to learn a new technology quickly.", "medium",
     STAR[:1] + ["learn|new technology|new framework|never used|unfamiliar", "documentation|tutorial|course|docs|practice|small project|asked",
                 "applied|used it|built|shipped|delivered", STAR[3]],
     "Explain the situation and why you needed the technology, how you learned it efficiently (docs, a small prototype, "
     "asking others), how you applied it in the real task, and the result."),
    ("Tell me about a time you took initiative or led something.", "medium",
     STAR[:1] + ["initiative|took the lead|led|volunteered|proposed|started", "team|others|members|organised|organized|coordinated",
                 STAR[2], STAR[3]],
     "Describe something you started or led without being asked, how you brought others along, the concrete actions you "
     "took, and the outcome — ideally with a number (time saved, users, grade, bugs fixed)."),
    ("Where do you see yourself in five years?", "easy",
     ["grow|growth|learn|develop", "skills|expertise|specialize|specialise|deeper", "responsibility|lead|mentor|ownership",
      "company|team|role|contribute", "goal|aim|hope|plan"],
     "Show ambition that fits the role: growing deep expertise in an area, taking on more ownership or mentoring, and "
     "contributing to the team's goals — without sounding like you plan to leave soon."),
    ("How do you receive and act on feedback?", "easy",
     ["feedback|criticism|review|comments", "listen|open|welcome|appreciate", "ask|clarify|understand",
      "act|change|improve|applied|implemented", "example|once|code review|when i|my mentor"],
     "Say you welcome feedback, listen without being defensive, ask questions to understand it, and act on it — backed by a "
     "specific example such as code-review comments that changed how you write code."),
    ("Describe a situation where you had to explain a technical concept to a non-technical person.", "medium",
     STAR[:1] + ["simple|simplify|analogy|example|without jargon|plain language", "understand|audience|their level|check|questions",
                 STAR[3]],
     "Describe who you were explaining to and why, how you adapted — an analogy, avoiding jargon, visuals — how you checked "
     "they understood, and what happened as a result."),
]

project_templates = [
    ("proj-walk", "easy", "Walk me through your project \"{title}\". What problem did it solve, and what was your role?",
     ["problem|goal|purpose|needed|users|built it to", "my role|i built|i designed|i developed|i was responsible|i implemented|i worked on",
      "{tech}", "architecture|components|frontend|backend|database|api|flow",
      "result|outcome|impact|users|accuracy|performance|learned"],
     "A strong answer explains the problem and who it was for, your specific contribution (not just the team's), the main "
     "components and technologies ({tech}) and how they fit together, and a concrete result or what you learned."),
    ("proj-tech", "medium", "In \"{title}\", why did you choose {tech_first}? What alternatives did you consider?",
     ["{tech_first}", "alternative|instead|compared|other options|considered|versus|vs",
      "trade-off|trade off|pros and cons|advantage|disadvantage|downside",
      "requirement|because|needed|performance|easy|familiar|ecosystem|scalab|cost"],
     "Explain the requirement that drove the choice, name at least one realistic alternative, compare them honestly "
     "(performance, ease of use, ecosystem, cost, team familiarity) and admit any downside you accepted."),
    ("proj-challenge", "medium", "What was the hardest technical challenge you faced in \"{title}\", and how did you solve it?",
     ["challenge|problem|difficult|hard|issue|bug", "investigate|debug|research|tried|experiment|analyzed|analysed|analysis",
      "solution|solved|fixed|resolved|implemented|changed", "result|outcome|worked|improved|faster|reduced",
      REFLECT],
     "Name one specific challenge, explain why it was hard, how you investigated and what you tried, the solution you "
     "chose and why, the result, and what you would do differently."),
    ("proj-scale", "hard", "If \"{title}\" suddenly had 100x more users, what would break first and how would you fix it?",
     ["bottleneck|break|slow|overload|limit", "database|index|query|replica|shard",
      "cache|caching|redis|cdn", "load balancer|horizontal|more servers|scale out|autoscaling",
      "monitor|metrics|logging|load test|measure"],
     "Identify the likely bottleneck for this project (often the database or a synchronous call), then propose fixes: "
     "indexing and caching, read replicas, stateless servers behind a load balancer, background queues — and say you'd "
     "measure with monitoring and load tests first."),
    ("proj-test", "medium", "How did you test \"{title}\", and how did you make sure it worked correctly?",
     ["unit test|unit tests|pytest|junit|jest", "integration|end-to-end|e2e|api test", "edge case|corner case|invalid input|error handling",
      "manual|user testing|feedback|demo", "bug|found|fixed|ci|automated"],
     "Describe the kinds of tests you used (unit, integration or end-to-end, manual checks), which edge cases you covered, "
     "a bug testing caught, and how you'd improve the test setup (automation/CI)."),
    ("proj-improve", "easy", "If you rebuilt \"{title}\" today, what would you do differently?",
     ["differently|improve|change|refactor|redo", "design|architecture|structure|code quality",
      "test|documentation|security|performance", "because|learned|since|realised|realized", "feature|users|feedback"],
     "Show reflection: name concrete changes (architecture, testing, security, performance or a feature), explain why — what "
     "you learned since — and how it would help users or maintainability."),
]

internship_templates = [
    ("int-walk", "easy", "Tell me about your internship at {company} as {role}. What did you work on?",
     ["team|project|product|company", "my role|i worked on|i built|i was responsible|my task|i developed",
      "{tech}", "result|impact|delivered|shipped|improved|used by", "learned|learnt|lesson|skill"],
     "Explain the team and product, your specific responsibilities and what you built, the technologies you used ({tech}), "
     "a concrete result, and what you learned."),
    ("int-learn", "easy", "What is the most valuable thing you learned during your internship at {company}?",
     ["learned|learnt|lesson|realised|realized", "example|when|project|task|situation", "code review|best practice|team|process|production",
      "apply|since then|now i|changed how", "why|because|important|valuable"],
     "Pick one specific lesson (technical or professional), tell the short story of how you learned it, and show how you've "
     "applied it since."),
    ("int-collab", "medium", "Describe how you collaborated with your team during your internship at {company}.",
     ["team|mentor|manager|colleagues|engineers", "communicate|communicated|communication|standup|meeting|slack|update|sync",
      "code review|pull request|pr|feedback", "tools|git|jira|agile|sprint", "result|delivered|helped|outcome"],
     "Explain how the team worked (stand-ups, sprints, code reviews, tools), how you communicated progress and asked for "
     "help, a moment where collaboration mattered, and the outcome."),
    ("int-challenge", "medium", "What was a difficult task during your internship at {company}, and how did you handle it?",
     STAR[:1] + ["difficult|challenge|hard|unfamiliar|problem", "asked|mentor|research|documentation|debug|broke it down",
                 STAR[3], REFLECT],
     "Use STAR: the task, why it was difficult, the steps you took (research, asking your mentor, breaking it down), the "
     "result and what you learned."),
]

skill_templates = [
    ("skill-used", "easy", "Your resume lists {skill}. Tell me about a time you used it in a real project.",
     ["{skill}", "project|built|developed|internship|assignment", "feature|implemented|used it to|for the",
      "challenge|problem|difficult|learned", "result|worked|outcome|improved"],
     "Name the project, what you used {skill} for specifically, a challenge you hit with it and how you solved it, and the "
     "result — interviewers want evidence that the skill on your resume is real."),
    ("skill-depth", "medium", "What are the strengths and limitations of {skill}? When would you not use it?",
     ["{skill}", "strength|advantage|good at|pros|benefit", "limitation|disadvantage|drawback|cons|weakness|not suitable",
      "alternative|instead|another|other", "when|use case|situation|depends"],
     "Show depth: what {skill} is good at and why, its real limitations, a situation where you'd pick an alternative "
     "(and which one), and how you decide."),
]


if __name__ == "__main__":
    out = {
        "behavioral": [{"id": f"bh{i + 1:02d}", "topic": "Behavioral", "type": "short_answer", "difficulty": d,
                        "prompt": p, "keywords": k, "ideal_answer": ideal} for i, (p, d, k, ideal) in enumerate(behavioral)],
        "project_templates": [{"tid": t, "difficulty": d, "prompt": p, "keywords": k, "ideal_answer": ideal}
                              for t, d, p, k, ideal in project_templates],
        "internship_templates": [{"tid": t, "difficulty": d, "prompt": p, "keywords": k, "ideal_answer": ideal}
                                 for t, d, p, k, ideal in internship_templates],
        "skill_templates": [{"tid": t, "difficulty": d, "prompt": p, "keywords": k, "ideal_answer": ideal}
                            for t, d, p, k, ideal in skill_templates],
    }
    json.dump(out, open(sys.argv[1], "w"), indent=1, ensure_ascii=False)
    print({k: len(v) for k, v in out.items()})
