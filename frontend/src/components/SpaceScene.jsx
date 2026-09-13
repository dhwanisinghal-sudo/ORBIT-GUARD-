import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stars } from "@react-three/drei";
import Earth from "./Earth";
import Satellite from "./Satellite";

export default function SpaceScene() {
  return (
    <Canvas
      camera={{
        position: [0, 0, 7],
        fov: 45,
      }}
    >
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
      <Satellite
        position={[2.8, 0.8, 1.2]}
        risk="low"
      />

      <Satellite
        position={[-2.7, 1.2, 0.5]}
        risk="medium"
      />

      <Satellite
        position={[1.8, -1.4, 2.1]}
        risk="high"
      />

      <Satellite
        position={[-1.5, -1.2, -2.2]}
        risk="critical"
      />

      <OrbitControls />
    </Canvas>
  );
}