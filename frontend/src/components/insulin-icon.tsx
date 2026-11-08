import type { SVGProps } from "react";

/**
 * Stylised insulin monomer, the protein behind the homepage animation:
 * the longer B chain (top) and shorter A chain (bottom) held together by
 * the two inter-chain disulfide bridges. Drawn in `currentColor` so the
 * parent decides the colour; the header logo keeps it black.
 */
export function InsulinIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M12 11V21M20 11V21" strokeWidth="1.6" />
      <path d="M4 11q2-4 4 0t4 0t4 0t4 0t4 0t4 0" strokeWidth="2.4" />
      <path d="M8 21q2 4 4 0t4 0t4 0t4 0" strokeWidth="2.4" />
      <g fill="currentColor" stroke="none">
        <circle cx="12" cy="11" r="1.9" />
        <circle cx="20" cy="11" r="1.9" />
        <circle cx="12" cy="21" r="1.9" />
        <circle cx="20" cy="21" r="1.9" />
      </g>
    </svg>
  );
}
