"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import SlideDown from "./SlideDown";

export interface CollapsibleProps {
  title: string;
  // Shown after the title while collapsed, e.g. "(3)".
  count?: number;
  isInitiallyOpen?: boolean;
  children: ReactNode;
}

/**
 * Titled section whose body slides open and only mounts once opened, so heavy content
 * (charts, tables) never crowds the scannable overview by default.
 */
export default function Collapsible({
  title,
  count,
  isInitiallyOpen = false,
  children,
}: CollapsibleProps) {
  const [isOpen, setIsOpen] = useState(isInitiallyOpen);
  const Chevron = isOpen ? ChevronDown : ChevronRight;

  return (
    <section aria-label={title}>
      <h2>
        <button
          type="button"
          aria-expanded={isOpen}
          onClick={() => setIsOpen((previous) => !previous)}
          className="inline-flex cursor-pointer items-center gap-1 font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800 transition-colors hover:text-emerald-600"
        >
          <Chevron className="h-3.5 w-3.5" aria-hidden />
          {title}
          {count !== undefined && (
            <span className="font-normal tabular-nums text-zinc-400">
              ({count})
            </span>
          )}
        </button>
      </h2>
      <SlideDown isOpen={isOpen} className="pt-3">
        {children}
      </SlideDown>
    </section>
  );
}
