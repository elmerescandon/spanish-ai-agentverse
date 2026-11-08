import { Download, FileText } from "lucide-react";
import { LATEST_REPORT_PDF_URL, REPORT_PAGE_PATH } from "@/lib/api";

const PILL_CLASS =
  "flex items-center gap-2 rounded-full border border-zinc-200 px-3.5 py-1.5 font-sans text-sm text-zinc-700 transition-colors animate-in fade-in duration-500 hover:border-zinc-900 hover:text-zinc-900";

/** Header button that downloads the latest upload's review as a PDF. */
export function DownloadReportLink() {
  return (
    <a
      href={LATEST_REPORT_PDF_URL}
      download
      aria-label="Download report (PDF)"
      className={PILL_CLASS}
    >
      <Download className="h-4 w-4" strokeWidth={1.5} aria-hidden />
      <span className="hidden sm:inline">Download report</span>
    </a>
  );
}

/**
 * Header link to the report page. Opens a new tab so the analysis being
 * reviewed is still there to come back to.
 */
export function ViewReportLink() {
  return (
    <a
      href={REPORT_PAGE_PATH}
      target="_blank"
      rel="noopener"
      aria-label="View report"
      className={PILL_CLASS}
    >
      <FileText className="h-4 w-4" strokeWidth={1.5} aria-hidden />
      <span className="hidden sm:inline">View report</span>
    </a>
  );
}
