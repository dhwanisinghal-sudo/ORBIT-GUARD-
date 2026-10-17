import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getObjects } from "../api";

export default function Objects() {
  const [objects, setObjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadObjects() {
      try {
        const data = await getObjects("stations", 100);
        setObjects(data.objects);
      } catch (err) {
        console.error(err);
        setError("Unable to load orbital objects.");
      } finally {
        setLoading(false);
      }
    }

    loadObjects();
  }, []);

  return (
    <main className="page">

      <div className="page-header">
        <div>
          <h2>Tracked Objects</h2>
          <p>
            Live orbital objects from CelesTrak and SGP4 propagation.
          </p>
        </div>

        <div className="page-status">
          ● LIVE DATA
        </div>
      </div>

      {loading && (
        <div className="content-card">
          <h3>LOADING ORBITAL DATA...</h3>
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

          <div className="object-summary">
            <span>OBJECTS TRACKED</span>
            <strong>{objects.length}</strong>
          </div>

          <div className="object-table-wrapper">

            <table className="object-table">

              <thead>
                <tr>
                  <th>OBJECT</th>
                  <th>NORAD ID</th>
                  <th>ALTITUDE</th>
                  <th>POSITION</th>
                  <th>VELOCITY</th>
                  <th></th>
                </tr>
              </thead>

              <tbody>

                {objects.map((object) => (
                  <tr key={object.norad_id}>

                    <td>
                      <strong>{object.name}</strong>
                    </td>

                    <td>
                      {object.norad_id}
                    </td>

                    <td>
                      {object.altitude_km} km
                    </td>

                    <td>
                      {object.position_km.x.toFixed(0)},
                      {" "}
                      {object.position_km.y.toFixed(0)},
                      {" "}
                      {object.position_km.z.toFixed(0)}
                      {" "}km
                    </td>

                    <td>
                      {Math.sqrt(
                        object.velocity_km_s.x ** 2 +
                        object.velocity_km_s.y ** 2 +
                        object.velocity_km_s.z ** 2
                      ).toFixed(2)}
                      {" "}km/s
                    </td>

                    <td>
                      <Link
                        className="view-button"
                        to={`/objects/${object.norad_id}`}
                      >
                        VIEW
                      </Link>
                    </td>

                  </tr>
                ))}

              </tbody>

            </table>

          </div>

        </div>
      )}

    </main>
  );
}