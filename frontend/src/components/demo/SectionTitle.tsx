import type { ReactNode } from "react";

/** Small uppercase emerald heading used for every detail section. */
export default function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <h2 className="font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800">
      {children}
    </h2>
  );
}
