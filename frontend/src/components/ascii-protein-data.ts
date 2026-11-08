export type ProteinPresetId = "insulin-3i40" | "sglt2-pocket" | "glp1-helix";

export interface ProteinChainData {
  id: string;
  label: string;
  colorHex: string;
  /** 3D C-alpha backbone coordinates in Angstroms, centered near origin */
  caCoords: readonly (readonly [number, number, number])[];
  /** Optional 0-based inclusive index ranges of alpha-helices along caCoords */
  helixRanges: readonly (readonly [number, number])[];
}

export interface ProteinBridgeData {
  label: string;
  from: readonly [number, number, number];
  to: readonly [number, number, number];
  colorHex: string;
}

export interface ProteinStructurePreset {
  id: ProteinPresetId;
  name: string;
  pdbCode: string;
  subtitle: string;
  clinicalContext: string;
  chains: readonly ProteinChainData[];
  bridges: readonly ProteinBridgeData[];
  ligandCenter?: readonly [number, number, number];
}

const INSULIN_CHAIN_A: readonly (readonly [number, number, number])[] = [
  [-6.99, 6.71, -2.57],
  [-4.81, 3.7, -1.8],
  [-7.73, 1.28, -1.82],
  [-8.74, 2.3, -5.34],
  [-5.13, 2.09, -6.52],
  [-3.95, -1.1, -4.8],
  [-7.05, -3.07, -3.77],
  [-9.64, -2.44, -6.49],
  [-6.8, -2.34, -9.02],
  [-3.3, -3.81, -9.18],
  [-0.83, -2.2, -6.79],
  [2.71, -1.09, -7.6],
  [5.88, -0.34, -5.68],
  [5.7, 3.2, -7.03],
  [2.3, 3.81, -5.48],
  [3.02, 2.06, -2.18],
  [6.04, 4.29, -1.62],
  [3.78, 7.33, -1.99],
  [2.46, 6.3, 1.42],
  [5.75, 5.93, 3.29],
  [6.63, 8.67, 5.77],
];

const INSULIN_CHAIN_B: readonly (readonly [number, number, number])[] = [
  [4.87, -9.21, -3.71],
  [3.69, -5.69, -4.53],
  [2.42, -6.23, -8.06],
  [-1.05, -7.61, -7.34],
  [-4.41, -6.79, -5.76],
  [-3.71, -5.98, -2.12],
  [-6.64, -5.43, 0.23],
  [-6.97, -5.07, 3.99],
  [-4.22, -6.77, 5.97],
  [-2.5, -7.73, 2.71],
  [-2.14, -4.04, 1.81],
  [-0.98, -3.01, 5.26],
  [1.56, -5.84, 5.23],
  [2.96, -4.63, 1.89],
  [3.19, -1.05, 3.15],
  [5.05, -2.3, 6.22],
  [7.53, -4.32, 4.16],
  [8.11, -1.59, 1.6],
  [8.39, 1.39, 3.94],
  [10.65, -0.15, 6.58],
  [11.79, 2.21, 9.34],
  [10.22, 5.18, 7.53],
  [6.82, 3.83, 8.5],
  [3.7, 4.73, 6.56],
  [0.15, 6.02, 6.66],
  [-2.83, 3.86, 5.77],
  [-5.93, 5.82, 4.84],
  [-8.63, 3.56, 3.34],
  [-11.27, 6.32, 3.26],
  [-9.11, 9.25, 2.13],
];

function generateHelixCoords(
  length: number,
  radius: number,
  pitch: number,
  offset: readonly [number, number, number],
  tiltRad: number
): (readonly [number, number, number])[] {
  const coords: (readonly [number, number, number])[] = [];
  const cosTilt = Math.cos(tiltRad);
  const sinTilt = Math.sin(tiltRad);
  for (let i = 0; i < length; i++) {
    const t = i - (length - 1) / 2;
    const angle = i * 1.745; // ~100 degrees per residue in an alpha-helix
    const localX = radius * Math.cos(angle);
    const localY = t * pitch;
    const localZ = radius * Math.sin(angle);

    const rotX = localX * cosTilt - localY * sinTilt;
    const rotY = localX * sinTilt + localY * cosTilt;
    coords.push([
      Number((rotX + offset[0]).toFixed(2)),
      Number((rotY + offset[1]).toFixed(2)),
      Number((localZ + offset[2]).toFixed(2)),
    ]);
  }
  return coords;
}

const SGLT2_TM1 = generateHelixCoords(16, 2.5, 1.15, [-6.2, 0, -2.5], 0.22);
const SGLT2_TM2 = generateHelixCoords(16, 2.5, 1.15, [6.2, 0, -2.2], -0.24);
const SGLT2_TM3 = generateHelixCoords(14, 2.4, 1.15, [0, 0.5, 5.8], 0.15);

const GLP1_PEPTIDE = generateHelixCoords(24, 2.7, 0.95, [-2.2, 0, 1.8], -0.35);
const GLP1_ECD_LOOP: readonly (readonly [number, number, number])[] = [
  [5.5, -8.5, -3.2],
  [7.2, -5.8, -1.4],
  [6.1, -2.4, 1.2],
  [4.8, 0.8, -0.8],
  [6.4, 3.9, -2.9],
  [4.9, 6.8, -1.1],
  [1.8, 8.4, 1.4],
  [-1.4, 7.6, 3.6],
];

export const PROTEIN_PRESETS: Record<ProteinPresetId, ProteinStructurePreset> =
  {
    "insulin-3i40": {
      id: "insulin-3i40",
      name: "Human Insulin",
      pdbCode: "PDB: 3I40",
      subtitle: "Chain A (21 aa) + Chain B (30 aa) + 3 Cys-Cys Bridges",
      clinicalContext:
        "Core glycemic regulator in Type 1 & Type 2 Diabetes Mellitus",
      chains: [
        {
          id: "A",
          label: "Chain A (GlyA1–AsnA21)",
          colorHex: "#059669", // deep emerald
          caCoords: INSULIN_CHAIN_A,
          helixRanges: [
            [0, 7],
            [11, 18],
          ],
        },
        {
          id: "B",
          label: "Chain B (PheB1–ThrB30)",
          colorHex: "#0284c7", // deep ocean blue
          caCoords: INSULIN_CHAIN_B,
          helixRanges: [[7, 22]],
        },
      ],
      bridges: [
        {
          label: "SS1 (CysA6–CysA11)",
          from: INSULIN_CHAIN_A[5],
          to: INSULIN_CHAIN_A[10],
          colorHex: "#d97706", // warm amber
        },
        {
          label: "SS2 (CysA7–CysB7)",
          from: INSULIN_CHAIN_A[6],
          to: INSULIN_CHAIN_B[6],
          colorHex: "#d97706",
        },
        {
          label: "SS3 (CysA20–CysB19)",
          from: INSULIN_CHAIN_A[19],
          to: INSULIN_CHAIN_B[18],
          colorHex: "#d97706",
        },
      ],
    },
    "sglt2-pocket": {
      id: "sglt2-pocket",
      name: "SGLT2 Cotransporter Pocket",
      pdbCode: "PDB: 7VSI (Core)",
      subtitle: "TM Helical Bundle + Bound Gliflozin Inhibitor",
      clinicalContext:
        "Target of active Phase III protocol (prot-t2d-001) for renal glucose reabsorption",
      chains: [
        {
          id: "TM1",
          label: "TM Helix 1 (Na+ Gate)",
          colorHex: "#059669",
          caCoords: SGLT2_TM1,
          helixRanges: [[0, 15]],
        },
        {
          id: "TM6",
          label: "TM Helix 6 (Glucose Pore)",
          colorHex: "#0284c7",
          caCoords: SGLT2_TM2,
          helixRanges: [[0, 15]],
        },
        {
          id: "TM10",
          label: "TM Helix 10 (Scaffold)",
          colorHex: "#7c3aed", // deep violet
          caCoords: SGLT2_TM3,
          helixRanges: [[0, 13]],
        },
      ],
      bridges: [
        {
          label: "H-Bond (His80–Ligand)",
          from: SGLT2_TM1[8],
          to: [0, 0, 0],
          colorHex: "#d97706",
        },
        {
          label: "H-Bond (Glu99–Ligand)",
          from: SGLT2_TM2[7],
          to: [0, 0, 0],
          colorHex: "#d97706",
        },
        {
          label: "Pi-Stack (Phe453–Ligand)",
          from: SGLT2_TM3[7],
          to: [0, 0, 0],
          colorHex: "#d97706",
        },
      ],
      ligandCenter: [0, 0, 0],
    },
    "glp1-helix": {
      id: "glp1-helix",
      name: "GLP-1 Incretin Agonist",
      pdbCode: "PDB: 5VAI (Helix)",
      subtitle: "Amphipathic Alpha-Helix + Receptor ECD Groove",
      clinicalContext:
        "Comparator arm class benchmarked across historical AACT diabetes trials",
      chains: [
        {
          id: "P",
          label: "GLP-1(7-36) Alpha-Helix",
          colorHex: "#059669",
          caCoords: GLP1_PEPTIDE,
          helixRanges: [[1, 22]],
        },
        {
          id: "R",
          label: "GLP-1R ECD Binding Loop",
          colorHex: "#0284c7",
          caCoords: GLP1_ECD_LOOP,
          helixRanges: [[0, 3]],
        },
      ],
      bridges: [
        {
          label: "Salt Bridge (Glu27–Arg121)",
          from: GLP1_PEPTIDE[14],
          to: GLP1_ECD_LOOP[3],
          colorHex: "#d97706",
        },
        {
          label: "Hydrophobic Contact (Phe28–Trp)",
          from: GLP1_PEPTIDE[19],
          to: GLP1_ECD_LOOP[5],
          colorHex: "#d97706",
        },
      ],
    },
  };

export interface SymbolPreset {
  id: string;
  label: string;
  /** Ordered from lightest/farthest (index 0) to densest/nearest (last index) */
  chars: string;
}

export const SYMBOL_PRESETS: readonly SymbolPreset[] = [
  {
    id: "simple",
    label: "Simple Symbols",
    chars: "  .·:+oO#",
  },
  {
    id: "minimal",
    label: "Dots & Crosses",
    chars: " .·:+*#",
  },
  {
    id: "classic",
    label: "Classic ASCII",
    chars: " .:-=+*#%@",
  },
  {
    id: "molecular",
    label: "Atomic Rings",
    chars: " ·∘○◎●@",
  },
  {
    id: "helix",
    label: "Helix Matrix",
    chars: " .~:;xX$#",
  },
];
