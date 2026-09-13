import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getConjunctions } from "../api";

export default function ConjunctionAlerts() {
  const [conjunctions, setConjunctions] = useState([]);

  useEffect(() => {
    async function loadAlerts() {
      try {
        const data = await getConjunctions("stations", 100, 5);
        setConjunctions(data.conjunctions.slice(0, 3));
      } catch (error) {
        console.error("Failed to load conjunction alerts:", error);
      }
    }

    loadAlerts();
  }, []);

  return (
    <section className="alerts-section">

      <div className="section-title">
        <span>TOP CONJUNCTION ALERTS</span>
      </div>

      <div className="alerts">

        {conjunctions.length === 0 && (
          <div className="alert-card">
            <p>No close approaches detected.</p>
          </div>
        )}

        {conjunctions.map((alert, index) => (
          <div className="alert-card" key={index}>

            <div className="alert-header">

              <span>
                {alert.object_1.name} ↔ {alert.object_2.name}
              </span>

              <span
                className={`risk-badge ${alert.risk_level.toLowerCase()}`}
              >
                {alert.risk_level}
              </span>

            </div>

            <div className="alert-details">

              <div>
                <small>MISS DISTANCE</small>
                <strong>
                  {alert.distance_km} km
                </strong>
              </div>

              <div>
                <small>REL. VELOCITY</small>
                <strong>
                  {alert.relative_velocity_km_s} km/s
                </strong>
              </div>

              <div>
                <small>NORAD PAIR</small>
                <strong>
                  {alert.object_1.norad_id} / {alert.object_2.norad_id}
                </strong>
              </div>

            </div>

            <Link
              className="analysis-button"
              to={`/conjunctions/${alert.object_1.norad_id}/${alert.object_2.norad_id}`}
            >
              VIEW ANALYSIS →
            </Link>

          </div>
        ))}

      </div>

    </section>
  );
}