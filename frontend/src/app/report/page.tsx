"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import { DownloadReportLink } from "@/components/report/ReportLinks";
import ReportLoading from "@/components/report/ReportLoading";
import ReviewReport from "@/components/report/ReviewReport";
import { getLatestReview, type ProtocolFieldsResponse } from "@/lib/api";

type ReportState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; review: ProtocolFieldsResponse };

/** The latest upload's review, as a page (the PDF holds the same). */
export default function ReportPage() {
  const [state, setState] = useState<ReportState>({ status: "loading" });

  useEffect(() => {
    let isCurrent = true;
    getLatestReview()
      .then((review) => {
        if (isCurrent) setState({ status: "ready", review });
      })
      .catch((error: unknown) => {
        if (!isCurrent) return;
        const message = error instanceof Error ? error.message : String(error);
        setState({ status: "error", message });
      });
    return () => {
      isCurrent = false;
    };
  }, []);

  return (
    <div className="min-h-screen bg-white text-zinc-900 selection:bg-emerald-100">
      <SiteHeader>
        {state.status === "ready" && <DownloadReportLink />}
      </SiteHeader>
      <main className="mx-auto w-full max-w-4xl px-6 pb-12 pt-2 sm:px-10 lg:px-12">
        {state.status === "loading" && <ReportLoading />}
        {state.status === "error" && (
          <div className="space-y-3 pt-16 text-center">
            <p role="alert" className="font-sans text-sm text-rose-700">
              {state.message}
            </p>
            <Link
              href="/demo"
              className="font-sans text-sm text-zinc-700 underline decoration-zinc-300 underline-offset-4 hover:text-zinc-900"
            >
              Analyze a protocol
            </Link>
          </div>
        )}
        {state.status === "ready" && <ReviewReport review={state.review} />}
      </main>
    </div>
  );
}
