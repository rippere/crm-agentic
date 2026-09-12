# NovaCRM In-App Onboarding Tutorial — Master Spec
> Living planning document. Status: structure + methodology locked (2026-09-10). Module content: in progress.

## 1. Goal & audience
Build a procedural, in-app guided onboarding that teaches a brand-new NovaCRM user the whole product by *doing* — each module builds on the one before it, so the user finishes with a populated, working CRM and the habits to run it.
- Audience: new end-user (founder / salesperson). Assume ZERO product knowledge.
- Delivery: in-app guided walkthrough (spotlights / anchored steps on real UI), NOT a doc. No coachmark/tooltip system exists yet — net-new to build. Existing apps/web/src/app/help/page.tsx is static marketing copy — mine for VOICE, not structure.
- Data mode: REAL data. The user creates their actual first contact / deal during onboarding. Nothing is a throwaway sandbox.

## 2. Teaching methodology — per-module 6-slot template
1. Why this exists (1-2 sentences, job-to-be-done). 2. Prerequisite check (= previous module's checkpoint). 3. Anchored walkthrough (spotlight the real UI element, one action at a time). 4. Do it with your data (user performs the action for real). 5. What just happened (reinforce result + forward-reference downstream). 6. Checkpoint (verifiable completion signal before advancing).
Structural principles:
- Progressive gating (SOFT): each module's prerequisite check IS the previous module's checkpoint. Recommend order, warn on skips, let power-users jump ahead.
- Forward references: every "what just happened" points to where that data resurfaces later (feels like one experience, not disconnected tips).
- AI woven in-context: all AI is in-app (Nova via ⌘K, compose-email, briefs, deal coaching, forecasts, call summaries, triage). Introduce the relevant AI capability INSIDE the module it helps, as a tooling tip — never bolted on separately. (mcp__novacrm__* tools are a separate external interface, out of scope.)
- Branch by mode: onboarding forces a workspace mode (Sales / PM / Both) that hides/shows nav. Tutorial follows: shared core → mode-specific track → shared capstone. Never teach nav the user's mode hides.
- Level-2 split: first-run makes the user productive on fundamentals. The most advanced modules (deep Nova AI, Nexus agents + Slack HITL approvals) are a separate level-2, surfaced later once the user has data and habits.

## 3. Module map
Shared core (everyone, in order):
0. Get set up — signup, name workspace, pick mode, connect Gmail+Slack, invite team (no AI)
1. Your home base — dashboard, ⌘K command bar, sidebar shell | AI: Meet Nova "ask your CRM anything" via ⌘K
2. Contacts — the foundation. Create / CSV-import, enrich, dedupe | AI: enrich contact, semantic search, contact brief
3. Inbox & Calls — Gmail/Slack sync, upload a call | AI: sentiment, auto-extract tasks/contacts, call summary + action items
Sales track (mode = Sales or Both):
S1 Leads — capture, score, promote to contact/deal | AI: lead scoring
S2 Pipeline & Deals — Kanban board, stages, deal health | AI: deal coaching, forecast, win/loss
S3 Sequences → Campaigns → Outreach — automate follow-up | AI: reply drafting, follow-up sequences
S4 Reports — funnel, velocity, forecast dashboards | AI: pipeline narrative / pulse
PM track (mode = PM or Both):
P1 Tasks — create, prioritize | AI: task prioritization
P2 Projects — organize work, PM agent | AI: project health check
Level-2 capstone (everyone, unlocked later):
C1 Goals: Commitments & KPIs | C2 Nova AI, deep (NL querying, digests, briefings — full-power ⌘K) | C3 Nexus agents & Slack approvals (background automation + HITL)

## 4. Product surface reference (for authoring)
Frontend: Next.js 16 (App Router, React 19, TS), Tailwind v4, framer-motion, lucide-react, recharts, @dnd-kit (Kanban), Supabase auth. Dark-themed collapsible left-sidebar shell with ⌘K command palette + live "Nexus" agent-status panel. Demo Mode via NEXT_PUBLIC_DEMO_MODE.
Key entry points:
- Sidebar nav: apps/web/src/components/layout/Sidebar.tsx:60 (mode gating :250)
- Onboarding wizard: apps/web/src/app/onboarding/page.tsx:11
- Existing help copy (voice source): apps/web/src/app/help/page.tsx
- API router wiring: apps/api/app/main.py:126-153

## 5. Open items / next steps
- [ ] Develop Module 0 (Get set up) end-to-end against the 6-slot template.
- [ ] Decide the delivery mechanism for the in-app coachmark/spotlight layer (net-new). [RESOLVED by product owner: custom framer-motion overlay, no new dep.]
- [ ] Per-track proceed to S1… / P1… once core modules are drafted.

## 6. Implementation notes (engine — first slice, 2026-09-11)
The reusable tour engine and Module 0 are implemented. Modules 1+ are authored purely as data against this engine.

- Engine types: `apps/web/src/lib/onboarding/types.ts` — the 6-slot `TourStep`
  (`whyThisExists`, `prerequisiteCheck`, `anchor`, `actionGuidance`,
  `whatJustHappened`+`forwardReference`, `checkpoint`), plus the `aiTip` slot
  (for the "AI woven in-context" principle) and `showForModes`/`hideForModes`
  (for "branch by mode"). A `TourModule` groups steps.
- Controller: `apps/web/src/lib/onboarding/TourProvider.tsx` — `TourProvider` +
  `useTour`. Soft-gating with jump-ahead, skip/pause/resume, localStorage
  progress per (module, user/workspace). `filterStepsForMode` guarantees the
  engine never spotlights nav the workspace mode hides.
- Spotlight layer: `apps/web/src/components/onboarding/TourSpotlight.tsx` +
  `useAnchorRect.ts` — React-portal backdrop with a box-shadow cut-out, an
  anchored auto-placing popover, selector lookup with polling (re-attaches as
  the underlying UI mounts new elements), reposition on scroll/resize/mutation,
  focus management, Esc/skip. Non-blocking coach-mark so the real UI stays
  interactive (required — checkpoints are manual-confirm on real controls).
- Checkpoints: manual-confirm ("I did it → Next") + optional cheap, non-blocking
  soft-verify + nudge. Progressive gating is SOFT per §2.
- Module 0: `apps/web/src/lib/onboarding/modules/module-0-setup.ts`, anchored to
  the real onboarding wizard via `data-tour="..."` selectors, mounted through
  `apps/web/src/components/onboarding/OnboardingTour.tsx`.

Authoring a later module (e.g. S1 Leads): supply a `TourModule` whose steps set
`anchor.selector` to a stable `data-tour` on the target page, set
`showForModes`/`hideForModes` for the track, put the module's AI capability in
`aiTip`, express the "prerequisite check = previous module's checkpoint" via the
step's soft `prerequisiteCheck.verify`, and mount `<TourSpotlight/>` inside a
`<TourProvider mode={workspaceMode} scopeKey={workspaceId}>` in the app shell.
