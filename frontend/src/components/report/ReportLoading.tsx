const METRIC_COUNT = 4;
const CHANGE_ROW_COUNT = 2;
const TABLE_ROW_COUNT = 5;

function Bar({ className }: { className: string }) {
  return <div className={`report-shimmer rounded ${className}`} />;
}

/**
 * Placeholder shaped like the report, so the page keeps its layout while
 * the review loads and the real content settles into the same places.
 */
export default function ReportLoading() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="report-loading space-y-12 pb-16 pt-8"
    >
      <span className="sr-only">Loading report…</span>
      <div aria-hidden className="space-y-3">
        <Bar className="h-3 w-36" />
        <Bar className="h-9 w-3/4" />
        <Bar className="h-3.5 w-56" />
      </div>

      <div
        aria-hidden
        className="grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-3 lg:grid-cols-4"
      >
        {Array.from({ length: METRIC_COUNT }, (_, index) => (
          <div key={index} className="space-y-2">
            <Bar className="h-3.5 w-24" />
            <Bar className="h-7 w-12" />
          </div>
        ))}
      </div>

      <div aria-hidden className="space-y-4">
        <Bar className="h-5 w-40" />
        <div className="divide-y divide-zinc-100 border-y border-zinc-100">
          {Array.from({ length: CHANGE_ROW_COUNT }, (_, index) => (
            <div key={index} className="space-y-2 py-4">
              <Bar className="h-3.5 w-1/3" />
              <Bar className="h-3.5 w-2/3" />
            </div>
          ))}
        </div>
      </div>

      <div aria-hidden className="space-y-4">
        <Bar className="h-5 w-36" />
        <div className="divide-y divide-zinc-100 border-y border-zinc-100">
          {Array.from({ length: TABLE_ROW_COUNT }, (_, index) => (
            <div key={index} className="grid grid-cols-4 gap-6 py-3">
              <Bar className="h-3.5" />
              <Bar className="h-3.5" />
              <Bar className="h-3.5 w-8" />
              <Bar className="h-3.5 w-14" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
