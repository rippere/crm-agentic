import Link from "next/link";
import { Zap, ArrowLeft, CheckCircle2 } from "lucide-react";

export const metadata = { title: "Status — NovaCRM" };

const services = ["Web app", "API", "Background workers", "Scheduler", "Database"];

export default function StatusPage() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 px-6 py-4">
        <div className="mx-auto max-w-3xl">
          <Link href="/" className="flex w-fit items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600"><Zap className="h-4 w-4 text-white" aria-hidden="true" /></div>
            <span className="text-sm font-bold">NovaCRM</span>
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-12">
        <div className="flex items-center gap-3 mb-8">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-400 agent-pulse" aria-hidden="true" />
          <h1 className="text-2xl font-bold">All systems operational</h1>
        </div>
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 divide-y divide-zinc-800">
          {services.map((s) => (
            <div key={s} className="flex items-center justify-between px-5 py-4">
              <span className="text-sm text-zinc-300">{s}</span>
              <span className="flex items-center gap-1.5 text-xs font-mono text-emerald-400"><CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> Operational</span>
            </div>
          ))}
        </div>
        <Link href="/" className="mt-8 inline-flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-300"><ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" /> Back to home</Link>
      </main>
    </div>
  );
}
