"use client";

import { motion } from "framer-motion";
import { Quote } from "lucide-react";
import { cn } from "@/lib/utils";

// ─── Testimonials ────────────────────────────────────────────────────────────
// NovaCRM-flavored social proof. Quotes lean into the agentic angle (scoring,
// autonomous email, pipeline stall detection) rather than generic SaaS praise.
type Testimonial = {
  name: string;
  role: string;
  company: string;
  quote: string;
  metric: string;
  initials: string;
  image: string;
  accent: "indigo" | "signal";
};

const testimonials: Testimonial[] = [
  {
    name: "Sarah Chen",
    role: "VP Sales",
    company: "Lumen Logistics",
    quote:
      "The lead scorer reordered our entire pipeline on day one. Reps stopped chasing dead deals and our hottest accounts finally got worked first.",
    metric: "+34% win rate",
    initials: "SC",
    image: "/testimonials/sarah-chen.jpg",
    accent: "signal",
  },
  {
    name: "Marcus Webb",
    role: "Founder & CEO",
    company: "Solvio",
    quote:
      "It drafts outreach that actually sounds like me. I review a queue every morning instead of writing cold emails from scratch.",
    metric: "6 hrs/week back",
    initials: "MW",
    image: "/testimonials/marcus-webb.jpg",
    accent: "indigo",
  },
  {
    name: "Hannah Brooks",
    role: "RevOps Lead",
    company: "Northwind",
    quote:
      "Stall detection caught a $180k deal that had gone quiet for three weeks. We re-engaged the day it flagged and closed it.",
    metric: "$180k saved",
    initials: "HB",
    image: "/testimonials/hannah-brooks.jpg",
    accent: "signal",
  },
  {
    name: "Dmitri Volkov",
    role: "Head of Growth",
    company: "Caldera",
    quote:
      "Semantic sorting tagged 1,200 contacts by buying stage overnight. No rules, no manual fields. It just understood the book.",
    metric: "1.2k auto-tagged",
    initials: "DV",
    image: "/testimonials/dmitri-volkov.jpg",
    accent: "indigo",
  },
  {
    name: "Lena Kovacs",
    role: "Customer Success",
    company: "Brightpath",
    quote:
      "Churn risk pinged me before a key account went cold. I'd have missed the sentiment drop entirely in our old CRM.",
    metric: "0 surprise churns",
    initials: "LK",
    image: "/testimonials/lena-kovacs.jpg",
    accent: "signal",
  },
  {
    name: "James Wilson",
    role: "COO",
    company: "ScaleUp",
    quote:
      "We replaced three tools and a part-time ops hire with NovaCRM. The agents run whether anyone's watching the dashboard or not.",
    metric: "3 tools → 1",
    initials: "JW",
    image: "/testimonials/james-wilson.jpg",
    accent: "indigo",
  },
];

const accentMap = {
  indigo: { ring: "hover:border-indigo-500/30", quote: "text-indigo-500/40", metric: "bg-indigo-500/10 text-indigo-300 border-indigo-500/20" },
  signal: { ring: "hover:border-[#00C896]/30", quote: "text-[#00C896]/40", metric: "bg-[#00C896]/10 text-[#6EFFD5] border-[#00C896]/20" },
} as const;

const container = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};
const item = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.55, ease: [0.22, 1, 0.36, 1] as const } },
};

export function Testimonials() {
  return (
    <section id="testimonials" className="px-6 py-24" aria-labelledby="testimonials-heading">
      <div className="mx-auto max-w-6xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="mb-16 text-center"
        >
          <p className="text-xs font-mono text-[#00C896] uppercase tracking-widest mb-3">Proof</p>
          <h2 id="testimonials-heading" className="text-3xl font-bold text-zinc-100 sm:text-4xl">
            Sales teams that stopped doing busywork
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-zinc-400">
            Revenue leaders run their pipeline on NovaCRM&apos;s agents — and let the busywork run itself.
          </p>
        </motion.div>

        <motion.div
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
          variants={container}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.1 }}
        >
          {testimonials.map((t) => {
            const a = accentMap[t.accent];
            return (
              <motion.figure
                key={t.name}
                variants={item}
                className={cn(
                  "group relative flex flex-col rounded-2xl border border-zinc-800 bg-zinc-900/60 p-6 backdrop-blur-sm transition-all duration-300 hover:bg-zinc-900",
                  a.ring
                )}
              >
                <Quote className={cn("mb-4 h-7 w-7", a.quote)} aria-hidden="true" />
                <blockquote className="flex-1 text-[15px] leading-relaxed text-zinc-300">
                  &ldquo;{t.quote}&rdquo;
                </blockquote>
                <figcaption className="mt-6 flex items-center justify-between border-t border-zinc-800 pt-5">
                  <div className="flex items-center gap-3">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={t.image}
                      alt={t.name}
                      loading="lazy"
                      width={44}
                      height={44}
                      className="h-11 w-11 rounded-full object-cover ring-2 ring-zinc-700/60"
                    />
                    <div className="leading-tight">
                      <p className="text-sm font-semibold text-zinc-100">{t.name}</p>
                      <p className="text-xs text-zinc-500">{t.role} · {t.company}</p>
                    </div>
                  </div>
                  <span className={cn("shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-mono font-medium", a.metric)}>
                    {t.metric}
                  </span>
                </figcaption>
              </motion.figure>
            );
          })}
        </motion.div>
      </div>
    </section>
  );
}
