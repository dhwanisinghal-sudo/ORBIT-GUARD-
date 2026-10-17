import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getConjunctions } from "../api";

export default function Conjunctions() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadConjunctions() {
      try {
        const result = await getConjunctions("stations", 100, 5);
        setData(result);
      } catch (err) {
        console.error(err);
        setError("Unable to load conjunction data.");
      } finally {
        setLoading(false);
      }
    }

    loadConjunctions();
  }, []);

  return (
    <main className="page">

      <div className="page-header">

        <div>
          <h2>Conjunctions</h2>
          <p>
            Detected close approaches between tracked orbital objects.
          </p>
        </div>

        <div className="page-status">
          ● LIVE DATA
        </div>

      </div>

      {loading && (
        <div className="content-card">
          <h3>LOADING CONJUNCTION DATA...</h3>
        </div>
      )}

      {error && (
        <div className="content-card">
          <h3>DATA ERROR</h3>
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && (
        <div className="content-card">

          <div className="conjunction-summary">
            <div>
              <span>OBJECTS CHECKED</span>
              <strong>{data.objects_checked}</strong>
            </div>

            <div>
              <span>CONJUNCTIONS</span>
              <strong>{data.count}</strong>
            </div>

            <div>
              <span>THRESHOLD</span>
              <strong>{data.threshold_km} km</strong>
            </div>
          </div>

          <h3>DETECTED CLOSE APPROACHES</h3>

          {data.conjunctions.length === 0 ? (
            <p>
              No conjunctions detected within the current threshold.
            </p>
          ) : (
            <div className="conjunction-list">

              {data.conjunctions.map((item, index) => (
                <div className="conjunction-row" key={index}>

                  <div>
                    <strong>
                      {item.object_1.name}
                    </strong>

                    <span>
                      ↕
                    </span>

                    <strong>
                      {item.object_2.name}
                    </strong>
                  </div>

                  <div>
                    <span>DISTANCE</span>
                    <strong>{item.distance_km} km</strong>
                  </div>

                  <div>
                    <span>REL. VELOCITY</span>
                    <strong>
                      {item.relative_velocity_km_s} km/s
                    </strong>
                  </div>

                  <div>
                    <span>RISK</span>
                    <strong className={
                      `risk-text ${item.risk_level.toLowerCase()}`
                    }>
                      {item.risk_level}
                    </strong>
                  </div>

                  <Link
                    className="analysis-button"
                    to={`/conjunctions/${item.object_1.norad_id}/${item.object_2.norad_id}`}
                  >
                    VIEW ANALYSIS →
                  </Link>

                </div>
              ))}

            </div>
          )}

        </div>
      )}

    </main>
  );
}