import { useRef } from "react";
import { useFrame } from "@react-three/fiber";


export default function Satellite({
  position = [3, 0, 0],
  risk = "low",
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

  return (
    <mesh
      ref={satelliteRef}
      position={position}
    >
      <sphereGeometry args={[0.08, 16, 16]} />

      <meshStandardMaterial
        color={riskColors[risk.toLowerCase()] || "#ffffff"}
        emissive={riskColors[risk.toLowerCase()] || "#ffffff"}
        emissiveIntensity={2}
      />
    </mesh>
  );
}