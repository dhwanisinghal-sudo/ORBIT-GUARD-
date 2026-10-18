import { Link } from "react-router-dom";
import "../styles/Landing.css";

export default function Landing() {
  return (
    <main className="landing">
      {/* NAV */}
      <nav className="landing-nav">
        <div className="landing-brand">
          <span className="landing-brand-icon">🛰️</span>
          <strong>ORBITGUARD</strong>
        </div>
        <div className="landing-nav-actions">
          <Link to="/login" className="landing-btn-ghost">Sign in</Link>
          <Link to="/register" className="landing-btn-primary">Create account</Link>
        </div>
      </nav>

      {/* HERO */}
      <section className="landing-hero">
        <div className="landing-hero-badge">OPEN EDUCATIONAL PLATFORM</div>
        <h1>
          Track satellites.<br />
          Understand orbital risk.<br />
          Learn the science.
        </h1>
        <p className="landing-hero-sub">
          OrbitGuard combines real CelesTrak TLE data, SGP4 orbital propagation,
          and interactive education to make space situational awareness accessible
          to engineering students.
        </p>
        <div className="landing-hero-ctas">
          <Link to="/register" className="landing-btn-primary large">Create Account</Link>
          <Link to="/landing#learn" className="landing-btn-ghost large">Start Learning</Link>
          <Link to="/login" className="landing-btn-ghost large">Explore Orbital Map</Link>
        </div>
        <p className="landing-disclaimer">
          ⚠ Educational prototype only — not an operational collision-avoidance authority.
        </p>
      </section>

      {/* HOW IT WORKS */}
      <section className="landing-flow" id="how">
        <h2>How OrbitGuard Works</h2>
        <div className="flow-steps">
          <div className="flow-step">
            <div className="flow-num">1</div>
            <h3>TLE Data</h3>
            <p>Real orbital element sets fetched from CelesTrak, sourced from the U.S. Space Surveillance Network.</p>
          </div>
          <div className="flow-arrow">→</div>
          <div className="flow-step">
            <div className="flow-num">2</div>
            <h3>SGP4 Propagation</h3>
            <p>Python sgp4 library computes 3D positions in the TEME frame from orbital elements and time.</p>
          </div>
          <div className="flow-arrow">→</div>
          <div className="flow-step">
            <div className="flow-num">3</div>
            <h3>3D Visualization</h3>
            <p>Three.js/React Three Fiber renders satellites on an interactive globe with orbit path previews.</p>
          </div>
          <div className="flow-arrow">→</div>
          <div className="flow-step">
            <div className="flow-num">4</div>
            <h3>Conjunction Screening</h3>
            <p>Distance-based screening identifies object pairs within configurable thresholds for risk review.</p>
          </div>
        </div>
      </section>

      {/* WHAT YOU'LL LEARN */}
      <section className="landing-learn" id="learn">
        <h2>What You'll Learn</h2>
        <p>Eight structured modules, from orbital basics to conjunction risk analysis:</p>
        <div className="landing-topics">
          {[
            ["🛰️", "Space Situational Awareness", "Why and how 27,000+ objects are tracked"],
            ["🌍", "Orbital Mechanics", "Gravity, velocity, altitude, orbital period"],
            ["🔄", "Orbit Types", "LEO, MEO, GEO, polar, and sun-synchronous"],
            ["📡", "TLE Format", "Reading NORAD catalog data and understanding data age"],
            ["📐", "SGP4 Propagation", "How positions are estimated from orbital elements"],
            ["💥", "Space Debris", "Sources, risks, mitigation, and the Kessler Syndrome"],
            ["⚠️", "Conjunction Analysis", "Closest approach, relative velocity, and risk assessment"],
            ["🖥️", "Using OrbitGuard", "How to interpret dashboard metrics and their limitations"],
          ].map(([emoji, title, desc]) => (
            <div key={title} className="landing-topic">
              <span>{emoji}</span>
              <div>
                <strong>{title}</strong>
                <p>{desc}</p>
              </div>
            </div>
          ))}
        </div>
        <Link to="/register" className="landing-btn-primary">
          Start Learning — Create a Free Account
        </Link>
      </section>

      {/* LIMITATION NOTICE */}
      <section className="landing-limits">
        <h2>Honest Limitations</h2>
        <ul>
          <li>OrbitGuard is an <strong>educational prototype</strong>, not an operational space surveillance system.</li>
          <li>Positions are SGP4 predictions from TLE data — not real-time radar observations.</li>
          <li>Conjunction alerts are distance-based screening categories, not validated collision probabilities.</li>
          <li>ML risk scores are illustrative; they are not validated against real conjunction events.</li>
          <li>OrbitGuard has no affiliation with ISRO, NASA, ESA, or any space agency.</li>
        </ul>
      </section>

      <footer className="landing-footer">
        ORBITGUARD · K.J. Somaiya College of Engineering · TY B.Tech WPL/FSDL Mini Project · 2026
      </footer>
    </main>
  );
}

