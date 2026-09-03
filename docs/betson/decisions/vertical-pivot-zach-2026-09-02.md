---
title: "DECISION — NovaCRM commits to the photo-booth VERTICAL (owner-confirmed, both sides)"
crm_task: mtg20260902-crm-vertical-pivot
project: crm-agentic (NovaCRM)
status: CONFIRMED (Ben stated the commitment on-call; Zach's demand-side conviction matches; pending Mike ratification of scope)
decision_owner: Ben (owns the build); Zach (division reality + requirements); Mike Betti (ratifies scope / viability call)
date: 2026-09-02
source_meeting: "2026-09-02 Ben ↔ Zach DiMotta — first live NovaCRM demo (1h07m)"
supersedes_intent_of: ./leadgen-direction-zach-2026-08-31.md   # answers its Open Questions §5
related:
  - ./leadgen-direction-zach-2026-08-31.md
  - ./salesforce-coexistence.md
  - ../BUILD-SPEC-leadgen.md
  - ../meetings/2026-09-02-zach-dimotta/BACKLOG.md
  - ../meetings/2026-09-02-zach-dimotta/ANALYSIS-keywords.md
---

# DECISION: NovaCRM goes vertical — the photo-booth product

## TL;DR — the decision

The horizontal-vs-vertical question is **answered: vertical.** On the 2026-09-02 call Ben stated it
plainly — *"I'm fully prepared to turn this into a vertical product instead of having a wide
breadth… form-fit it to the industry [for] a higher velocity"* (`29:23`) — and Zach's north star is
the identical demand: *"I don't want a Swiss Army knife… I just need a knife"* (`52:00`). NovaCRM's
Betson instance is now explicitly a **form-fit photo-booth partner-acquisition CRM**, not a generic
CRM that happens to be used for photo booths.

This decision **ratifies and extends** `leadgen-direction-zach-2026-08-31.md`: the four-pillar
thesis holds, and this meeting **answered its open questions** with concrete requirements. It does
**not** change `salesforce-coexistence.md` (native-first, no SF dependency for v1) — Zach's HubSpot/
Shopify war stories reinforce it.

The pivot is **reversible and cheap**: form-fitting is configuration + additive modules over the
shipped horizontal substrate, not a rebuild.

---

## 1. What changed since 2026-08-31

The Aug-31 direction doc captured Zach's thesis **secondhand** (structure notes) and listed four
**open questions** needed to turn direction into a spec. The Sep-2 call was the **first live demo**,
and it converted thesis → owner-confirmed commitment and answered three of the four questions from
the horse's mouth. New this meeting: a large, concrete feature wishlist (see
`../meetings/2026-09-02-zach-dimotta/BACKLOG.md`) and the **partner-acquisition** reframing.

---

## 2. Open questions from Aug-31 — now answered

### Q1 (ICP criteria) — ANSWERED (substantially)
The signals of a good photo-booth lead, in Zach's words:
- **Venue type** (bar, nightclub, truck stop, retail marketing-play — non-traditional, NOT arcades).
- **Geography + proximity-to-anchors:** distance from airport / school / stadium / venue density
  (`14:56`); event-anchored spots (near ballparks — `39:01`).
- **Venue size** and **what the venue does** (`14:56`).
- **Disposable-income proxy:** *"$15–$20 cocktails, not $2 beers"* (`44:07`); Delray Beach yes,
  "demilitarized zone" no (`43:03`). Foot-traffic **quality** over volume.
- **The lookalike primitive:** seed targets from the attributes of *proven winners* — "the best
  booths in Dallas → find the same venues in Houston/San Antonio/Fort Worth" (`15:18`).
→ Feeds the `lead_segments.filter` ICP vocabulary (additive) + a "find lookalikes" action.
**Still to confirm:** exact attribute weights and the disposable-income proxy source (BACKLOG Open-Q1).

### Q2 (HITL boundary) — ANSWERED
Zach's comfort, early: **auto-draft, human sends.** *"Generate a bunch of emails, it sits in drafts,
I go through and hit send"* (`19:15`); human takes over *"once they hook that fish"* (`20:30`).
→ Default `sequence_step.requires_approval = true`; the escalation graph starts human-heavy and moves
up as trust is earned (matches the cascade spec's delegation levels). This is the initial delegation
posture, confirmed.

### Q3 (install/event metrics — Pillar D) — ANSWERED (concretely, but gated on access)
The Apple Industries booth dashboard defines the metric set: online/offline, paper, ink %, vends,
uptime, last-connected, per-booth revenue (`47:59`). Ingest is via **"Out of Booth Experience" /
"Smile OS"** — **no clean API**, pull/scrape from their portal (`49:33`).
→ Scopes the Pillar-D `device/asset` telemetry object (BACKLOG D1). **External gate:** Smile OS portal
access (Apple Industries / Joseph Camarota).

### Q4 (whisper / real-time deal adaptation) — PARTIALLY REFRAMED
Not discussed as live in-call whispering; the adjacent surface that *did* land is the **NL-query
chatbot** (Ben, `54:34`) — ask-don't-navigate over the workspace DB. Treat "whisper" as a later
real-time surface; the near-term expression is conversational query (BACKLOG C2).

---

## 3. New strategic signal from this meeting

- **Partner acquisition, not customer acquisition** (`24:56`) — a distinct funnel type: cold
  education (95% have never considered a booth), quality-over-quantity, two-sided ROI. This reshapes
  ICP, messaging, and the landing page.
- **Onboarding-as-progressive-disclosure is the design doctrine** ("boil the frog," junior vs. senior
  views — `31:10`, `17:58`) — and it's aimed squarely at the incumbents' #1 failure (aversive
  onboarding).
- **The moat is the success-story correlation loop** (`38:10`) — compounding cross-account
  pattern→play, fed by booth telemetry. This is the durable "why not HubSpot" answer.
- **Pacing contract:** Zach must sell booths the traditional way for ~6 months (`50:26`); both agreed
  "keep it simple, prove it narrow." Do not over-build.

## 4. Positioning — unchanged, reinforced

Consistent with `salesforce-coexistence.md`: **native-first, no Salesforce in the loop for v1.**
Zach independently corroborated every reason: Salesforce was mis-spec'd for a non-Betson division
(`1:19`), HubSpot integration is *"terrible without a developer"* (`30:43`), Shopify is B2C-great /
B2B-bad (`34:41`), and Betson's own SF rebuild is slow (`46:13`). NovaCRM's wedge is **integration
that works + vertical fit + AI-native + non-clunky staged onboarding** — the exact three seams the
incumbents leave open.

---

## 5. Decision + what to confirm

**Decision:** build NovaCRM's Betson instance as a **form-fit photo-booth partner-acquisition
vertical**. Scope near-term work to make Zach faster at his *traditional* motion (retention cadence,
call disposition, the acquisition email loop he knows from HubSpot); design — but defer — the
booth-telemetry moat until units and data exist. Ben owns the build; sequencing in
`../meetings/2026-09-02-zach-dimotta/BACKLOG.md`.

**Confirm with Mike (ratification):**
1. Vertical form-fit (not a generic CRM) is the sanctioned direction, and the "is Nova viable as a
   product" test is being run on the photo-booth division.
2. Scope pacing: retention/acquisition basics now; booth IoT / surge / quarterly recaps are later
   phases (not Sept/Oct commitments).

**Confirm with Zach (requirements → spec):** the five BACKLOG open questions (ICP attribute weights;
tier SLAs; booking backend; landing-page ownership w/ Michael-in-marketing; Smile OS data access).

**Trigger to revisit:** if Mike wants corporate Salesforce roll-up of Zach's numbers (revisit the
A2 one-way push in `salesforce-coexistence.md`), or if the photo-booth book turns out entangled with
corporate records (it is currently greenfield / "Zach on an island").
