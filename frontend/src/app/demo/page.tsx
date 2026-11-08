import DemoPipeline from "@/components/demo/DemoPipeline";

export default function DemoPage() {
  return (
    <div className="min-h-screen bg-white px-6 py-12 text-zinc-900 selection:bg-emerald-100 sm:px-10 lg:px-12">
      <main className="mx-auto w-full max-w-5xl">
        <DemoPipeline />
      </main>
    </div>
  );
}
