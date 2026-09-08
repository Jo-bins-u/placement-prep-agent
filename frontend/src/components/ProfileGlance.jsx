import { useEffect, useState } from 'react';
import './ProfileGlance.css';

// Point the fly-out animation "originates" from — roughly the resume
// page's bottom-right corner in stage coordinates.
const ORIGIN = { x: 150, y: 214 };

const CHIPS = [
  { name: 'Python', glyph: 'code', width: '88%', top: 28, left: 172, rot: -4 },
  { name: 'React', glyph: 'orbit', width: '70%', top: 78, left: 220, rot: 3 },
  { name: 'SQL', glyph: 'db', width: '80%', top: 132, left: 176, rot: -3 },
  { name: 'Data Structures', glyph: 'tree', width: '60%', top: 184, left: 224, rot: 4 },
  { name: 'DBMS', glyph: 'layers', width: '75%', top: 238, left: 180, rot: -2 },
];

function Glyph({ type }) {
  const common = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round' };
  switch (type) {
    case 'code':
      return (
        <svg viewBox="0 0 20 20" width="13" height="13" aria-hidden="true">
          <path d="M7 5 3 10l4 5M13 5l4 5-4 5" {...common} />
        </svg>
      );
    case 'orbit':
      return (
        <svg viewBox="0 0 20 20" width="13" height="13" aria-hidden="true">
          <circle cx="10" cy="10" r="1.7" fill="currentColor" stroke="none" />
          <ellipse cx="10" cy="10" rx="8" ry="3.1" fill="none" stroke="currentColor" strokeWidth="1.4" />
          <ellipse cx="10" cy="10" rx="8" ry="3.1" fill="none" stroke="currentColor" strokeWidth="1.4" transform="rotate(60 10 10)" />
        </svg>
      );
    case 'db':
      return (
        <svg viewBox="0 0 20 20" width="13" height="13" aria-hidden="true">
          <ellipse cx="10" cy="5" rx="6" ry="2.1" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <path d="M4 5v10c0 1.16 2.69 2.1 6 2.1s6-.94 6-2.1V5" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <path d="M4 10c0 1.16 2.69 2.1 6 2.1s6-.94 6-2.1" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      );
    case 'tree':
      return (
        <svg viewBox="0 0 20 20" width="13" height="13" aria-hidden="true">
          <circle cx="10" cy="4" r="1.7" fill="currentColor" stroke="none" />
          <circle cx="5" cy="15" r="1.7" fill="currentColor" stroke="none" />
          <circle cx="15" cy="15" r="1.7" fill="currentColor" stroke="none" />
          <path d="M10 6v3M10 9 5 13M10 9l5 4" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" />
        </svg>
      );
    case 'layers':
      return (
        <svg viewBox="0 0 20 20" width="13" height="13" aria-hidden="true">
          <path d="M10 3 3 7l7 4 7-4-7-4Z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
          <path d="M3 11l7 4 7-4" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
          <path d="M3 15l7 4 7-4" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
        </svg>
      );
    default:
      return null;
  }
}

export default function ProfileGlance() {
  const [phase, setPhase] = useState('scanning'); // scanning | extracted

  useEffect(() => {
    const id = setTimeout(() => setPhase('extracted'), 900);
    return () => clearTimeout(id);
  }, []);

  return (
    <div className="glance card">
      <p className="glance-label">From your resume</p>

      <div className="glance-stage">
        <span className={`stage-caption ${phase === 'extracted' ? 'is-in' : ''}`}>
          Extracted into your profile
        </span>

        <div className="glance-page">
          <div className="page-head">
            <span className="page-avatar" />
            <div className="page-head-lines">
              <span className="page-line-sm w-70" />
              <span className="page-line-sm w-45 muted" />
            </div>
          </div>

          <div className="page-body">
            {CHIPS.map((chip, i) => (
              <span
                key={chip.name}
                className={`page-line ${phase === 'extracted' ? 'is-done' : ''}`}
                style={{ width: chip.width, transitionDelay: `${i * 0.09 + 0.05}s` }}
              />
            ))}
          </div>

          {phase === 'scanning' && <div className="glance-scan" />}
        </div>

        {CHIPS.map((chip, i) => (
          <span
            key={chip.name}
            className={`glance-chip chip-${i % 4} ${phase === 'extracted' ? 'is-in' : ''}`}
            style={{
              top: chip.top,
              left: chip.left,
              '--fx': `${ORIGIN.x - chip.left}px`,
              '--fy': `${ORIGIN.y - chip.top}px`,
              '--r': `${chip.rot}deg`,
              animationDelay: `${i * 0.09}s`,
            }}
          >
            <Glyph type={chip.glyph} />
            {chip.name}
          </span>
        ))}
      </div>
    </div>
  );
}
