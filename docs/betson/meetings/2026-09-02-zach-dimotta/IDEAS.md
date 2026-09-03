---
title: "IDEAS — Generalized concepts from the Zach DiMotta call (2026-09-02)"
project: crm-agentic (NovaCRM)
date: 2026-09-02
note: "Ideas that GENERALIZE beyond the photo-booth build — strategy/product concepts worth carrying forward. Concrete build units live in BACKLOG.md; this is the higher-altitude layer."
related:
  - ./ANALYSIS-keywords.md
  - ./BACKLOG.md
---

# Generalized ideas — Zach DiMotta call (2026-09-02)

Twelve ideas the conversation surfaced that are bigger than a single feature. Each: the seed (with
cite), why it generalizes, and the "so what." Photo-booth is **instance #1**, not the ceiling.

---

### I1 — "CRM-101 per industry": NovaCRM as a vertical-CRM *factory*
- **Seed:** Zach — *"here's your Hardware 101 CRM… or 'this is different, this is really what they're
  trying to accomplish.'"* (`33:44`); Ben's commitment to form-fit to the industry (`29:23`).
- **Generalizes:** the durable product may not be *a* CRM but a **method + engine for standing up a
  form-fit vertical CRM from a discovery conversation**. Photo-booth is the first instance; the
  reusable asset is the pipeline that turns "tell me how your business works" → a configured vertical.
- **So what:** every vertical build should leave behind reusable *scaffolding* (config schema,
  onboarding flow, ICP vocabulary), not just photo-booth-specific code. Treat this build as the
  template for build #2.

### I2 — Partner-acquisition is a distinct funnel type (not just a relabeled sales funnel)
- **Seed:** *"partner acquisition, not customer acquisition… 95% have never considered this… we're
  not actually selling anything."* (`24:56`).
- **Generalizes:** any host/reseller/channel model (put-our-asset-in-your-venue, revenue-share)
  shares this shape: cold *education*, low prior intent, quality-over-quantity, two-sided value. It
  deserves its own object semantics and messaging library, reusable across such businesses.
- **So what:** a first-class "funnel type" concept in Nova (demand-capture vs. partner-education)
  changes defaults for scoring, sequences, and landing pages.

### I3 — The success-story correlation loop is the compounding moat
- **Seed:** the Rays/Rangers ballpark story (`38:10`) + Ben's "your neighbor Nancy loves it"
  door-to-door model (`39:41`).
- **Generalizes:** any multi-location / multi-account operator (franchises, distributors, equipment
  fleets) can mine *what makes a winner win* and push that play to lookalikes that haven't adopted it.
  Value **compounds with every account** — a genuine data network effect no horizontal CRM captures.
- **So what:** this is the feature to point at when asked "why not just use HubSpot?" Protect it;
  design data capture from install #1 so the correlation has fuel.

### I4 — Onboarding as progressive disclosure ("boil the frog") is a product doctrine
- **Seed:** *"phase one for three months… then phase two, sales analysis"* (`31:10`); *"you can't
  throw a frog into boiling water"* (`1:04:20`); two personas / dumbed-down junior view (`17:58`).
- **Generalizes:** the #1 stated failure of the incumbents is **aversive onboarding / too many moving
  parts** (`31:33`, `30:43`). Maturity-gated feature reveal + role-scoped views is a doctrine that
  applies to the entire app and to every future vertical.
- **So what:** ship less at once, on purpose. Feature-flag by tenure and role. Onboarding is a
  designed surface with its own metrics.

### I5 — NL-query-first is the antidote to feature bloat
- **Seed:** Ben — *"house the bells and whistles under the chatbot"* (`54:34`); Zach via Sidekick —
  *"the data was there, I just didn't want to go find it"* (`55:50`).
- **Generalizes:** a conversational front door lets you keep power features **without** paying the
  cognitive-load tax that makes users bounce. Applies to any data-dense app. It also elegantly
  reconciles the tension between Zach's "keep it simple" and Ben's rich agent stack.
- **So what:** the query layer isn't a feature, it's the **information architecture** — the default
  way a user retrieves anything.

### I6 — CRM ⨯ IoT: the customer's connected asset becomes a first-class CRM object
- **Seed:** the Apple Industries booth dashboard (paper/ink/vends/uptime — `47:59`) + surge pricing
  (`49:06`).
- **Generalizes:** when the customer operates a connected device (booth, vending, kiosk, leased
  equipment), the "account" gets a **live operational twin**. That telemetry is the ground truth for
  churn signals (T6), value-recaps (I7), and dynamic pricing. Fuses CRM with device management.
  (Directly adjacent to Ben's existing Betson **gameroom-twin** IoT work — shared spine.)
- **So what:** model a `device/asset` object with telemetry early; it's the substrate three other
  features stand on.

### I7 — Value-recap as a reusable retention primitive
- **Seed:** the Amazon quarterly "here's how much you saved" email (`27:45`–`28:46`).
- **Generalizes:** any recurring-revenue relationship benefits from a scheduled, data-grounded
  "here's the value we delivered" artifact. Cheap to generate, high perceived care, reinforces
  retention. Reusable mechanic across verticals.
- **So what:** a periodic-report generator that reads whatever value metric a vertical has (vends,
  orders, tickets) → a partner-facing recap.

### I8 — AI-as-thought-partner as an explicit product stance
- **Seed:** *"be a thought partner… help me think of ways I'm not using it"* + accept correction
  (`57:21`); *"there's still a creativity required to ask the questions"* (`56:29`).
- **Generalizes:** differentiate from passive dashboards by making the assistant **proactively
  surface the questions the user didn't think to ask**, and make correction a first-class loop. A
  stance that applies to the whole agent layer.
- **So what:** the agents shouldn't just answer — they should *propose*. Bake "here's something you're
  not looking at" into the digest.

### I9 — "Winners → lookalikes" as a lead-gen primitive
- **Seed:** *"the most successful photo booths in Dallas → find the same venues in Houston, San
  Antonio, Fort Worth"* (`15:18`).
- **Generalizes:** take your best accounts, extract their attributes, find matches in a new
  geography/segment. A reusable acquisition primitive for any attribute-driven B2B motion, not just
  photo booths.
- **So what:** an explicit "find lookalikes of this cohort" action, seeded by your own winners — the
  acquisition twin of I3's retention loop.

### I10 — A/B testing lives inside the CRM
- **Seed:** Zach's closing spark — *"we could do A/B testing on marketing materials, that's freaking
  cool"* (`1:06:41`).
- **Generalizes:** the CRM already holds the outreach content **and** the conversion outcome, so it's
  the natural home to run and read the experiment. Applies to any outreach-driven product.
- **So what:** sequence steps / templates get variant support + a readout tied to engagement events.

### I11 — Encoding a domain expert's tacit judgment as the real IP
- **Seed:** Ben — *"I'm trying to sponge as much up from really good salesmen like you… ingrain that
  into a product"* (`36:54`); the whole call is Zach's 20 years being mined.
- **Generalizes:** a repeatable method — instrument an expert's judgment (what makes a venue good,
  when to call, how to word the intro) into product logic and training data. Ties directly to Ben's
  **brain-encoding-model** class project (grading content by how a brain interprets it — `52:37`).
- **So what:** structure future Zach sessions as *elicitation* (capture the heuristics as rules/
  labels), not just feedback. The expert is a data source, deliberately.

### I12 — Two-sided ROI as the positioning template
- **Seed:** *"it's gonna make you money, it's gonna make me money"* (`37:28`); venues paying $1,000/mo
  for a marketing-play booth they're *thrilled* to host (`50:53`).
- **Generalizes:** partner products win when the pitch quantifies value for **both** sides. Surge,
  telemetry, and recaps all serve this. A reusable framing for any revenue-share or channel product.
- **So what:** every partner-facing artifact should show the venue *their* upside, not just Betson's.

---

## Cross-links to Ben's other work
- **I6 (CRM⨯IoT)** shares a spine with the **Betson gameroom-twin** (device telemetry, technician
  walkthrough) Ben referenced at `10:55` — a booth-telemetry object could reuse that thinking.
- **I1 / I11** are the general thesis behind Ben's whole "build vibe-coded observability products,
  form-fit to a niche" pattern — worth capturing in the build-in-public idea bank, not just here.
