import Link from "next/link";
import { Zap, ArrowLeft } from "lucide-react";

export const metadata = { title: "Privacy — NovaCRM" };

export default function PrivacyPage() {
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
        <h1 className="text-3xl font-bold">Privacy</h1>
        <p className="text-sm text-zinc-400 leading-relaxed">Your CRM data lives in your own workspace, isolated per tenant and encrypted in transit and at rest. We do not sell your data or use it to train AI models.</p>
        <p className="text-sm text-zinc-400 leading-relaxed">Generative features (email drafting, call summaries, pre-meeting briefs, and natural-language query) send the relevant context to Anthropic&apos;s Claude API to produce a response. These calls are stateless and are not used for model training. Call transcription uses OpenAI Whisper, and contact classification uses an open-source embedding model (all-MiniLM-L6-v2).</p>
        <p className="text-xs text-zinc-600">This is a summary of how NovaCRM handles data during active development; a full policy will be published before general availability. Questions: <a className="text-indigo-400 hover:text-indigo-300" href="mailto:privacy@novacrm.dev">privacy@novacrm.dev</a>.</p>
        <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-300"><ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" /> Back to home</Link>
      </main>
    </div>
  );
}
