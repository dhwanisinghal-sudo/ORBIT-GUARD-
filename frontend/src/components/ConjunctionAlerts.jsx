const alerts = [
  {
    objectA: "SAT-1042",
    objectB: "DEBRIS-7831",
    distance: "2.4 km",
    velocity: "7.4 km/s",
    time: "11h 32m",
    risk: "HIGH"
  },
  {
    objectA: "SAT-2218",
    objectB: "DEBRIS-1120",
    distance: "5.7 km",
    velocity: "6.1 km/s",
    time: "18h 44m",
    risk: "MEDIUM"
  },
  {
    objectA: "SAT-8897",
    objectB: "DEBRIS-4491",
    distance: "12.3 km",
    velocity: "5.8 km/s",
    time: "31h 07m",
    risk: "LOW"
  }
];

export default function ConjunctionAlerts() {
  return (
    <section className="alerts-section">

      <div className="section-title">
        <span>TOP CONJUNCTION ALERTS</span>
      </div>

      <div className="alerts">

        {alerts.map((alert, index) => (

          <div className="alert-card" key={index}>

            <div className="alert-header">
              <span>
                {alert.objectA} ↔ {alert.objectB}
              </span>

              <span
                className={`risk-badge ${alert.risk.toLowerCase()}`}
              >
                {alert.risk}
              </span>
            </div>

            <div className="alert-details">

              <div>
                <small>MISS DISTANCE</small>
                <strong>{alert.distance}</strong>
              </div>

              <div>
                <small>REL. VELOCITY</small>
                <strong>{alert.velocity}</strong>
              </div>

              <div>
                <small>TCA</small>
                <strong>{alert.time}</strong>
              </div>

            </div>

            <button className="analysis-button">
              VIEW ANALYSIS →
            </button>

          </div>

        ))}

      </div>

    </section>
  );
}