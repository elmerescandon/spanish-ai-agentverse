"use client";

import { useState, type ReactNode } from "react";
import SlideDown from "./SlideDown";

export interface CollapsibleProps {
  title: string;
  // Anchor target for "Jump to" links.
  id?: string;
  // Shown after the title while collapsed, e.g. "(3)".
  count?: number;
  isInitiallyOpen?: boolean;
  children: ReactNode;
}

/**
 * Titled section with a plain Expand/Collapse text button; the body only
 * mounts while open.
 */
export default function Collapsible({
  title,
  id,
  count,
  isInitiallyOpen = false,
  children,
}: CollapsibleProps) {
  const [isOpen, setIsOpen] = useState(isInitiallyOpen);

  return (
    <section id={id} aria-label={title} className="scroll-mt-32">
      <h2 className="flex items-baseline gap-3 font-serif text-lg font-normal text-zinc-900">
        <span>
          {title}
          {count !== undefined && (
            <span className="ml-1.5 font-sans text-sm tabular-nums text-zinc-400">
              ({count})
            </span>
          )}
        </span>
        <button
          type="button"
          aria-expanded={isOpen}
          aria-label={title}
          onClick={() => setIsOpen((previous) => !previous)}
          className="cursor-pointer font-sans text-sm text-zinc-500 underline underline-offset-4 hover:text-zinc-900"
        >
          <span aria-hidden>{isOpen ? "Collapse" : "Expand"}</span>
        </button>
      </h2>
      <SlideDown isOpen={isOpen} className="pt-4">
        {children}
      </SlideDown>
    </section>
  );
}
