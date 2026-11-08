import { ExternalLink } from "lucide-react";
import { formatNumber } from "@/lib/demo/format";
import type { DataSource } from "@/lib/demo/types";

/** Which datasets the agent read, with version and size for provenance. */
export default function DataSourceList({
  sources,
}: {
  sources: readonly DataSource[];
}) {
  if (sources.length === 0) return null;

  return (
    <ul className="divide-y divide-zinc-200/60">
      {sources.map((source) => {
        const meta = [
          source.source.toUpperCase(),
          source.version ? `v${source.version.replace(/^v/i, "")}` : null,
          source.record_count != null
            ? `${formatNumber(source.record_count)} records`
            : null,
        ].filter(Boolean);
        return (
          <li key={`${source.source}-${source.name}`} className="py-2">
            <p className="flex flex-wrap items-baseline gap-x-2 font-sans text-sm text-zinc-900">
              {source.url ? (
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 underline decoration-zinc-300 underline-offset-4 transition-colors hover:text-emerald-700"
                >
                  {source.name}
                  <ExternalLink className="h-3 w-3" aria-hidden />
                </a>
              ) : (
                <span>{source.name}</span>
              )}
              <span className="text-xs text-zinc-400">
                {meta.join(" · ")}
              </span>
            </p>
            {source.description && (
              <p className="font-sans text-xs text-zinc-500">
                {source.description}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
