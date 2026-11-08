"use client";

import { useEffect } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

export type StepBarState = "done" | "running" | "pending";

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
};

function isTextEntry(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  return (
    element?.tagName === "INPUT" ||
    element?.tagName === "TEXTAREA" ||
    element?.isContentEditable === true
  );
}

/** Index of the nearest done step in a direction, or -1 if none. */
function neighbourIndex(
  items: StepBarItem[],
  activeIndex: number,
  direction: 1 | -1
): number {
  const index = activeIndex + direction;
  return items[index]?.state === "done" ? index : -1;
}

/**
 * Compact progress bar over the sequential flow. Only done steps can be
 * opened; a thin line fills emerald as steps complete.
 */
export default function StepBar({
  items,
  activeId,
  onSelect,
}: StepBarProps) {
  const activeIndex = items.findIndex((item) => item.id === activeId);
  const previousIndex = neighbourIndex(items, activeIndex, -1);
  const nextIndex = neighbourIndex(items, activeIndex, 1);
  const doneCount = items.filter((item) => item.state === "done").length;
  const fillPercent = items.length ? (doneCount / items.length) * 100 : 0;

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
      className="sticky top-0 z-10 -mx-2 bg-white/95 px-2 pb-3 pt-2 backdrop-blur-sm"
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

        <div className="relative flex-1">
          <div
            aria-hidden
            className="absolute inset-x-0 top-0 h-px bg-zinc-200"
          >
            <div
              className="h-px bg-emerald-500 transition-all duration-500"
              style={{ width: `${fillPercent}%` }}
            />
          </div>
          <ol className="grid grid-cols-4 gap-2 pt-2">
            {items.map((item, index) => {
              const isActive = item.id === activeId;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    aria-label={item.title}
                    aria-current={isActive ? "step" : undefined}
                    disabled={item.state !== "done"}
                    onClick={() => onSelect(item.id)}
                    className={`w-full cursor-pointer text-left font-sans transition-colors disabled:cursor-default ${
                      isActive ? "text-zinc-900" : "text-zinc-500"
                    }`}
                  >
                    <span className="flex items-baseline gap-1.5 text-xs">
                      <span className="font-serif text-emerald-800">
                        {index + 1}
                      </span>
                      <span
                        className={`truncate ${
                          isActive ? "font-medium" : ""
                        }`}
                      >
                        {item.title}
                      </span>
                    </span>
                    <span className="block text-[11px] text-zinc-400">
                      {STATE_LABELS[item.state]}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </div>

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
