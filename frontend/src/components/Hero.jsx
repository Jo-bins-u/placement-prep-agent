import { useEffect, useState } from 'react';
import ProfileGlance from './ProfileGlance';
import './Hero.css';

export default function Hero() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  return (
    <section id="top" className="hero">
      <div className="container hero-grid">
        <div className={`hero-copy ${mounted ? 'is-in' : ''}`}>
          <span className="hero-kicker">For final-year students</span>
          <h1 className="hero-heading">
            Prepare for placements against your own profile, not a generic bank of questions.
          </h1>
          <p className="hero-sub">
            Upload your resume once. Get interview questions matched to your actual
            skills and projects, honest feedback on every answer, and a clear map
            of what to study next.
          </p>
          <div className="hero-actions">
            <a href="#upload" className="btn btn-primary">Upload your resume</a>
            <a href="#pipeline" className="btn btn-ghost">See how it works</a>
          </div>
        </div>
        <div className={`hero-visual blob-field ${mounted ? 'is-in' : ''}`}>
          <span className="blob blob-accent" aria-hidden="true" />
          <span className="blob blob-growth" aria-hidden="true" />
          <ProfileGlance />
        </div>
      </div>
    </section>
  );
}
