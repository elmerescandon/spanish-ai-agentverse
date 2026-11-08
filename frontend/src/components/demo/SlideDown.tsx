"use client";

import { useEffect, useState, type ReactNode } from "react";

// Matches duration-300 below; unmounts the body if transitionend never
// fires (reduced motion, jsdom).
const SLIDE_DURATION_MS = 300;

export interface SlideDownProps {
  isOpen: boolean;
  id?: string;
  className?: string;
  children: ReactNode;
}

/**
 * Body that slides open and closed by animating its height. It mounts on
 * open and unmounts once the close finishes, so heavy content (charts,
 * tables) costs nothing while folded. Hidden from assistive tech while
 * closing.
 */
export default function SlideDown({
  isOpen,
  id,
  className,
  children,
}: SlideDownProps) {
  const [isMounted, setIsMounted] = useState(isOpen);
  const [isExpanded, setIsExpanded] = useState(isOpen);

  // Adjusting state during render: mount at once on open, start the
  // close at once so it is hidden before the transition ends.
  if (isOpen && !isMounted) setIsMounted(true);
  if (!isOpen && isExpanded) setIsExpanded(false);

  useEffect(() => {
    if (isOpen) {
      // One frame at zero height first, so the height transition runs.
      const frame = requestAnimationFrame(() => setIsExpanded(true));
      return () => cancelAnimationFrame(frame);
    }
    const timer = setTimeout(() => setIsMounted(false), SLIDE_DURATION_MS);
    return () => clearTimeout(timer);
  }, [isOpen]);

  if (!isMounted) return null;

  return (
    <div
      id={id}
      aria-hidden={!isOpen}
      className={`grid transition-[grid-template-rows,opacity] duration-300 ease-out motion-reduce:transition-none ${
        isExpanded ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
      }`}
    >
      <div className="min-h-0 overflow-hidden">
        <div className={className}>{children}</div>
      </div>
    </div>
  );
}
