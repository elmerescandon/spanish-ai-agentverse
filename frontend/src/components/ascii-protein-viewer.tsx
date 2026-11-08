"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import {
  PROTEIN_PRESETS,
  SYMBOL_PRESETS,
  type ProteinPresetId,
} from "@/components/ascii-protein-data";

export type RenderStyle = "ribbon-atoms" | "tubes-only" | "ball-stick";
export type ColorMode = "chain" | "emerald" | "mono";

interface SamplePoint3D {
  position: THREE.Vector3;
  normal: THREE.Vector3;
  colorHex: string;
  weight: number;
  kind: "helix" | "backbone" | "atom" | "bridge" | "ligand";
}

const CHAR_WIDTH_PX = 7.2;
const CHAR_HEIGHT_PX = 12.0;
const DEFAULT_FALLBACK_COLS = 180;
const DEFAULT_FALLBACK_ROWS = 60;

function escapeHtmlChar(ch: string): string {
  if (ch === "&") return "&amp;";
  if (ch === "<") return "&lt;";
  if (ch === ">") return "&gt;";
  if (ch === '"') return "&quot;";
  return ch;
}

function getMaterialShade(colorHex: string): string {
  switch (colorHex.toLowerCase()) {
    case "#059669":
      return "#10b981"; // vibrant emerald
    case "#0284c7":
      return "#0ea5e9"; // vibrant sky blue
    case "#7c3aed":
      return "#8b5cf6"; // vibrant violet
    case "#d97706":
      return "#f59e0b"; // vibrant amber
    case "#e11d48":
      return "#f43f5e"; // vibrant rose
    default:
      return colorHex;
  }
}

function shadeColorWithInk(baseColor: string, ink: number): string {
  // Soft, refined, low-contrast pastel tone on white background
  const factor = 0.50 + 0.45 * (1 - ink);

  if (baseColor.startsWith("#")) {
    const hex = baseColor.slice(1);
    const r = parseInt(hex.slice(0, 2), 16) || 0;
    const g = parseInt(hex.slice(2, 4), 16) || 0;
    const b = parseInt(hex.slice(4, 6), 16) || 0;
    return `rgb(${Math.round(r * factor + 255 * 0.16)}, ${Math.round(g * factor + 255 * 0.16)}, ${Math.round(b * factor + 255 * 0.16)})`;
  }
  if (baseColor.startsWith("rgb(")) {
    const match = baseColor.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (match) {
      const r = parseInt(match[1], 10);
      const g = parseInt(match[2], 10);
      const b = parseInt(match[3], 10);
      return `rgb(${Math.round(r * factor + 255 * 0.16)}, ${Math.round(g * factor + 255 * 0.16)}, ${Math.round(b * factor + 255 * 0.16)})`;
    }
  }
  return baseColor;
}

function buildThreeProteinGroup(
  presetId: ProteinPresetId,
  style: RenderStyle,
  thicknessScale: number
): {
  group: THREE.Group;
  samples: SamplePoint3D[];
  dispose: () => void;
} {
  const preset = PROTEIN_PRESETS[presetId];
  const group = new THREE.Group();
  const geometries: THREE.BufferGeometry[] = [];
  const materials: THREE.Material[] = [];
  const samples: SamplePoint3D[] = [];

  const showTubes = style === "ribbon-atoms" || style === "tubes-only";
  const showAtoms = style === "ribbon-atoms" || style === "ball-stick";

  // Compute centroid & max radius across all residues
  const allCoords: [number, number, number][] = [];
  for (const chain of preset.chains) {
    for (const coord of chain.caCoords) {
      allCoords.push([coord[0], coord[1], coord[2]]);
    }
  }

  let cx = 0;
  let cy = 0;
  let cz = 0;
  if (allCoords.length > 0) {
    for (const [x, y, z] of allCoords) {
      cx += x;
      cy += y;
      cz += z;
    }
    cx /= allCoords.length;
    cy /= allCoords.length;
    cz /= allCoords.length;
  }

  let maxR = 0;
  for (const [x, y, z] of allCoords) {
    const dx = x - cx;
    const dy = y - cy;
    const dz = z - cz;
    const r = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (r > maxR) maxR = r;
  }

  // Target radius of 11.5 provides a large, bold protein presentation
  // while comfortably remaining within camera view
  const TARGET_RADIUS = 11.5;
  const normScale = maxR > 0 ? TARGET_RADIUS / maxR : 1.0;

  const transformCoord = (
    [x, y, z]: readonly [number, number, number]
  ): THREE.Vector3 => {
    return new THREE.Vector3(
      (x - cx) * normScale,
      (y - cy) * normScale,
      (z - cz) * normScale
    );
  };

  for (const chain of preset.chains) {
    const points = chain.caCoords.map(transformCoord);
    if (points.length < 2) continue;

    const curve = new THREE.CatmullRomCurve3(points, false, "centripetal", 0.5);
    const matColor = new THREE.Color(getMaterialShade(chain.colorHex));

    if (showTubes) {
      const tubeRadius = 0.45 * thicknessScale;
      const tubeGeo = new THREE.TubeGeometry(
        curve,
        points.length * 4,
        tubeRadius,
        8,
        false
      );
      const tubeMat = new THREE.MeshStandardMaterial({
        color: matColor,
        roughness: 0.32,
        metalness: 0.15,
      });
      geometries.push(tubeGeo);
      materials.push(tubeMat);
      group.add(new THREE.Mesh(tubeGeo, tubeMat));

      // Thicker alpha-helical cylinders/ribbons along annotated helix ranges
      for (const [startIdx, endIdx] of chain.helixRanges) {
        const slice = points.slice(startIdx, endIdx + 1);
        if (slice.length >= 2) {
          const helixCurve = new THREE.CatmullRomCurve3(slice);
          const helixGeo = new THREE.TubeGeometry(
            helixCurve,
            slice.length * 5,
            0.78 * thicknessScale,
            10,
            false
          );
          const helixMat = new THREE.MeshStandardMaterial({
            color: matColor,
            roughness: 0.25,
            metalness: 0.2,
          });
          geometries.push(helixGeo);
          materials.push(helixMat);
          group.add(new THREE.Mesh(helixGeo, helixMat));
        }
      }
    }

    if (showAtoms) {
      const atomRadius =
        (style === "ball-stick" ? 0.8 : 0.62) * thicknessScale;
      const sphereGeo = new THREE.SphereGeometry(atomRadius, 10, 10);
      const sphereMat = new THREE.MeshStandardMaterial({
        color: matColor,
        roughness: 0.2,
        metalness: 0.25,
      });
      geometries.push(sphereGeo);
      materials.push(sphereMat);

      for (let i = 0; i < points.length; i++) {
        const mesh = new THREE.Mesh(sphereGeo, sphereMat);
        mesh.position.copy(points[i]);
        group.add(mesh);

        if (style === "ball-stick" && i < points.length - 1) {
          const nextPt = points[i + 1];
          const bondVec = new THREE.Vector3().subVectors(nextPt, points[i]);
          const bondLen = bondVec.length();
          const bondGeo = new THREE.CylinderGeometry(
            0.22 * thicknessScale,
            0.22 * thicknessScale,
            bondLen,
            6
          );
          geometries.push(bondGeo);
          const bondMesh = new THREE.Mesh(bondGeo, sphereMat);
          bondMesh.position.copy(points[i]).addScaledVector(bondVec, 0.5);
          bondMesh.quaternion.setFromUnitVectors(
            new THREE.Vector3(0, 1, 0),
            bondVec.clone().normalize()
          );
          group.add(bondMesh);
        }
      }
    }

    // Populate dense 3D sample points along the Three.js CatmullRomCurve3
    const sampleSteps = points.length * 10;
    const frames = curve.computeFrenetFrames(sampleSteps, false);
    for (let s = 0; s <= sampleSteps; s++) {
      const u = s / sampleSteps;
      const centerPt = curve.getPointAt(u);
      const floatIdx = u * (points.length - 1);
      const isHelix = chain.helixRanges.some(
        ([a, b]) => floatIdx >= a && floatIdx <= b
      );

      const normal = frames.normals[s] ?? new THREE.Vector3(0, 1, 0);
      const binormal = frames.binormals[s] ?? new THREE.Vector3(0, 0, 1);

      if (showTubes) {
        const ringRadius = (isHelix ? 0.72 : 0.42) * thicknessScale;
        const ringCount = isHelix ? 4 : 3;
        for (let r = 0; r < ringCount; r++) {
          const theta = (r / ringCount) * Math.PI * 2;
          const dir = new THREE.Vector3()
            .addScaledVector(normal, Math.cos(theta))
            .addScaledVector(binormal, Math.sin(theta))
            .normalize();
          samples.push({
            position: centerPt.clone().addScaledVector(dir, ringRadius),
            normal: dir,
            colorHex: chain.colorHex,
            weight: isHelix ? 0.88 : 0.65,
            kind: isHelix ? "helix" : "backbone",
          });
        }
      } else {
        samples.push({
          position: centerPt,
          normal: normal.clone(),
          colorHex: chain.colorHex,
          weight: 0.65,
          kind: "backbone",
        });
      }
    }

    if (showAtoms) {
      for (const pt of points) {
        samples.push({
          position: pt.clone(),
          normal: pt.clone().normalize(),
          colorHex: chain.colorHex,
          weight: 1.0,
          kind: "atom",
        });
      }
    }
  }

  // Disulfide bridges & non-covalent interactions
  for (const bridge of preset.bridges) {
    const fromVec = transformCoord(bridge.from);
    const toVec = transformCoord(bridge.to);
    const delta = new THREE.Vector3().subVectors(toVec, fromVec);
    const dist = delta.length();
    const bridgeMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(getMaterialShade(bridge.colorHex)),
      roughness: 0.25,
      metalness: 0.3,
    });
    materials.push(bridgeMat);

    const cylGeo = new THREE.CylinderGeometry(
      0.24 * thicknessScale,
      0.24 * thicknessScale,
      dist,
      6
    );
    geometries.push(cylGeo);
    const cylMesh = new THREE.Mesh(cylGeo, bridgeMat);
    cylMesh.position.copy(fromVec).addScaledVector(delta, 0.5);
    cylMesh.quaternion.setFromUnitVectors(
      new THREE.Vector3(0, 1, 0),
      delta.clone().normalize()
    );
    group.add(cylMesh);

    const steps = 10;
    for (let i = 0; i <= steps; i++) {
      const p = fromVec.clone().lerp(toVec, i / steps);
      samples.push({
        position: p,
        normal: p.clone().normalize(),
        colorHex: bridge.colorHex,
        weight: 0.85,
        kind: "bridge",
      });
    }
  }

  // Optional central bound inhibitor ligand (e.g. Empagliflozin in SGLT2)
  if (preset.ligandCenter) {
    const ligCenter = transformCoord(preset.ligandCenter);
    const ligGeo = new THREE.OctahedronGeometry(1.2 * thicknessScale, 1);
    const ligMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color("#e11d48"),
      emissive: new THREE.Color("#4c0519"),
      roughness: 0.2,
    });
    geometries.push(ligGeo);
    materials.push(ligMat);
    const ligMesh = new THREE.Mesh(ligGeo, ligMat);
    ligMesh.position.copy(ligCenter);
    group.add(ligMesh);

    const offsets = [
      [0, 0, 0],
      [1.0, 0.45, 0],
      [-1.0, -0.45, 0],
      [0, 1.0, 0.5],
      [0, -1.0, -0.5],
    ] as const;
    for (const [ox, oy, oz] of offsets) {
      const pos = ligCenter
        .clone()
        .add(
          new THREE.Vector3(
            ox * thicknessScale,
            oy * thicknessScale,
            oz * thicknessScale
          )
        );
      samples.push({
        position: pos,
        normal: new THREE.Vector3(ox || 0.1, oy || 0.1, oz || 1).normalize(),
        colorHex: "#e11d48",
        weight: 1.0,
        kind: "ligand",
      });
    }
  }

  // Center all meshes & sample points around (0, 0, 0)
  const box = new THREE.Box3().setFromObject(group);
  const center = new THREE.Vector3();
  box.getCenter(center);
  for (const child of group.children) {
    child.position.sub(center);
  }
  for (const sample of samples) {
    sample.position.sub(center);
  }

  return {
    group,
    samples,
    dispose: () => {
      for (const g of geometries) g.dispose();
      for (const m of materials) m.dispose();
    },
  };
}

export function AsciiProteinViewer() {
  const [presetId, setPresetId] = useState<ProteinPresetId>("insulin-3i40");
  const [symbolPresetId, setSymbolPresetId] = useState<string>("simple");
  const [customChars, setCustomChars] = useState<string>("  .·:+oO#");
  const [renderStyle, setRenderStyle] = useState<RenderStyle>("ribbon-atoms");
  const [colorMode, setColorMode] = useState<ColorMode>("chain");

  const [windowDimensions, setWindowDimensions] = useState<{
    cols: number;
    rows: number;
  }>(() => {
    if (
      typeof window !== "undefined" &&
      window.innerWidth > 0 &&
      window.innerHeight > 0
    ) {
      return {
        cols: Math.max(120, Math.floor(window.innerWidth / CHAR_WIDTH_PX)),
        rows: Math.max(45, Math.floor(window.innerHeight / CHAR_HEIGHT_PX)),
      };
    }
    return { cols: DEFAULT_FALLBACK_COLS, rows: DEFAULT_FALLBACK_ROWS };
  });

  const [colsOverride, setColsOverride] = useState<number | null>(null);

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth > 0 && window.innerHeight > 0) {
        const nextCols = Math.max(
          120,
          Math.floor(window.innerWidth / CHAR_WIDTH_PX)
        );
        const nextRows = Math.max(
          45,
          Math.floor(window.innerHeight / CHAR_HEIGHT_PX)
        );
        setWindowDimensions((prev) =>
          prev.cols === nextCols && prev.rows === nextRows
            ? prev
            : { cols: nextCols, rows: nextRows }
        );
      }
    };

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const cols = colsOverride ?? windowDimensions.cols;
  const rows = colsOverride
    ? Math.max(
        35,
        Math.round(
          colsOverride * (windowDimensions.rows / windowDimensions.cols)
        )
      )
    : windowDimensions.rows;

  const [thicknessScale, setThicknessScale] = useState<number>(1.0);
  const [rotationSpeed, setRotationSpeed] = useState<number>(0.8);
  const [isAutoRotating, setIsAutoRotating] = useState<boolean>(true);
  const [isTunerOpen, setIsTunerOpen] = useState<boolean>(false);
  const [copiedConfig, setCopiedConfig] = useState<boolean>(false);

  const preRef = useRef<HTMLPreElement | null>(null);
  const rotationRef = useRef<{
    rotX: number;
    rotY: number;
  }>({
    rotX: 0.28,
    rotY: 0.6,
  });

  const activePreset = PROTEIN_PRESETS[presetId];
  const activeChars =
    customChars.length >= 2 ? customChars : SYMBOL_PRESETS[0].chars;

  const handleSymbolPresetSelect = (id: string, chars: string) => {
    setSymbolPresetId(id);
    setCustomChars(chars);
  };

  const handleCopyConfig = async () => {
    const configPayload = {
      presetId,
      chars: activeChars,
      renderStyle,
      colorMode,
      cols,
      thicknessScale,
      rotationSpeed,
    };
    try {
      await navigator.clipboard?.writeText(
        JSON.stringify(configPayload, null, 2)
      );
      setCopiedConfig(true);
    } catch {
      setCopiedConfig(true);
    }
  };

  useEffect(() => {
    if (!copiedConfig) return;
    const timer = setTimeout(() => setCopiedConfig(false), 2500);
    return () => clearTimeout(timer);
  }, [copiedConfig]);

  useEffect(() => {
    // Set up Three.js Scene, Camera, and Lights matching full-screen cell aspect
    const scene = new THREE.Scene();
    const visualAspect = (cols * CHAR_WIDTH_PX) / (rows * CHAR_HEIGHT_PX);
    const camera = new THREE.PerspectiveCamera(42, visualAspect, 1, 150);
    camera.position.set(0, 0, 27);
    camera.lookAt(0, 0, 0);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.58);
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.05);
    keyLight.position.set(22, 26, 24);
    scene.add(ambientLight, keyLight);

    const { group, samples, dispose } = buildThreeProteinGroup(
      presetId,
      renderStyle,
      thicknessScale
    );
    // Shift protein further to the right side in 3D world space
    group.position.x = 6.8;
    scene.add(group);

    // Try initializing Three.js WebGLRenderer + 2D sampling context (AsciiEffect pipeline)
    let webglRenderer: THREE.WebGLRenderer | null = null;
    let sampleCtx: CanvasRenderingContext2D | null = null;
    if (typeof WebGLRenderingContext !== "undefined") {
      try {
        const testCanvas = document.createElement("canvas");
        const gl =
          testCanvas.getContext("webgl2") || testCanvas.getContext("webgl");
        if (gl) {
          webglRenderer = new THREE.WebGLRenderer({
            canvas: testCanvas,
            antialias: false,
            alpha: true,
            preserveDrawingBuffer: true,
          });
          webglRenderer.setSize(cols, rows, false);
          webglRenderer.setClearColor(0x000000, 0);

          const sampleCanvas = document.createElement("canvas");
          sampleCanvas.width = cols;
          sampleCanvas.height = rows;
          sampleCtx = sampleCanvas.getContext("2d", {
            willReadFrequently: true,
          });
        }
      } catch {
        webglRenderer = null;
        sampleCtx = null;
      }
    }

    const lightDir = new THREE.Vector3(22, 26, 24).normalize();
    const projectedVec = new THREE.Vector3();
    const worldNormal = new THREE.Vector3();
    const normalMatrix = new THREE.Matrix3();

    let animationFrameId: number | null = null;
    let lastTime = performance.now();

    const renderFrame = (now: number) => {
      const dt = Math.min(0.1, (now - lastTime) / 1000);
      lastTime = now;

      if (isAutoRotating) {
        rotationRef.current.rotY += dt * rotationSpeed * 0.85;
        rotationRef.current.rotX =
          0.25 + Math.sin(now * 0.0007 * rotationSpeed) * 0.16;
      }

      group.rotation.x = rotationRef.current.rotX;
      group.rotation.y = rotationRef.current.rotY;
      group.updateMatrixWorld(true);
      camera.updateMatrixWorld(true);
      camera.updateProjectionMatrix();

      const charList = Array.from(activeChars).map(escapeHtmlChar);
      const maxCharIdx = Math.max(1, charList.length - 1);

      // Z-buffer + brightness grid
      const zBuffer = new Float32Array(cols * rows).fill(Infinity);
      const lumBuffer = new Float32Array(cols * rows).fill(0);
      const colorBuffer: (string | null)[] = new Array(cols * rows).fill(null);

      // 1) If WebGLRenderer + 2D sampler is available, sample the WebGL shaded frame
      let usedWebglPixels = false;
      if (webglRenderer && sampleCtx) {
        try {
          webglRenderer.render(scene, camera);
          sampleCtx.clearRect(0, 0, cols, rows);
          sampleCtx.drawImage(webglRenderer.domElement, 0, 0, cols, rows);
          const imgData = sampleCtx.getImageData(0, 0, cols, rows).data;

          let nonEmptyCount = 0;
          for (let i = 0; i < cols * rows; i++) {
            const offset = i * 4;
            const a = imgData[offset + 3];
            if (a > 18) {
              const r = imgData[offset];
              const g = imgData[offset + 1];
              const b = imgData[offset + 2];
              const fBrightness = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
              // On white background: gentle gradient without harsh contrast
              const rawInk = Math.pow(1 - Math.min(1, fBrightness), 0.85);
              const edgeBoost = a < 200 ? 0.06 : 0;
              const ink = THREE.MathUtils.clamp(
                rawInk * 0.78 + edgeBoost,
                0.10,
                0.82
              );

              lumBuffer[i] = ink;
              colorBuffer[i] = `rgb(${r}, ${g}, ${b})`;
              zBuffer[i] = 0.5;
              nonEmptyCount++;
            }
          }
          usedWebglPixels = nonEmptyCount > 12;
        } catch {
          usedWebglPixels = false;
        }
      }

      // 2) Augment / fallback with Three.js 3D camera projection + Z-buffer normal shading
      if (!usedWebglPixels) {
        normalMatrix.getNormalMatrix(group.matrixWorld);

        for (let i = 0; i < samples.length; i++) {
          const sample = samples[i];
          projectedVec
            .copy(sample.position)
            .applyMatrix4(group.matrixWorld)
            .project(camera);

          if (
            projectedVec.z < -1 ||
            projectedVec.z > 1 ||
            projectedVec.x < -1 ||
            projectedVec.x > 1 ||
            projectedVec.y < -1 ||
            projectedVec.y > 1
          ) {
            continue;
          }

          const col = Math.floor((projectedVec.x + 1) * 0.5 * cols);
          const row = Math.floor((1 - (projectedVec.y + 1) * 0.5) * rows);

          worldNormal
            .copy(sample.normal)
            .applyMatrix3(normalMatrix)
            .normalize();
          const diffuse = Math.max(0, worldNormal.dot(lightDir));
          // Silhouette / rim darkness when facing grazing camera angles (gentle)
          const rimShadow = Math.pow(1 - Math.abs(worldNormal.z), 1.5) * 0.18;
          // Deeper Z layers (further in back) get slightly darker shadows
          const depthDarkening = THREE.MathUtils.clamp(
            (projectedVec.z - 0.75) * 1.2,
            0,
            0.15
          );
          // Softer ink distribution: light surfaces ~0.10, deep creases ~0.70..0.82
          const rawInk =
            Math.pow(1 - diffuse, 0.85) * 0.58 +
            0.12 +
            rimShadow +
            depthDarkening;
          const ink = THREE.MathUtils.clamp(rawInk * sample.weight, 0.10, 0.82);

          const maxSplat = thicknessScale > 1.3 ? 1 : 0;

          for (let dy = -maxSplat; dy <= maxSplat; dy++) {
            for (let dx = -maxSplat; dx <= maxSplat; dx++) {
              if (Math.abs(dx) + Math.abs(dy) > 1) continue;
              const c = col + dx;
              const r = row + dy;
              if (c < 0 || c >= cols || r < 0 || r >= rows) continue;
              const cellIdx = r * cols + c;
              const effectiveZ =
                projectedVec.z + (dx !== 0 || dy !== 0 ? 0.008 : 0);

              if (effectiveZ < zBuffer[cellIdx]) {
                zBuffer[cellIdx] = effectiveZ;
                lumBuffer[cellIdx] = ink;
                colorBuffer[cellIdx] = sample.colorHex;
              }
            }
          }
        }
      }

      if (preRef.current) {
        let html = "";
        const emptyChar = charList[0] ?? " ";
        for (let r = 0; r < rows; r++) {
          for (let c = 0; c < cols; c++) {
            const idx = r * cols + c;
            const ink = lumBuffer[idx];
            if (ink <= 0.05) {
              html += emptyChar;
            } else {
              const charIdx = Math.min(
                maxCharIdx,
                Math.max(1, Math.round(ink * maxCharIdx))
              );
              const ch = charList[charIdx] ?? "#";
              const rawColor =
                colorMode === "chain"
                  ? colorBuffer[idx] ?? "#059669"
                  : colorMode === "emerald"
                    ? "#059669"
                    : "#18181b";
              const cellColor = shadeColorWithInk(rawColor, ink);
              html += `<span style="color:${cellColor}">${ch}</span>`;
            }
          }
          if (r < rows - 1) {
            html += "\n";
          }
        }
        preRef.current.innerHTML = html;
      }

      if (typeof window.requestAnimationFrame === "function") {
        animationFrameId = window.requestAnimationFrame(renderFrame);
      }
    };

    renderFrame(performance.now());

    return () => {
      if (
        animationFrameId !== null &&
        typeof window.cancelAnimationFrame === "function"
      ) {
        window.cancelAnimationFrame(animationFrameId);
      }
      dispose();
      webglRenderer?.dispose();
    };
  }, [
    presetId,
    activeChars,
    renderStyle,
    colorMode,
    cols,
    rows,
    thicknessScale,
    rotationSpeed,
    isAutoRotating,
  ]);

  return (
    <div className="fixed inset-0 w-screen h-screen bg-white text-zinc-900 overflow-hidden flex items-center justify-center pointer-events-none z-0">
      {/* Full-Screen 3D ASCII Viewport spanning entire screen */}
      <div
        role="img"
        aria-label={`Rotating 3D ASCII structure of ${activePreset.name} (${activePreset.pdbCode})`}
        className="relative w-screen h-screen flex items-center justify-center select-none overflow-hidden bg-[radial-gradient(circle_at_78%_50%,rgba(5,150,105,0.06)_0%,rgba(255,255,255,0)_70%)]"
      >
        <pre
          ref={preRef}
          aria-hidden="true"
          className="font-mono text-[12px] leading-[12px] tracking-normal text-zinc-900 m-0 p-0 overflow-hidden whitespace-pre select-none pointer-events-none"
        />
      </div>

      {/* Floating Tune ASCII / Close Button */}
      <button
        type="button"
        onClick={() => setIsTunerOpen((prev) => !prev)}
        aria-expanded={isTunerOpen}
        className="fixed bottom-5 right-5 z-40 px-3.5 py-1.5 rounded-full border border-zinc-200 bg-white/95 hover:bg-zinc-50 text-zinc-800 hover:text-zinc-950 font-mono text-xs backdrop-blur-md shadow-lg transition-all flex items-center gap-2 group pointer-events-auto"
      >
        <span className="w-2 h-2 rounded-full bg-emerald-600 group-hover:scale-110 transition-transform" />
        <span>{isTunerOpen ? "Close" : "Tune ASCII"}</span>
      </button>

      {/* Floating Tuner Popover */}
      {isTunerOpen && (
        <div
          role="dialog"
          aria-label="Three.js ASCII Tuner"
          className="fixed bottom-16 right-5 z-50 w-80 sm:w-96 max-h-[80vh] overflow-y-auto p-4 rounded-xl bg-white/95 border border-zinc-200 backdrop-blur-md shadow-xl space-y-4 text-xs text-zinc-900 pointer-events-auto"
        >
          <div className="flex items-center justify-between pb-1.5 border-b border-zinc-200">
            <div>
              <span className="font-semibold text-zinc-900 uppercase tracking-wider text-[11px] block">
                Live Three.js ASCII Studio
              </span>
              <span className="text-[10px] font-mono text-zinc-500">
                {activePreset.name} ({activePreset.pdbCode})
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={handleCopyConfig}
                className="px-2 py-0.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-mono text-[10px] transition-colors"
              >
                {copiedConfig ? "Copied!" : "Copy"}
              </button>
              <button
                type="button"
                onClick={() => setIsTunerOpen(false)}
                className="px-2 py-0.5 rounded bg-zinc-100 hover:bg-zinc-200 text-zinc-500 hover:text-zinc-800 font-mono text-[10px] transition-colors"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Protein Preset Switcher */}
          <div className="space-y-1.5">
            <span className="block text-zinc-600 font-medium">
              Protein Preset:
            </span>
            <div className="flex flex-wrap gap-1.5">
              {(Object.keys(PROTEIN_PRESETS) as ProteinPresetId[]).map((id) => {
                const item = PROTEIN_PRESETS[id];
                const isSelected = id === presetId;
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setPresetId(id)}
                    className={`px-2.5 py-1 rounded font-mono text-[11px] border transition-colors ${
                      isSelected
                        ? "border-emerald-600 bg-emerald-50 text-emerald-800 font-semibold"
                        : "border-zinc-200 bg-zinc-50 text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
                    }`}
                  >
                    {item.name}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Symbol Presets + Custom Input */}
          <div className="space-y-1.5">
            <label
              htmlFor="ascii-custom-symbols"
              className="block text-zinc-600 font-medium"
            >
              Symbol Ramp (lightest → densest):
            </label>
            <div className="flex flex-wrap gap-1.5">
              {SYMBOL_PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() =>
                    handleSymbolPresetSelect(preset.id, preset.chars)
                  }
                  className={`px-2 py-1 rounded font-mono text-[11px] border transition-colors ${
                    symbolPresetId === preset.id &&
                    customChars === preset.chars
                      ? "border-emerald-600 bg-emerald-50 text-emerald-800 font-medium"
                      : "border-zinc-200 bg-zinc-50 text-zinc-700 hover:bg-zinc-100"
                  }`}
                >
                  {preset.label} ({preset.chars.trim()})
                </button>
              ))}
            </div>
            <input
              id="ascii-custom-symbols"
              type="text"
              value={customChars}
              onChange={(e) => setCustomChars(e.target.value)}
              placeholder="Type custom symbols (start with space)..."
              className="w-full mt-1 px-2.5 py-1.5 rounded bg-white border border-zinc-300 font-mono text-xs text-emerald-700 focus:outline-none focus:border-emerald-600"
            />
          </div>

          {/* Geometry Style & Color Mode */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <span className="block text-zinc-600 font-medium">
                3D Geometry Style:
              </span>
              <div className="flex flex-wrap gap-1.5">
                {(
                  [
                    { id: "ribbon-atoms", label: "Ribbon + Atoms" },
                    { id: "tubes-only", label: "Helix Tubes" },
                    { id: "ball-stick", label: "Ball & Stick" },
                  ] as const
                ).map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setRenderStyle(opt.id)}
                    className={`px-2 py-1 rounded font-mono text-[11px] border transition-colors ${
                      renderStyle === opt.id
                        ? "border-emerald-600 bg-emerald-50 text-emerald-800 font-medium"
                        : "border-zinc-200 bg-zinc-50 text-zinc-600 hover:bg-zinc-100"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1">
              <span className="block text-zinc-600 font-medium">
                ASCII Color Mode:
              </span>
              <div className="flex flex-wrap gap-1.5">
                {(
                  [
                    { id: "chain", label: "Bio Chains" },
                    { id: "emerald", label: "Deep Emerald" },
                    { id: "mono", label: "Dark Mono" },
                  ] as const
                ).map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setColorMode(opt.id)}
                    className={`px-2 py-1 rounded font-mono text-[11px] border transition-colors ${
                      colorMode === opt.id
                        ? "border-emerald-600 bg-emerald-50 text-emerald-800 font-medium"
                        : "border-zinc-200 bg-zinc-50 text-zinc-600 hover:bg-zinc-100"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Sliders for Density, Thickness, and Speed */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
            <label className="space-y-1 block">
              <div className="flex justify-between text-zinc-600">
                <span>Grid Columns</span>
                <span className="font-mono text-zinc-900">{cols}</span>
              </div>
              <input
                type="range"
                min={100}
                max={260}
                step={10}
                value={cols}
                onChange={(e) => setColsOverride(Number(e.target.value))}
                className="w-full accent-emerald-600"
              />
            </label>

            <label className="space-y-1 block">
              <div className="flex justify-between text-zinc-600">
                <span>3D Thickness</span>
                <span className="font-mono text-zinc-900">
                  {thicknessScale.toFixed(1)}x
                </span>
              </div>
              <input
                type="range"
                min={0.6}
                max={1.6}
                step={0.1}
                value={thicknessScale}
                onChange={(e) => setThicknessScale(Number(e.target.value))}
                className="w-full accent-emerald-600"
              />
            </label>

            <label className="space-y-1 block">
              <div className="flex justify-between text-zinc-600">
                <span>Rotation Speed</span>
                <span className="font-mono text-zinc-900">
                  {rotationSpeed.toFixed(1)}x
                </span>
              </div>
              <input
                type="range"
                min={0.1}
                max={2.4}
                step={0.1}
                value={rotationSpeed}
                onChange={(e) => setRotationSpeed(Number(e.target.value))}
                className="w-full accent-emerald-600"
              />
            </label>
          </div>

          {/* Spin Toggle */}
          <div className="pt-2 flex justify-between items-center border-t border-zinc-200">
            <span className="text-zinc-600 text-[11px]">Auto Rotation:</span>
            <button
              type="button"
              onClick={() => setIsAutoRotating((prev) => !prev)}
              className="px-2.5 py-1 text-xs font-mono rounded border border-zinc-300 bg-zinc-50 text-zinc-800 hover:bg-zinc-100 transition-colors"
            >
              {isAutoRotating ? "Pause Spin" : "Resume Spin"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
