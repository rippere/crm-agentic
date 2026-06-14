# NovaCRM — Product Showcase Script
**Audience:** Company president (internal showcase)
**Duration:** ~8 minutes
**Run in demo mode:** `cd apps/web && NEXT_PUBLIC_DEMO_MODE=true pnpm dev` → open `http://localhost:3000`
(Demo mode renders rich pre-generated data with no backend dependency — nothing can fail mid-demo.)
**Persona:** You're the founder of Acme Corp, a 10-person SaaS team. Your CRM has been running for 6 weeks.

---

## The pitch in one sentence
> "NovaCRM replaces the manual work of CRM maintenance — emails, scoring, pipeline health, call notes — with autonomous agents that run in the background and surface intelligence when you need it, while keeping a human in the loop on anything that matters."

---

## Step 1 — Dashboard (1 min)
**Navigate to:** `/dashboard`

Point out:
- Revenue, active deals, hot leads, and agents running right now — the at-a-glance state of the business.
- The **activity feed** on the right — this is the agents' work log. Point to the Pipeline Optimizer flagging a stalled deal automatically overnight.
- **Stale deal alert** — the system caught it before you did.

**Say:** "Most CRMs just store data. NovaCRM acts on it."

---

## Step 2 — Inbox (1.5 min)
**Navigate to:** `/inbox`

Point out:
- Emails ingested from Gmail this morning.
- Open the **Sarah Chen** email (Re: Enterprise Platform — SLA Review).
- Show the **auto-extracted tasks** on the right with clarity scores: *"Revise SLA"*, *"Add EU data residency clause"*, *"Confirm P1 support SLA"*.
- The clarity score ranks how actionable an email is.

**Say:** "A rep opens their inbox and tasks are already created. No copy-paste, no manual logging."

---

## Step 3 — Contacts + Pre-Meeting Brief (2.5 min)
**Navigate to:** `/contacts`

- Click on **Marcus Rivera** (CRO, Global Finance — hot prospect).
- Show his lead-score signals: *"Demo scheduled, Requested pricing, Decision maker"*.
- Show his semantic tags: *enterprise, decision-maker* (these come from embedding his messages).
- Click **"Pre-Meeting Brief"** → wait ~2s → show the live AI-generated brief.

**Say:** "Before a call with Marcus, the rep clicks one button. Claude reads his deal history, email thread, and lead signals — and generates a personalized brief in real time."

- Click **"Compose AI Email"** → show it drafting a personalized email grounded in his deal stage and last message — not a template.

**Say:** "The composer knows he's in the proposal stage. It writes accordingly — and nothing sends without a human approving it."

---

## Step 4 — Pipeline + Reports (1.5 min)
**Navigate to:** `/pipeline`

- Show the Kanban board — deals across Discovery → Negotiation.
- Point to a deal flagged with a low health score (stalled).

**Say:** "Health scores decay automatically based on inactivity, engagement silence, and stage duration. The Pipeline Optimizer runs every night and flags deals before they go cold."

- Navigate to `/reports` — show the revenue trend chart and the 3-month forecast.

---

## Step 5 — Nova AI Query (1 min)
**Press `⌘K`** (or the search bar)

Type: *"Which deals are at risk this week?"*
→ Nova responds with specific deal names, health scores, and a suggested action.

Type: *"Who are my hottest leads right now?"*
→ Nova lists them by name with scores.

**Say:** "Any rep or manager can ask the pipeline a natural-language question. Nova has full context — every contact, deal, and agent action."

---

## Step 6 — Agents + Help (45 sec)
**Navigate to:** `/agents`

- Show the 6 agents — Semantic Sorter, Lead Scorer, Email Composer, Call Summarizer, Pipeline Optimizer, Sentiment Analyzer.
- Click into **Call Summarizer** — show it processing a call (Whisper transcribes, Claude extracts action items).
- Click into **Pipeline Optimizer** — show its workflow: scan → velocity analysis → flag → notify.

**Say:** "These agents run on a schedule or are triggered by events — tagging contacts, scoring leads, summarizing calls — and they hand anything high-stakes back to a human for approval."

- Optional: open **Help** (`/help`) to show the built-in How-It-Works and FAQ.

---

## Closing line
> "Traditional CRMs are expensive databases. NovaCRM is an active participant in the sales process — built on semantic search, Whisper, and Claude, deployed and running today. Here's what we've shipped, and where it goes next."

---

## Likely questions

**"How does the AI actually work?"**
> Contact classification and semantic search use sentence-transformer embeddings (all-MiniLM-L6-v2). Call transcription uses Whisper. Email drafts, pre-meeting briefs, call summaries, sentiment, and the Nova query all use Anthropic's Claude. Lead and pipeline scoring use transparent heuristics over your own engagement signals — not a black box. Everything runs on your data, in your workspace.

**"What's the data privacy story?"**
> All customer data stays in the workspace's own database, isolated per tenant and encrypted in transit and at rest. We never train on it. The only external calls are to Anthropic's API for generative features, and those are stateless.

**"How does this compare to Salesforce/HubSpot?"**
> They're built for data entry. NovaCRM is built for automation. We connect to existing Gmail/Slack and start extracting value in hours, not months. The target is teams that aren't using a CRM today because setup friction is too high.

**"What's the revenue model?"**
> SaaS, per-seat. Intended pricing: $49/user/month for the core platform, $149/user for the AI tier (agents + Nova query), Enterprise custom.

**"What's actually live vs. roadmap?"**
> The product is deployed and running: ingestion, semantic search, scoring, compose, call summarization, pipeline analytics, and the agent framework with human-in-the-loop approval. Next up: deeper analytics, the in-app help/feedback loop, and broadening the connector set. (Real-time Gmail push ingest is built and gated behind a webhook secret that gets set per deployment.)

---

_Note: this script is for the demo-mode build, which uses honest pre-generated sample data. The live landing page and in-app copy were aligned to the real stack on 2026-06-13 — there are no fabricated model or accuracy claims to walk back if asked._
