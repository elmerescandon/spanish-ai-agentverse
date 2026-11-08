import type { ReactNode } from "react";

/** Plain heading for every detail section, like a document subheading. */
export default function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <h2 className="font-serif text-lg font-normal text-zinc-900">
      {children}
    </h2>
  );
}
