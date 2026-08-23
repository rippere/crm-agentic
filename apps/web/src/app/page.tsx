"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence, useReducedMotion, type Variants } from "framer-motion";
import {
  Zap, Brain, Sparkles, TrendingUp, Bot, Shield,
  ArrowRight, Check, ChevronDown, Mail, Mic, Heart,
  Users, KanbanSquare, Menu, X, Clock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { createBrowserClient } from "@/lib/supabase";

// ─── Auth params rescue ───────────────────────────────────────────────────────
// Supabase auth redirects fall back to the Site URL (this page) when the
// intended /auth/callback target isn't matched by the redirect allowlist.
// Catch those stragglers — a PKCE ?code= or implicit #access_token — and
// finish the sign-in instead of stranding the user on the landing page.
function AuthParamsRescue() {
  const router = useRouter();
  useEffect(() => {
    const search = new URLSearchParams(window.location.search);
    const code = search.get("code");
    if (code) {
      // PKCE code — the callback route exchanges it (verifier cookie is here).
      router.replace(`/auth/callback?code=${encodeURIComponent(code)}`);
      return;
    }
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    if (hash.get("error") || hash.get("error_code")) {
      router.replace("/login?error=confirm");
      return;
    }
    const access_token = hash.get("access_token");
    const refresh_token = hash.get("refresh_token");
    if (access_token && refresh_token) {
      const supabase = createBrowserClient();
      supabase.auth
        .setSession({ access_token, refresh_token })
        .then(({ error }) => {
          router.replace(error ? "/login?confirmed=1" : "/dashboard");
        })
        .catch(() => router.replace("/login?confirmed=1"));
    }
  }, [router]);
  return null;
}

// ─── Nav ───────────────────────────────────────────────────────────────────────
function Nav() {
  const [open, setOpen] = useState(false);
  return (
    <nav
      className="fixed top-4 left-4 right-4 z-50 flex items-center justify-between rounded-2xl border border-zinc-800 bg-zinc-950/80 px-5 py-3 backdrop-blur-xl"
      aria-label="Main navigation"
    >
      <div className="flex items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 shadow-glow-sm">
          <Zap className="h-4 w-4 text-white" aria-hidden="true" />
        </div>
        <span className="text-sm font-bold text-zinc-100">NovaCRM</span>
      </div>

      <div className="hidden md:flex items-center gap-6">
        {[
          { label: "Features", href: "#features" },
          { label: "Agents", href: "#agents" },
          { label: "Pricing", href: "#pricing" },
          { label: "Docs", href: "/help" },
        ].map((item) => (
          <a
            key={item.label}
            href={item.href}
            className="text-sm text-zinc-400 hover:text-zinc-100 transition-colors duration-200 cursor-pointer"
          >
            {item.label}
          </a>
        ))}
      </div>

      <div className="hidden md:flex items-center gap-3">
        <Link
          href="/dashboard"
          className="text-sm text-zinc-400 hover:text-zinc-100 transition-colors duration-200 cursor-pointer"
        >
          Log in
        </Link>
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-all duration-200 shadow-glow-sm cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-zinc-950"
        >
          Start Free
          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Link>
      </div>

      <button
        className="md:hidden text-zinc-400 hover:text-zinc-100 cursor-pointer"
        onClick={() => setOpen(!open)}
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
      >
        {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="absolute top-full left-0 right-0 mt-2 rounded-2xl border border-zinc-800 bg-zinc-950 p-4 space-y-3 md:hidden"
          >
            {[
              { label: "Features", href: "#features" },
              { label: "Agents", href: "#agents" },
              { label: "Pricing", href: "#pricing" },
              { label: "Docs", href: "/help" },
            ].map((item) => (
              <a
                key={item.label}
                href={item.href}
                className="block text-sm text-zinc-400 hover:text-zinc-100 py-2 transition-colors"
                onClick={() => setOpen(false)}
              >
                {item.label}
              </a>
            ))}
            <Link href="/dashboard" className="block w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-center text-sm font-medium text-white">
              Start Free
            </Link>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
}

// ─── Hero ─────────────────────────────────────────────────────────────────────
// Rotating verb-phrases — each maps to a real shipped agent (Lead Scorer,
// Email Composer, Call Summarizer, and stall detection), so the headline stays
// honest while it cycles.
const HERO_PHRASES = [
  "scores your leads",
  "drafts your outreach",
  "summarizes your calls",
  "chases your stalled deals",
];

function Hero() {
  const reduce = useReducedMotion();
  const [phrase, setPhrase] = useState(0);
  useEffect(() => {
    if (reduce) return; // hold on the first phrase when motion is reduced
    const id = setInterval(() => setPhrase((n) => (n + 1) % HERO_PHRASES.length), 2600);
    return () => clearInterval(id);
  }, [reduce]);
  return (
    <section
      className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-6 pt-28 pb-16 text-center"
      aria-labelledby="hero-heading"
    >
      <div className="pointer-events-none absolute inset-0 bg-grid-pattern bg-grid opacity-100" aria-hidden="true" />
      <div className="pointer-events-none absolute inset-0 bg-glow-indigo" aria-hidden="true" />

      <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-4 py-1.5 text-xs font-medium text-indigo-300">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 agent-pulse" aria-hidden="true" />
        6 AI Agents · Claude + semantic search
      </div>

      <h1
        id="hero-heading"
        className="mx-auto max-w-4xl text-4xl font-bold leading-[1.08] tracking-tight text-zinc-100 sm:text-5xl lg:text-6xl"
      >
        <span className="block">The CRM that</span>
        <span className="relative block py-1" aria-hidden="true">
          <span className="invisible">chases your stalled deals</span>
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={phrase}
              initial={reduce ? false : { opacity: 0, y: "0.4em" }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, y: "-0.4em" }}
              transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
              className="absolute inset-0 flex items-center justify-center bg-gradient-to-r from-indigo-300 via-indigo-400 to-[#2DD4AA] bg-clip-text text-transparent"
            >
              {HERO_PHRASES[phrase]}
            </motion.span>
          </AnimatePresence>
        </span>
        <span className="sr-only">works your pipeline</span>
        <span className="block">for you</span>
      </h1>

      <p className="mx-auto mt-6 max-w-xl text-pretty text-lg text-zinc-400 leading-relaxed">
        Six AI agents do the busywork, so your team sells.
      </p>

      <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-base font-semibold text-white hover:bg-indigo-500 transition-all duration-200 shadow-glow cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-zinc-950"
        >
          Launch App
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
        <a
          href="#features"
          className="inline-flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-900 px-6 py-3 text-base font-semibold text-zinc-300 hover:border-zinc-600 hover:text-zinc-100 transition-all duration-200 cursor-pointer"
        >
          See How It Works
          <ChevronDown className="h-4 w-4" aria-hidden="true" />
        </a>
      </div>

      <div className="mt-9 flex flex-col items-center gap-2.5">
        <p className="text-xs text-zinc-600">No credit card required to start</p>
      </div>

      {/* Dashboard preview */}
      <div className="relative mt-16 w-full max-w-4xl mx-auto">
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 backdrop-blur overflow-hidden">
          <div className="flex items-center gap-2 border-b border-zinc-800 px-4 py-3">
            <span className="h-3 w-3 rounded-full bg-rose-500/60" aria-hidden="true" />
            <span className="h-3 w-3 rounded-full bg-amber-500/60" aria-hidden="true" />
            <span className="h-3 w-3 rounded-full bg-emerald-500/60" aria-hidden="true" />
            <span className="ml-4 text-xs font-mono text-zinc-600">novacrm · dashboard</span>
          </div>
          <div className="p-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { val: "$2.4M", label: "Revenue" },
              { val: "148", label: "Deals" },
              { val: "12", label: "Hot Leads" },
              { val: "6 / 8", label: "Agents" },
            ].map(({ val, label }, i) => (
              <div key={label} className="rounded-xl border border-zinc-800 bg-zinc-950 p-3">
                <p className="text-lg font-bold font-mono text-zinc-100">{val}</p>
                <p className="text-xs text-zinc-500 mt-0.5">{label}</p>
                <div className="mt-2 h-1 rounded-full bg-zinc-800" aria-hidden="true">
                  <div className="h-full rounded-full bg-indigo-500" style={{ width: `${[72, 58, 64, 75][i]}%` }} />
                </div>
              </div>
            ))}
          </div>
          <div className="px-4 pb-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
            {[
              { agent: "Semantic Sorter", action: "Tagged 12 contacts · 'Enterprise Buyer'", color: "emerald" as const },
              { agent: "Lead Scorer", action: "Dmitri Volkov → 95/100 (↑ from 88)", color: "indigo" as const },
              { agent: "Pipeline Optimizer", action: "Stall detected: Solvio EU · 21 days", color: "amber" as const },
            ].map(({ agent, action, color }) => (
              <div key={agent} className="flex items-start gap-2.5 rounded-xl border border-zinc-800 bg-zinc-950 p-3">
                <span
                  className={cn(
                    "mt-0.5 h-2 w-2 rounded-full flex-shrink-0",
                    color === "emerald" ? "bg-emerald-400 agent-pulse" :
                    color === "indigo" ? "bg-indigo-400" : "bg-amber-400"
                  )}
                  aria-hidden="true"
                />
                <div>
                  <p className="text-[10px] font-semibold text-indigo-400">{agent}</p>
                  <p className="text-[10px] text-zinc-400 mt-0.5">{action}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── Features ────────────────────────────────────────────────────────────────
const features = [
  {
    icon: <Sparkles className="h-5 w-5" />,
    title: "Semantic Contact Sorting",
    description: "Our sentence-transformer model embeds every contact and classifies them by intent, role, industry, and buying stage — automatically.",
    tags: ["all-MiniLM-L6-v2", "Cosine Similarity", "Auto-tagging"],
    color: "indigo",
  },
  {
    icon: <Brain className="h-5 w-5" />,
    title: "Lead Scoring",
    description: "Scores every lead 0–100 from engagement signals, firmographic data, and deal history — so your team works the hottest leads first.",
    tags: ["Lead Scoring", "Engagement Signals", "0–100"],
    color: "emerald",
  },
  {
    icon: <TrendingUp className="h-5 w-5" />,
    title: "Pipeline Intelligence",
    description: "Surfaces stalled deals, flags aging opportunities, and recommends your next best action to keep the pipeline moving.",
    tags: ["Stall Detection", "Next Best Action", "Pipeline Health"],
    color: "indigo",
  },
  {
    icon: <Mail className="h-5 w-5" />,
    title: "Autonomous Email Composer",
    description: "Claude drafts personalized outreach using semantic tags, deal stage, and contact history. Review before you send.",
    tags: ["Claude", "Personalized", "Review queue"],
    color: "amber",
  },
  {
    icon: <Mic className="h-5 w-5" />,
    title: "Call Summarization",
    description: "Whisper transcribes your sales calls. Claude extracts action items, objections, and sentiment — and updates your CRM automatically.",
    tags: ["Whisper", "Claude", "Action Items"],
    color: "emerald",
  },
  {
    icon: <Heart className="h-5 w-5" />,
    title: "Sentiment Analysis",
    description: "Claude scores the sentiment of incoming messages and call summaries, so a cooling relationship shows up in the contact record instead of going unnoticed.",
    tags: ["Sentiment Analysis", "Per-message scoring", "Claude"],
    color: "rose",
  },
];

const colorMap: Record<string, { icon: string; tag: string; border: string }> = {
  indigo: { icon: "bg-indigo-500/10 border-indigo-500/20 text-indigo-400", tag: "bg-indigo-500/10 text-indigo-400", border: "hover:border-indigo-500/30" },
  emerald: { icon: "bg-emerald-500/10 border-emerald-500/20 text-emerald-400", tag: "bg-emerald-500/10 text-emerald-400", border: "hover:border-emerald-500/30" },
  amber: { icon: "bg-amber-500/10 border-amber-500/20 text-amber-400", tag: "bg-amber-500/10 text-amber-400", border: "hover:border-amber-500/30" },
  rose: { icon: "bg-rose-500/10 border-rose-500/20 text-rose-400", tag: "bg-rose-500/10 text-rose-400", border: "hover:border-rose-500/30" },
};

function FeaturesSection() {
  return (
    <section id="features" className="px-6 py-24" aria-labelledby="features-heading">
      <div className="mx-auto max-w-6xl">
        <div className="mb-16 text-center">
          <p className="text-xs font-mono text-indigo-400 uppercase tracking-widest mb-3">Intelligence Stack</p>
          <h2 id="features-heading" className="text-3xl font-bold text-zinc-100 sm:text-4xl">Six agents. One unified CRM.</h2>
          <p className="mx-auto mt-4 max-w-xl text-zinc-400">
            Each agent is a specialized AI workflow built for a specific CRM task — working together in a single, seamless flow.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 lg:auto-rows-fr">
          {features.map((f, i) => {
            const c = colorMap[f.color];
            // Bento spans — fills a 4-col × 3-row grid exactly. Index 0 is the
            // featured cell (2×2); the rest alternate wide and compact.
            const span = [
              "lg:col-span-2 lg:row-span-2",
              "lg:col-span-2",
              "lg:col-span-1",
              "lg:col-span-1",
              "lg:col-span-2",
              "lg:col-span-2",
            ][i];
            const featured = i === 0;
            return (
              <div
                key={f.title}
                className={cn(
                  "group relative flex flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900 p-6 transition-all duration-200 cursor-default hover:-translate-y-0.5 hover:bg-zinc-800/80",
                  c.border,
                  span
                )}
              >
                <div
                  className={cn(
                    "pointer-events-none absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100",
                    f.color === "indigo" ? "via-indigo-500/60" : f.color === "emerald" ? "via-[#00C896]/60" : f.color === "amber" ? "via-amber-500/60" : "via-rose-500/60"
                  )}
                  aria-hidden="true"
                />
                <div className={cn("mb-4 inline-flex items-center justify-center rounded-xl border", c.icon, featured ? "h-12 w-12" : "h-10 w-10")}>
                  {f.icon}
                </div>
                <h3 className={cn("font-semibold text-zinc-100 mb-2", featured ? "text-xl" : "text-base")}>{f.title}</h3>
                <p className={cn("text-zinc-400 leading-relaxed mb-4", featured ? "text-base max-w-md" : "text-sm")}>{f.description}</p>
                {featured && (
                  <div className="mb-6 space-y-2" aria-hidden="true">
                    {[
                      { name: "Dmitri Volkov", tag: "Enterprise Buyer", c: "text-indigo-300 bg-indigo-500/10 border-indigo-500/20" },
                      { name: "Marcus Webb", tag: "Champion", c: "text-[#6EFFD5] bg-[#00C896]/10 border-[#00C896]/20" },
                      { name: "Lena Kovacs", tag: "At Risk", c: "text-rose-300 bg-rose-500/10 border-rose-500/20" },
                      { name: "Priya Sharma", tag: "Power User", c: "text-amber-300 bg-amber-500/10 border-amber-500/20" },
                    ].map((row) => (
                      <div key={row.name} className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2">
                        <span className="text-xs text-zinc-400">{row.name}</span>
                        <span className="flex items-center gap-1.5 text-[11px] text-zinc-600">
                          <ArrowRight className="h-3 w-3" />
                          <span className={cn("rounded-full border px-2 py-0.5 font-mono font-medium", row.c)}>{row.tag}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="mt-auto flex flex-wrap gap-1.5">
                  {f.tags.map((tag) => (
                    <span key={tag} className={cn("rounded-full px-2 py-0.5 text-[10px] font-mono font-medium", c.tag)}>{tag}</span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

// ─── Shared scroll-reveal variants (module scope; also used by ProvenanceProof) ─
const revealParent: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.06 } },
};
const revealItem: Variants = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: [0.16, 1, 0.3, 1] } },
};

// ─── Agents roster — "Hire your six-agent team" ──────────────────────────────
// Signal-green is the sole agent accent; every line is exactly what ships; model
// provenance lives in the Fira-Code tech tag. Replaces the old activity-log block.
const roster = [
  {
    name: "Mira",
    role: "Contact Librarian",
    icon: <Sparkles className="h-5 w-5" aria-hidden="true" />,
    line: "Embeds every contact with a sentence-transformer, then auto-tags them by intent, role, industry, and buying stage.",
    tech: "all-MiniLM-L6-v2 · pgvector",
    schedule: "nightly · 02:00 UTC",
  },
  {
    name: "Vera",
    role: "Lead Scorer",
    icon: <Brain className="h-5 w-5" aria-hidden="true" />,
    line: "Scores each lead 0–100 from engagement signals, firmographics, and deal history — a heuristic model, not ML.",
    tech: "heuristic signals · 0–100",
    schedule: "nightly · 02:15 UTC",
  },
  {
    name: "Atlas",
    role: "Pipeline Watcher",
    icon: <TrendingUp className="h-5 w-5" aria-hidden="true" />,
    line: "Flags stalled and aging deals and recommends the next best action to keep the pipeline moving.",
    tech: "stall detection · next-best-action",
    schedule: "nightly + on stage change",
  },
  {
    name: "Quill",
    role: "Outreach Drafter",
    icon: <Mail className="h-5 w-5" aria-hidden="true" />,
    line: "Drafts personalized outreach from a contact's tags, stage, and history — into a review queue, never auto-sent.",
    tech: "claude-haiku-4-5 · review queue",
    schedule: "on request → queued",
  },
  {
    name: "Echo",
    role: "Call Scribe",
    icon: <Mic className="h-5 w-5" aria-hidden="true" />,
    line: "Transcribes your calls, then pulls action items, objections, and sentiment onto the record.",
    tech: "whisper · claude-haiku-4-5",
    schedule: "on call upload",
  },
  {
    name: "Pulse",
    role: "Sentiment Reader",
    icon: <Heart className="h-5 w-5" aria-hidden="true" />,
    line: "Scores sentiment on each incoming message and call summary so a cooling relationship surfaces on the contact.",
    tech: "claude-haiku-4-5 · per-message",
    schedule: "on new message",
  },
];

// Clearly-labeled SAMPLE data — never a live feed. Times echo the real cadence:
// nightly batch (02:00 / 02:15 UTC) plus daytime triggers.
const exampleLog = [
  { time: "02:00:04", agent: "Mira",  msg: "embedded 48 contacts · top tag: enterprise_buyer" },
  { time: "02:15:11", agent: "Vera",  msg: "rescored 1,204 leads · signals: engagement, firmographic" },
  { time: "02:15:12", agent: "Atlas", msg: "deal d1 flagged stalled · 21d in negotiation · next: re-engage" },
  { time: "09:41:33", agent: "Echo",  msg: "call ac-081 transcribed · 3 action items · 1 objection" },
  { time: "09:41:35", agent: "Pulse", msg: "message m-5521 sentiment 0.34 · cooling · surfaced on contact" },
  { time: "09:42:07", agent: "Quill", msg: "draft e-0092 → review queue · contact m_webb · stage proposal" },
];

function AgentsSection() {
  return (
    <section
      id="agents"
      className="relative overflow-hidden px-6 py-28 sm:py-32 bg-gradient-to-b from-zinc-950 to-zinc-900"
      aria-labelledby="agents-heading"
    >
      <div className="pointer-events-none absolute inset-0 bg-glow-emerald" aria-hidden="true" />

      <div className="relative mx-auto max-w-6xl">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="mx-auto max-w-2xl text-center"
        >
          <p className="mb-3 font-mono text-xs uppercase tracking-widest text-[#2DD4AA]">
            Your AI team
          </p>
          <h2 id="agents-heading" className="text-3xl font-bold text-zinc-100 sm:text-4xl">
            Hire your six-agent team
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-zinc-400">
            Six specialized agents handle the CRM busywork — each with one job it does well,
            a real model behind it, and your review before anything goes out.
          </p>
          <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-[#00C896]/20 bg-[#00C896]/10 px-3.5 py-1.5 font-mono text-xs text-[#6EFFD5]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#00C896]" aria-hidden="true" />
            Scheduled runs · Celery Beat nightly (02:00 &amp; 02:15 UTC) + triggers — not a live feed
          </div>
        </motion.div>

        {/* Roster grid — uniform, flush cells (auto-rows-fr + h-full + mt-auto footer) */}
        <motion.div
          variants={revealParent}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-60px" }}
          className="mt-16 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 lg:auto-rows-fr"
        >
          {roster.map((a) => (
            <motion.article
              key={a.name}
              variants={revealItem}
              className="group relative flex h-full flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900 p-6 transition-all duration-200 hover:-translate-y-0.5 hover:border-[#00C896]/30 hover:bg-zinc-800/60"
            >
              {/* signal-green top hairline on hover */}
              <div
                className="pointer-events-none absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-[#00C896]/60 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100"
                aria-hidden="true"
              />

              {/* Identity: icon tile + name + role + watermark initial */}
              <div className="flex items-center gap-3.5">
                <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl border border-[#00C896]/20 bg-[#00C896]/10 text-[#2DD4AA]">
                  {a.icon}
                </div>
                <div className="min-w-0">
                  <h3 className="text-base font-semibold text-zinc-100">{a.name}</h3>
                  <p className="font-mono text-xs text-[#6EFFD5]/80">{a.role}</p>
                </div>
                <span
                  className="ml-auto font-mono text-2xl font-bold leading-none text-zinc-800 transition-colors duration-200 group-hover:text-zinc-700"
                  aria-hidden="true"
                >
                  {a.name[0]}
                </span>
              </div>

              {/* Honest capability line */}
              <p className="mt-4 text-sm leading-relaxed text-zinc-400">{a.line}</p>

              {/* Footer: Fira-Code provenance tag (real tech) + schedule/trigger badge */}
              <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-5">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-[#00C896]/20 bg-[#00C896]/10 px-2.5 py-1 font-mono text-[10px] font-medium text-[#6EFFD5]">
                  <span className="h-1 w-1 rounded-full bg-[#00C896]" aria-hidden="true" />
                  {a.tech}
                </span>
                <span className="inline-flex items-center gap-1 rounded-full border border-zinc-800 bg-zinc-950/60 px-2 py-1 font-mono text-[10px] text-zinc-500">
                  <Clock className="h-2.5 w-2.5" aria-hidden="true" />
                  {a.schedule}
                </span>
              </div>
            </motion.article>
          ))}
        </motion.div>

        {/* Folded-in honest "example output" — static sample rows, deliberately
            not framed as a real-time feed (no blink, no auto-updating region). */}
        <motion.div
          variants={revealItem}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-60px" }}
          className="mx-auto mt-8 max-w-3xl overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950"
        >
          <div className="flex items-center gap-2 border-b border-zinc-800 bg-zinc-900 px-4 py-3">
            <Bot className="h-4 w-4 text-[#2DD4AA]" aria-hidden="true" />
            <span className="font-mono text-xs text-zinc-300">Agent Activity Log</span>
            <span className="ml-auto rounded-full border border-[#00C896]/20 bg-[#00C896]/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-[#6EFFD5]">
              example output
            </span>
          </div>

          <div
            className="space-y-2 p-4 font-mono text-xs"
            role="group"
            aria-label="Example agent activity log — sample data, not a live feed"
          >
            {exampleLog.map(({ time, agent, msg }) => (
              <div key={time + agent} className="flex items-start gap-3">
                <span className="flex-shrink-0 text-zinc-700">{time}</span>
                <span className="flex-shrink-0 text-[#2DD4AA]">[{agent}]</span>
                <span className="break-all text-zinc-400">{msg}</span>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2 border-t border-zinc-800 bg-zinc-900/60 px-4 py-2.5 font-mono text-[10px] text-zinc-500">
            <Clock className="h-3 w-3 text-zinc-600" aria-hidden="true" />
            <span>Sample data. Nightly jobs run 02:00 &amp; 02:15 UTC; the rest fire on triggers. Every draft waits in a review queue.</span>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

// ─── Provenance proof — capabilities we can point to (before CTASection) ──────
// Replaces the removed fake social proof. Proves CAPABILITIES, never customers —
// no logos, counts, ratings, or customer-endorsement claims. Reuses the shared variants.
const provenanceItems = [
  { icon: <Sparkles className="h-4 w-4" aria-hidden="true" />, label: "Semantic search", detail: "MiniLM embeddings over pgvector" },
  { icon: <Mic className="h-4 w-4" aria-hidden="true" />,      label: "Call summaries",  detail: "Whisper transcription + Claude (Haiku)" },
  { icon: <Shield className="h-4 w-4" aria-hidden="true" />,   label: "Encrypted",       detail: "In transit and at rest" },
  { icon: <Users className="h-4 w-4" aria-hidden="true" />,    label: "Isolated",        detail: "Per-workspace data separation" },
];

const infraStack = ["Postgres 16 + pgvector", "Supabase auth", "FastAPI async", "Celery + Redis"];

function ProvenanceProof() {
  return (
    <section className="border-y border-zinc-800/70 px-6 py-16" aria-labelledby="provenance-heading">
      <motion.div
        variants={revealParent}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-60px" }}
        className="mx-auto max-w-6xl"
      >
        <motion.div variants={revealItem} className="text-center">
          <p className="mb-2 font-mono text-xs uppercase tracking-widest text-[#2DD4AA]">
            Provenance, not promises
          </p>
          <h2 id="provenance-heading" className="text-lg font-semibold text-zinc-200">
            Every claim here is a capability we can point to.
          </h2>
        </motion.div>

        {/* Capability strip */}
        <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {provenanceItems.map((item) => (
            <motion.div
              key={item.label}
              variants={revealItem}
              className="flex items-center gap-3.5 rounded-2xl border border-zinc-800 bg-zinc-900 px-4 py-4 transition-colors duration-200 hover:border-[#00C896]/25"
            >
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl border border-[#00C896]/20 bg-[#00C896]/10 text-[#2DD4AA]">
                {item.icon}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-zinc-100">{item.label}</p>
                <p className="font-mono text-[11px] text-zinc-500">{item.detail}</p>
              </div>
            </motion.div>
          ))}
        </div>

        {/* Real infrastructure — Fira-Code chips */}
        <motion.div variants={revealItem} className="mt-8 flex flex-wrap items-center justify-center gap-2">
          <span className="font-mono text-[11px] uppercase tracking-wider text-zinc-600">Running on</span>
          {infraStack.map((tech) => (
            <span
              key={tech}
              className="rounded-full border border-zinc-800 bg-zinc-950 px-2.5 py-1 font-mono text-[11px] text-zinc-400"
            >
              {tech}
            </span>
          ))}
        </motion.div>
      </motion.div>
    </section>
  );
}

// ─── Pricing ─────────────────────────────────────────────────────────────────
const plans = [
  {
    name: "Starter", price: "$49", per: "/mo",
    description: "For small teams getting started with AI-assisted CRM.",
    features: ["3 AI Agents", "Up to 1,000 contacts", "Lead scoring", "Email templates", "Dashboard analytics"],
    cta: "Start Free Trial", highlight: false,
  },
  {
    name: "Pro", price: "$149", per: "/mo",
    description: "Full agent suite for growing sales teams.",
    features: ["All 6 AI Agents", "Unlimited contacts", "Advanced analytics", "Call summarization", "Pipeline optimizer", "Priority support"],
    cta: "Start Free Trial", highlight: true,
  },
  {
    name: "Enterprise", price: "Custom", per: "",
    description: "A scoped engagement for teams with specific requirements.",
    features: ["Custom agent development", "Custom onboarding", "Dedicated point of contact", "Requirements scoped with you"],
    cta: "Contact Sales", highlight: false,
  },
];

function PricingSection() {
  return (
    <section id="pricing" className="px-6 py-24" aria-labelledby="pricing-heading">
      <div className="mx-auto max-w-5xl">
        <div className="text-center mb-16">
          <p className="text-xs font-mono text-indigo-400 uppercase tracking-widest mb-3">Pricing</p>
          <h2 id="pricing-heading" className="text-3xl font-bold text-zinc-100 sm:text-4xl">Simple, transparent pricing</h2>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {plans.map((plan) => (
            <div key={plan.name} className={cn("rounded-2xl border p-6 flex flex-col", plan.highlight ? "border-indigo-500/40 bg-indigo-600/5 shadow-glow" : "border-zinc-800 bg-zinc-900")}>
              {plan.highlight && (
                <div className="mb-4 inline-flex self-start rounded-full bg-indigo-500/20 px-3 py-1 text-xs font-medium text-indigo-300 border border-indigo-500/30">
                  Recommended
                </div>
              )}
              <h3 className="text-base font-bold text-zinc-100">{plan.name}</h3>
              <div className="mt-2 flex items-end gap-1">
                <span className="text-3xl font-bold font-mono text-zinc-100">{plan.price}</span>
                <span className="text-sm text-zinc-500 mb-1">{plan.per}</span>
              </div>
              <p className="mt-2 text-sm text-zinc-400 mb-6">{plan.description}</p>
              <ul className="space-y-2.5 flex-1">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-center gap-2.5 text-sm text-zinc-300">
                    <Check className="h-4 w-4 text-emerald-400 flex-shrink-0" aria-hidden="true" />
                    {f}
                  </li>
                ))}
              </ul>
              <Link
                href="/dashboard"
                className={cn(
                  "mt-8 flex w-full items-center justify-center gap-2 rounded-xl py-2.5 text-sm font-semibold transition-all duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-zinc-950",
                  plan.highlight ? "bg-indigo-600 text-white hover:bg-indigo-500 shadow-glow-sm" : "border border-zinc-700 bg-zinc-800 text-zinc-300 hover:border-zinc-600 hover:text-zinc-100"
                )}
              >
                {plan.cta}
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── CTA ─────────────────────────────────────────────────────────────────────
function CTASection() {
  return (
    <section className="relative overflow-hidden px-6 py-24" aria-labelledby="cta-heading">
      <div className="pointer-events-none absolute inset-0 bg-glow-indigo" aria-hidden="true" />
      <div className="mx-auto max-w-2xl text-center relative">
        <h2 id="cta-heading" className="text-3xl font-bold text-zinc-100 sm:text-4xl">
          Your pipeline deserves{" "}
          <span className="bg-gradient-to-r from-indigo-300 via-indigo-400 to-[#2DD4AA] bg-clip-text text-transparent">a brain</span>
        </h2>
        <p className="mt-4 text-zinc-400">
          Put an AI layer on your pipeline — score leads, draft the follow-ups, and let the busywork run itself.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-8 py-3.5 text-base font-semibold text-white hover:bg-indigo-500 transition-all duration-200 shadow-glow cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-zinc-950"
          >
            Launch NovaCRM
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>
        <div className="mt-8 flex justify-center">
          <div className="flex items-center gap-2 text-sm text-zinc-500">
            <span className="text-indigo-400" aria-hidden="true"><Users className="h-4 w-4" /></span>
            You own your data
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── Footer ──────────────────────────────────────────────────────────────────
function Footer() {
  return (
    <footer className="border-t border-zinc-800 px-6 py-8">
      <div className="mx-auto max-w-6xl flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600">
            <Zap className="h-3.5 w-3.5 text-white" aria-hidden="true" />
          </div>
          <span className="text-sm font-bold text-zinc-300">NovaCRM</span>
        </div>
        <p className="text-xs text-zinc-600 font-mono">© 2026 NovaCRM · Agentic Intelligence Platform</p>
        <div className="flex items-center gap-4">
          {[
            { label: "Privacy", href: "/privacy" },
            { label: "Terms", href: "/terms" },
            { label: "Docs", href: "/help" },
            { label: "Status", href: "/status" },
          ].map((item) => (
            <a key={item.label} href={item.href} className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors cursor-pointer">{item.label}</a>
          ))}
        </div>
      </div>
    </footer>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function LandingPage() {
  return (
    <div className="min-h-screen bg-zinc-950">
      <AuthParamsRescue />
      <Nav />
      <Hero />
      <FeaturesSection />
      <AgentsSection />
      <PricingSection />
      <ProvenanceProof />
      <CTASection />
      <Footer />
    </div>
  );
}
