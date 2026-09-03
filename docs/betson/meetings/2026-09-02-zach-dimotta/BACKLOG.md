---
title: "BACKLOG — Photo-booth vertical: build triage from the Zach DiMotta call (2026-09-02)"
project: crm-agentic (NovaCRM)
date: 2026-09-02
status: "Forward-dev triage — NOT a build order yet. Ben scopes buckets B/C into BUILD-SPEC increments; buckets A/D are show-now / defer."
builds_on:
  - ../../BUILD-SPEC-leadgen.md            # shipped module (migration 023, PR #73)
  - ../../BUILD-SPEC-leadgen-criteria-cascade.md   # cascade increment (migration 024)
  - ../../decisions/leadgen-direction-zach-2026-08-31.md
related:
  - ./ANALYSIS-keywords.md
  - ../../decisions/vertical-pivot-zach-2026-09-02.md
---

# Photo-booth vertical — build triage (from 2026-09-02 call)

Every requirement Zach raised, triaged by **how close it already is** and mapped **reuse-first** onto
the shipped schema (`leads / lead_segments / sequences / sequence_steps / campaigns /
sequence_enrollments / engagement_events / cascade_rules / cascade_matches`, plus `contacts / deals /
tasks / commitments / activity_events`). Theme codes (T#) reference `ANALYSIS-keywords.md`.

**Four buckets:** **A** = already built (show, don't build) · **B** = near-term increments on the
shipped module (small, high-leverage) · **C** = new vertical modules (medium) · **D** = later /
depends on field data. The pacing contract (T18): ship B first; C after the acquisition slice proves;
D is explicitly "Star Trek — later."

---

## Bucket A — Already built → *demo it to Zach* (no build)

Zach asked for several things Ben has already shipped. The action is a **guided demo with seeded
photo-booth data**, not code. Seeding the demo workspace so Zach sees his own world (not Ben's
"vibe-coded" personal projects — `9:56`) is the single highest-ROI move this week.

| Zach asked (T#) | Already exists as | Action |
|---|---|---|
| Auto-drafted outreach a human reviews & sends (T4) | `/outreach` HITL queue + `sequence_step.requires_approval` + `ai_generate` | Seed a 3-step sequence; show draft → approve → send |
| Engagement scoring / hot-warm-cold (T4/T6) | `engagement_score` worker → `lead.score`+`score_detail` | Show the score gauge + timeline on `/leads/[id]` |
| Auto-enroll on matching criteria (T3) | cascade rules (`cascade_rules`/`cascade_matches`, migration 024) | Show a rule: criteria segment → preview count → activate |
| Call summarization / sentiment (T4) | call-summarization + sentiment-analyzer agents (demoed live) | Already shown; wire a real call transcript next |
| Nightly auto-tracking digest (T15) | worker digest / PM agent | Already shown |
| Enrichment (LinkedIn/phone/email) (T3) | contact/lead enrichment | Already shown |

> **Do first:** a photo-booth **demo seed** (`demo-data.ts` + optionally a seeded workspace) — venue
> leads, an A/B/C-tiered set of partners, a partner-education sequence, a couple of "booths in the
> field." Everything below demos better against real-shaped data.

---

## Bucket B — Near-term increments on the shipped module (small, high-leverage)

These are thin additions to code that already exists. Each is a candidate BUILD-SPEC increment sized
for one agent.

### B1 — Open/click/dwell engagement webhooks → the trigger ladder (T4) ★ top priority
- **Gap:** the trigger ladder Zach described ("opened → wait a week; clicked → 3 days; opened that →
  I call" — `21:39`) needs inbound **open/click** signals. The schema is ready:
  `engagement_events.type` already includes `opened`/`clicked`/`replied`, and
  `POST /webhooks/engagement` exists in the spec.
- **Reuse:** wire the email connector's tracking pixel + link-wrap → `POST /webhooks/engagement` →
  existing `engagement_score` + `sequence_sender` (`stop_on_reply`, step advance) already react.
- **New:** branch a sequence on an engagement event (open/click), not just elapsed delay — a
  `sequence_step.trigger` condition (`on_open` / `on_click` / `delay`).
- **Effort:** S–M. **Acceptance:** an open event advances an enrollment to the "clicked?" branch; a
  click fires the accelerated follow-up.

### B2 — Send-time optimization (T4)
- **Gap:** HubSpot's "this owner opens before 8am / after 3pm, send then" (`1:02:43`).
- **Reuse:** per-lead open timestamps already land in `engagement_events`. Compute a preferred
  send-window per lead; `sequence_sender` respects it when setting `next_run_at` (it already honors
  quiet-hours).
- **Effort:** S. **Acceptance:** a lead with a learned morning-open pattern gets sends scheduled into
  that window.

### B3 — Calendar-booking link primitive (T4)
- **Gap:** "make an appointment with me" link that self-books (`20:30`). High-conversion, Zach saw it
  work firsthand.
- **Reuse:** a `{{booking_link}}` token in `sequence_step.body_template`; a booking event posts back
  as an `engagement_event` (new type `booked`) and can auto-advance stage.
- **Effort:** S–M (needs a scheduling backend — Cal.com/Calendly embed or a minimal native slot
  picker). **Acceptance:** clicking the link books a slot and writes a `booked` engagement event.

### B4 — Account cadence + A/B/C tiering — "the holy grail" (T5) ★ Zach's #1 emotional ask
- **Gap:** per-partner tier (A/B/C) with a max-silence SLA (A=15d, B=90d, C=180d — `6:59`) that
  raises a reminder/task when breached. This is **retention**, distinct from acquisition sequences.
- **Reuse:** `contacts` (or a promoted `lead`) + `tasks`/`commitments` + a small beat worker
  (mirror `followup_sequences.py`). Add `contact.tier` (`A|B|C`) and derive the SLA; a daily sweep
  emits a task ("call Ben's Hardware — 62 days since contact") when `now - last_contacted > sla`.
- **New:** `tier` field + a `cadence_sweep` worker + a "due for contact" surface (reuse the
  followups/standup surface that already exists).
- **Effort:** M. **Acceptance:** a C-tier partner silent 181 days generates exactly one open task;
  contacting them clears it.

### B5 — Call-log → mandatory next-step disposition (T11)
- **Gap:** closing a call log must force a disposition + next-step (follow-up 1mo / 6mo / dead —
  `13:35`).
- **Reuse:** the existing log-activity modal + `tasks`. Add a required `disposition` enum on
  call-type activities; `dead` sets `lead.stage='lost'`; the follow-up choices create a dated task
  (feeds B4).
- **Effort:** S. **Acceptance:** a call log cannot be saved without a disposition; "follow up in a
  month" creates a task due +30d.

### B6 — Role-scoped junior-rep view (T10)
- **Gap:** a dumbed-down "call this guy today / here are your leads" view for a new rep vs. the full
  senior view (`17:58`).
- **Reuse:** the app already has a **mode system** (`hideModes`, a `pm` mode) on the sidebar/nav. Add
  a `rep_basic` mode that hides the agent/observability surfaces and foregrounds a today-list.
- **Effort:** M. **Acceptance:** a `rep_basic` user sees only leads/today-tasks/outreach; power
  surfaces are hidden, not removed.

---

## Bucket C — New vertical modules (medium; after the acquisition slice proves)

### C1 — ICP / lookalike lead-gen for venues (T2/T3/T9) ★ the vertical's front end
- **What:** answer Zach's Open-Q1 concretely — a venue **ICP vocabulary** (venue type, geography,
  proximity-to-anchors: airport/school/stadium/venue-density, size, disposable-income proxy,
  foot-traffic quality) feeding segment `filter`, plus a **"find lookalikes of my winners"** action
  (`15:18`) that seeds a target list from the attributes of successful placements.
- **Reuse:** extends the dynamic `lead_segments.filter` vocabulary (additive — unknown keys already
  ignored, per the cascade spec) + the cascade evaluator. Enrichment fills the venue attributes.
- **Effort:** M. **Depends on:** an enrichment source for venue/demographic attributes (Google
  Places / census / a scrape). **Acceptance:** define a "winning venue" cohort → generate a lookalike
  target segment in a new metro.
- **Adjacent:** the **partner-acquisition landing page + intake questionnaire** (T17) — a standalone,
  simple page (NOT `betson.com/revenue-share`) that captures the intake form and lands leads via
  `source='web'`. Coordinate with Betson marketing (Michael). Ship standalone → hand to IT (`1:03:51`).

### C2 — NL-query chatbot over the workspace DB (T8/T9)
- **What:** ask-don't-navigate front door — "how many partners are A-tier and silent >30 days,"
  "top metros by booth revenue," affinity queries ("venues with a booth but no crane" — T8 cross-sell).
  Houses the bells-and-whistles under one calm interface (Zach's own objection-killer).
- **Reuse:** Claude over a read-only, workspace-scoped query surface (guardrailed text-to-query or a
  tool-call layer over the existing routers). Ben's brain-encoding class project is the UX template.
- **Effort:** M–L (safety: workspace scoping, read-only, injection-hardening). **Acceptance:** three
  canned questions return correct, workspace-scoped answers with no cross-tenant leakage.

### C3 — Hot→cold churn / decline detection at the account level (T6)
- **What:** proactively flag a partner trending cold **before** it's lost (`26:07`) — the retention
  twin of C1.
- **Reuse:** generalize the existing lead-score decay into an **account-level anomaly alert** over
  activity cadence (and, once D1 exists, booth-revenue decline). Emits a `deal health alert` / task.
- **Effort:** M. **Depends on:** meaningful per-account signal (activity now; booth telemetry later).
  **Acceptance:** a partner whose booth revenue or contact cadence drops >X% vs. trailing baseline
  raises one alert.

---

## Bucket D — Later / depends on booths-in-the-field (the moat, explicitly deferred)

These need **field data** and were mutually flagged "keep it simple for now / Star Trek later"
(`1:04:20`). Design the data capture early (Pillar D of the Aug-31 doc) so the moat has fuel; build
the features after.

### D1 — Booth telemetry: `device/asset` object (T12)
- **What:** per-booth telemetry — online/offline, paper, ink %, vends, uptime, last-connected,
  per-booth revenue (`47:59`). The live operational twin of an account (idea I6).
- **Ingest:** Apple Industries exposes **"Out of Booth Experience" / "Smile OS"**, **no clean API**
  (`49:33`) — pull/scrape from their portal. Model a `device` object + a telemetry fact table
  (mirror `engagement_events`' append-only shape).
- **Note:** shares thinking with Ben's **gameroom-twin** device work.

### D2 — Success-story correlation engine (T7) ★ the flagship moat
- **What:** detect what makes a placement win, find lookalike placements that haven't adopted the
  winning move, emit a **call-now prompt with the social-proof narrative** (Rays→Rangers — `38:10`).
- **Depends on:** D1 telemetry + C1 lookalike logic + C3 signals. This is the feature that answers
  "why not HubSpot?" — protect and sequence it deliberately.

### D3 — Quarterly partner value-recap emails (T14)
- **What:** the Amazon-model periodic recap to each partner (300 pictures, $2,000, up vs last Q1 —
  `28:04`). Retention/branding.
- **Depends on:** D1 (needs booth metrics to report). **Reuse:** a periodic-report worker + the email
  connector.

### D4 — Event-aware surge / dynamic pricing (T13)
- **What:** booth prices react to local events (Fenway game, Noah Kahn concert — `49:06`).
- **Depends on:** D1 (booth control plane) + an events/calendar feed (sports schedules, concerts,
  local calendars). Marquee "Star Trek" feature — clearly later.

### D5 — Marketing A/B testing inside the CRM (T10/I10)
- **What:** variant sequence steps/templates + a readout tied to engagement events (`1:06:41`).
- **Reuse:** `sequence_steps` + `engagement_events` already hold content and outcome; add variant
  support + a conversion readout. Small once B1 (engagement webhooks) lands, but sequence it after
  the core loop is proven.

---

## Suggested sequencing (respecting the pacing contract)

1. **This week:** Bucket A demo seed (photo-booth-shaped demo data) → re-demo to Zach; capture his
   reactions as the next elicitation pass (idea I11).
2. **Increment 1 (Sept):** B5 (call disposition) + B4 (cadence/tiering) — smallest things that make
   Zach faster at the *traditional* motion he must run for 6 months. High trust, low risk.
3. **Increment 2:** B1 (engagement webhooks) + B2 (send-time) + B3 (booking link) — completes the
   acquisition email loop Zach already knows from HubSpot.
4. **Increment 3:** C1 (venue ICP + lookalikes + landing page) — the vertical's acquisition front end.
5. **Increment 4:** B6 (junior-rep view) + C2 (NL query) — the simplicity/onboarding doctrine (T10).
6. **After booths ship:** D1 → D2/D3/D4 — the moat, on real field data.

---

## Open questions still pending Zach (to turn triage → spec)

1. **ICP fields (C1):** confirm the concrete venue attributes and their weights (does proximity-to-
   stadium matter more than venue size? what's the disposable-income proxy — cocktail price band,
   census, both?).
2. **Tier SLAs (B4):** confirm A=15d / B=90d / C=180d as defaults, and who assigns tiers (manual vs.
   auto by revenue/potential).
3. **Booking backend (B3):** native slot picker vs. embed Cal.com/Calendly? (Betson-IT/tooling call.)
4. **Landing page (C1/T17):** align with Michael-in-marketing — does marketing own the page, or does
   Ben ship standalone and hand to IT? What inbound leads can marketing feed?
5. **Booth data access (D1):** can we get Smile OS / Out-of-Booth-Experience portal credentials to
   pull telemetry, or is that gated by Apple Industries / Joseph Camarota?
