import './Navbar.css';

export default function Navbar() {
  return (
    <header className="nav">
      <div className="container nav-inner">
        <a href="#top" className="nav-logo">
          <span className="nav-logo-mark" aria-hidden="true" />
          Prepwise
        </a>
        <nav className="nav-links">
          <a href="#pipeline">How it works</a>
          <a href="#dashboard">Dashboard</a>
          <a href="#upload">Upload resume</a>
        </nav>
        <a href="#upload" className="btn btn-primary nav-cta">Get started</a>
      </div>
    </header>
  );
}
