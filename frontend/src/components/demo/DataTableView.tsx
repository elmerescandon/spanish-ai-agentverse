"use client";

import { useState } from "react";
import {
  formatCellValue,
  formatRowCount,
  isNumericColumn,
} from "@/lib/demo/format";
import type { DataTable } from "@/lib/demo/types";

// Longer tables show this many rows until the reader expands them.
const MAX_COLLAPSED_ROWS = 10;

/** Plain text button that reveals secondary content; never hides silently. */
export function ExpandButton({
  isOpen,
  onToggle,
  label,
}: {
  isOpen: boolean;
  onToggle: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      aria-expanded={isOpen}
      onClick={onToggle}
      className="cursor-pointer font-sans text-xs text-zinc-500 underline decoration-zinc-300 underline-offset-2 hover:text-zinc-800"
    >
      {isOpen ? "Show less" : label}
    </button>
  );
}

/** One agent table; scrolls inside its own box so the page never does. */
export default function DataTableView({ table }: { table: DataTable }) {
  const [isExpanded, setIsExpanded] = useState(false);
  if (table.columns.length === 0) return null;

  const isLong = table.rows.length > MAX_COLLAPSED_ROWS;
  const visibleRows =
    isLong && !isExpanded
      ? table.rows.slice(0, MAX_COLLAPSED_ROWS)
      : table.rows;
  const numericKeys = new Set(
    table.columns
      .filter((column) =>
        isNumericColumn(table.rows.map((row) => row[column.key])),
      )
      .map((column) => column.key),
  );
  const alignment = (key: string) =>
    numericKeys.has(key) ? "text-right tabular-nums" : "text-left";

  return (
    <figure className="space-y-1.5">
      <figcaption className="space-y-0.5">
        <span className="block font-sans text-sm font-medium text-zinc-900">
          {table.title}
        </span>
        {table.description && (
          <span className="block font-sans text-xs text-zinc-500">
            {table.description}
          </span>
        )}
      </figcaption>
      <div className="overflow-x-auto">
        <table
          aria-label={table.title}
          className="w-full border-collapse font-sans text-xs"
        >
          <thead>
            <tr className="border-b border-zinc-300">
              {table.columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={`whitespace-nowrap px-2 py-1.5 font-medium text-zinc-600 first:pl-0 last:pr-0 ${alignment(column.key)}`}
                >
                  {column.label}
                  {column.unit && (
                    <>
                      {" "}
                      <span className="font-normal text-zinc-400">
                        ({column.unit})
                      </span>
                    </>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-200/60">
            {visibleRows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {table.columns.map((column) => (
                  <td
                    key={column.key}
                    className={`px-2 py-1.5 align-top text-zinc-800 first:pl-0 last:pr-0 ${alignment(column.key)}`}
                  >
                    {formatCellValue(row[column.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table.rows.length === 0 && (
        <p className="font-sans text-xs text-zinc-400">No rows.</p>
      )}
      {isLong && (
        <ExpandButton
          isOpen={isExpanded}
          onToggle={() => setIsExpanded((previous) => !previous)}
          label={`Show all ${formatRowCount(table.rows.length)}`}
        />
      )}
    </figure>
  );
}
