import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import RiskOverview from "../components/RiskOverview";

import SpaceScene from "../components/SpaceScene";
import { getObjects, getConjunctions } from "../api";

const TIME_RANGES = ["LIVE", "1H", "6H", "24H", "48H"];

export default function Overview() {
  const [activeRange, setActiveRange] = useState("LIVE");
  const [stats, setStats] = useState(null);
  const [now, setNow] = useState(new Date());

  // Live clock
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Load real stats
  useEffect(() => {
    let active = true;
    Promise.allSettled([
      getObjects("stations", 100),
      getConjunctions("stations", 100, 5),
    ]).then(([objRes, conjRes]) => {
      if (!active) return;
      const objCount =
        objRes.status === "fulfilled" ? objRes.value.count ?? objRes.value.objects?.length ?? "—" : "—";
      const conjCount =
        conjRes.status === "fulfilled" ? conjRes.value.count ?? "—" : "—";
      setStats({ objCount, conjCount });
    });
    return () => { active = false; };
  }, []);

  const utcStr = now.toISOString().replace("T", " ").slice(0, 19) + " UTC";

  return (
    <main className="dashboard">
      <div className="top-bar">
        <div className="time-controls">
          {TIME_RANGES.map((range) => (
            <button
              key={range}
              className={activeRange === range ? "selected" : ""}
              onClick={() => setActiveRange(range)}
              title={
                range === "LIVE"
                  ? "Current propagated positions"
                  : `Propagated positions offset by ${range} (SGP4 prediction, not historical observation)`
              }
            >
              {range}
            </button>
          ))}
        </div>
        <span className="timestamp">{utcStr}</span>
        {activeRange !== "LIVE" && (
          <span className="range-note">
            ⚠ Showing SGP4-propagated prediction · not observed historical data
          </span>
        )}
      </div>

      <div className="main-grid">
        <div className="orbital-area">
          <SpaceScene timeRange={activeRange} />
          <div className="map-label">ORBITAL MAP · SELECT A SATELLITE</div>
        </div>

        <aside className="sidebar">
          <RiskOverview />


          <section style={{ marginTop: 20 }}>
            <div className="section-title">QUICK LINKS</div>
            <Link to="/learn" className="quick-learn-link">
              📚 Open Academy — Learn how OrbitGuard works
            </Link>
          </section>
        </aside>
      </div>

      <footer className="stats-bar">
        <div>
          <span>OBJECTS TRACKED</span>
          <strong>{stats?.objCount ?? "—"}</strong>
        </div>
        <div>
          <span>ACTIVE CONJUNCTIONS</span>
          <strong>{stats?.conjCount ?? "—"}</strong>
        </div>
        <div>
          <span>DATA SOURCE</span>
          <strong>CELESTRAK</strong>
        </div>
        <div>
          <span>PROPAGATOR</span>
          <strong>SGP4</strong>
        </div>
        <div>
          <span>LAST UPDATE</span>
          <strong>{activeRange === "LIVE" ? "LIVE" : activeRange + " PRED"}</strong>
        </div>
      </footer>
    </main>
  );
}