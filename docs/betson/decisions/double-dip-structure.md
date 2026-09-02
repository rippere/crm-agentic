# Decision: The Betson "Double Dip" — Structure

**Status:** Proposed (structure ready to walk Mike through)
**Date:** 2026-08-13
**Owner:** Ben Rippere
**CRM task:** `mtg20260812-crm-double-dip`
**Sources:** [[Ben & Mike Betti Meeting 2026-08-12]] — NovaCRM slice (§2), Fleet/Continuity slice (§3)
**Related decisions:** AVOS/Voss data interface (open) · Salesforce coexistence vs. migration (open)

---

## TL;DR

Betson pays Ben to build the lead-generation CRM that Zach needs on Sept 1. That same
build is the core of NovaCRM's own product roadmap. So Betson funds product development
Ben was going to do anyway — Betson gets a working tool faster than buying it, Ben keeps
the generalizable IP. That is the "double dip": **one paid build, two owners of value,
clean line between them.**

This is Mike's own framing, restated back to him: *"I can use Betson to test out some
other stuff I'm working on, and they pay me well enough to do it."* Mike's interest is to
**accelerate, not to save cost** — "as much of this as you want to take on." This doc puts
a spine on that so the boundary stays clean as the work scales.

---

## 1. What the "double dip" actually is

A **double dip** is any unit of work where **Zach's/Betson's concrete need and NovaCRM's
own roadmap are the same build**. Ben gets paid once (by Betson, for solving Zach's
problem) and banks the reusable product IP a second time (as NovaCRM the product). Neither
dip is a favor or a discount — both parties get the full value of the thing they wanted:

- **Betson's dip:** a working, AI-forward lead-gen CRM standing up for Zach's photo-booth
  division by September, demonstrable enough that Zach never reaches for Salesforce or a
  cheap off-the-shelf tool. Bought as *outcome + service*, not as a software license.
- **Ben's dip:** the generalizable engine — lead ingestion, dedupe/fuzzy-match, funnel,
  outreach automation — hardened against a real client with real data. That engine is
  NovaCRM's product core and the spine of the "landscape" local-business lead-gen product.

The double dip only works because CRM's center of gravity *is* lead-gen. Mike's own
definition of a CRM — **"10,000 leads → a database → a funnel of engagement"** — is
NovaCRM's product thesis stated by the client. When the client's definition of the
category and the product's roadmap coincide, building for the client *is* building the
product. That coincidence is the whole opportunity; the rest of this doc is about keeping
it clean.

---

## 2. The structure — what Betson pays for vs. what Ben retains

The boundary is drawn on **generalizability**, not on who typed the code. The rule:

> **Betson pays for the outcome and the Betson-specific surface. Ben retains the
> generalizable engine underneath it. Anything reusable across clients is product IP.**

| Layer | Example (Zach's build) | Who pays | Who owns | Reusable? |
|---|---|---|---|---|
| **Engine** (product core) | Lead ingest, dedupe/fuzzy-match, funnel state machine, outreach automation, scoring | Betson funds the build via the engagement | **Ben** (NovaCRM IP) | Yes — this is the product |
| **Connectors** | AVOS/Voss rep-share feed adapter, a specific integration Betson needs | Betson (it's their integration) | Shared: interface pattern is Ben's, the Betson-specific config/credentials are Betson's | Pattern yes, wiring no |
| **Configuration** | Zach's funnel stages, photo-booth lead filters, field mappings, templates | Betson | **Betson** (their data + setup) | No |
| **Data** | Betson's leads, contacts, deals, rep-share records | Betson | **Betson**, always | No — never |

**How the boundary stays clean in practice:**

1. **Two repos / one product line.** The engine lives in `crm-agentic` (NovaCRM, Ben's
   product). Betson-specific config, connectors, and data live in a separate Betson
   tenant/deployment layer that *consumes* the engine. Nothing Betson-specific gets
   committed into the product core; nothing generalizable gets stranded in the Betson
   deployment. This is the physical enforcement of the table above.
2. **Default-generalize.** When a Zach requirement can be met with a config knob or a
   pluggable interface instead of a hardcode, do that. It keeps the engine reusable *and*
   makes Zach's setup cleaner — the interests point the same way.
3. **State ownership in writing, once.** The engagement note says plainly: Betson owns its
   data and its configuration; Ben owns the generalizable engine and retains the right to
   sell NovaCRM to other clients. This is not adversarial — it is exactly the arrangement
   Mike described ("test out stuff I'm working on"). Naming it removes it as a future
   surprise.
4. **Data never leaves the tenant boundary.** Betson's leads/contacts/rep-share data are
   Betson's, full stop — consistent with Betson's local-only-proprietary-data convention.
   The product learns *patterns* (a fuzzy-match approach, a funnel shape); it never carries
   *records* to the next client.

---

## 3. Which of Zach's lead-gen needs are also core NovaCRM roadmap

These are the double-dip items — build for Zach, ship the product. Ranked by how cleanly
they coincide:

| Zach's need | NovaCRM roadmap item | Double dip? |
|---|---|---|
| Ingest ~10k leads into a database | Lead ingestion pipeline | **Pure** — same build |
| Dedupe / fuzzy-name matching (also the AVOS ask) | Entity resolution / fuzzy match | **Pure** — needed by every CRM client |
| Move leads through a funnel of engagement | Funnel / pipeline state engine | **Pure** — the product's spine |
| AI-forward outreach (Zach wants AI-first) | Outreach automation + AI compose | **Pure** — already NovaCRM's differentiator (compose/draft) |
| Lead scoring / prioritization | Deal & lead scoring | **Strong** — generalizable |
| Rep-share data ingest via AVOS/Voss | Connector *pattern* (external feed adapter) | **Partial** — pattern reusable, the Betson feed is Betson's |
| Photo-booth-specific funnel stages & filters | — | **No** — this is Betson configuration |
| Salesforce coexistence for Betson's division | Import/coexistence adapter (light) | **Partial** — a generic importer is product; Betson's SF org is theirs |

**The read:** roughly the top five are *pure* double dips — building them for Zach is
literally building NovaCRM's core. This is the argument for **prioritizing the lead-gen /
marketing module** (already the high-priority action item from the meeting): it is the
maximal-overlap surface. Do not start from a Salesforce-shaped contact/account/opportunity
model; start from the lead-gen engine, because that is where Zach's need and the product
roadmap are the same object.

---

## 4. Commercial framing (test-client shape, not a contract)

Keep this light. This is a **paid test-client engagement**, not a software license and not
a bespoke dev shop retainer. The shape:

- **Engagement, not license.** Betson pays Ben for time + outcome (the working CRM for
  Zach), inside the existing 10–20 hrs/week Betson relationship. NovaCRM is not "sold" to
  Betson as a product; Betson is the **proving ground** that funds its hardening.
- **Rate/cadence:** folds into the existing Betson arrangement (Mike: "they pay me well
  enough"). No separate SaaS pricing to negotiate now — that would over-formalize a test
  engagement and slow the September bar.
- **IP clause, one sentence:** *Betson owns its data and its configuration; Ben retains the
  generalizable NovaCRM engine and the right to offer it to other clients.* Put this in the
  engagement note now, before scale makes it awkward.
- **The bar is the deliverable, not a spec:** demonstrable in September (Mike first, then
  Zach), works well enough in October that Zach doesn't defect to Salesforce/off-the-shelf.
  Success is Zach *choosing* to keep using it.

**How the "landscape" product relates.** The local-business lead-gen product (Google Maps
→ filter → source contacts → bot outreach → escalate to human close) is **the same engine
pointed at a different lead source.** Zach's build hardens ingest → dedupe → funnel →
outreach against real data; "landscape" swaps the front-end lead *source* (Maps scrape
instead of Zach's list) and reuses everything downstream. So the double dip funds a third
dip: the engine Betson pays to harden is the engine the standalone "landscape" product
runs on. This is also the honest scope line — Zach's engagement is *not* the Maps-scraper;
that's a separate roadmap track that inherits the engine. Say so, so it doesn't get pulled
into the September bar.

This positioning is deliberately **not** Salesforce-scale. Per Mike's reality check, the
win is being lighter, leaner, more configurable, and catching the **"residual silt"** the
giants won't serve — a single-division test client like Zach is exactly that silt, by
design.

---

## 5. Risks + guardrails

| Risk | What it looks like | Guardrail |
|---|---|---|
| **Scope creep** | Zach's "just one more thing" quietly turns the engagement into an open-ended Betson dev retainer; Salesforce-coexistence balloons | The September bar is the scope boundary. Anything outside "10k leads → funnel, demonstrable in Sept" is a new track, named as such. Mike will *throttle* work anyway ("he should also be working on other things") — use that. |
| **One-client-shaped product** | NovaCRM ossifies around Zach's photo-booth funnel and can't serve client #2 | The two-repo boundary (§2). Every Zach requirement gets built as config/interface, not hardcode. Litmus test before each feature: *"Would client #2 want this exact behavior, or their own version?"* If their own → it's configuration, build the knob. |
| **IP ambiguity later** | At scale or handoff, "who owns the CRM" becomes a live question | The one-sentence IP clause (§4), written **now** while it's uncontroversial. Mike explicitly frames this as Ben testing his own stuff — capture that framing before it drifts. |
| **Data bleed** | Betson records or a client-specific rep-share feed leak into the product core or another client | Data never leaves the tenant boundary (§2). Product learns patterns, never carries records. Aligns with Betson's local-only-data convention. |
| **Continuity coupling** | The double dip deepens Betson's dependence on Ben's harness right as Mike wants succession-ready | Maintainer-grade "monkey-proof" docs cover the *Betson deployment layer*, not the product engine. Betson can run/maintain its tenant; the engine stays Ben's product. Clean seam = clean succession. |

---

## 6. Next step to propose to Mike

**Propose in one move:** confirm the double-dip structure and let it set the September
scope.

> "Here's how I'd structure the CRM work: I build Zach's lead-gen CRM against the
> September bar. The generalizable engine underneath — lead ingest, dedupe, funnel,
> outreach — is the core of the product I'm already building, so Betson's paying to harden
> something I own and keep improving, and Zach gets a working tool faster than buying one.
> Betson owns its data and setup; I keep the generalizable engine and the right to run it
> for other clients. Zach's photo-booth specifics are configuration on top. That keeps the
> line clean and stops the CRM from becoming Zach-shaped. Sound right?"

Then, concretely:
1. **Get Mike's nod** on the IP one-liner (§4) and log it to the `betson-engagement` note.
2. **Lock the September scope** to the lead-gen/marketing module (top-five pure double-dip
   items, §3) — explicitly *excluding* the Maps "landscape" scraper and full Salesforce
   migration from the September bar.
3. **Feed the AVOS/Voss connector** into the engagement as the first *connector-pattern*
   test (Friday VOS meeting), building it as a pluggable feed adapter, not a Betson
   hardcode.

`[[log:crm-agentic: confirm double-dip IP one-liner with Mike + lock Sept lead-gen scope]]`
