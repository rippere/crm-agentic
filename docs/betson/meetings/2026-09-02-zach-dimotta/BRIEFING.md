---
title: "BRIEFING — NovaCRM photo-booth vertical: directives from the Zach DiMotta call (2026-09-02)"
project: crm-agentic (NovaCRM)
date: 2026-09-02
audience: Ben (owner) · Mike Betti (ratify) · Zach DiMotta (requirements)
related:
  - ./RECAP.md
  - ./ANALYSIS-keywords.md
  - ./IDEAS.md
  - ./BACKLOG.md
  - ../../decisions/vertical-pivot-zach-2026-09-02.md
---

# Briefing — Zach DiMotta call (2026-09-02)

## TL;DR

The first live NovaCRM demo to Zach DiMotta **confirmed the vertical pivot from both sides** and
produced a concrete photo-booth requirements set. NovaCRM's Betson instance is now a **form-fit
photo-booth partner-acquisition CRM** — *"a knife, not a Swiss Army knife"* (Zach, `52:00`). Most of
what Zach wants **already exists** in the shipped module; the near-term win is **demoing it against
photo-booth-shaped data**, then adding two small retention features (account cadence/tiering; call
disposition). The booth-telemetry "moat" is designed now, built later. **Do not over-build** — Zach
has to sell booths the traditional way for ~6 months; make *that* faster first.

## Recap (60 seconds)

A 1h07m discovery call (Zach ~72% of the talking). Zach — 20 yrs billiards sales, ex-HubSpot/Shopify
— downloaded his ideal CRM; Ben demoed the built NovaCRM and committed to form-fitting it to the
photo-booth vertical (`29:23`). The funnel is **partner acquisition, not customer acquisition**
(`24:56`): cold-educating venues (bars, truck stops, retail) that have never considered a booth, on
revenue-share. Big themes: automated email sequences with open/click triggers, A/B/C account cadence
("the holy grail" — `6:53`), hot→cold churn detection, a success-story correlation engine, booth
telemetry + surge pricing, and an NL-query chatbot to keep it all simple. Full recap:
[`RECAP.md`](./RECAP.md); analysis: [`ANALYSIS-keywords.md`](./ANALYSIS-keywords.md).

---

## Directive points (act on these)

> Owner is Ben unless noted. Sequenced to the pacing contract (simple first).

1. **Seed the demo with photo-booth data and re-demo to Zach — THIS WEEK.** Replace Ben's personal
   "vibe-coded" workspace (`9:56`) with venue leads, A/B/C-tiered partners, a partner-education
   sequence, and a couple of "booths in the field." Highest ROI move; most of Zach's asks are already
   built and just need to be *shown in his world*. (BACKLOG Bucket A.)
2. **Ship Increment 1 (Sept): account cadence + A/B/C tiering (B4) and call-log mandatory
   next-step (B5).** These are small, reuse `tasks`/`commitments`, and make Zach faster at the
   traditional motion he must run now. B4 is his #1 emotional ask.
3. **Then Increment 2: the acquisition email loop — engagement webhooks (B1), send-time (B2),
   booking link (B3).** Completes the HubSpot-style trigger ladder Zach already knows works.
4. **Reframe the funnel as partner-acquisition** across ICP, scoring defaults, and messaging — and
   flag that `betson.com/revenue-share` is the wrong destination for non-traditional venues (`22:47`).
   Standalone landing page + simple intake questionnaire is a C1 dependency.
5. **Design (don't build yet) the booth-telemetry `device/asset` object (D1)** so the moat
   (success-story correlation, D2) has data from install #1. Book the external gate now: **get Smile
   OS / Out-of-Booth-Experience access** (via Joseph Camarota / Apple Industries).
6. **Take the five open questions to Zach and Mike** (below) to convert the triage into specs.
7. **Hold the pacing line.** Booth IoT, surge pricing, quarterly recaps = clearly-labeled later
   phases, not Sept/Oct commitments (`1:04:20`). Resist scope creep — both parties flagged it.
8. **Coordinate with Betson marketing (Michael)** on inbound leads + the landing page — Zach has that
   call this week (`22:47`).

## What will come from it

- **Immediately:** a photo-booth-shaped demo Zach can react to → the next elicitation pass (his
  reactions become requirements, idea I11). Ben's own committed next step was exactly this: *"take the
  transcript, ingest it, apply it to the CRM schema, see what it generates, shoot Zach another
  message"* (`1:06:08`) — **this document set is that deliverable; the follow-up message to Zach is
  the remaining action.**
- **September:** retention basics (cadence/tiering, call disposition) live — Zach measurably faster at
  relationship upkeep across a growing account base.
- **Following increments:** the full acquisition email loop, then the venue ICP / lookalike lead-gen
  front end (the vertical's top of funnel) + a simplified junior-rep view and NL query.
- **Once booths are in the field:** the telemetry spine → the **success-story correlation moat** +
  quarterly value-recaps + surge pricing. This is the compounding, "why-not-HubSpot" differentiation.
- **Strategically:** a proven vertical instance that doubles as the **template for the next vertical**
  (idea I1) and a live test of Mike's "is Nova viable as a product" question.

## Risks & guardrails

- **Over-building (highest risk).** Both parties named it. The metric of success is Zach choosing Nova
  because it makes his *current* job easier — not feature count. Ship B before C before D.
- **Demoing the wrong world.** Showing Ben's personal projects undersells it; seed photo-booth data
  first (Directive 1).
- **External gate — Smile OS access (D1).** Booth telemetry, and everything downstream, is blocked
  without portal access. Start that ask early; it's not in hand.
- **Marketing dependency (C1).** The landing page / inbound leads need Betson marketing; Ben ships
  standalone and hands to IT, which is "still pretty slow" (`1:03:51`) — plan around that latency.
- **Positioning drift.** Keep native-first; do not let "we might integrate Salesforce someday" pull
  the schema back toward Salesforce's shape (`salesforce-coexistence.md`).

## Open questions (need Zach / Mike)

| # | Question | Ask |
|---|---|---|
| 1 | Venue ICP attributes + weights; disposable-income proxy source | Zach |
| 2 | A/B/C tier SLAs (default 15/90/180d?) + who assigns tiers | Zach |
| 3 | Booking backend: native slot picker vs. Cal.com/Calendly | Zach / IT |
| 4 | Landing page ownership + what inbound leads marketing can feed | Zach ↔ Michael |
| 5 | Smile OS / booth telemetry data access | Zach → Joseph Camarota / Apple Industries |
| 6 | Ratify vertical form-fit + defer-the-moat pacing | Mike Betti |

---

*Sources: [`transcript.md`](./transcript.md) (cited `M:SS`), [`ANALYSIS-keywords.md`](./ANALYSIS-keywords.md),
[`BACKLOG.md`](./BACKLOG.md), [`decisions/vertical-pivot-zach-2026-09-02.md`](../../decisions/vertical-pivot-zach-2026-09-02.md).*
