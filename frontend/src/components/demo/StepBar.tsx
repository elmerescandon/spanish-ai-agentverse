"use client";

import { useEffect } from "react";
import {
  AlertCircle,
  Check,
  ChevronLeft,
  ChevronRight,
  Loader2,
} from "lucide-react";

export type StepBarState = "done" | "running" | "pending" | "error";

export interface StepBarItem {
  id: string;
  title: string;
  state: StepBarState;
}

export interface StepBarProps {
  items: StepBarItem[];
  activeId: string;
  onSelect: (id: string) => void;
}

const STATE_LABELS: Record<StepBarState, string> = {
  done: "Done",
  running: "Running",
  pending: "Pending",
  error: "Failed",
};

function isTextEntry(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  return (
    element?.tagName === "INPUT" ||
    element?.tagName === "TEXTAREA" ||
    element?.isContentEditable === true
  );
}

// A failed step can be opened too, so its error is readable.
function isOpenable(item: StepBarItem | undefined): boolean {
  return item?.state === "done" || item?.state === "error";
}

/** Index of the nearest done step in a direction, or -1 if none. */
function neighbourIndex(
  items: StepBarItem[],
  activeIndex: number,
  direction: 1 | -1
): number {
  const index = activeIndex + direction;
  return isOpenable(items[index]) ? index : -1;
}

function circleClass(
  state: StepBarState,
  isActive: boolean,
  isReached: boolean
): string {
  if (isActive) {
    return "border-zinc-900 bg-zinc-900 text-white";
  }
  if (isReached) return "border-zinc-400 bg-white text-zinc-700";
  if (state === "error") return "border-rose-300 bg-white text-rose-600";
  if (state === "done") {
    return "border-zinc-300 bg-white text-zinc-600 group-hover:border-zinc-900";
  }
  if (state === "running") return "border-zinc-200 bg-white text-zinc-500";
  return "border-zinc-200 bg-white text-zinc-300";
}

/**
 * Circle stepper over the sequential flow. Only done steps can be opened;
 * circles and connectors fill emerald up to the step being viewed.
 */
export default function StepBar({
  items,
  activeId,
  onSelect,
}: StepBarProps) {
  const activeIndex = items.findIndex((item) => item.id === activeId);
  const previousIndex = neighbourIndex(items, activeIndex, -1);
  const nextIndex = neighbourIndex(items, activeIndex, 1);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isTextEntry(event.target)) return;
      const target =
        event.key === "ArrowLeft"
          ? previousIndex
          : event.key === "ArrowRight"
            ? nextIndex
            : -1;
      if (target >= 0) onSelect(items[target].id);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [items, previousIndex, nextIndex, onSelect]);

  const arrowClass =
    "cursor-pointer rounded-full p-1.5 text-zinc-500 transition-colors hover:text-zinc-900 disabled:cursor-default disabled:opacity-30 disabled:hover:text-zinc-500";

  return (
    <nav
      aria-label="Pipeline steps"
      className="sticky top-18 z-20 -mx-2 border-b border-zinc-100 bg-white/95 px-2 pb-3 pt-2 backdrop-blur-sm"
    >
      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-label="Previous step"
          disabled={previousIndex < 0}
          onClick={() => onSelect(items[previousIndex].id)}
          className={arrowClass}
        >
          <ChevronLeft className="h-4 w-4" strokeWidth={1.5} />
        </button>

        <ol className="flex flex-1">
          {items.map((item, index) => {
            const isActive = index === activeIndex;
            // Progress follows the tab being viewed, not run completion.
            const isReached = index <= activeIndex;
            return (
              <li key={item.id} className="relative flex-1">
                {index > 0 && (
                  <span
                    aria-hidden
                    className={`absolute right-1/2 top-3.5 z-0 h-px w-full transition-colors duration-500 ${
                      isReached ? "bg-zinc-400" : "bg-zinc-200"
                    }`}
                  />
                )}
                <button
                  type="button"
                  aria-label={item.title}
                  aria-current={isActive ? "step" : undefined}
                  disabled={!isOpenable(item)}
                  onClick={() => onSelect(item.id)}
                  className="group relative z-10 flex w-full cursor-pointer flex-col items-center gap-1.5 font-sans disabled:cursor-default"
                >
                  <span
                    className={`flex h-7 w-7 items-center justify-center rounded-full border text-xs transition-all duration-300 ${circleClass(
                      item.state,
                      isActive,
                      isReached
                    )}`}
                  >
                    {item.state === "running" ? (
                      <Loader2
                        className="h-3.5 w-3.5 animate-spin"
                        strokeWidth={1.5}
                        aria-hidden
                      />
                    ) : item.state === "error" ? (
                      <AlertCircle
                        className="h-3.5 w-3.5"
                        strokeWidth={1.5}
                        aria-hidden
                      />
                    ) : isReached && !isActive ? (
                      <Check
                        className="h-3.5 w-3.5"
                        strokeWidth={2}
                        aria-hidden
                      />
                    ) : (
                      index + 1
                    )}
                  </span>
                  <span
                    className={`max-w-full truncate px-1 text-xs transition-colors ${
                      isActive
                        ? "font-medium text-zinc-900"
                        : item.state === "done" || item.state === "error"
                          ? "text-zinc-500 group-hover:text-zinc-900"
                          : "text-zinc-300"
                    }`}
                  >
                    {item.title}
                  </span>
                  <span className="sr-only">{STATE_LABELS[item.state]}</span>
                </button>
              </li>
            );
          })}
        </ol>

        <button
          type="button"
          aria-label="Next step"
          disabled={nextIndex < 0}
          onClick={() => onSelect(items[nextIndex].id)}
          className={arrowClass}
        >
          <ChevronRight className="h-4 w-4" strokeWidth={1.5} />
        </button>
      </div>
    </nav>
  );
}
