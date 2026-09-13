import Header from "./components/Header";
import RiskOverview from "./components/RiskOverview";
import ConjunctionAlerts from "./components/ConjunctionAlerts";
import SpaceScene from "./components/SpaceScene";

import "./App.css";

function App() {
  return (
    <div className="app">

      <Header />

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
            2026-09-13 14:27:38 UTC
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
            <strong>2,483</strong>
          </div>

          <div>
            <span>ACTIVE CONJUNCTIONS</span>
            <strong>15</strong>
          </div>

          <div>
            <span>DEBRIS TRACKED</span>
            <strong>1,842</strong>
          </div>

          <div>
            <span>ACTIVE SATELLITES</span>
            <strong>641</strong>
          </div>

          <div>
            <span>LAST UPDATE</span>
            <strong>2 min ago</strong>
          </div>

        </footer>

      </main>

    </div>
  );
}

export default App;