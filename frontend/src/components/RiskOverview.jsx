import { useEffect, useState } from "react";
import { getConjunctions } from "../api";

/**
 * RiskOverview: shows live risk summary from conjunction data.
 * Counts are derived from real backend data, not hardcoded.
 */
export default function RiskOverview() {
  const [counts, setCounts] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);

    getConjunctions("stations", 100, 100) // wide threshold to get all risk levels
      .then((data) => {
        if (!active) return;
        const conjunctions = data.conjunctions || [];
        const c = { Critical: 0, High: 0, Medium: 0, Low: 0 };
        for (const conj of conjunctions) {
          const lvl = conj.risk_level;
          if (lvl in c) c[lvl]++;
        }
        setCounts(c);
      })
      .catch(() => {
        if (active) setCounts(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => { active = false; };
  }, []);

  const risks = [
    { label: "Critical", key: "Critical", className: "critical" },
    { label: "High", key: "High", className: "high" },
    { label: "Medium", key: "Medium", className: "medium" },
    { label: "Low", key: "Low", className: "low" },
  ];

  return (
    <section className="risk-section">
      <div className="section-title">
        <span>RISK OVERVIEW</span>
        {!loading && counts && (
          <small className="risk-live-tag">LIVE DATA</small>
        )}
      </div>

      <div className="risk-list">
        {risks.map((risk) => (
          <div className={`risk-card ${risk.className}`} key={risk.label}>
            <div className="risk-name">
              <span className="risk-dot" />
              {risk.label}
            </div>
            <strong>
              {loading ? "…" : counts ? (counts[risk.key] ?? 0) : "—"}
            </strong>
          </div>
        ))}
      </div>

      {!loading && !counts && (
        <p className="risk-error-msg">
          Risk data unavailable — backend unreachable.
        </p>
      )}
    </section>
  );
}