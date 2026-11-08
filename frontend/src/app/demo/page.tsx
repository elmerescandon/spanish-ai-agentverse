"use client";

import { useState } from "react";
import ProtocolIngestion from "@/components/ProtocolIngestion";
import { type ProtocolSummary } from "@/lib/api";

export default function DemoPage() {
  const [loadedProtocol, setLoadedProtocol] = useState<ProtocolSummary | null>(
    null
  );

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8">
      <main className="max-w-2xl w-full mx-auto">
        <ProtocolIngestion
          onProtocolLoaded={setLoadedProtocol}
          activeProtocolId={loadedProtocol?.protocol_id}
        />
      </main>
    </div>
  );
}
