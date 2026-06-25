"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Zap, ArrowLeft, Sparkles, Brain, Mail, Mic, TrendingUp, Heart,
  Search, Bot, ShieldCheck, Plug, ChevronDown, MessageSquarePlus,
} from "lucide-react";
import { cn } from "@/lib/utils";

const steps = [
  { n: 1, title: "Connect your tools", body: "Link Gmail and Slack in the onboarding wizard. NovaCRM starts ingesting messages and calls right away — no manual data entry." },
  { n: 2, title: "Everything gets understood", body: "Each contact and message is embedded with a sentence-transformer model (all-MiniLM-L6-v2), so NovaCRM can classify, tag, and semantically search your whole book of business." },
  { n: 3, title: "Agents handle the busywork", body: "Scoring, drafting, summarizing, and risk-flagging run automatically in the background — on a schedule or whenever an event fires." },
  { n: 4, title: "You stay in control", body: "High-stakes actions like sending an email route through human-in-the-loop approval in Slack. You approve or dismiss with one click." },
  { n: 5, title: "Ask anything", body: "Press ⌘K and ask Nova a natural-language question about your pipeline. It answers with full context across every contact, deal, and agent action." },
];

const capabilities = [
  { icon: Sparkles, title: "Semantic Contact Sorting", how: "Embeds every contact and classifies them by intent, role, and buying stage.", tech: "all-MiniLM-L6-v2 embeddings" },
  { icon: Brain, title: "Lead Scoring", how: "Scores leads 0–100 from engagement, firmographic, and deal-history signals.", tech: "Transparent heuristics" },
  { icon: Mail, title: "Email Composer", how: "Drafts personalized outreach grounded in deal stage and contact history.", tech: "Claude Sonnet" },
  { icon: Mic, title: "Call Summarization", how: "Transcribes calls, then extracts action items, objections, and sentiment.", tech: "Whisper + Claude" },
  { icon: TrendingUp, title: "Pipeline Intelligence", how: "Flags stalled deals and recommends the next best action to keep things moving.", tech: "Heuristics over deal velocity" },
  { icon: Heart, title: "Churn Risk", how: "Reads emails, tickets, and transcripts to flag at-risk accounts early.", tech: "Claude Haiku sentiment" },
];

const faqs = [
  { q: "How does the AI actually work?", a: "Semantic search uses sentence-transformer embeddings (all-MiniLM-L6-v2). Generative features — email drafts, call summaries, pre-meeting briefs, sentiment, and Nova query — use Anthropic's Claude. Lead and pipeline scoring use transparent heuristics over your own engagement signals." },
  { q: "Which models do you use?", a: "all-MiniLM-L6-v2 for embeddings, OpenAI Whisper for call transcription, and Anthropic Claude (Haiku and Sonnet) for generative features. We don't train any models on your data." },
  { q: "Is my data private?", a: "Your CRM data lives in your own workspace, isolated per tenant and encrypted in transit and at rest. The only external calls are to Anthropic's API for generative features — those are stateless and are never used for training." },
  { q: "How do I get started?", a: "Sign up and run the onboarding wizard: set your name, pick a workspace mode, connect Gmail and Slack, and invite your team. The agents begin working immediately." },
  { q: "What can the agents do on their own?", a: "Tag contacts, score leads, summarize calls, detect stalled deals, and flag at-risk accounts — automatically. Sending emails and other high-stakes actions are held for human-in-the-loop approval in Slack." },
  { q: "How is this different from Salesforce or HubSpot?", a: "Traditional CRMs store data; NovaCRM acts on it. Connect your existing Gmail and Slack and start getting value in hours, not months." },
  { q: "What does it cost?", a: "Starter is $49/user/month, Pro is $149/user/month (full agent suite + Nova query), and Enterprise is custom." },
];

function Faq({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-4 px-5 py-4 text-left cursor-pointer hover:bg-zinc-900 transition-colors"
        aria-expanded={open}
      >
        <span className="text-sm font-medium text-zinc-200">{q}</span>
        <ChevronDown className={cn("h-4 w-4 shrink-0 text-zinc-500 transition-transform", open && "rotate-180")} aria-hidden="true" />
      </button>
      {open && <p className="px-5 pb-4 text-sm text-zinc-400 leading-relaxed">{a}</p>}
    </div>
  );
}

export default function HelpPage() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 px-6 py-4">
        <div className="mx-auto max-w-5xl flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600"><Zap className="h-4 w-4 text-white" aria-hidden="true" /></div>
            <span className="text-sm font-bold">NovaCRM</span>
          </Link>
          <Link href="/dashboard" className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors">Launch App</Link>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-12 space-y-16">
        <section>
          <p className="text-xs font-mono text-indigo-400 uppercase tracking-widest mb-3">Help &amp; How-To</p>
          <h1 className="text-3xl sm:text-4xl font-bold">How NovaCRM works</h1>
          <p className="mt-4 max-w-2xl text-zinc-400 leading-relaxed">
            NovaCRM connects to the tools your team already uses, understands every contact and conversation, and runs autonomous agents that handle CRM busywork — with you in control of anything that matters.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold mb-6">From inbox to action in five steps</h2>
          <div className="space-y-3">
            {steps.map((s) => (
              <div key={s.n} className="flex gap-4 rounded-xl border border-zinc-800 bg-zinc-900/60 p-5">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-400 font-mono text-sm font-bold">{s.n}</div>
                <div>
                  <h3 className="text-sm font-semibold text-zinc-100">{s.title}</h3>
                  <p className="mt-1 text-sm text-zinc-400 leading-relaxed">{s.body}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-xl font-semibold mb-6">What each agent does</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {capabilities.map((c) => (
              <div key={c.title} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5">
                <div className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-400"><c.icon className="h-4 w-4" aria-hidden="true" /></div>
                <h3 className="text-sm font-semibold text-zinc-100">{c.title}</h3>
                <p className="mt-1 text-sm text-zinc-400 leading-relaxed">{c.how}</p>
                <p className="mt-2 text-[11px] font-mono text-zinc-600">{c.tech}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 flex flex-wrap gap-x-8 gap-y-3">
          {[
            { icon: ShieldCheck, label: "Encrypted in transit & at rest" },
            { icon: Plug, label: "Connects to Gmail & Slack" },
            { icon: Bot, label: "Human-in-the-loop on high-stakes actions" },
            { icon: Search, label: "Natural-language pipeline search" },
          ].map((t) => (
            <div key={t.label} className="flex items-center gap-2 text-sm text-zinc-400"><t.icon className="h-4 w-4 text-indigo-400" aria-hidden="true" />{t.label}</div>
          ))}
        </section>

        <section>
          <h2 className="text-xl font-semibold mb-6">Frequently asked questions</h2>
          <div className="space-y-2.5">
            {faqs.map((f) => <Faq key={f.q} q={f.q} a={f.a} />)}
          </div>
        </section>

        <section className="rounded-2xl border border-indigo-500/20 bg-indigo-600/5 p-6 text-center">
          <MessageSquarePlus className="h-6 w-6 text-indigo-400 mx-auto mb-3" aria-hidden="true" />
          <h2 className="text-lg font-semibold">Have a question or some feedback?</h2>
          <p className="mt-2 text-sm text-zinc-400">We&apos;re shipping fast and want to hear what would make NovaCRM more useful for your team.</p>
          <a href="mailto:feedback@novacrm.dev?subject=NovaCRM%20feedback" className="mt-4 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 transition-colors">Send feedback</a>
        </section>
      </main>

      <footer className="border-t border-zinc-800 px-6 py-8">
        <div className="mx-auto max-w-5xl flex items-center justify-between text-xs text-zinc-600">
          <span className="font-mono">© 2026 NovaCRM</span>
          <Link href="/" className="inline-flex items-center gap-1.5 hover:text-zinc-400"><ArrowLeft className="h-3 w-3" aria-hidden="true" /> Back to home</Link>
        </div>
      </footer>
    </div>
  );
}
