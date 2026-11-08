import { formatCellValue } from "@/lib/demo/format";
import type { DataTable } from "@/lib/demo/types";

/** One agent table; scrolls inside its own box so the page never does. */
export default function DataTableView({ table }: { table: DataTable }) {
  if (table.columns.length === 0) return null;

  return (
    <figure className="space-y-1.5">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse font-sans text-xs">
          <caption className="pb-1.5 text-left">
            <span className="block font-serif text-sm text-zinc-900">
              {table.title}
            </span>
            {table.description && (
              <span className="block text-xs text-zinc-500">
                {table.description}
              </span>
            )}
          </caption>
          <thead>
            <tr className="border-b border-zinc-200">
              {table.columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className="whitespace-nowrap px-2 py-1.5 text-left font-medium text-zinc-500 first:pl-0"
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
            {table.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {table.columns.map((column) => (
                  <td
                    key={column.key}
                    className="px-2 py-1.5 tabular-nums text-zinc-800 first:pl-0"
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
    </figure>
  );
}
