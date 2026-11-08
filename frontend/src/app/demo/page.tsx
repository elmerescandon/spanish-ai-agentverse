"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { Download } from "lucide-react";
import DemoPipeline from "@/components/demo/DemoPipeline";
import { InsulinIcon } from "@/components/insulin-icon";
import { LATEST_REPORT_PDF_URL } from "@/lib/api";

const serifFont = {
  fontFamily:
    "var(--font-serif), 'Libre Baskerville', Georgia, 'Times New Roman', serif",
};

export default function DemoPage() {
  // Once the last step is reached the report stays offered in the header.
  const [hasReachedEnd, setHasReachedEnd] = useState(false);
  const markReachedEnd = useCallback(() => setHasReachedEnd(true), []);

  return (
    <div className="min-h-screen bg-white text-zinc-900 selection:bg-emerald-100">
      <header className="sticky top-0 z-30 w-full border-b border-zinc-100/60 bg-white/70 backdrop-blur-md">
        <div className="mx-auto flex h-18 max-w-7xl items-center justify-between px-6 sm:px-10 lg:px-12">
          <Link
            href="/"
            style={serifFont}
            className="flex items-center gap-2.5 text-2xl sm:text-3xl font-normal tracking-tight text-zinc-950"
          >
            <InsulinIcon className="h-8 w-8 sm:h-9 sm:w-9 shrink-0" />
            ProtocolAI
          </Link>
          {hasReachedEnd && (
            <a
              href={LATEST_REPORT_PDF_URL}
              download
              aria-label="Download report (PDF)"
              className="flex items-center gap-2 rounded-full border border-zinc-200 px-3.5 py-1.5 font-sans text-sm text-zinc-700 transition-colors animate-in fade-in duration-500 hover:border-zinc-900 hover:text-zinc-900"
            >
              <Download className="h-4 w-4" strokeWidth={1.5} aria-hidden />
              <span className="hidden sm:inline">Download report</span>
            </a>
          )}
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl px-6 pb-12 pt-2 sm:px-10 lg:px-12">
        <DemoPipeline onReachEnd={markReachedEnd} />
      </main>
    </div>
  );
}
