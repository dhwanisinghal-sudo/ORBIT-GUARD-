
import { useCallback, useEffect, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Line, OrbitControls, Stars } from "@react-three/drei";

import Earth from "./Earth";
import Satellite from "./Satellite";
import { getObjects, getTrajectory } from "../api";
import * as THREE from "three";

const EARTH_RADIUS = 6371;
const SCENE_RADIUS = 2;
const SCALE = SCENE_RADIUS / EARTH_RADIUS;

function toScenePos(pos) {
  return [pos.x * SCALE, pos.y * SCALE, pos.z * SCALE];
}

/**
 * OrbitPath renders raw SGP4 sample positions as a line.
 *
 * Root cause of previous "loop" bug:
 *   The backend /trajectory endpoint returns only 6 widely-spaced points
 *   (0, 1, 6, 12, 24, 48 h). CatmullRomCurve3 interpolating between points
 *   ~1000s km apart (half-orbit) over-shoots and creates huge loops that
 *   pass through/across the Earth. Fix: request dense samples (~1 orbit
 *   worth) via a custom hours list, then connect them with a plain LineSegments
 *   without any smoothing spline — the samples are already dense enough.
 */
function OrbitPath({ points, selected }) {
  if (!points || points.length < 2) return null;

  return (
    <Line
      points={points}
      color={selected ? "#35a7ff" : "#2a5a80"}
      lineWidth={selected ? 1.8 : 0.6}
      transparent
      opacity={selected ? 0.92 : 0.28}
      depthWrite={false}
    />
  );
}

function InfoPanel({ object, onClose }) {
  if (!object) return null;
  const vel = object.velocity_km_s;
  const speed = vel
    ? Math.hypot(vel.x, vel.y, vel.z).toFixed(2) + " km/s"
    : "—";
  const alt = Number.isFinite(object.altitude_km)
    ? object.altitude_km.toFixed(1) + " km"
    : "—";

  return (
    <aside className="satellite-details">
      <button
        className="satellite-details-close"
        onClick={onClose}
        aria-label="Close satellite details"
      >
        ×
      </button>
      <span className="satellite-details-eyebrow">SELECTED OBJECT</span>
      <h3>{object.name}</h3>
      <p>NORAD ID: {object.norad_id}</p>
      <p>Altitude: {alt}</p>
      <p>Speed: {speed}</p>
    </aside>
  );
}

function Scene({ objects, trajectories, selectedId, onSelect }) {
  return (
    <>
      <ambientLight intensity={0.8} />
      <directionalLight position={[5, 5, 5]} intensity={2} />
      <Stars radius={100} depth={50} count={5000} factor={4} fade />
      <Earth />

      {objects.map((obj) => {
        const id = String(obj.norad_id);
        const selected = id === String(selectedId);
        const pos = toScenePos(obj.position_km);
        const traj = trajectories[id] || [];

        return (
          <group key={id}>
            {traj.length >= 2 && (
              <OrbitPath points={traj} selected={selected} />
            )}
            <Satellite
              position={pos}
              name={obj.name}
              noradId={id}
              risk="low"
              selected={selected}
              onSelect={() => onSelect(obj)}
            />
          </group>
        );
      })}

      <OrbitControls enablePan={true} enableZoom={true} enableRotate={true} />
    </>
  );
}

export default function SpaceScene() {
  const [objects, setObjects] = useState([]);
  const [trajectories, setTrajectories] = useState({});
  const [selectedObject, setSelectedObject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const fetchedTraj = useRef(new Set());

  // Load object positions on mount
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");

    getObjects("stations", 30)
      .then((data) => {
        if (!active) return;
        setObjects(data.objects || []);
      })
      .catch((err) => {
        if (!active) return;
        console.error("Failed to load orbital objects:", err);
        setError("Unable to load orbital data. Check the backend connection.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => { active = false; };
  }, []);

  // When a satellite is selected, lazily fetch its dense orbit trajectory.
  // We request ~one full orbit (96 min ≈ 1.6 h for LEO) at 2-min intervals = 48 points.
  useEffect(() => {
    if (!selectedObject) return;
    const id = String(selectedObject.norad_id);
    if (fetchedTraj.current.has(id)) return;

    fetchedTraj.current.add(id);

    // Build a dense sample list: 0 to 100 minutes in 2-min steps (1 orbit ~90-120 min)
    const minuteSteps = Array.from({ length: 60 }, (_, i) => i * (100 / 59) / 60);
    const hoursParam = minuteSteps.join(",");

    getTrajectory(selectedObject.norad_id, hoursParam)
      .then((data) => {
        const samples = data.trajectory || data.points || [];
        const valid = samples
          .map((s) => s.position_km)
          .filter(
            (p) =>
              p &&
              Number.isFinite(p.x) &&
              Number.isFinite(p.y) &&
              Number.isFinite(p.z)
          )
          .map((p) => new THREE.Vector3(p.x * SCALE, p.y * SCALE, p.z * SCALE));

        if (valid.length >= 2) {
          setTrajectories((prev) => ({ ...prev, [id]: valid }));
        }
      })
      .catch((err) => {
        console.warn(`Trajectory fetch failed for ${id}:`, err);
        fetchedTraj.current.delete(id); // allow retry on next select
      });
  }, [selectedObject]);

  return (
    <div className="space-scene">
      <Canvas
        camera={{ position: [0, 0, 7], fov: 45 }}
        onPointerMissed={() => setSelectedObject(null)}
      >
        <Scene
          objects={objects}
          trajectories={trajectories}
          selectedId={selectedObject?.norad_id}
          onSelect={setSelectedObject}
        />
      </Canvas>

      {loading && (
        <div className="scene-status">LOADING ORBITAL DATA...</div>
      )}
      {error && <div className="scene-status error">{error}</div>}
      {!loading && !error && (
        <div className="object-count">{objects.length} OBJECTS TRACKED</div>
      )}

      <InfoPanel
        object={selectedObject}
        onClose={() => setSelectedObject(null)}
      />
    </div>
  );
}
