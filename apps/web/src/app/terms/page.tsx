import Link from "next/link";
import { Zap, ArrowLeft } from "lucide-react";

export const metadata = { title: "Terms — NovaCRM" };

export default function TermsPage() {
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
      <main className="mx-auto max-w-3xl px-6 py-12 space-y-5">
        <h1 className="text-3xl font-bold">Terms of Service</h1>
        <p className="text-sm text-zinc-400 leading-relaxed">NovaCRM is provided as a software-as-a-service product. By using it you agree to use it lawfully, to keep your account credentials secure, and not to misuse the platform or attempt to access other workspaces&apos; data.</p>
        <p className="text-sm text-zinc-400 leading-relaxed">NovaCRM is under active development and is offered on an as-is basis during this period. Features, pricing, and availability may change. You retain ownership of the data you bring into your workspace and may export or delete it.</p>
        <p className="text-xs text-zinc-600">These summary terms apply during active development; full terms will be published before general availability. Questions: <a className="text-indigo-400 hover:text-indigo-300" href="mailto:legal@novacrm.dev">legal@novacrm.dev</a>.</p>
        <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-300"><ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" /> Back to home</Link>
      </main>
    </div>
  );
}
