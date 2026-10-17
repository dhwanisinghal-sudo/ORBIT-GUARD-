import { useRef } from "react";
import { useFrame, useLoader } from "@react-three/fiber";
import * as THREE from "three";

export default function Earth() {
  const earthRef = useRef();

  const earthTexture = useLoader(
    THREE.TextureLoader,
    "/earth.jpg"
  );

  useFrame(() => {
    if (earthRef.current) {
      earthRef.current.rotation.y += 0.0015;
    }
  });

  return (
    <mesh ref={earthRef}>
      <sphereGeometry args={[2, 64, 64]} />

      <meshStandardMaterial
        map={earthTexture}
        roughness={0.8}
        metalness={0}
      />
    </mesh>
  );
}