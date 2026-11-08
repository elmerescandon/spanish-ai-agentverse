import type { ReactNode } from "react";
import Link from "next/link";
import { InsulinIcon } from "@/components/insulin-icon";

const serifFont = {
  fontFamily:
    "var(--font-serif), 'Libre Baskerville', Georgia, 'Times New Roman', serif",
};

/** Sticky site header: the logo links home, page actions sit right. */
export default function SiteHeader({ children }: { children?: ReactNode }) {
  return (
    <header className="sticky top-0 z-30 w-full border-b border-zinc-100/60 bg-white/70 backdrop-blur-md">
      <div className="mx-auto flex h-18 max-w-7xl items-center justify-between px-6 sm:px-10 lg:px-12">
        <Link
          href="/"
          style={serifFont}
          className="flex items-center gap-2.5 text-2xl sm:text-3xl font-normal tracking-tight text-zinc-950"
        >
          <InsulinIcon className="h-8 w-8 sm:h-9 sm:w-9 shrink-0" />
          ProtocolAI
        </Link>
        {children && <div className="flex items-center gap-2">{children}</div>}
      </div>
    </header>
  );
}
