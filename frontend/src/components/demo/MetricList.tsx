import { formatWithUnit } from "@/lib/demo/format";
import type { Metric, MetricTone } from "@/lib/demo/types";

const TONE_CLASSES: Record<MetricTone, string> = {
  neutral: "text-zinc-900",
  good: "text-emerald-700",
  warn: "text-amber-700",
  risk: "text-rose-700",
};

const VALUE_SIZE_CLASSES = {
  large: "text-lg",
  small: "text-base",
} as const;

// Benchmarks share the metric's unit; append it unless already written.
function benchmarkValue(value: string, unit?: string | null): string {
  return unit && !value.endsWith(unit) ? formatWithUnit(value, unit) : value;
}

export interface MetricListProps {
  metrics: readonly Metric[];
  size?: keyof typeof VALUE_SIZE_CLASSES;
  ariaLabel?: string;
}

/** Inline figures: value, unit and label, then peer benchmarks if any. */
export default function MetricList({
  metrics,
  size = "large",
  ariaLabel,
}: MetricListProps) {
  if (metrics.length === 0) return null;

  return (
    <dl aria-label={ariaLabel} className="flex flex-wrap gap-x-8 gap-y-3">
      {metrics.map((metric) => {
        const benchmarks = metric.benchmarks ?? [];
        return (
          <div
            key={metric.metric_id ?? metric.label}
            className="max-w-[16rem] space-y-0.5"
          >
            <div className="flex flex-wrap items-baseline gap-x-1.5">
              <dd
                className={`font-serif font-normal ${
                  VALUE_SIZE_CLASSES[size]
                } ${TONE_CLASSES[metric.tone ?? "neutral"]}`}
              >
                <span>{metric.value}</span>
                {metric.unit && (
                  <span className="ml-0.5 font-sans text-xs">
                    {metric.unit}
                  </span>
                )}
              </dd>
              <dt className="font-sans text-xs text-zinc-500">
                {metric.label}
              </dt>
            </div>
            {benchmarks.length > 0 && (
              <dd className="font-sans text-[11px] text-zinc-400">
                {benchmarks
                  .map(
                    (benchmark) =>
                      `${benchmark.label} ${benchmarkValue(
                        benchmark.value,
                        metric.unit
                      )}`
                  )
                  .join(" · ")}
              </dd>
            )}
            {metric.description && (
              <dd className="font-sans text-[11px] leading-snug text-zinc-400">
                {metric.description}
              </dd>
            )}
          </div>
        );
      })}
    </dl>
  );
}
