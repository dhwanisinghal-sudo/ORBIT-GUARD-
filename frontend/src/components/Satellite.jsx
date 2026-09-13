import { useRef } from "react";
import { useFrame } from "@react-three/fiber";

export default function Satellite({
  position = [3, 0, 0],
  risk = "low",
  name = "UNKNOWN",
}) {
  const satelliteRef = useRef();

  useFrame(() => {
    if (satelliteRef.current) {
      satelliteRef.current.rotation.y += 0.02;
    }
  });

  const riskColors = {
    low: "#20d88a",
    medium: "#e5c52d",
    high: "#ff963d",
    critical: "#ff3b3b",
  };

  const color =
    riskColors[risk.toLowerCase()] || "#ffffff";

  return (
    <mesh
      ref={satelliteRef}
      position={position}
    >
      <sphereGeometry args={[0.06, 16, 16]} />

      <meshStandardMaterial
        color={color}
        emissive={color}
        emissiveIntensity={2}
      />
    </mesh>
  );
}