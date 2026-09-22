# NovaCRM In-App Onboarding Tutorial — Master Spec

> Living planning document. Captures the agreed structure and methodology for the
> procedural, in-app guided onboarding. Each module is developed against this spec.
> Status: **structure + methodology locked** (2026-09-10). Module content: in progress.

---

## 1. Goal & audience

Build a **procedural, in-app guided onboarding** that teaches a brand-new NovaCRM user
the whole product by *doing* — each module builds on the one before it, so the user
finishes with a populated, working CRM and the habits to run it.

- **Audience:** new end-user (founder / salesperson). Assume **zero** product knowledge.
- **Delivery:** in-app guided walkthrough (spotlights / anchored steps on real UI),
  **not** a doc someone reads. NB: no coachmark/tooltip system exists in the app yet —
  this onboarding UI is net-new to build. Existing `apps/web/src/app/help/page.tsx` is
  static marketing copy — mine it for product *voice*, not structure.
- **Data mode:** **real data.** The user creates their actual first contact / deal
  during onboarding. Learn by doing for real; nothing is a throwaway sandbox.

---

## 2. Teaching methodology — the per-module template

Every module is a self-contained, do-it-live unit following this 6-slot loop:

| Slot | Purpose | New-user framing example |
|------|---------|--------------------------|
| **1. Why this exists** | 1–2 sentences, job-to-be-done | "Deals are how you track money in motion. Without them, the pipeline is empty." |
| **2. Prerequisite check** | What must already be true (= previous module's checkpoint) | Deals module won't start until ≥1 contact exists |
| **3. Anchored walkthrough** | Spotlight the real UI element, one action at a time | Highlight the actual button; user clicks it — not a screenshot |
| **4. Do it with your data** | User performs the action for real, on a real record | Creates their first real deal |
| **5. What just happened** | Reinforce the result + forward-reference downstream | "That deal now feeds your Pipeline view — you'll see it in module S2." |
| **6. Checkpoint** | Verifiable completion signal before advancing | Action detected as done |

### Structural principles

- **Progressive gating (soft).** Each module's *prerequisite check* is literally the
  previous module's *checkpoint* — that is what makes it procedural. Gating is **soft**:
  recommend the order, warn on skips, but let power-users jump ahead.
- **Forward references.** Every "what just happened" points to where that data resurfaces
  later. This makes it feel like one comprehensive experience, not disconnected tips.
- **AI woven in-context.** All AI is in-app (Nova via ⌘K, compose-email, briefs, deal
  coaching, forecasts, call summaries, triage). Introduce the relevant AI capability
  *inside* the module it helps, as a tooling tip — never bolted on as a separate feature.
  (The `mcp__novacrm__*` tools are a separate external agent interface, out of scope here.)
- **Branch by mode.** Onboarding forces a workspace mode (Sales / PM / Both) that
  hides/shows nav. The tutorial follows suit: a shared core, then a mode-specific track,
  then a shared capstone. Never teach nav the user's mode hides.
- **Level-2 split.** First-run onboarding makes the user *productive on fundamentals*.
  The most advanced modules (deep Nova AI, Nexus agents + Slack HITL approvals) are a
  **separate level-2**, surfaced later once the user has data and habits.

---

## 3. Module map

### Shared core — everyone, in order

| # | Module | Builds on | AI woven in |
|---|--------|-----------|-------------|
| 0 | **Get set up** — signup, name workspace, pick mode, connect Gmail+Slack, invite team | — | — |
| 1 | **Your home base** — dashboard, ⌘K command bar, sidebar shell | 0 | Meet Nova: "ask your CRM anything" via ⌘K |
| 2 | **Contacts** — the foundation. Create / CSV-import, enrich, dedupe | 1 | Enrich contact, semantic search, contact brief |
| 3 | **Inbox & Calls** — Gmail/Slack sync, upload a call | 2 | Sentiment, auto-extract tasks/contacts, call summary + action items |

### Sales track (mode = Sales or Both)

| # | Module | AI tip |
|---|--------|--------|
| S1 | **Leads** — capture, score, promote to contact/deal | Lead scoring |
| S2 | **Pipeline & Deals** — Kanban board, stages, deal health | Deal coaching, forecast, win/loss |
| S3 | **Sequences → Campaigns → Outreach** — automate follow-up | AI reply drafting, follow-up sequences |
| S4 | **Reports** — funnel, velocity, forecast dashboards | Pipeline narrative / pulse |

### PM track (mode = PM or Both)

| # | Module | AI tip |
|---|--------|--------|
| P1 | **Tasks** — create, prioritize | AI task prioritization |
| P2 | **Projects** — organize work, PM agent | Project health check |

### Level-2 capstone — everyone, unlocked later

| # | Module | Notes |
|---|--------|-------|
| C1 | **Goals: Commitments & KPIs** | set targets against real activity |
| C2 | **Nova AI, deep** | natural-language querying, digests, briefings — the ⌘K assistant from module 1, full-power |
| C3 | **Nexus agents & Slack approvals** | background automation + human-in-the-loop approvals |

---

## 4. Product surface reference (for authoring)

Frontend: Next.js 16 (App Router, React 19, TS), Tailwind v4, framer-motion, lucide-react,
recharts, @dnd-kit (Kanban), Supabase auth. Dark-themed collapsible left-sidebar shell with
⌘K command palette and a live "Nexus" agent-status panel. Demo Mode via `NEXT_PUBLIC_DEMO_MODE`.

Key entry points:
- Sidebar nav: `apps/web/src/components/layout/Sidebar.tsx:60` (mode gating `:250`)
- Onboarding wizard: `apps/web/src/app/onboarding/page.tsx:11`
- Existing help copy (voice source): `apps/web/src/app/help/page.tsx`
- API router wiring: `apps/api/app/main.py:126-153`

---

## 5. Open items / next steps

- [ ] Develop **Module 0 (Get set up)** end-to-end against the 6-slot template.
- [ ] Decide the delivery mechanism for the in-app coachmark/spotlight layer (net-new).
- [ ] Per-track proceed to S1… / P1… once core modules are drafted.
