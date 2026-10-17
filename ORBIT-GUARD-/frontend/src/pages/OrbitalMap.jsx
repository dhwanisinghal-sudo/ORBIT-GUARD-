import SpaceScene from "../components/SpaceScene";

export default function OrbitalMap() {
  return (
    <main className="page">

      <div className="page-header">
        <div>
          <h2>Orbital Map</h2>
          <p>
            Live visualization of tracked orbital objects
          </p>
        </div>

        <div className="page-status">
          ● LIVE DATA
        </div>
      </div>

      <div className="full-map">
        <SpaceScene />

        <div className="map-overlay">
          <span>CELESTRAK / SGP4</span>
          <span>REAL-TIME POSITION DATA</span>
        </div>
      </div>

    </main>
  );
}