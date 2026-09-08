import { useEffect, useState } from 'react';
import './DashboardMockup.css';

const TOPICS = [
  { name: 'Data structures', score: 82, tone: 'growth' },
  { name: 'Operating systems', score: 64, tone: 'accent' },
  { name: 'DBMS', score: 41, tone: 'warn' },
  { name: 'System design', score: 55, tone: 'accent' },
];

export default function DashboardMockup() {
  const [animate, setAnimate] = useState(false);

  useEffect(() => {
    const id = setTimeout(() => setAnimate(true), 250);
    return () => clearTimeout(id);
  }, []);

  return (
    <div className="dash card">
      <div className="dash-header">
        <div className="dash-who">
          <span className="dash-avatar">AR</span>
          <div>
            <p className="dash-eyebrow">Skill proficiency</p>
            <h3 className="dash-title">Aisha R.</h3>
          </div>
        </div>
        <span className="dash-tag dash-tag-warn">1 weak area</span>
      </div>

      <div className="dash-rows">
        {TOPICS.map((topic) => (
          <div className="dash-row" key={topic.name}>
            <div className="dash-row-labels">
              <span>{topic.name}</span>
              <span className="dash-row-score">{topic.score}%</span>
            </div>
            <div className="dash-track">
              <div
                className={`dash-fill dash-fill-${topic.tone}`}
                style={{ width: animate ? `${topic.score}%` : '0%' }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="dash-recommend">
        <p className="dash-recommend-label">Recommended next</p>
        <div className="dash-chips">
          <span className="dash-chip">Normalization &amp; joins</span>
          <span className="dash-chip">Transaction isolation</span>
        </div>
      </div>
    </div>
  );
}
