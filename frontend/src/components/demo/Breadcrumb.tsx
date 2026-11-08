"use client";

import { ChevronRight } from "lucide-react";

export interface BreadcrumbItem {
  label: string;
  onSelect?: () => void;
}

export default function Breadcrumb({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav aria-label="Zoom level" className="font-sans text-xs">
      <ol className="flex flex-wrap items-center gap-1.5">
        {items.map((item, index) => {
          const isLast = index === items.length - 1;
          return (
            <li key={`${item.label}-${index}`} className="flex items-center">
              {isLast ? (
                <span
                  aria-current="page"
                  className="font-medium text-zinc-900"
                >
                  {item.label}
                </span>
              ) : (
                <button
                  type="button"
                  onClick={item.onSelect}
                  className="cursor-pointer text-zinc-500 transition-colors hover:text-emerald-700"
                >
                  {item.label}
                </button>
              )}
              {!isLast && (
                <ChevronRight
                  className="ml-1.5 h-3 w-3 text-zinc-300"
                  strokeWidth={1.5}
                  aria-hidden
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
