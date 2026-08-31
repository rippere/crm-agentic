---
title: "DIRECTION — NovaCRM Lead-Gen: Target Acquisition → Vertical Photobooth Analytics"
crm_task: mtg20260831-crm-leadgen-direction
project: crm-agentic (NovaCRM)
status: DIRECTION CAPTURED (Zach notes — pending Ben scoping into build units)
decision_owner: Ben (scopes into BUILD-SPEC increments); Zach (division reality + criteria)
date: 2026-08-31
source_meeting: Zach ↔ Ben — CRM tooling structure notes (leadgen area)
related:
  - ../BUILD-SPEC-leadgen.md
  - ./salesforce-coexistence.md
  - ./avos-data-interface.md
---

# DIRECTION: Lead-Gen — from Target Acquisition to a Vertical Photobooth CRM

## TL;DR — the strategic thesis

NovaCRM's wedge against a horizontal CRM (HubSpot) is **not** being a better generic CRM. It is
two things stacked in time:

1. **Now:** an AI **target-acquisition** engine — identify prospects against custom criteria,
   fan out top-of-funnel outreach, and gate engagement through a human-in-the-loop escalation
   graph. This is the current `leads → segments → sequences → campaigns → outreach` module.
2. **Later (the moat):** once photobooth units are **in the field**, NovaCRM ingests
   per-event/per-install operational data and becomes a **vertical revenue-optimization advisory
   layer** for the photobooth business — "why does Booth 1 out-earn Booth 2 on the same street?"
   No horizontal CRM does this, and it compounds with every install.

Go-to-market is a **vertical slice**: prove the loop on a **small pool in the Northeast**, earn
provenance, then expand breadth and **transpose to other markets**. Breadth follows proof, not
the reverse.

This doc captures Zach's direction verbatim-in-substance and maps it to concrete near-term
implications for the leadgen module. It is **direction, not a build order** — Ben scopes it into
BUILD-SPEC increments before anything is built.

---

## 1. The four pillars (Zach's notes, structured)

### Pillar A — Target identification
- Ways to **identify** prospects: define what to look for (the criteria that mark a good lead).
- Identification **triggers cascading workflows** and avenues of development — spotting a target
  kicks off downstream sequences automatically.
- A **delegative graph** maps the **escalation / de-escalation of the human-in-the-loop**: some
  steps auto-proceed, some require a person, and the boundary moves as trust is earned.
- Sequencing matters: **first** get the tooling out there, **then** focus shifts to *managing the
  cascades* it produces.

### Pillar B — Lead-gen (top of funnel)
- Focused on **criteria** with **populated information** and **output customized as far as
  possible** — organizing lead outreach is fundamentally a top-of-funnel exercise.
- **Breadth of funnel** matters, and so do **classification and filtering** — you need volume
  *and* the ability to slice it.

### Pillar C — Real-time engagement ("whisper")
- When actually engaging: how do we let a **whisper model** engage with the proposition and
  **actively adapt the deal in real time** — a live advisory layer during the conversation, not
  just a pre-drafted sequence.

### Pillar D — Vertical photobooth analytics (the eventual moat)
- Against a main CRM (HubSpot), the **AI tool really just helps with target acquisition** today.
- **Down the road, once units are in the field:** analyze sales from the photobooths — Booth 1 vs
  Booth 2 have **differing results** even at "different ends of the same street." *Why?*
- **Capture install/event data from the jump** — details that can be captured at install must be
  covered, put into software so we can **interpret later**.
- The question NovaCRM must answer vertically: **"what is the secret sauce — how is the sausage
  made at the event? How does a photobooth optimize revenue?"** NovaCRM builds **metrics + a
  controllable advisory layer** for this, so the data yields conclusions worth drawing.

---

## 2. Positioning vs. HubSpot (the coexistence line)

Consistent with [salesforce-coexistence](./salesforce-coexistence.md): NovaCRM does **not** try to
out-feature a horizontal CRM on generic pipeline management. Its defensible surface is:

| Layer | Horizontal CRM (HubSpot) | NovaCRM |
|---|---|---|
| Generic contacts / deals / pipeline | ✅ commodity | present, not the wedge |
| AI target acquisition (criteria → leads → outreach) | weak / add-on | **wedge, now** |
| Vertical photobooth event/install analytics + advisory | ✗ nonexistent | **moat, later** |

The near-term AI tool is a **target-acquisition assist**; the long-term product is a
**vertical operating system for photobooth revenue**.

---

## 3. Go-to-market: vertical slice, then transpose

- **Optimize from a smaller pool first**, expand breadth **after proven provenance**.
- Once **one campaign demonstrably works**, configure how online outreach can be
  **demystified and made the norm** (repeatable playbook).
- **Geography:** start **Northeast**, transpose the proven model to other markets.

This is the same reversible, prove-narrow-then-scale posture as the coexistence decision.

---

## 4. What this changes NEAR-TERM for the current leadgen module

The current module (`BUILD-SPEC-leadgen.md`) already covers most of Pillars A & B. Mapping the
notes to what is **present vs. a gap**, so Ben can scope increments:

| Note | Current module | Gap / next increment |
|---|---|---|
| Identify against **criteria** | `lead.source`, `lead.score_detail`, `lead.custom_fields`; dynamic `lead_segments.filter` | Add a first-class **criteria/ICP** concept feeding segment filters (a saved, named target profile) — candidate table `lead_criteria` or a typed `segment.filter` schema |
| **Cascading workflows** on identification | `campaigns` enroll a segment into a `sequence` | Auto-trigger: a rule that enrolls a lead into a sequence **on classification**, not just manual campaign launch — candidate `sequence_enrollments` auto-create trigger |
| **Delegative graph** of HITL escalation/de-escalation | binary `sequence_step.requires_approval` + `/outreach` approval queue | The **graph** is richer than a per-step boolean — model escalation levels / who-approves-what and let the boundary move with trust. **Design placeholder, do not build yet.** |
| **Customized output** per lead | `sequence_step.body_template` tokens + `ai_generate` | Already supported; deepen token/context coverage from `custom_fields` |
| **Breadth + classification + filtering** | segments (static/dynamic), `lead.stage`, `engagement_score` | Present; add richer classification facets as criteria mature |
| **Whisper / real-time deal adaptation** (Pillar C) | pre-send drafting via Claude in `/outreach` | **New surface** — a live in-conversation advisory layer. Roadmap, not this module. |
| **Install/event analytics** (Pillar D) | ❌ not in leadgen scope | **Separate vertical module** — capture event/install metrics from day one; distinct from top-of-funnel. Needs its own spec. Explicitly a **design non-goal of the current leadgen phase** (matches BUILD-SPEC §0). |

**Recommendation:** do **not** widen the current leadgen build to chase Pillars C or D — they are
separate modules. The one near-term, in-scope enhancement worth scoping now is the **criteria →
auto-cascade** loop (Pillars A/B), because it makes the existing module feel like a target-
acquisition *engine* rather than a manual campaign tool, which is exactly Zach's framing.

The **install-analytics moat (Pillar D) is the strategically important thread** — its value is
that data captured *from the first install* compounds — so the sooner Ben scopes a minimal
"capture event metrics" schema, the sooner provenance starts accruing. But it is a new vertical,
sequenced **after** the target-acquisition slice is proven in the Northeast.

---

## 5. Open questions for Zach (to turn direction into a spec)

1. **Criteria:** what are the concrete signals that mark a good photobooth lead (venue type,
   event volume, geography, budget band)? These become the ICP / segment-filter schema.
2. **HITL boundary:** which outreach steps should ever auto-send vs. always require a person, and
   what earns a step the right to auto-proceed? (Defines the delegative graph's initial levels.)
3. **Install metrics:** at install/event, what data is actually capturable, by whom, and how
   (booth telemetry, operator entry, event metadata)? This scopes the Pillar-D schema.
4. **"Whisper":** live-during-conversation, or fast-turnaround draft assist? Sets whether Pillar C
   is a new real-time surface or an extension of the existing draft flow.
