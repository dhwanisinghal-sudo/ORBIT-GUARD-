import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getObject, getWhatIf } from "../api";

export default function ConjunctionAnalysis() {

  const { object1Id, object2Id } = useParams();

  const [object1, setObject1] = useState(null);
  const [object2, setObject2] = useState(null);

  const [analysis, setAnalysis] = useState(null);

  const [delta, setDelta] = useState(1);

  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {

    async function loadAnalysis() {

      try {

        setLoading(true);

        const [first, second, result] =
          await Promise.all([
            getObject(object1Id),
            getObject(object2Id),
            getWhatIf(
              object1Id,
              object2Id,
              1
            ),
          ]);

        setObject1(first);
        setObject2(second);
        setAnalysis(result);

      } catch (err) {

        console.error(err);
        setError("Unable to load analysis.");

      } finally {

        setLoading(false);

      }
    }

    loadAnalysis();

  }, [object1Id, object2Id]);


  async function runSimulation() {

    try {

      setSimulating(true);
      setError("");

      const result = await getWhatIf(
        object1Id,
        object2Id,
        Number(delta)
      );

      setAnalysis(result);

    } catch (err) {

      console.error(err);
      setError("Simulation failed.");

    } finally {

      setSimulating(false);

    }
  }


  if (loading) {

    return (
      <main className="page">

        <div className="content-card">

          <h2>
            Loading analysis...
          </h2>

        </div>

      </main>
    );
  }


  if (error || !analysis) {

    return (
      <main className="page">

        <div className="content-card">

          <h2>
            Analysis Error
          </h2>

          <p>
            {error}
          </p>

          <Link to="/conjunctions">
            ← BACK TO CONJUNCTIONS
          </Link>

        </div>

      </main>
    );
  }


  return (

    <main className="page">

      <div className="page-header">

        <div>

          <h2>
            Conjunction Analysis
          </h2>

          <p>
            {object1?.name} ↔ {object2?.name}
          </p>

        </div>

        <div className="page-status">
          ● LIVE DATA
        </div>

      </div>


      <div className="details-grid">

        <div className="content-card">

          <span className="card-label">
            OBJECT 1
          </span>

          <h3>
            {object1?.name}
          </h3>

          <p>
            NORAD ID: {object1?.norad_id}
          </p>

          <p>
            Altitude: {object1?.altitude_km} km
          </p>

        </div>


        <div className="content-card">

          <span className="card-label">
            OBJECT 2
          </span>

          <h3>
            {object2?.name}
          </h3>

          <p>
            NORAD ID: {object2?.norad_id}
          </p>

          <p>
            Altitude: {object2?.altitude_km} km
          </p>

        </div>

      </div>



      {analysis.scenario?.co_located_at_start && (
        <div className="content-card">
          <h3>⚠ CO-LOCATED OBJECTS</h3>
          <p>
            These objects are only {analysis.scenario.initial_separation_km} km
            apart with ~0 km/s relative speed (likely docked, or sharing the
            same orbital data). The closest approach is the starting instant,
            so a burn cannot change it. Use the drift numbers below, or pick a
            pair with a real future conjunction.
          </p>
        </div>
      )}

      <div className="content-card">

        <h3>
          CURRENT CONJUNCTION
        </h3>

        <div className="analysis-metrics">

          <div>
            <span>
              CURRENT DISTANCE
            </span>

            <strong>
              {analysis.before.distance_km} km
            </strong>
          </div>


          <div>
            <span>
              CURRENT RISK
            </span>

            <strong>
              {analysis.before.risk_level}
            </strong>
          </div>

        </div>

      </div>


      <div className="content-card">

        <h3>
          WHAT-IF MANEUVER
        </h3>

        <p>
          Apply a prograde burn to Object 1 and compare
          the closest approach before and after.
        </p>


        <div className="maneuver-controls">

          <label>

            ALONG-TRACK ΔV

            <input
              type="number"
              value={delta}
              onChange={(e) =>
                setDelta(e.target.value)
              }
            />

            <span>m/s</span>

          </label>


          <button
            className="analysis-button"
            onClick={runSimulation}
            disabled={simulating}
          >

            {simulating
              ? "SIMULATING..."
              : "RUN SIMULATION"}

          </button>

        </div>


        <div className="analysis-metrics">

          <div>

            <span>
              BEFORE
            </span>

            <strong>
              {analysis.before.distance_km} km
            </strong>

          </div>


          <div>

            <span>
              AFTER
            </span>

            <strong>
              {analysis.after.distance_km} km
            </strong>

          </div>


          <div>

            <span>
              RISK AFTER
            </span>

            <strong>
              {analysis.after.risk_level}
            </strong>

          </div>

        </div>


        {analysis.post_burn_separation_km && (
          <div className="analysis-metrics">
            <div>
              <span>MAX SEPARATION (NO BURN)</span>
              <strong>{analysis.post_burn_separation_km.before.max} km</strong>
            </div>
            <div>
              <span>MAX SEPARATION (AFTER BURN)</span>
              <strong>{analysis.post_burn_separation_km.after.max} km</strong>
            </div>
          </div>
        )}

        {analysis.closest_approaches?.after?.length > 1 && (
          <div>
            <p>CLOSEST APPROACHES AFTER BURN</p>
            <ul>
              {analysis.closest_approaches.after.map((a) => (
                <li key={a.tca_utc}>
                  {a.tca_utc} — {a.miss_distance_km} km
                </li>
              ))}
            </ul>
          </div>
        )}

        {analysis.warnings?.length > 0 && (
          <div>
            {analysis.warnings.map((w) => (
              <p key={w}>⚠ {w}</p>
            ))}
          </div>
        )}

      </div>


      <Link
        className="back-link"
        to="/conjunctions"
      >
        ← BACK TO CONJUNCTIONS
      </Link>

    </main>

  );
}