"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Zap, Brain, Sparkles, TrendingUp, Bot, Shield,
  ArrowRight, Check, ChevronDown, Mail, Mic, Heart,
  BarChart3, Users, KanbanSquare, Menu, X,
} from "lucide-react";
import { cn } from "@/lib/utils";

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
        {["Features", "Agents", "Pricing", "Docs"].map((item) => (
          <a
            key={item}
            href={`#${item.toLowerCase()}`}
            className="text-sm text-zinc-400 hover:text-zinc-100 transition-colors duration-200 cursor-pointer"
          >
            {item}
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

      {open && (
        <div className="absolute top-full left-0 right-0 mt-2 rounded-2xl border border-zinc-800 bg-zinc-950 p-4 space-y-3 md:hidden">
          {["Features", "Agents", "Pricing", "Docs"].map((item) => (
            <a
              key={item}
              href={`#${item.toLowerCase()}`}
              className="block text-sm text-zinc-400 hover:text-zinc-100 py-2 transition-colors"
              onClick={() => setOpen(false)}
            >
              {item}
            </a>
          ))}
          <Link href="/dashboard" className="block w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-center text-sm font-medium text-white">
            Start Free
          </Link>
        </div>
      )}
    </nav>
  );
}

// ─── Hero ─────────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section
      className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-6 pt-28 pb-16 text-center"
      aria-labelledby="hero-heading"
    >
      <div className="pointer-events-none absolute inset-0 bg-grid-pattern bg-grid opacity-100" aria-hidden="true" />
      <div className="pointer-events-none absolute inset-0 bg-glow-indigo" aria-hidden="true" />

      <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-4 py-1.5 text-xs font-medium text-indigo-300">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 agent-pulse" aria-hidden="true" />
        6 AI Agents Running · 94.7% Accuracy
      </div>

      <h1
        id="hero-heading"
        className="mx-auto max-w-4xl text-5xl font-bold leading-tight tracking-tight text-zinc-100 sm:text-6xl lg:text-7xl"
      >
        Your CRM{" "}
        <span className="bg-gradient-to-r from-indigo-400 to-emerald-400 bg-clip-text text-transparent">
          thinks for itself
        </span>
      </h1>

      <p className="mx-auto mt-6 max-w-2xl text-lg text-zinc-400 leading-relaxed">
        NovaCRM uses semantic AI to classify leads, ML models to score deals,
        and autonomous agents to compose emails, summarize calls, and move
        your pipeline — all without lifting a finger.
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

      <p className="mt-8 text-xs text-zinc-600">No credit card required · SOC 2 Type II · 99.9% uptime</p>

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
              { val: "94.7%", label: "Accuracy" },
              { val: "6 / 8", label: "Agents" },
            ].map(({ val, label }, i) => (
              <div key={label} className="rounded-xl border border-zinc-800 bg-zinc-950 p-3">
                <p className="text-lg font-bold font-mono text-zinc-100">{val}</p>
                <p className="text-xs text-zinc-500 mt-0.5">{label}</p>
                <div className="mt-2 h-1 rounded-full bg-zinc-800" aria-hidden="true">
                  <div className="h-full rounded-full bg-indigo-500" style={{ width: `${[72, 58, 94, 75][i]}%` }} />
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
    title: "ML Lead Scoring",
    description: "An XGBoost model trained on your historical deal outcomes scores every lead 0–100 using behavioral signals and firmographic data.",
    tags: ["XGBoost v2", "Feature Store", "F1: 0.947"],
    color: "emerald",
  },
  {
    icon: <TrendingUp className="h-5 w-5" />,
    title: "Pipeline Intelligence",
    description: "Detects deal stalls with reinforcement learning, predicts win probability in real time, and recommends your next best action.",
    tags: ["RL Policy", "LightGBM", "Win Prediction"],
    color: "indigo",
  },
  {
    icon: <Mail className="h-5 w-5" />,
    title: "Autonomous Email Composer",
    description: "GPT-4o drafts hyper-personalized outreach using semantic tags, deal stage, and contact history. Review or send automatically.",
    tags: ["GPT-4o Fine-tuned", "48% Open Rate", "22% Reply Rate"],
    color: "amber",
  },
  {
    icon: <Mic className="h-5 w-5" />,
    title: "Call Summarization",
    description: "Whisper transcribes your sales calls. Claude extracts action items, objections, and sentiment — updating your CRM in 23 seconds.",
    tags: ["Whisper Large v3", "Claude 3.5", "Action Item Extraction"],
    color: "emerald",
  },
  {
    icon: <Heart className="h-5 w-5" />,
    title: "Churn Prediction",
    description: "RoBERTa analyzes every email, ticket, and call transcript. Flags at-risk accounts before sentiment drops below your threshold.",
    tags: ["RoBERTa Fine-tuned", "Sentiment Score", "Early Warning"],
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
            Each agent is a specialized ML model trained for a specific CRM task — working together in a single, seamless workflow.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => {
            const c = colorMap[f.color];
            return (
              <div key={f.title} className={cn("group rounded-2xl border border-zinc-800 bg-zinc-900 p-6 transition-all duration-200 cursor-default hover:bg-zinc-800/80", c.border)}>
                <div className={cn("mb-4 inline-flex h-10 w-10 items-center justify-center rounded-xl border", c.icon)}>
                  {f.icon}
                </div>
                <h3 className="text-base font-semibold text-zinc-100 mb-2">{f.title}</h3>
                <p className="text-sm text-zinc-400 leading-relaxed mb-4">{f.description}</p>
                <div className="flex flex-wrap gap-1.5">
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

// ─── Agents showcase ─────────────────────────────────────────────────────────
function AgentsSection() {
  return (
    <section id="agents" className="relative overflow-hidden px-6 py-24 bg-gradient-to-b from-zinc-950 to-zinc-900" aria-labelledby="agents-heading">
      <div className="pointer-events-none absolute inset-0 bg-glow-emerald" aria-hidden="true" />
      <div className="mx-auto max-w-4xl text-center relative">
        <p className="text-xs font-mono text-emerald-400 uppercase tracking-widest mb-3">Live Automation</p>
        <h2 id="agents-heading" className="text-3xl font-bold text-zinc-100 sm:text-4xl">Agents that never sleep</h2>
        <p className="mt-4 text-zinc-400 max-w-xl mx-auto">
          Every agent runs on a live feedback loop — retraining on your data, updating scores in real-time, and triggering actions when conditions are met.
        </p>
        <div className="mt-12 rounded-2xl border border-zinc-800 bg-zinc-950 text-left overflow-hidden">
          <div className="flex items-center gap-2 border-b border-zinc-800 px-4 py-3 bg-zinc-900">
            <Bot className="h-4 w-4 text-indigo-400" aria-hidden="true" />
            <span className="text-xs font-mono text-zinc-400">Agent Activity Log · Live</span>
            <span className="ml-auto flex items-center gap-1.5 text-xs text-emerald-400 font-mono">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 agent-pulse" aria-hidden="true" />
              streaming
            </span>
          </div>
          <div className="p-4 space-y-2 font-mono text-xs" role="log" aria-live="polite" aria-label="Agent activity log">
            {[
              { time: "14:32:01", agent: "LeadScorer", msg: "contact:c6 score updated 88→95 · signals:[upsell,champion,power_user]", color: "text-emerald-400" },
              { time: "14:31:58", agent: "SemanticSorter", msg: "batch:48 contacts tagged · avg_confidence:0.941", color: "text-indigo-400" },
              { time: "14:31:44", agent: "EmailComposer", msg: "draft:email_0092 queued · contact:marcus_webb · stage:proposal", color: "text-amber-400" },
              { time: "14:31:32", agent: "PipelineOptimizer", msg: "deal:d1 moved discovery→negotiation · win_prob:87%", color: "text-indigo-300" },
              { time: "14:31:19", agent: "SentimentAnalyzer", msg: "⚠ at_risk:lena_kovacs · sentiment:0.31 · re_engagement:triggered", color: "text-rose-400" },
              { time: "14:31:05", agent: "LeadScorer", msg: "model_retrain complete · samples:1204 · f1:0.947→0.951", color: "text-emerald-400" },
            ].map(({ time, agent, msg, color }) => (
              <div key={time + agent} className="flex items-start gap-3">
                <span className="text-zinc-700 flex-shrink-0">{time}</span>
                <span className={cn("flex-shrink-0", color)}>[{agent}]</span>
                <span className="text-zinc-400 break-all">{msg}</span>
              </div>
            ))}
            <div className="flex items-center gap-2 pt-1">
              <span className="text-zinc-700">14:32:02</span>
              <span className="text-indigo-400">[SemanticSorter]</span>
              <span className="text-zinc-500 cursor-blink">processing batch:49</span>
            </div>
          </div>
        </div>
      </div>
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
    features: ["All 6 AI Agents", "Unlimited contacts", "Custom ML models", "Call summarization", "Pipeline optimizer", "Priority support"],
    cta: "Start Free Trial", highlight: true,
  },
  {
    name: "Enterprise", price: "Custom", per: "",
    description: "Dedicated infrastructure, custom training, and SLAs.",
    features: ["Custom agent development", "On-premise deployment", "SSO + SCIM", "Dedicated ML engineer", "99.99% SLA"],
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
                  Most Popular
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
          <span className="bg-gradient-to-r from-indigo-400 to-emerald-400 bg-clip-text text-transparent">a brain</span>
        </h2>
        <p className="mt-4 text-zinc-400">
          Join teams using NovaCRM to close deals faster, never miss a follow-up, and let AI handle the work that slows you down.
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
        <div className="mt-8 flex flex-wrap justify-center gap-6">
          {[{ icon: <Shield className="h-4 w-4" />, label: "SOC 2 Type II" }, { icon: <BarChart3 className="h-4 w-4" />, label: "99.9% Uptime" }, { icon: <Users className="h-4 w-4" />, label: "GDPR Compliant" }].map(({ icon, label }) => (
            <div key={label} className="flex items-center gap-2 text-sm text-zinc-500">
              <span className="text-indigo-400" aria-hidden="true">{icon}</span>
              {label}
            </div>
          ))}
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
          {["Privacy", "Terms", "Docs", "Status"].map((item) => (
            <a key={item} href="#" className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors cursor-pointer">{item}</a>
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
      <Nav />
      <Hero />
      <FeaturesSection />
      <AgentsSection />
      <PricingSection />
      <CTASection />
      <Footer />
    </div>
  );
}
