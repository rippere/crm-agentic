---
title: "RECAP — Ben ↔ Zach DiMotta: first live NovaCRM demo + photo-booth vertical requirements"
project: crm-agentic (NovaCRM)
date: 2026-09-02
duration: 1h07m
source_meeting: "Call with Zachary DiMotta-20260902_140735 (Betson Teams)"
participants: [Ben Rippere, Zachary DiMotta]
related:
  - ./ANALYSIS-keywords.md
  - ./IDEAS.md
  - ./BACKLOG.md
  - ./BRIEFING.md
  - ../../decisions/vertical-pivot-zach-2026-09-02.md
  - ../../decisions/leadgen-direction-zach-2026-08-31.md
  - ../../decisions/salesforce-coexistence.md
---

# Recap — Ben ↔ Zach DiMotta (2026-09-02)

## TL;DR

Ben gave Zach the **first live demo** of the built NovaCRM (leads → pipeline → agents/observability
layer) and Zach — a 20-year billiards salesman now running Betson's new **photo-booth division** —
responded with a rich, concrete requirements download drawn from his HubSpot + Shopify experience.
The meeting's decisive moment: Ben stated plainly that he is **"fully prepared to turn this into a
vertical product instead of having a wide breadth"** (`29:23`), and Zach's north star is the same —
**"I don't want a Swiss Army knife… I just need a knife. I just need this thing to work for me"**
(`52:00`). This is the meeting where the horizontal-vs-vertical question got answered *vertical*, by
both sides, out loud. It was a discovery call (Zach ~72% of words); no build was committed beyond
Ben's closing promise to ingest the transcript and fold it into the CRM schema.

## Who Zach is (the parts that shape the product)

- **20 years of Imperial (billiards / pool-table) sales** — relationship-driven, no pipeline: *"you
  talk to the guy for the first time and then he could buy something… that was the pipeline"*
  (`13:55`). He grew Imperial for two decades largely **without** a CRM.
- **Ran a standalone division** at his last company; evaluated **Salesforce, HubSpot, and one other**,
  chose **HubSpot** to live alongside **Shopify** (`3:10`, `30:37`). Deep, opinionated hands-on
  experience with what these tools do well and where they fail (esp. HubSpot↔Shopify integration
  friction, and Shopify being great B2C / terrible B2B — `34:41`).
- Uses **Shopify Sidekick** (AI query assistant) and **ChatGPT** daily; comfortable being an AI
  "thought partner" and correcting the model (`57:21`).
- Now **~"day five"** (`59:14`) at Betson leading the photo-booth push; his job for the next ~6 months
  is to **sell photo booths the traditional way** (find location → place booth → contract via
  Catherine — `50:26`). Everything CRM is upside on top of that.
- Self-aware about scope creep: *"I do need to remind myself, and I'm sure Mike will remind me… we
  get carried away"* (`50:17`); *"keep it simple to start"* / the **boiling-frog** metaphor for
  introducing new ideas at Betson (`1:04:20`).

## The arc of the call

1. **Framing (0:00–3:10).** Ben clarifies NovaCRM is **not** Salesforce — a standalone product he
   built as a "layover" for Salesforce; it's how he got the internship (Mike: *"way less clunky than
   Salesforce"* — `0:34`). Bill Seibert owns a Salesforce redesign Ben is kept out of ("echo
   chamber"); Mike wants to test whether Nova is viable as its own thing rather than bolting an
   agentic layer onto Salesforce (`2:25`).
2. **Zach's HubSpot download (3:10–9:56).** Unprompted, Zach paints his ideal: caller-ID capture,
   call/email transcription, auto-populated account data, **cadence reminders** ("call Ben's
   Hardware, you haven't spoken in 60 days"), **A/B/C account tiers** with contact-frequency rules,
   and **automated check-in email sequences** with dynamic fields pulled from order history. He calls
   the cadence reminder *"the holy grail"* (`6:53`).
3. **Ben demos the software (9:56–20:30).** Screen-shares his own workspace (admits *"it looks pretty
   vibe coded"* — `9:56`). Walks the pipeline, contacts, LinkedIn/phone/email enrichment, call
   summarization model, sentiment analyzer, PM agent, email composer, pipeline optimizer, semantics
   sorter, lead score, and the nightly worker digest. Zach: *"this is all awesome… incredible"*
   (`17:58`) and immediately reframes it for the two user types (senior "me" vs. a junior rep who
   gets a **dumbed-down, fed-leads view**) (`17:58`).
4. **The vertical thesis crystallizes (20:30–29:49).** Fishing analogy — let the machine **choose the
   rod, lure, cast** (target + draft), and the human takes over **once the fish is hooked** (`20:30`).
   The betson.com/revenue-share page is **wrong for non-traditional venues** (`22:47`); this is
   **partner acquisition, not customer acquisition** (`24:56`). Ben commits to the **vertical pivot**
   (`29:23`).
5. **What a *vertical* CRM should uniquely do (29:49–45:21).** Staged onboarding ("boil the frog");
   **hot→cold churn detection** (the "Ben stopped buying one-piece cues six months ago and I didn't
   notice" problem — `26:07`); **quarterly value-recap emails** to partners (the Amazon-credit-card
   model — `27:05`); the **success-story correlation engine** (Rays-stadium booth wins → prompt the
   Rangers-ballpark booth's rep to call — `38:10`); **cross-sell affinity queries** (Sidekick: buyers
   of pool tables + cues but *not* cloth — `41:06`); demographic/geographic targeting (disposable
   income; Delray Beach yes, "demilitarized zone" no — `43:03`).
6. **Booth-side / IoT tangent (45:40–49:33).** The **Apple Industries** dashboard (photo-booth
   manufacturer) — per-booth telemetry (online/offline, paper, ink %, vends, uptime) — and
   **event-aware surge pricing** ("the booth outside Fenway should know the Sox are in town, 3pm game,
   Noah Kahn concert, and surge accordingly" — `49:06`). Ben checks live: Apple Industries exposes
   **"Out of Booth Experience" / "Smile OS"** software, no direct API, but data is pullable (`49:33`).
7. **Chatbot / query-first UX (52:37–58:25).** Ben pitches a **natural-language query layer** over the
   CRM DB (ask instead of navigate — the banking-app / Sidekick model), which also houses the "bells
   and whistles" under one calm interface. Zach affirms via Sidekick experience and adds the
   **AI-as-thought-partner** principle (`57:21`).
8. **Close (58:25–end).** Ben reflects that he was hired to fix CAD, found the Salesforce mess, and
   now sees a real opening for his skill set (`58:40`). Both agree to **keep it simple, prove it
   narrow**. Zach's parting spark: **A/B testing marketing materials** (`1:06:41`). Ben's stated next
   step: *"take the transcript from this meeting, ingest it, apply this to all of the CRM schema…
   see what ideas this generates, and I'll shoot you another message"* (`1:06:08`). **← this document
   set is that deliverable.**

## What Zach explicitly asked for (cited)

| # | Ask | Cite |
|---|---|---|
| 1 | Cadence reminders + A/B/C account tiers ("holy grail") | `6:31`, `6:59` |
| 2 | Automated check-in email sequences w/ dynamic fields from order history | `8:05`, `9:05` |
| 3 | Open/click/dwell tracking → triggered follow-ups + send-time optimization | `21:20`, `1:02:43` |
| 4 | Calendar-booking link in emails ("make an appointment with me") | `20:30`, `21:20` |
| 5 | Call log → **mandatory next-step** dropdown (follow-up 1mo/6mo/dead-lead) | `13:35` |
| 6 | Simplified **junior-rep view** (role-based progressive disclosure) | `17:58` |
| 7 | Geo/demographic **lead-gen** ("find the winning venues in Dallas, replicate in Houston") | `14:56`, `15:18` |
| 8 | **Hot→cold churn** detection from order/purchase/call patterns | `26:07`, `27:04` |
| 9 | **Quarterly value-recap** emails to partners (Amazon model) | `27:05`, `28:04` |
| 10 | **Success-story correlation** → proactive call prompts | `38:10`, `39:26` |
| 11 | **Cross-sell affinity** queries (Sidekick "buying X and Y but not Z") | `41:06` |
| 12 | Dedicated **partner-acquisition landing page + simple questionnaire** (revenue-share page is wrong) | `22:47`, `24:12` |
| 13 | Booth **telemetry dashboard** (paper/ink/vends/uptime/revenue) | `46:39`, `47:59` |
| 14 | Event-aware **surge pricing** | `48:31`, `49:06` |
| 15 | **A/B testing** of marketing materials | `1:06:41` |

## What Ben showed / committed

- Demonstrated the **already-built** surface: pipeline/contacts, enrichment (LinkedIn/phone/email),
  call summarization, sentiment analyzer, PM agent, email composer, pipeline optimizer, semantics
  sorter, lead score, nightly worker digest, connectors (Gmail, Slack; Salesforce via API "down the
  road").
- **Committed to the vertical pivot** and to form-fitting the schema to the photo-booth business.
- Proposed the **NL-query chatbot** as the calming front door to the tool.
- Reconfirmed **standalone-first** (no Salesforce dependency for v1; Betson's SF rebuild is slow).
- **Next step:** ingest this transcript into the CRM schema and follow up with Zach. Zach explicitly
  left it collaborative — *"I can't tell you to do something, you're not my intern"* (`1:06:03`).

## Dynamics & sentiment

Warm, high-rapport, exploratory. Zach did most of the talking (72%) and was visibly energized
(*"sorry, I get excited about this stuff"* — `44:07`); Ben played discovery/reflect-back well
(*"what it sounds like you're asking for is… am I getting that right?"* — `15:42`). Both repeatedly
self-checked scope ("keep it simple," "hedge expectations," "boiling frog"). No friction, no
decisions forced — this was a **requirements-mining and alignment** call, and it landed the strategic
alignment (vertical, partner-acquisition, prove-narrow) cleanly.
