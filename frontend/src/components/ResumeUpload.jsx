import { useEffect, useRef, useState } from 'react';
import './ResumeUpload.css';

const EXTRACTED = [
  { label: 'Skills detected', value: 'Python, React, SQL, +6 more' },
  { label: 'Projects found', value: '3' },
  { label: 'CGPA', value: 'needs review' },
];

export default function ResumeUpload() {
  const [status, setStatus] = useState('idle'); // idle | dragging | parsing | done
  const [progress, setProgress] = useState(0);
  const [fileName, setFileName] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    if (status !== 'parsing') return undefined;
    const id = setInterval(() => {
      setProgress((p) => {
        if (p >= 100) {
          clearInterval(id);
          setStatus('done');
          return 100;
        }
        return p + 4;
      });
    }, 60);
    return () => clearInterval(id);
  }, [status]);

  function handleFile(name) {
    setFileName(name);
    setStatus('parsing');
  }

  function onDrop(e) {
    e.preventDefault();
    setStatus('idle');
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file.name);
  }

  function onPick(e) {
    const file = e.target.files?.[0];
    if (file) handleFile(file.name);
  }

  function reset() {
    setStatus('idle');
    setProgress(0);
    setFileName('');
  }

  return (
    <section id="upload">
      <div className="container upload-wrap">
        <h2 className="section-heading upload-heading">Upload your resume to see your profile take shape.</h2>
        <p className="section-sub upload-sub">
          PDF or DOCX. This preview parses nothing on our servers yet — it's a
          look at the interaction, not the finished pipeline.
        </p>

        <div
          className={`dropzone ${status === 'dragging' ? 'is-dragging' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setStatus('dragging'); }}
          onDragLeave={() => setStatus((s) => (s === 'dragging' ? 'idle' : s))}
          onDrop={onDrop}
        >
          {status === 'idle' || status === 'dragging' ? (
            <>
              <span className="dropzone-icon" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M10 13V3M10 3L5.5 7.5M10 3l4.5 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M3.5 14v1.5A1.5 1.5 0 0 0 5 17h10a1.5 1.5 0 0 0 1.5-1.5V14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <p className="dropzone-title">Drag your resume here</p>
              <p className="dropzone-sub">or</p>
              <button className="btn btn-ghost" onClick={() => inputRef.current?.click()}>
                Browse files
              </button>
              <input
                ref={inputRef}
                type="file"
                accept=".pdf,.doc,.docx"
                hidden
                onChange={onPick}
              />
            </>
          ) : (
            <div className="dropzone-progress">
              <p className="dropzone-filename">{fileName}</p>
              <div className="dropzone-track">
                <div className="dropzone-fill" style={{ width: `${progress}%` }} />
              </div>
              <p className="dropzone-status">
                {status === 'parsing' ? `Parsing your profile — ${progress}%` : 'Profile ready'}
              </p>
            </div>
          )}
        </div>

        {status === 'done' && (
          <div className="extracted card">
            {EXTRACTED.map((field) => (
              <div className="extracted-row" key={field.label}>
                <span className="extracted-label">{field.label}</span>
                <span className={`extracted-value ${field.value === 'needs review' ? 'is-review' : ''}`}>
                  {field.value}
                </span>
              </div>
            ))}
            <button className="btn btn-ghost extracted-reset" onClick={reset}>Try another file</button>
          </div>
        )}
      </div>
    </section>
  );
}
