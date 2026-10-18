
import { useRef } from "react";
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";

export default function Satellite({
  position = [3, 0, 0],
  risk = "low",
  name = "UNKNOWN",
  noradId = "",
  selected = false,
  onSelect,
}) {
  const satelliteRef = useRef();

  useFrame((_, delta) => {
    if (satelliteRef.current) {
      satelliteRef.current.rotation.y += delta;
    }
  });

  const riskColors = {
    low: "#20d88a",
    medium: "#e5c52d",
    high: "#ff963d",
    critical: "#ff3b3b",
  };

  const color = riskColors[risk.toLowerCase()] || "#ffffff";

  return (
    <group position={position}>
      <mesh
        ref={satelliteRef}
        onClick={(event) => {
          event.stopPropagation();
          onSelect?.();
        }}
        onPointerOver={(event) => {
          event.stopPropagation();
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={() => {
          document.body.style.cursor = "auto";
        }}
      >
        <sphereGeometry args={[selected ? 0.085 : 0.065, 16, 16]} />
        <meshStandardMaterial
          color={selected ? "#ffffff" : color}
          emissive={color}
          emissiveIntensity={selected ? 3 : 1.8}
        />
      </mesh>

      {selected && (
        <>
          <mesh>
            <sphereGeometry args={[0.12, 16, 16]} />
            <meshBasicMaterial
              color={color}
              transparent
              opacity={0.22}
            />
          </mesh>

          <Html center distanceFactor={8} style={{ pointerEvents: "none" }}>
            <div className="satellite-label">
              <strong>{name}</strong>
              <span>NORAD {noradId || "N/A"}</span>
            </div>
          </Html>
        </>
      )}
    </group>
  );
}
