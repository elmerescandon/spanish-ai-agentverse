import type { ProtocolLocation } from "./types";

// Pure display helpers for the demo views. Every input may be missing:
// the backend sends null for unknown values and mocks may omit fields.

const MS_PER_SECOND = 1000;
const SECONDS_PER_MINUTE = 60;

const numberFormatter = new Intl.NumberFormat("en-GB", {
  maximumFractionDigits: 2,
});

export function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

/** "12 wk", "38%": units that read as a suffix sit flush to the number. */
export function formatWithUnit(
  value: number | string,
  unit?: string | null
): string {
  const text = typeof value === "number" ? formatNumber(value) : value;
  if (!unit) return text;
  return unit === "%" ? `${text}%` : `${text} ${unit}`;
}

/** "850 ms", "4.2 s", "2 min 5 s". */
export function formatDuration(durationMs: number): string {
  if (durationMs < MS_PER_SECOND) return `${Math.round(durationMs)} ms`;
  const seconds = durationMs / MS_PER_SECOND;
  if (seconds < SECONDS_PER_MINUTE) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / SECONDS_PER_MINUTE);
  const remainder = Math.round(seconds % SECONDS_PER_MINUTE);
  return remainder > 0 ? `${minutes} min ${remainder} s` : `${minutes} min`;
}

/** Duration from the explicit field, else from the two timestamps. */
export function resolveDurationMs(
  durationMs?: number | null,
  startedAt?: string | null,
  completedAt?: string | null
): number | null {
  if (durationMs != null) return durationMs;
  if (!startedAt || !completedAt) return null;
  const elapsed = Date.parse(completedAt) - Date.parse(startedAt);
  return Number.isFinite(elapsed) && elapsed >= 0 ? elapsed : null;
}

/** Confidence arrives as a 0-1 score; "0.92" reads as "92%". */
export function formatConfidence(confidence: number): string {
  const percent = confidence <= 1 ? confidence * 100 : confidence;
  return `${Math.round(percent)}%`;
}

/** "10:31:04" in the viewer's clock, or null for an unparseable value. */
export function formatClockTime(timestamp: string): string | null {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatPageRange(
  startPage?: number | null,
  endPage?: number | null
): string | null {
  if (startPage == null) return endPage == null ? null : `p. ${endPage}`;
  if (endPage == null || endPage === startPage) return `p. ${startPage}`;
  return `pp. ${startPage}–${endPage}`;
}

/** Section, pages and criterion as separate labels, empty ones dropped. */
export function formatLocationParts(
  location?: ProtocolLocation | null
): string[] {
  if (!location) return [];
  const section = [location.section_heading, location.section_title]
    .filter(Boolean)
    .join(" ");
  return [
    section ? `§ ${section}` : null,
    formatPageRange(location.start_page, location.end_page),
    location.criterion_id ?? null,
  ].filter((part): part is string => Boolean(part));
}

/** Table cells hold arbitrary JSON; show scalars plainly, others as JSON. */
export function formatCellValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

/** "1 row", "48 rows". */
export function formatRowCount(count: number): string {
  return count === 1 ? "1 row" : `${count} rows`;
}

/** A column is numeric when it has values and every present one is a number. */
export function isNumericColumn(values: readonly unknown[]): boolean {
  const present = values.filter(
    (value) => value !== null && value !== undefined && value !== ""
  );
  return present.length > 0 && present.every((v) => typeof v === "number");
}
