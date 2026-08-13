---
title: "DECISION — NovaCRM Salesforce Coexistence vs. Native Data-Slice Migration"
crm_task: mtg20260812-crm-salesforce-coexist
project: crm-agentic (NovaCRM)
status: DECIDED (pending Mike/Zach confirmation)
decision_owner: Ben (Ben proposes; Mike ratifies scope; Zach confirms division reality)
date: 2026-08-13
source_meeting: 2026-08-12 Ben ↔ Mike Betti
related:
  - ../../../../obsidian-vault/note/NovaCRM — Betson Meeting Distillation 2026-08-12.md
  - ../../../../obsidian-vault/note/Betson Engagement — Fleet Vision & Continuity 2026-08-12.md
---

# DECISION: Salesforce Coexistence vs. Native Data-Slice Migration

## TL;DR — the decision

**Ship Zach's photo-booth division on NovaCRM natively, with NO Salesforce in the loop for v1.**
Do not build a Salesforce sync connector for the September demo or the October "solid"
milestone. Zach's division is greenfield and organizationally separate — "Zach on an island."
There is no shared record that forces Nova and Salesforce to reconcile, so a sync connector
would be pure cost with no v1 payoff, and it would drag Nova's data model toward the very
Salesforce shape Mike explicitly told us not to copy.

Keep coexistence as a **deferred, optional, one-way outbound** capability we design the schema
to *allow* but do not build until a concrete integration requirement appears (most likely the
AVOS/Voss rep-share feed, not Salesforce itself).

This is reversible. Starting native and adding a connector later is cheap. Starting coupled to
Salesforce and unwinding it later is not.

---

## 1. The two options, framed honestly

### Option A — Coexistence (Nova alongside Salesforce)
Nova runs Zach's division day-to-day, but a **slice of data** is kept in step with the
corporate Salesforce org via a connector. Two sub-variants:

- **A1 — Bi-directional sync.** Leads/contacts/deals flow both ways. Edits in either system
  propagate. Requires conflict resolution, field mapping, dedup (the same fuzzy-naming problem
  AVOS is already surfacing), and an idempotent write path into Salesforce.
- **A2 — One-way slice.** Either Salesforce → Nova (seed Nova from a corporate export/read) or
  Nova → Salesforce (push Zach's activity up for corporate visibility). No conflict resolution;
  a single writer of record per object.

### Option B — Native migration of a data slice (RECOMMENDED)
A defined slice — for the photo-booth division, effectively a **new/empty book of business**:
the 10k-lead lead-gen list, contacts, and the engagement funnel — lives **natively in Nova as
the system of record**. Salesforce is simply not part of Zach's loop. If any corporate data is
needed to seed it, it is a **one-time import**, not a standing sync.

The key insight that separates these: **coexistence only earns its cost when two systems must
share a live record.** For Zach's separate division, that shared record largely does not exist.

---

## 2. Pros / cons / risk — scored against Zach's context and the Sept-demo / Oct-solid bar

### Option A — Coexistence

**Pros**
- Corporate keeps a single pane of glass; Zach's activity shows up in the org Betson already pays
  ~$130k/yr for.
- If the photo-booth division must roll up into corporate reporting, the plumbing already exists.
- A working Salesforce connector is a genuine reusable fleet asset — integrations are explicitly
  the moat ("their moat is integrations"), so a clean connector has value beyond Betson.

**Cons**
- **Directly contradicts the standing instruction: "Don't model on Salesforce."** Mapping Nova's
  objects to Salesforce objects to sync them silently imports Salesforce's schema and its clunk —
  the exact gravity we were told to escape.
- Salesforce API work (auth, object model, field mapping, sandbox access, rate limits, error
  handling) is real engineering that produces **nothing Zach can see in the September demo.** It
  spends the scarcest resource — demo runway — on plumbing corporate cares about and Zach doesn't.
- Requires access we don't yet have: a Salesforce sandbox/org, API credentials, and someone on
  Betson's side to own field mapping. That's an external gate that can slip the timeline.

**Risk**
- **Timeline risk (high).** Sync is the classic scope sink. Missing the September bar is the one
  outcome that loses Zach — "so Zach isn't tempted to grab Salesforce or a cheap off-the-shelf CRM
  instead." Building Salesforce sync to keep Zach is self-defeating: it raises the odds he just
  stays on Salesforce.
- **Schema-contamination risk (high).** Bi-directional (A1) forces Nova's model to be Salesforce-
  compatible forever. This is the residual-silt anti-goal: we win by being lighter/leaner/more
  configurable, not by mirroring the giant.
- **Data-integrity risk (medium).** A1 needs dedup + fuzzy matching + conflict resolution on day
  one — the AVOS rep-share problem, unsolved, now on the critical path.

### Option B — Native slice (recommended)

**Pros**
- **Fastest path to the September bar.** No external credential gate, no field mapping, no API
  integration. Build the lead-gen/marketing module (10k leads → database → funnel) straight into
  Nova and demo it end-to-end.
- **Lets Nova be Nova.** The data model is designed for the "leads → funnel of engagement" job,
  free of Salesforce's shape. This is exactly the "don't model on Salesforce; look at Zoho/HubSpot/
  modern CRMs" directive.
- **Matches the org reality.** Zach's division is separate ("Zach on an island"). A separate
  division running a separate book of business on a separate tool is not an anomaly to reconcile —
  it's the natural fit.
- **Clean proving ground** for the fleet/double-dip: Nova demonstrated as a standalone product, not
  as a Salesforce satellite.

**Cons**
- No corporate roll-up in v1. If Mike later wants Zach's numbers inside Salesforce, that's new work.
- If a real shared-record requirement emerges (e.g. corporate owns some photo-booth accounts), we'd
  add a connector then rather than now.

**Risk**
- **Corporate-visibility risk (low, and deferrable).** Mitigated by (a) confirming with Mike/Zach
  that the division truly is standalone, and (b) designing the schema so an outbound one-way push
  can be bolted on later without a migration.
- **Rework risk (low).** Native-first → add sync later is additive. There is no data model we'd
  have to tear down; a connector reads from Nova, it doesn't require reshaping Nova.

---

## 3. RECOMMENDATION

**Choose Option B — native slice, no Salesforce connector for v1.** Design the schema to *permit*
a future one-way outbound push (Option A2, Nova → Salesforce) but do not build it until a concrete
requirement lands.

**Rationale**
1. **The org structure removes the reason to sync.** Coexistence is worth its cost only when two
   systems share a live record. Zach's photo-booth division is greenfield and separate — there is
   essentially no shared record. Absent that, a connector is cost without benefit.
2. **The Sept-demo / Oct-solid bar is the whole game, and it's about Zach, not corporate.** The
   explicit success condition is that Zach chooses Nova over Salesforce/off-the-shelf. Every hour
   on Salesforce plumbing is an hour not spent on the lead-gen/funnel experience that actually wins
   him — and ironically deepens the Salesforce dependency we're trying to displace.
3. **"Don't model on Salesforce" and building a Salesforce sync are in tension.** A sync forces an
   object-for-object mapping that reimports Salesforce's shape. Native-first protects the
   lighter/leaner/configurable positioning that is the actual strategy.
4. **It's the reversible door.** Native-now + connector-later is cheap and additive. Salesforce-
   coupled-now + decouple-later is expensive. When one direction is cheaply reversible and the
   other isn't, take the reversible one.

---

## 4. What a minimal Salesforce sync connector would take IF chosen — vs. the cost of skipping

### If we build it (scope of the *minimum* viable connector — recommend A2, Nova → Salesforce, one-way)
- **Direction:** one-way outbound, Nova → Salesforce. Nova stays system of record for the division;
  Salesforce receives a read-only mirror for corporate visibility. (Avoid A1 bi-directional — it
  triggers conflict resolution and locks Nova's schema to Salesforce's.)
- **Objects (minimum):** `Lead`, `Contact`, `Account`, `Opportunity` — mapped from Nova's
  contact / deal / funnel-stage entities. Photo-booth's real need is likely just Contact + a
  deal/Opportunity with a stage; Lead only if corporate wants top-of-funnel visibility.
- **API:** Salesforce REST API (sufficient at Zach's volume) with OAuth 2.0 (JWT bearer / connected
  app for server-to-server). Bulk API 2.0 only if the 10k-lead seed is pushed up in one shot.
- **Field mapping:** an explicit Nova-field → SF-field table per object, owned jointly with Betson.
  This is where Salesforce's clunk leaks in — keep it a thin, external, versioned mapping, never
  baked into Nova's core model.
- **Dedup / identity:** an external-ID field on each SF object keyed to Nova's primary key
  (idempotent upsert), plus the fuzzy-name matching the AVOS/Voss work is already surfacing.
- **Prereqs / external gates:** Salesforce sandbox + connected-app credentials + a Betson-side
  owner for field mapping. **None of these are in hand today** — starting the connector starts a
  dependency wait.
- **Rough effort:** a real multi-day integration once credentials exist (auth + object mapping +
  idempotent upsert + error handling + a sandbox test loop) — not a demo-week task.

### Cost of skipping it (Option B)
- **Direct cost:** near zero. We build the native module we were going to build anyway.
- **Opportunity cost:** no corporate roll-up of Zach's numbers into Salesforce in v1. Given the
  division is separate and corporate visibility was never stated as a Sept/Oct requirement, this
  cost is low and **fully recoverable later** via the A2 push, which the schema is designed to allow.
- **Net:** skipping buys back the entire demo runway and keeps Nova's model clean. The only thing
  we forgo is a corporate-reporting nicety nobody has asked for yet.

---

## 5. Decision owner + what to confirm with Mike / Zach

**Decision owner:** Ben. Ben proposes and owns the build. Mike ratifies the scope boundary (that
corporate visibility is out of v1 scope); Zach confirms the on-the-ground division reality.

**Confirm with Mike:**
1. **Corporate visibility is not a v1 requirement.** Is Betson-corporate fine with Zach's photo-booth
   division running entirely in Nova, with *no* Salesforce roll-up until/unless explicitly requested?
   (Expected: yes — this is the "Zach on an island" framing.)
2. **If/when roll-up is wanted, one-way Nova → Salesforce is acceptable** (not bi-directional), so
   Nova stays system of record for the division.

**Confirm with Zach (returns Sept 1):**
3. **Is the photo-booth book of business genuinely greenfield** — does he start from the 10k-lead
   list with no legacy Salesforce data he needs carried over? If there IS legacy data, scope a
   **one-time import** (still not a standing sync).
4. **Does he touch corporate Salesforce at all** for this division, or is he fully independent?
   (This is the single fact that could flip the recommendation — if his division is entangled with
   corporate records, revisit A2.)

**Trigger to revisit this decision:** a concrete, named integration requirement appears — most
likely the **AVOS/Voss rep-share feed** (Friday's VOS meeting), which is a *different* integration
than Salesforce and should be scoped on its own merits. Do not let "we might integrate someday"
justify building the Salesforce connector now.
