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
      <p className="font-sans text-sm leading-relaxed text-zinc-900">
        {change.before && (
          <>
            <del className="text-zinc-500 decoration-rose-400">
              {change.before}
            </del>{" "}
          </>
        )}
        {change.after && (
          <ins className="font-medium text-zinc-900 underline decoration-emerald-500 underline-offset-4">
            {change.after}
          </ins>
        )}
      </p>
      {change.rationale && (
        <p className="font-sans text-sm text-zinc-600">{change.rationale}</p>
      )}
    </div>
  );
}
