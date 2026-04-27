"use client";

import { Component, type ReactNode, Suspense } from "react";
import { Canvas, useLoader } from "@react-three/fiber";
import { Bounds, OrbitControls } from "@react-three/drei";
import { MeshStandardMaterial } from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";

type Props = {
  url?: string;
};

// Catches WebGL init failures, loader errors, and any Three.js runtime error
// so they never propagate to Next.js's global error boundary.
class CanvasErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed) {
      return (
        <div className="flex h-[420px] items-center justify-center rounded-3xl border border-white/10 bg-black/20 text-sm text-slate-400">
          Pré-visualização 3D indisponível neste ambiente.
        </div>
      );
    }
    return this.props.children;
  }
}

function STLMesh({ url }: { url: string }) {
  const geometry = useLoader(STLLoader, url);
  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial color="#f97316" roughness={0.35} metalness={0.1} />
    </mesh>
  );
}

function OBJMesh({ url }: { url: string }) {
  const object = useLoader(OBJLoader, url);
  object.traverse((child) => {
    const meshChild = child as { material?: MeshStandardMaterial | MeshStandardMaterial[] };
    if (meshChild.material) {
      meshChild.material = new MeshStandardMaterial({ color: "#38bdf8", roughness: 0.45, metalness: 0.05 });
    }
  });
  return <primitive object={object} />;
}

function Scene({ url }: { url: string }) {
  const extension = url.split(".").pop()?.toLowerCase();
  return (
    <Bounds fit clip observe margin={1.2}>
      {extension === "stl" ? <STLMesh url={url} /> : null}
      {extension === "obj" ? <OBJMesh url={url} /> : null}
    </Bounds>
  );
}

export function ModelPreview({ url }: Props) {
  const extension = url?.split(".").pop()?.toLowerCase();
  const is3D = extension === "stl" || extension === "obj";

  if (!url || !is3D) {
    return (
      <div className="flex h-[420px] items-center justify-center rounded-3xl border border-white/10 bg-black/20 text-sm text-slate-400">
        Preview 3D habilitado para arquivos STL e OBJ.
      </div>
    );
  }

  return (
    <CanvasErrorBoundary>
      <div className="h-[420px] overflow-hidden rounded-3xl border border-white/10 bg-slate-950/50">
        <Canvas camera={{ position: [140, 120, 160], fov: 45 }}>
          <ambientLight intensity={1.1} />
          <directionalLight position={[120, 80, 60]} intensity={1.4} castShadow />
          <directionalLight position={[-80, 40, -60]} intensity={0.6} />
          <Suspense fallback={null}>
            <Scene url={url} />
          </Suspense>
          <OrbitControls enablePan enableZoom enableRotate />
        </Canvas>
      </div>
    </CanvasErrorBoundary>
  );
}
