import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getObject, getTrajectory } from "../api";

export default function ObjectDetails() {
  const { noradId } = useParams();

  const [object, setObject] = useState(null);
  const [trajectory, setTrajectory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadDetails() {
      try {
        setLoading(true);

        const [objectData, trajectoryData] = await Promise.all([
          getObject(noradId),
          getTrajectory(noradId),
        ]);

        setObject(objectData);
        setTrajectory(trajectoryData.trajectory);
      } catch (err) {
        console.error(err);
        setError("Unable to load object details.");
      } finally {
        setLoading(false);
      }
    }

    loadDetails();
  }, [noradId]);

  if (loading) {
    return (
      <main className="page">
        <div className="content-card">
          <h2>Loading object...</h2>
        </div>
      </main>
    );
  }

  if (error || !object) {
    return (
      <main className="page">
        <div className="content-card">
          <h2>Object Not Available</h2>
          <p>{error}</p>

          <Link to="/objects">
            ← BACK TO OBJECTS
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="page">

      <div className="page-header">

        <div>
          <h2>{object.name}</h2>

          <p>
            NORAD ID: {object.norad_id}
          </p>
        </div>

        <div className="page-status">
          ● LIVE DATA
        </div>

      </div>

      <div className="details-grid">

        <div className="content-card">
          <span className="card-label">ALTITUDE</span>
          <strong className="big-value">
            {object.altitude_km} km
          </strong>
        </div>

        <div className="content-card">
          <span className="card-label">TIMESTAMP</span>
          <strong className="big-value">
            {new Date(object.timestamp_utc).toLocaleTimeString()}
          </strong>
        </div>

        <div className="content-card">

          <span className="card-label">
            POSITION
          </span>

          <p>X: {object.position_km.x} km</p>
          <p>Y: {object.position_km.y} km</p>
          <p>Z: {object.position_km.z} km</p>

        </div>

        <div className="content-card">

          <span className="card-label">
            VELOCITY
          </span>

          <p>X: {object.velocity_km_s.x} km/s</p>
          <p>Y: {object.velocity_km_s.y} km/s</p>
          <p>Z: {object.velocity_km_s.z} km/s</p>

        </div>

      </div>

      <div className="content-card">

        <h3>TRAJECTORY</h3>

        <p>
          Predicted positions from the SGP4 propagation model.
        </p>

        <div className="trajectory-table-wrapper">

          <table className="object-table">

            <thead>
              <tr>
                <th>TIME AHEAD</th>
                <th>ALTITUDE</th>
                <th>X</th>
                <th>Y</th>
                <th>Z</th>
              </tr>
            </thead>

            <tbody>

              {trajectory.map((point, index) => (
                <tr key={index}>

                  <td>
                    {point.hours_from_now} hours
                  </td>

                  <td>
                    {point.altitude_km} km
                  </td>

                  <td>
                    {point.position_km.x} km
                  </td>

                  <td>
                    {point.position_km.y} km
                  </td>

                  <td>
                    {point.position_km.z} km
                  </td>

                </tr>
              ))}

            </tbody>

          </table>

        </div>

      </div>

      <Link
        className="back-link"
        to="/objects"
      >
        ← BACK TO OBJECTS
      </Link>

    </main>
  );
}