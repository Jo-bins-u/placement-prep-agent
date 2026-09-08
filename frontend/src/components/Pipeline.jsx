import { useReveal } from '../hooks/useReveal';
import './Pipeline.css';

const STEPS = [
  {
    n: '01',
    tone: 'primary',
    title: 'Parse your profile',
    body: 'Upload a resume and your academic record. We extract skills, projects, and coursework into a structured profile — no manual form-filling.',
  },
  {
    n: '02',
    tone: 'accent',
    title: 'Practice questions built for you',
    body: 'Questions are pulled from a curated bank and biased toward the topics your own projects and skills actually touch.',
  },
  {
    n: '03',
    tone: 'growth',
    title: 'Get evaluated, not just graded',
    body: 'Every answer is scored against a rubric or test cases, with specific feedback on what to fix — not just right or wrong.',
  },
  {
    n: '04',
    tone: 'warn',
    title: 'See exactly what to study next',
    body: 'Performance rolls up into per-topic proficiency, flags weak areas, and points you to the resources that close the gap.',
  },
];

export default function Pipeline() {
  const ref = useReveal();

  return (
    <section id="pipeline">
      <div className="container">
        <h2 className="section-heading">One profile. A preparation path built around it.</h2>
        <p className="section-sub">
          Most tools hand every student the same question bank. This one starts
          from what you've actually built and studied.
        </p>

        <div ref={ref} className="pipeline-grid reveal-stagger">
          {STEPS.map((step) => (
            <div className="pipeline-step" key={step.n}>
              <span className={`pipeline-n pipeline-n-${step.tone}`}>{step.n}</span>
              <h3 className="pipeline-title">{step.title}</h3>
              <p className="pipeline-body">{step.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
