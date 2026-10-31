import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getObject, getWhatIf } from "../api";

export default function ConjunctionAnalysis() {
  const { object1Id, object2Id } = useParams();

  const [object1, setObject1] = useState(null);
  const [object2, setObject2] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [delta, setDelta] = useState(1);
  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadAnalysis() {
      try {
        setLoading(true);
        const [first, second, result] = await Promise.all([
          getObject(object1Id),
          getObject(object2Id),
          getWhatIf(object1Id, object2Id, 1),
        ]);
        setObject1(first);
        setObject2(second);
        setAnalysis(result);
      } catch (err) {
        console.error(err);
        setError("Unable to load analysis.");
      } finally {
        setLoading(false);
      }
    }
    loadAnalysis();
  }, [object1Id, object2Id]);

  async function runSimulation() {
    try {
      setSimulating(true);
      setError("");
      const result = await getWhatIf(object1Id, object2Id, Number(delta));
      setAnalysis(result);
    } catch (err) {
      console.error(err);
      setError("Simulation failed.");
    } finally {
      setSimulating(false);
    }
  }

  if (loading) {
    return (
      <main className="page">
        <div className="content-card">
          <h2>Loading analysis...</h2>
        </div>
      </main>
    );
  }

  if (error || !analysis) {
    return (
      <main className="page">
        <div className="content-card">
          <h2>Analysis Error</h2>
          <p>{error || "No analysis data available."}</p>
          <Link to="/conjunctions">← BACK TO CONJUNCTIONS</Link>
        </div>
      </main>
    );
  }

  const beforeDist = analysis.before?.distance_km ?? analysis.before?.miss_distance_km ?? "—";
  const beforeRisk = analysis.before?.risk_level ?? "—";
  const afterDist = analysis.after?.distance_km ?? analysis.after?.miss_distance_km ?? "—";
  const afterRisk = analysis.after?.risk_level ?? "—";

  return (
    <main className="page">
      <div className="page-header">
        <div>
          <h2>Conjunction Analysis</h2>
          <p>
            {object1?.name || "Object 1"} ↔ {object2?.name || "Object 2"}
          </p>
        </div>
        <div className="page-status">● LIVE DATA</div>
      </div>

      <div className="details-grid">
        <div className="content-card">
          <span className="card-label">OBJECT 1</span>
          <h3>{object1?.name || "Unknown"}</h3>
          <p>NORAD ID: {object1?.norad_id ?? "—"}</p>
          <p>Altitude: {object1?.altitude_km != null ? `${object1.altitude_km} km` : "—"}</p>
        </div>

        <div className="content-card">
          <span className="card-label">OBJECT 2</span>
          <h3>{object2?.name || "Unknown"}</h3>
          <p>NORAD ID: {object2?.norad_id ?? "—"}</p>
          <p>Altitude: {object2?.altitude_km != null ? `${object2.altitude_km} km` : "—"}</p>
        </div>
      </div>

      {analysis.scenario?.co_located_at_start && (
        <div className="content-card">
          <h3>⚠ CO-LOCATED / DOCKED OBJECTS</h3>
          <p>
            These objects start co-located ({analysis.scenario.initial_separation_km != null ? `${analysis.scenario.initial_separation_km} km` : "~0 km"} apart, {analysis.scenario.initial_relative_speed_km_s != null ? `${analysis.scenario.initial_relative_speed_km_s} km/s` : "0 km/s"} relative speed), typically docked or sharing the same orbit. Initial distance cannot change instantly after a velocity maneuver. Check post-burn separation below to observe drift separation over time.
          </p>
        </div>
      )}

      {analysis.warnings?.length > 0 && (
        <div className="content-card">
          <h3>⚠ OPERATIONAL WARNINGS</h3>
          {analysis.warnings.map((w, idx) => (
            <p key={idx} style={{ margin: "6px 0" }}>⚠ {w}</p>
          ))}
        </div>
      )}

      <div className="content-card">
        <h3>CURRENT CONJUNCTION</h3>
        <div className="analysis-metrics">
          <div>
            <span>CURRENT DISTANCE</span>
            <strong>{beforeDist !== "—" ? `${beforeDist} km` : "—"}</strong>
          </div>
          <div>
            <span>CURRENT RISK</span>
            <strong className={`risk-text ${String(beforeRisk).toLowerCase()}`}>
              {beforeRisk}
            </strong>
          </div>
        </div>
      </div>

      <div className="content-card">
        <h3>WHAT-IF MANEUVER</h3>
        <p>
          Apply an along-track burn to Object 1 and compare the separation before and after.
        </p>

        <div className="maneuver-controls">
          <label>
            ALONG-TRACK ΔV
            <input
              type="number"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
            />
            <span>m/s</span>
          </label>

          <button
            className="analysis-button"
            onClick={runSimulation}
            disabled={simulating}
          >
            {simulating ? "SIMULATING..." : "RUN SIMULATION"}
          </button>
        </div>

        <div className="analysis-metrics">
          <div>
            <span>BEFORE</span>
            <strong>{beforeDist !== "—" ? `${beforeDist} km` : "—"}</strong>
          </div>
          <div>
            <span>AFTER</span>
            <strong>{afterDist !== "—" ? `${afterDist} km` : "—"}</strong>
          </div>
          <div>
            <span>RISK AFTER</span>
            <strong className={`risk-text ${String(afterRisk).toLowerCase()}`}>
              {afterRisk}
            </strong>
          </div>
        </div>

        {analysis.post_burn_separation_km && (
          <div style={{ marginTop: "24px" }}>
            <h4 style={{ margin: "0 0 12px 0", fontSize: "18px", color: "var(--text-secondary)" }}>
              POST-BURN SEPARATION
            </h4>
            <div className="analysis-metrics">
              <div>
                <span>MAX SEPARATION (BEFORE BURN)</span>
                <strong>
                  {analysis.post_burn_separation_km.before?.max != null
                    ? `${analysis.post_burn_separation_km.before.max} km`
                    : "—"}
                </strong>
                {analysis.post_burn_separation_km.before?.at_window_end != null && (
                  <span style={{ marginTop: "6px", fontSize: "14px" }}>
                    End of window: {analysis.post_burn_separation_km.before.at_window_end} km
                  </span>
                )}
              </div>
              <div>
                <span>MAX SEPARATION (AFTER BURN)</span>
                <strong>
                  {analysis.post_burn_separation_km.after?.max != null
                    ? `${analysis.post_burn_separation_km.after.max} km`
                    : "—"}
                </strong>
                {analysis.post_burn_separation_km.after?.at_window_end != null && (
                  <span style={{ marginTop: "6px", fontSize: "14px" }}>
                    End of window: {analysis.post_burn_separation_km.after.at_window_end} km
                  </span>
                )}
              </div>
            </div>
          </div>
        )}

        {analysis.closest_approaches?.after?.length > 1 && (
          <div style={{ marginTop: "24px" }}>
            <h4 style={{ margin: "0 0 12px 0", fontSize: "18px", color: "var(--text-secondary)" }}>
              LATER CLOSEST APPROACHES (AFTER BURN)
            </h4>
            <div style={{ display: "grid", gap: "8px" }}>
              {analysis.closest_approaches.after.map((a, idx) => (
                <div
                  key={idx}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "12px 16px",
                    background: "rgba(255, 255, 255, 0.02)",
                    border: "1px solid var(--border-color)",
                    borderRadius: "6px",
                    fontSize: "16px"
                  }}
                >
                  <span>TCA: {a.tca_utc || a.tca || "—"}</span>
                  <strong>{a.miss_distance_km ?? a.distance_km ?? "—"} km</strong>
                  {a.risk_level && (
                    <span className={`risk-text ${String(a.risk_level).toLowerCase()}`}>
                      {a.risk_level}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <Link className="back-link" to="/conjunctions">
        ← BACK TO CONJUNCTIONS
      </Link>
    </main>
  );
}
