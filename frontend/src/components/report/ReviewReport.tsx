import ChangeDiff from "@/components/demo/ChangeDiff";
import DataTableView from "@/components/demo/DataTableView";
import MetricList from "@/components/demo/MetricList";
import SectionTitle from "@/components/demo/SectionTitle";
import type { ProtocolFieldsResponse } from "@/lib/api";
import { formatWithUnit } from "@/lib/demo/format";
import type { DataTable, Metric } from "@/lib/demo/types";
import {
  changedFieldNames,
  fieldLabel,
  groupFieldsBySection,
  type FieldSection,
} from "@/lib/report";

const DATE_FORMAT: Intl.DateTimeFormatOptions = {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
};

function formatDate(timestamp: string): string {
  return new Date(timestamp).toLocaleString("en-GB", DATE_FORMAT);
}

function reportMetrics(review: ProtocolFieldsResponse): Metric[] {
  const changedCount = changedFieldNames(review.changes).size;
  return [
    {
      label: "Changes accepted",
      value: String(review.changes.length),
      tone: review.changes.length > 0 ? "good" : "neutral",
    },
    { label: "Fields changed", value: String(changedCount) },
    { label: "Fields stored", value: String(review.fields.length) },
    { label: "Protocol pages", value: String(review.page_count) },
  ];
}

function sectionTable(
  section: FieldSection,
  changedFields: ReadonlySet<string>
): DataTable {
  return {
    table_id: `fields-${section.key}`,
    title: section.title,
    description: `${section.fields.length} fields`,
    columns: [
      { key: "field", label: "Field" },
      { key: "value", label: "Value" },
      { key: "page", label: "Page" },
      { key: "review", label: "Review" },
    ],
    rows: section.fields.map((field) => ({
      field: fieldLabel(field.field),
      value: formatWithUnit(field.value, field.unit),
      page: field.page ?? "",
      review: changedFields.has(field.field) ? "Changed" : "",
    })),
  };
}

/** The final review of one protocol: what changed, then every field. */
export default function ReviewReport({
  review,
}: {
  review: ProtocolFieldsResponse;
}) {
  const changedFields = changedFieldNames(review.changes);
  const sections = groupFieldsBySection(review.fields);

  return (
    <article className="report-reveal space-y-12 pb-16 pt-8">
      <div className="space-y-2">
        <p className="font-sans text-xs uppercase tracking-wider text-zinc-500">
          Final protocol review
        </p>
        <h1 className="font-serif text-4xl font-normal tracking-tight text-zinc-900">
          {review.title}
        </h1>
        <p className="font-sans text-sm text-zinc-500">
          {review.protocol_id} · Uploaded {formatDate(review.uploaded_at)}
        </p>
      </div>

      <MetricList metrics={reportMetrics(review)} ariaLabel="Review summary" />

      <section aria-label="Accepted changes" className="space-y-4">
        <SectionTitle>Accepted changes</SectionTitle>
        {review.changes.length === 0 ? (
          <p className="font-sans text-sm text-zinc-500">
            No changes accepted yet. Values accepted during the review show
            up here.
          </p>
        ) : (
          <ol className="divide-y divide-zinc-100 border-y border-zinc-100">
            {review.changes.map((change) => (
              <li key={change.change_id} className="space-y-1 py-4">
                <ChangeDiff
                  change={{
                    path: fieldLabel(change.field),
                    before: change.old_value ?? "",
                    after: change.new_value,
                    change_type: change.old_value === null ? "add" : "modify",
                    rationale: change.rationale,
                  }}
                />
                <p className="font-sans text-xs text-zinc-400">
                  Accepted {formatDate(change.changed_at)}
                </p>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-label="Protocol fields" className="space-y-6">
        <SectionTitle>Protocol fields</SectionTitle>
        {sections.length === 0 ? (
          <p className="font-sans text-sm text-zinc-500">No fields stored.</p>
        ) : (
          sections.map((section) => (
            <DataTableView
              key={section.key}
              table={sectionTable(section, changedFields)}
            />
          ))
        )}
      </section>
    </article>
  );
}
