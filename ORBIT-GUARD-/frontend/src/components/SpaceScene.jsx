import { useEffect, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stars } from "@react-three/drei";

import Earth from "./Earth";
import Satellite from "./Satellite";
import { getObjects } from "../api";

function OrbitalObjects({ objects }) {
  const earthRadius = 2;
  const scale = earthRadius / 6371;

  return (
    <>
      {objects.map((object) => {
        const { x, y, z } = object.position_km;

        const position = [
          x * scale,
          y * scale,
          z * scale,
        ];

        return (
          <Satellite
            key={object.norad_id}
            position={position}
            risk="low"
            name={object.name}
          />
        );
      })}
    </>
  );
}

export default function SpaceScene() {
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
        setError("Unable to load orbital data");
      } finally {
        setLoading(false);
      }
    }

    loadObjects();
  }, []);

  return (
    <div className="space-scene">
      <Canvas camera={{ position: [0, 0, 7], fov: 45 }}>
        <ambientLight intensity={0.8} />

        <directionalLight
          position={[5, 5, 5]}
          intensity={2}
        />

        <Stars
          radius={100}
          depth={50}
          count={5000}
          factor={4}
          fade
        />

        <Earth />

        <OrbitalObjects objects={objects} />

        <OrbitControls />
      </Canvas>

      {loading && (
        <div className="scene-status">
          LOADING ORBITAL DATA...
        </div>
      )}

      {error && (
        <div className="scene-status error">
          {error}
        </div>
      )}

      {!loading && !error && (
        <div className="object-count">
          {objects.length} OBJECTS TRACKED
        </div>
      )}
    </div>
  );
}