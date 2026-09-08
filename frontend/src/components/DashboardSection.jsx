import { useReveal } from '../hooks/useReveal';
import DashboardMockup from './DashboardMockup';
import './DashboardSection.css';

const POINTS = [
  'Per-topic proficiency, computed from every question you answer — not a one-time quiz.',
  'Weak areas are flagged automatically once a topic falls below your own baseline.',
  'Recommendations are specific topics and resources, not "practice more DBMS".',
];

export default function DashboardSection() {
  const textRef = useReveal();
  const visualRef = useReveal();

  return (
    <section id="dashboard" className="dashboard-section">
      <div className="container dashboard-grid">
        <div ref={visualRef} className="reveal blob-field">
          <span className="blob blob-accent" aria-hidden="true" />
          <DashboardMockup />
        </div>
        <div ref={textRef} className="reveal dashboard-copy">
          <h2 className="section-heading">A dashboard that updates as you go, not a static report.</h2>
          <ul className="dashboard-points">
            {POINTS.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
