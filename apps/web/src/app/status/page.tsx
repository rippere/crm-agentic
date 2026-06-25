import Link from "next/link";
import { Zap, ArrowLeft, CheckCircle2, AlertTriangle } from "lucide-react";

export const metadata = { title: "Status — NovaCRM" };

// Always check live — never serve a stale/cached "all green".
export const dynamic = "force-dynamic";
export const revalidate = 0;

type Probe = { reachable: boolean; ok: boolean; database: boolean; redis: boolean };

async function probeApi(): Promise<Probe> {
  const api = (process.env.NEXT_PUBLIC_FASTAPI_URL ?? "").replace(/\/+$/, "");
  if (!api) return { reachable: false, ok: false, database: false, redis: false };
  try {
    const res = await fetch(`${api}/health`, { cache: "no-store", signal: AbortSignal.timeout(8000) });
    if (!res.ok) return { reachable: true, ok: false, database: false, redis: false };
    const j = (await res.json()) as { status?: string; database?: string; redis?: string };
    return {
      reachable: true,
      ok: j?.status === "ok",
      database: j?.database === "ok",
      redis: j?.redis === "ok",
    };
  } catch {
    return { reachable: false, ok: false, database: false, redis: false };
  }
}

export default async function StatusPage() {
  const p = await probeApi();
  // Web app is up by definition (it is serving this page). API/Database come
  // straight from the live /health probe; queue/scheduler depend on Redis + API.
  const services: { name: string; up: boolean }[] = [
    { name: "Web app", up: true },
    { name: "API", up: p.reachable && p.ok },
    { name: "Database", up: p.database },
    { name: "Background workers", up: p.ok && p.redis },
    { name: "Scheduler", up: p.ok && p.redis },
  ];
  const allUp = services.every((s) => s.up);

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
        <div className="flex items-center gap-3 mb-2">
          <span className={`h-2.5 w-2.5 rounded-full ${allUp ? "bg-emerald-400 agent-pulse" : "bg-amber-400"}`} aria-hidden="true" />
          <h1 className="text-2xl font-bold">{allUp ? "All systems operational" : "Some systems degraded"}</h1>
        </div>
        <p className="text-xs text-zinc-500 mb-8">Live check · refresh to re-run</p>
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 divide-y divide-zinc-800">
          {services.map((s) => (
            <div key={s.name} className="flex items-center justify-between px-5 py-4">
              <span className="text-sm text-zinc-300">{s.name}</span>
              {s.up ? (
                <span className="flex items-center gap-1.5 text-xs font-mono text-emerald-400"><CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> Operational</span>
              ) : (
                <span className="flex items-center gap-1.5 text-xs font-mono text-amber-400"><AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> Disruption</span>
              )}
            </div>
          ))}
        </div>
        <Link href="/" className="mt-8 inline-flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-300"><ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" /> Back to home</Link>
      </main>
    </div>
  );
}
