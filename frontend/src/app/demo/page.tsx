import Link from "next/link";
import DemoPipeline from "@/components/demo/DemoPipeline";
import { InsulinIcon } from "@/components/insulin-icon";

const serifFont = {
  fontFamily:
    "var(--font-serif), 'Libre Baskerville', Georgia, 'Times New Roman', serif",
};

export default function DemoPage() {
  return (
    <div className="min-h-screen bg-white text-zinc-900 selection:bg-emerald-100">
      <header className="sticky top-0 z-30 w-full border-b border-zinc-100/60 bg-white/70 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 sm:px-10 lg:px-12">
          <Link
            href="/"
            style={serifFont}
            className="flex items-center gap-2.5 text-2xl sm:text-3xl font-normal tracking-tight text-zinc-950"
          >
            <InsulinIcon className="h-8 w-8 sm:h-9 sm:w-9 shrink-0" />
            ProtocolAI
          </Link>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl px-6 py-12 sm:px-10 lg:px-12">
        <DemoPipeline />
      </main>
    </div>
  );
}
