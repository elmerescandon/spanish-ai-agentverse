"use client";

import { useCallback, useState } from "react";
import DemoPipeline from "@/components/demo/DemoPipeline";
import SiteHeader from "@/components/SiteHeader";
import {
  DownloadReportLink,
  ViewReportLink,
} from "@/components/report/ReportLinks";

export default function DemoPage() {
  // Once the last step is reached the report stays offered in the header.
  const [hasReachedEnd, setHasReachedEnd] = useState(false);
  const markReachedEnd = useCallback(() => setHasReachedEnd(true), []);

  return (
    <div className="min-h-screen bg-white text-zinc-900 selection:bg-emerald-100">
      <SiteHeader>
        {hasReachedEnd && (
          <>
            <ViewReportLink />
            <DownloadReportLink />
          </>
        )}
      </SiteHeader>
      <main className="mx-auto w-full max-w-7xl px-6 pb-12 pt-2 sm:px-10 lg:px-12">
        <DemoPipeline onReachEnd={markReachedEnd} />
      </main>
    </div>
  );
}
