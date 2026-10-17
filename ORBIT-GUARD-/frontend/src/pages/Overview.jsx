import RiskOverview from "../components/RiskOverview";
import ConjunctionAlerts from "../components/ConjunctionAlerts";
import SpaceScene from "../components/SpaceScene";

export default function Overview() {
  return (
    <main className="dashboard">

      <div className="top-bar">
        <div className="time-controls">
          <button className="selected">LIVE</button>
          <button>1H</button>
          <button>6H</button>
          <button>24H</button>
          <button>48H</button>
        </div>

        <span className="timestamp">
          {new Date().toISOString().replace("T", " ").slice(0, 19)} UTC
        </span>
      </div>

      <div className="main-grid">

        <div className="orbital-area">
          <SpaceScene />

          <div className="map-label">
            ORBITAL MAP
          </div>
        </div>

        <aside className="sidebar">

          <RiskOverview />

          <ConjunctionAlerts />

        </aside>

      </div>

      <footer className="stats-bar">

        <div>
          <span>OBJECTS TRACKED</span>
          <strong>—</strong>
        </div>

        <div>
          <span>ACTIVE CONJUNCTIONS</span>
          <strong>—</strong>
        </div>

        <div>
          <span>DEBRIS TRACKED</span>
          <strong>—</strong>
        </div>

        <div>
          <span>ACTIVE SATELLITES</span>
          <strong>—</strong>
        </div>

        <div>
          <span>LAST UPDATE</span>
          <strong>LIVE</strong>
        </div>

      </footer>

    </main>
  );
}