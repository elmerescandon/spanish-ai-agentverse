import type { ChangeType, ProposedChange } from "@/lib/demo/types";
import { formatPageRange } from "@/lib/demo/format";

const CHANGE_TYPE_LABEL: Record<ChangeType, string> = {
  add: "Add",
  modify: "Modify",
  remove: "Remove",
};

/** A protocol edit as strike-through before and highlighted after. */
export default function ChangeDiff({ change }: { change: ProposedChange }) {
  const meta = [
    change.change_type ? CHANGE_TYPE_LABEL[change.change_type] : null,
    change.path,
    change.section_title,
    formatPageRange(change.page),
  ].filter(Boolean);

  return (
    <div className="space-y-1.5">
      <p className="font-sans text-xs text-zinc-500">{meta.join(" · ")}</p>
      <p className="font-serif text-base text-zinc-900">
        {change.before && (
          <>
            <del className="text-rose-700 decoration-rose-300">
              {change.before}
            </del>{" "}
          </>
        )}
        {change.after && (
          <ins className="rounded-sm bg-emerald-50 text-emerald-800 no-underline">
            {change.after}
          </ins>
        )}
      </p>
      {change.rationale && (
        <p className="font-sans text-xs text-zinc-600">{change.rationale}</p>
      )}
    </div>
  );
}
