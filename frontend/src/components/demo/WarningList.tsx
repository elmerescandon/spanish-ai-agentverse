import { Info, OctagonAlert, TriangleAlert } from "lucide-react";
import type { Severity } from "@/lib/api";
import type { StepWarning } from "@/lib/demo/types";

const SEVERITY_STYLES: Record<
  Severity,
  { icon: typeof Info; label: string; className: string }
> = {
  info: { icon: Info, label: "Info", className: "text-zinc-500" },
  warning: {
    icon: TriangleAlert,
    label: "Warning",
    className: "text-amber-700",
  },
  critical: {
    icon: OctagonAlert,
    label: "Critical",
    className: "text-rose-700",
  },
};

/** Caveats the agent raised about its own run (e.g. a source was down). */
export default function WarningList({
  warnings,
}: {
  warnings: readonly StepWarning[];
}) {
  if (warnings.length === 0) return null;

  return (
    <ul aria-label="Run warnings" className="space-y-2">
      {warnings.map((warning, index) => {
        const style = SEVERITY_STYLES[warning.severity];
        const Icon = style.icon;
        return (
          <li
            key={`${warning.code}-${index}`}
            className="flex items-start gap-2 font-sans text-sm"
          >
            <Icon
              className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${style.className}`}
              strokeWidth={1.5}
              aria-label={style.label}
              role="img"
            />
            <span className="text-zinc-700">
              {warning.message}{" "}
              <code className="text-xs text-zinc-400">
                {warning.code}
              </code>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
