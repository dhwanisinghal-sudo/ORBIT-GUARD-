import SpaceScene from "../components/SpaceScene";

export default function OrbitalMap() {
  return (
    <main className="orbital-map-page">
      <div className="orbital-map-toolbar">
        <div className="orbital-map-title">
          <h2>Orbital Map</h2>
          <p>Live 3D visualization of tracked orbital objects</p>
        </div>

        <div className="orbital-map-badges">
          <div className="page-status">● LIVE DATA</div>
          <div className="toolbar-tag">SGP4 PROPAGATED</div>
        </div>
      </div>

      <div className="full-map">
        <SpaceScene />

        <div className="map-overlay">
          <span>CELESTRAK / SGP4</span>
          <span>SGP4 PROPAGATED POSITIONS</span>
        </div>
      </div>
    </main>
  );
}