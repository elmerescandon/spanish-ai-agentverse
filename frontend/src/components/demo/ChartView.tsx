import type { ReactNode } from "react";
import { formatWithUnit } from "@/lib/demo/format";
import type { Chart, ChartPoint, ChartSeries } from "@/lib/demo/types";

// One colour per series, in order; a chart rarely has more than three.
const SERIES_COLORS = [
  { bar: "bg-emerald-600", stroke: "stroke-emerald-600", band: "fill-emerald-600" },
  { bar: "bg-zinc-400", stroke: "stroke-zinc-400", band: "fill-zinc-400" },
  { bar: "bg-amber-500", stroke: "stroke-amber-500", band: "fill-amber-500" },
  { bar: "bg-sky-600", stroke: "stroke-sky-600", band: "fill-sky-600" },
  { bar: "bg-rose-500", stroke: "stroke-rose-500", band: "fill-rose-500" },
] as const;

// Beyond this many points, per-point value labels overlap on a phone.
const MAX_LABELLED_POINTS = 8;

type SeriesColor = (typeof SERIES_COLORS)[number];

function colorFor(seriesIndex: number): SeriesColor {
  return SERIES_COLORS[seriesIndex % SERIES_COLORS.length];
}

interface Scale {
  min: number;
  max: number;
  // Position of a value as a percentage of the plot width or height.
  toPercent: (value: number) => number;
}

function makeScale(values: number[], isZeroIncluded: boolean): Scale {
  const all = isZeroIncluded ? [0, ...values] : values;
  let min = Math.min(...all);
  let max = Math.max(...all);
  if (min === max) {
    // A flat series still needs a non-zero span to draw.
    min -= 1;
    max += 1;
  }
  return {
    min,
    max,
    toPercent: (value) => ((value - min) / (max - min)) * 100,
  };
}

function pointValues(point: ChartPoint): number[] {
  return [point.value, point.lower, point.upper].filter(
    (value): value is number => value != null
  );
}

function allValues(series: readonly ChartSeries[]): number[] {
  return series.flatMap((one) => one.points.flatMap(pointValues));
}

/** Point labels across every series, in first-seen order. */
function collectLabels(series: readonly ChartSeries[]): string[] {
  return [...new Set(series.flatMap((one) => one.points.map((p) => p.label)))];
}

function findPoint(
  series: ChartSeries,
  label: string
): ChartPoint | undefined {
  return series.points.find((point) => point.label === label);
}

function formatRange(point: ChartPoint, unit?: string | null): string {
  if (point.lower == null || point.upper == null) return "";
  return ` (${formatWithUnit(point.lower, unit)}–${formatWithUnit(
    point.upper,
    unit
  )})`;
}

/** Text equivalent of the chart, read out instead of the drawing. */
export function describeChart(chart: Chart): string {
  const seriesText = chart.series
    .filter((one) => one.points.length > 0)
    .map((one) => {
      const points = one.points
        .map(
          (point) =>
            `${point.label} ${formatWithUnit(point.value, chart.unit)}` +
            formatRange(point, chart.unit) +
            (point.annotation ? ` (${point.annotation})` : "")
        )
        .join(", ");
      return `${one.name}: ${points}`;
    })
    .join("; ");
  return `${chart.title}. ${seriesText}`;
}

function Annotation({ point }: { point?: ChartPoint }) {
  if (!point?.annotation) return null;
  return (
    <p className="font-sans text-[11px] italic text-zinc-500">
      {point.label}: {point.annotation}
    </p>
  );
}

function RangeWhisker({
  point,
  scale,
}: {
  point: ChartPoint;
  scale: Scale;
}) {
  if (point.lower == null || point.upper == null) return null;
  const left = scale.toPercent(Math.min(point.lower, point.upper));
  const right = scale.toPercent(Math.max(point.lower, point.upper));
  return (
    <span
      aria-hidden
      className="absolute top-1/2 h-2 -translate-y-1/2 border-x border-zinc-700"
      style={{ left: `${left}%`, width: `${right - left}%` }}
    >
      <span className="absolute inset-x-0 top-1/2 h-px bg-zinc-700" />
    </span>
  );
}

function ScaleFooter({ scale, unit }: { scale: Scale; unit?: string | null }) {
  return (
    <div className="flex justify-between font-sans text-[10px] tabular-nums text-zinc-400 sm:ml-40 sm:mr-24">
      <span>{formatWithUnit(scale.min, unit)}</span>
      <span>{formatWithUnit(scale.max, unit)}</span>
    </div>
  );
}

/** Label column + plot track + value column, stacked on a phone. */
function Row({
  label,
  value,
  children,
}: {
  label: string;
  value: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:items-center sm:gap-0">
      <span className="truncate font-sans text-xs text-zinc-600 sm:w-40 sm:shrink-0 sm:pr-3">
        {label}
      </span>
      <div className="flex flex-1 items-center gap-2">
        <div className="min-w-0 flex-1 space-y-0.5">{children}</div>
        <span className="w-22 shrink-0 text-right font-sans text-xs tabular-nums text-zinc-700">
          {value}
        </span>
      </div>
    </div>
  );
}

function BarChart({ chart }: { chart: Chart }) {
  const scale = makeScale(allValues(chart.series), true);
  const zero = scale.toPercent(0);
  return (
    <div className="space-y-2">
      {collectLabels(chart.series).map((label) => {
        const points = chart.series.map((one) => findPoint(one, label));
        return (
          <div key={label} className="space-y-0.5">
            <Row
              label={label}
              value={points
                .map((point) =>
                  point ? formatWithUnit(point.value, chart.unit) : "—"
                )
                .join(" / ")}
            >
              {points.map((point, seriesIndex) =>
                point ? (
                  <div
                    key={seriesIndex}
                    className="relative h-2.5 rounded-sm bg-zinc-100"
                  >
                    <span
                      className={`absolute inset-y-0 rounded-sm ${
                        colorFor(seriesIndex).bar
                      }`}
                      style={{
                        left: `${Math.min(zero, scale.toPercent(point.value))}%`,
                        width: `${Math.abs(
                          scale.toPercent(point.value) - zero
                        )}%`,
                      }}
                    />
                    <RangeWhisker point={point} scale={scale} />
                  </div>
                ) : null
              )}
            </Row>
            {points.map((point, seriesIndex) => (
              <Annotation key={seriesIndex} point={point} />
            ))}
          </div>
        );
      })}
      <ScaleFooter scale={scale} unit={chart.unit} />
    </div>
  );
}

function StackedBarChart({ chart }: { chart: Chart }) {
  const labels = collectLabels(chart.series);
  const totals = labels.map((label) =>
    chart.series.reduce(
      (sum, one) => sum + Math.max(0, findPoint(one, label)?.value ?? 0),
      0
    )
  );
  const scale = makeScale(totals, true);
  return (
    <div className="space-y-2">
      {labels.map((label, labelIndex) => {
        const points = chart.series.map((one) => findPoint(one, label));
        return (
          <div key={label} className="space-y-0.5">
            <Row
              label={label}
              value={formatWithUnit(totals[labelIndex], chart.unit)}
            >
              <div className="flex h-3 overflow-hidden rounded-sm bg-zinc-100">
                {points.map((point, seriesIndex) =>
                  point && point.value > 0 ? (
                    <span
                      key={seriesIndex}
                      title={`${chart.series[seriesIndex].name}: ${formatWithUnit(
                        point.value,
                        chart.unit
                      )}`}
                      className={`h-full ${colorFor(seriesIndex).bar}`}
                      style={{
                        width: `${
                          scale.toPercent(point.value) - scale.toPercent(0)
                        }%`,
                      }}
                    />
                  ) : null
                )}
              </div>
              <p className="font-sans text-[10px] tabular-nums text-zinc-400">
                {points
                  .map((point, seriesIndex) =>
                    point
                      ? `${chart.series[seriesIndex].name} ${formatWithUnit(
                          point.value,
                          chart.unit
                        )}`
                      : null
                  )
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </Row>
            {points.map((point, seriesIndex) => (
              <Annotation key={seriesIndex} point={point} />
            ))}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Each point is a signed step from the running total, starting at zero,
 * so the first point is the starting count and later ones add or remove.
 */
function WaterfallChart({ chart }: { chart: Chart }) {
  return (
    <div className="space-y-4">
      {chart.series.map((one) => {
        let running = 0;
        const steps = one.points.map((point) => {
          const from = running;
          running += point.value;
          return { point, from, to: running };
        });
        const scale = makeScale(
          steps.flatMap((step) => [step.from, step.to]),
          true
        );
        return (
          <div key={one.name} className="space-y-1.5">
            {chart.series.length > 1 && (
              <p className="font-sans text-xs text-zinc-500">{one.name}</p>
            )}
            {steps.map(({ point, from, to }, stepIndex) => {
              const isStart = stepIndex === 0;
              const barColor = isStart
                ? "bg-zinc-700"
                : point.value < 0
                  ? "bg-rose-400"
                  : "bg-emerald-600";
              const sign = !isStart && point.value > 0 ? "+" : "";
              return (
                <div key={`${point.label}-${stepIndex}`} className="space-y-0.5">
                  <Row
                    label={point.label}
                    value={
                      <>
                        {sign}
                        {formatWithUnit(point.value, chart.unit)}
                        {!isStart && (
                          <span className="block text-[10px] text-zinc-400">
                            → {formatWithUnit(to, chart.unit)}
                          </span>
                        )}
                      </>
                    }
                  >
                    <div className="relative h-3">
                      <span
                        className={`absolute inset-y-0 rounded-sm ${barColor}`}
                        style={{
                          left: `${scale.toPercent(Math.min(from, to))}%`,
                          width: `${Math.abs(
                            scale.toPercent(to) - scale.toPercent(from)
                          )}%`,
                        }}
                      />
                    </div>
                  </Row>
                  <Annotation point={point} />
                </div>
              );
            })}
            <ScaleFooter scale={scale} unit={chart.unit} />
          </div>
        );
      })}
    </div>
  );
}

/** Dot plot: each series as a dot per label, ranges as whiskers. */
function ComparisonChart({ chart }: { chart: Chart }) {
  const scale = makeScale(allValues(chart.series), false);
  return (
    <div className="space-y-2">
      {collectLabels(chart.series).map((label) => {
        const points = chart.series.map((one) => findPoint(one, label));
        return (
          <div key={label} className="space-y-0.5">
            <Row
              label={label}
              value={points
                .map((point) =>
                  point ? formatWithUnit(point.value, chart.unit) : "—"
                )
                .join(" / ")}
            >
              <div className="relative h-4">
                <span className="absolute inset-x-0 top-1/2 h-px bg-zinc-200" />
                {points.map((point, seriesIndex) =>
                  point ? (
                    <span key={seriesIndex}>
                      <RangeWhisker point={point} scale={scale} />
                      <span
                        className={`absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white ${
                          colorFor(seriesIndex).bar
                        }`}
                        style={{ left: `${scale.toPercent(point.value)}%` }}
                      />
                    </span>
                  ) : null
                )}
              </div>
            </Row>
            {points.map((point, seriesIndex) => (
              <Annotation key={seriesIndex} point={point} />
            ))}
          </div>
        );
      })}
      <ScaleFooter scale={scale} unit={chart.unit} />
    </div>
  );
}

/** Vertical plot area with min/max labels on the left edge. */
function VerticalPlot({
  scale,
  unit,
  labels,
  children,
}: {
  scale: Scale;
  unit?: string | null;
  labels: string[];
  children: ReactNode;
}) {
  // Keep x labels legible: show at most MAX_LABELLED_POINTS of them.
  const labelStep = Math.ceil(labels.length / MAX_LABELLED_POINTS);
  return (
    <div className="flex gap-2">
      <div className="flex h-40 flex-col justify-between font-sans text-[10px] tabular-nums text-zinc-400">
        <span>{formatWithUnit(scale.max, unit)}</span>
        <span>{formatWithUnit(scale.min, unit)}</span>
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="relative h-40 border-b border-l border-zinc-200">
          {children}
        </div>
        <div className="flex font-sans text-[10px] text-zinc-500">
          {labels.map((label, index) => (
            <span key={`${label}-${index}`} className="min-w-0 flex-1 truncate text-center">
              {index % labelStep === 0 ? label : ""}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function HistogramChart({ chart }: { chart: Chart }) {
  const labels = collectLabels(chart.series);
  const scale = makeScale(allValues(chart.series), true);
  const isLabelled = labels.length <= MAX_LABELLED_POINTS;
  return (
    <VerticalPlot scale={scale} unit={chart.unit} labels={labels}>
      <div className="absolute inset-0 flex items-end gap-px">
        {labels.map((label) => (
          <div key={label} className="flex h-full flex-1 items-end gap-px">
            {chart.series.map((one, seriesIndex) => {
              const point = findPoint(one, label);
              if (!point) return null;
              return (
                <div
                  key={seriesIndex}
                  className="relative flex h-full flex-1 items-end"
                >
                  <span
                    title={`${label}: ${formatWithUnit(point.value, chart.unit)}`}
                    className={`w-full ${colorFor(seriesIndex).bar}`}
                    style={{ height: `${scale.toPercent(point.value)}%` }}
                  />
                  {isLabelled && (
                    <span
                      className="absolute inset-x-0 text-center font-sans text-[10px] tabular-nums text-zinc-600"
                      style={{ bottom: `${scale.toPercent(point.value)}%` }}
                    >
                      {formatWithUnit(point.value, chart.unit)}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </VerticalPlot>
  );
}

function LineChart({ chart }: { chart: Chart }) {
  const labels = collectLabels(chart.series);
  const scale = makeScale(allValues(chart.series), false);
  const isLabelled = labels.length <= MAX_LABELLED_POINTS;
  // Points sit at the centre of equal-width label slots.
  const xPercent = (label: string): number =>
    ((labels.indexOf(label) + 0.5) / labels.length) * 100;
  const yPercent = (value: number): number => 100 - scale.toPercent(value);

  return (
    <VerticalPlot scale={scale} unit={chart.unit} labels={labels}>
      <svg
        aria-hidden
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full overflow-visible"
      >
        {chart.series.map((one, seriesIndex) => {
          const color = colorFor(seriesIndex);
          const ranged = one.points.filter(
            (point) => point.lower != null && point.upper != null
          );
          const band =
            ranged.length > 1
              ? [
                  ...ranged.map(
                    (p) => `${xPercent(p.label)},${yPercent(p.upper!)}`
                  ),
                  ...[...ranged]
                    .reverse()
                    .map((p) => `${xPercent(p.label)},${yPercent(p.lower!)}`),
                ].join(" ")
              : null;
          return (
            <g key={one.name}>
              {band && (
                <polygon points={band} className={`${color.band} opacity-15`} />
              )}
              <polyline
                points={one.points
                  .map((p) => `${xPercent(p.label)},${yPercent(p.value)}`)
                  .join(" ")}
                fill="none"
                strokeWidth={1.5}
                vectorEffect="non-scaling-stroke"
                className={color.stroke}
              />
            </g>
          );
        })}
      </svg>
      {chart.series.map((one, seriesIndex) =>
        one.points.map((point) => (
          <span
            key={`${one.name}-${point.label}`}
            title={`${one.name} · ${point.label}: ${formatWithUnit(
              point.value,
              chart.unit
            )}`}
            className="absolute -translate-x-1/2 translate-y-1/2"
            style={{
              left: `${xPercent(point.label)}%`,
              bottom: `${scale.toPercent(point.value)}%`,
            }}
          >
            <span
              className={`block h-2 w-2 rounded-full ring-2 ring-white ${
                colorFor(seriesIndex).bar
              }`}
            />
            {isLabelled && (
              <span className="absolute bottom-full left-1/2 -translate-x-1/2 whitespace-nowrap pb-0.5 font-sans text-[10px] tabular-nums text-zinc-600">
                {formatWithUnit(point.value, chart.unit)}
              </span>
            )}
          </span>
        ))
      )}
    </VerticalPlot>
  );
}

const CHART_RENDERERS: Record<
  Chart["kind"],
  (props: { chart: Chart }) => ReactNode
> = {
  bar: BarChart,
  stacked_bar: StackedBarChart,
  waterfall: WaterfallChart,
  line: LineChart,
  histogram: HistogramChart,
  comparison: ComparisonChart,
};

/**
 * Any agent chart drawn with plain CSS/SVG. The drawing is one image to
 * assistive tech, named by a text version of every value.
 */
export default function ChartView({ chart }: { chart: Chart }) {
  const series = chart.series.filter((one) => one.points.length > 0);
  if (series.length === 0) return null;
  const visibleChart = { ...chart, series };
  // An unknown future kind still shows its numbers as plain bars.
  const Renderer = CHART_RENDERERS[chart.kind] ?? BarChart;
  const annotations = series.flatMap((one) =>
    one.points.filter((point) => point.annotation)
  );
  const isLineOrHistogram = chart.kind === "line" || chart.kind === "histogram";

  return (
    <figure className="space-y-2">
      <figcaption className="space-y-0.5">
        <span className="block font-serif text-sm text-zinc-900">
          {chart.title}
        </span>
        {chart.description && (
          <span className="block font-sans text-xs text-zinc-500">
            {chart.description}
          </span>
        )}
      </figcaption>
      {/* Waterfalls name each series above its own block instead. */}
      {series.length > 1 && chart.kind !== "waterfall" && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 font-sans text-[11px] text-zinc-600">
          {series.map((one, seriesIndex) => (
            <li key={one.name} className="inline-flex items-center gap-1.5">
              <span
                aria-hidden
                className={`h-2 w-2 rounded-full ${colorFor(seriesIndex).bar}`}
              />
              {one.name}
            </li>
          ))}
        </ul>
      )}
      <div role="img" aria-label={describeChart(visibleChart)} className="space-y-1">
        {chart.y_label && (
          <p className="font-sans text-[10px] text-zinc-400">{chart.y_label}</p>
        )}
        <Renderer chart={visibleChart} />
        {chart.x_label && (
          <p className="text-right font-sans text-[10px] text-zinc-400">
            {chart.x_label}
          </p>
        )}
      </div>
      {/* Bar-style charts annotate inline; vertical ones list notes here. */}
      {isLineOrHistogram && annotations.length > 0 && (
        <div className="space-y-0.5">
          {annotations.map((point) => (
            <Annotation key={point.label} point={point} />
          ))}
        </div>
      )}
    </figure>
  );
}
