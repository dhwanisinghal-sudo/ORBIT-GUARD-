
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, LockKeyhole, Mail, Orbit } from "lucide-react";
import { loginUser } from "../api";
import "./Auth.css";

function Login({ onAuthSuccess }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const result = await loginUser({
        email: email.trim(),
        password,
      });

      onAuthSuccess(result.user);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message || "Unable to log in. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-stars" aria-hidden="true" />

      <Link to="/login" className="auth-brand">
        <span className="auth-brand-icon"><Orbit size={22} /></span>
        <span>
          <strong>ORBITGUARD</strong>
          <small>SPACE SITUATIONAL AWARENESS</small>
        </span>
      </Link>

      <section className="auth-card">
        <div className="auth-eyebrow">WELCOME BACK</div>
        <h1>Sign in to OrbitGuard</h1>
        <p className="auth-description">
          Continue exploring orbital data and satellite conjunctions.
        </p>

        <form onSubmit={handleSubmit}>
          <label htmlFor="login-email">Email address</label>
          <div className="auth-input-wrap">
            <Mail size={18} aria-hidden="true" />
            <input
              id="login-email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
            />
          </div>

          <label htmlFor="login-password">Password</label>
          <div className="auth-input-wrap">
            <LockKeyhole size={18} aria-hidden="true" />
            <input
              id="login-password"
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          {error && <div className="auth-error" role="alert">{error}</div>}

          <button className="auth-submit" type="submit" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
            {!loading && <ArrowRight size={18} />}
          </button>
        </form>

        <p className="auth-switch">
          New to OrbitGuard? <Link to="/register">Create an account</Link>
        </p>
      </section>

      <footer className="auth-footer">
        ORBITGUARD · EDUCATION · ORBITAL MONITORING
      </footer>
    </main>
  );
}

export default Login;
