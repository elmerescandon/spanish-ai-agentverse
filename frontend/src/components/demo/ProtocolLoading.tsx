"use client";

export default function ProtocolLoading({ sample = false }: {
  sample?: boolean;
}) {
  return (
    <div role="status" aria-live="polite"
      className="protocol-loading flex min-h-[65vh] flex-col items-center justify-center gap-6 text-center">
      <div className="protocol-document" aria-hidden="true">
        <svg viewBox="0 0 96 120" fill="none"
          style={{ height: "9.6rem", width: "8.4rem" }}>
          <path d="M16 4h43l25 25v79a8 8 0 0 1-8 8H16a8 8 0 0 1-8-8V12a8 8 0 0 1 8-8Z"
            fill="white" stroke="currentColor" strokeWidth="2" />
          <path d="M59 4v18a7 7 0 0 0 7 7h18"
            stroke="currentColor" strokeWidth="2" />
          <path d="M25 49h41M25 61h33M25 73h41M25 85h25"
            stroke="#a1a1aa" strokeWidth="3" strokeLinecap="round" />
          <path d="M26 27h12M32 21v12"
            stroke="#059669" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <span className="protocol-scan-line" />
      </div>
      <div className="space-y-2">
        <p className="font-serif text-2xl text-zinc-900">
          {sample ? "Opening sample protocol" : "Reading your protocol"}
        </p>
        <p className="text-sm text-zinc-500">
          {sample ? "Preparing your review · demonstration" :
            "Uploading the PDF and extracting clinical criteria…"}
        </p>
      </div>
    </div>
  );
}
