import { Link } from "react-router-dom";
import { LESSONS } from "../data/lessons";
import "../styles/Learn.css";

const MODULE_COLORS = ["#399cff", "#20d88a", "#ff963d", "#a78bfa", "#f472b6", "#34d399", "#fb923c", "#60a5fa"];

export default function Learn() {
  return (
    <div className="learn-page page-content">
      <div className="learn-hero">
        <div className="learn-hero-badge">ORBITGUARD ACADEMY</div>
        <h1>Learn the Science of Orbital Awareness</h1>
        <p>
          Eight structured modules covering everything from orbital mechanics to
          real-world conjunction analysis — explained for engineering students
          and space enthusiasts.
        </p>
        <div className="learn-disclaimer">
          ⚠ OrbitGuard is an educational prototype. It is not an operational
          collision-avoidance authority and should not be used for safety-critical decisions.
        </div>
      </div>

      <section className="learn-modules">
        <h2>Learning Modules</h2>
        <div className="module-grid">
          {LESSONS.map((lesson, i) => (
            <Link
              key={lesson.id}
              to={`/learn/${lesson.id}`}
              className="module-card"
              style={{ "--accent": MODULE_COLORS[i % MODULE_COLORS.length] }}
            >
              <div className="module-emoji">{lesson.emoji}</div>
              <div className="module-num">MODULE {lesson.module}</div>
              <h3>{lesson.title}</h3>
              <p>{lesson.summary}</p>
              <div className="module-footer">
                <span>{lesson.quiz.length} quiz questions</span>
                <span className="module-cta">Start →</span>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section className="learn-explore">
        <h2>Explore the Application</h2>
        <div className="explore-links">
          <Link to="/" className="explore-link">
            <span>🌍</span>
            <strong>Live Dashboard</strong>
            <small>View current satellite positions</small>
          </Link>
          <Link to="/orbital-map" className="explore-link">
            <span>🔭</span>
            <strong>Orbital Map</strong>
            <small>3D globe visualization</small>
          </Link>
          <Link to="/conjunctions" className="explore-link">
            <span>⚠️</span>
            <strong>Conjunctions</strong>
            <small>Close approach screening</small>
          </Link>
          <Link to="/objects" className="explore-link">
            <span>📡</span>
            <strong>Objects</strong>
            <small>Tracked satellite catalog</small>
          </Link>
        </div>
      </section>

      <section className="learn-about">
        <h2>Why Space Situational Awareness Matters</h2>
        <p>
          More than 27,000 human-made objects orbit Earth right now. Each active
          satellite depends on accurate tracking to avoid collisions with debris
          travelling at over 7 km/s. Understanding how orbital mechanics, TLE
          data, and propagation models work empowers the next generation of
          aerospace engineers to make sense of this increasingly crowded
          environment.
        </p>
        <p>
          These lessons use real orbital data fetched from CelesTrak and
          propagated with the same SGP4 model used by professional tracking
          systems — so what you see is connected to real physics, not animation.
        </p>
      </section>
    </div>
  );
}

