# NovaCRM — Investor Demo Script
**Duration:** ~8 minutes  
**URL:** http://localhost:3000  
**Persona:** You're the founder of Acme Corp, a 10-person SaaS team. Your CRM has been running for 6 weeks.

---

## The pitch in one sentence
> "NovaCRM replaces the manual work of CRM maintenance — emails, scoring, pipeline health — with autonomous agents that run in the background and surface intelligence when you need it."

---

## Step 1 — Dashboard (1 min)
**Navigate to:** `/dashboard`

Point out:
- **$485K revenue**, 91% ML lead accuracy, 3 agents running right now
- The **activity feed** on the right — this is the agents' work log. Point to ev-004: *"Pipeline Optimizer flagged TechCorp deal as stalled — 18 days in Negotiation. Recommended: schedule follow-up call."* That happened automatically at 2am.
- **Stale deal alert** — the system caught it before you did

**Say:** "Most CRMs just store data. NovaCRM acts on it."

---

## Step 2 — Inbox (1.5 min)
**Navigate to:** `/inbox`

Point out:
- 6 emails ingested from Gmail this morning
- Open the **Sarah Chen** email (Re: Enterprise Platform — SLA Review)
- Show the **3 auto-extracted tasks** on the right with clarity scores: *"Revise SLA — 99.95% uptime"*, *"Add EU data residency clause"*, *"Confirm P1 support SLA"*
- Clarity score 92/100 — the AI ranked this email as highly actionable

**Say:** "A rep opens their inbox and tasks are already created. No copy-paste, no manual logging."

- Open the **James Whitfield** email — show clarity score 88, two tasks auto-generated, hard deadline detected

---

## Step 3 — Contacts + Pre-Meeting Brief (2.5 min)
**Navigate to:** `/contacts`

- Click on **Marcus Rivera** (CRO, Global Finance — hot prospect, score 78)
- Show his lead score signals: *"Demo scheduled, Requested pricing, Decision maker"*
- Show semantic tags: *enterprise, decision-maker*
- Click **"Pre-Meeting Brief"** → wait ~2s → show the live AI-generated brief

**Say:** "Before jumping on a call with Marcus, the rep clicks one button. Claude reads his deal history, email thread, and lead signals — and generates a personalized brief in real time."

- Click **"Compose AI Email"** → show it drafting a personalized email for Marcus
- Point out it's grounded in his deal stage and last message, not a template

**Say:** "The email composer knows he's in the proposal stage with $250K on the line. It writes accordingly."

---

## Step 4 — Pipeline (1.5 min)
**Navigate to:** `/pipeline`

- Show the Kanban board — deals across Discovery → Negotiation
- Point to **Global Finance Enterprise Suite** in Proposal — health score 35, flagged
- Point to **ScalePath Japan** in Discovery — health 22, stalled

**Say:** "Health scores decay automatically based on inactivity, engagement silence, and stage duration. The Pipeline Optimizer runs every night and fires alerts before deals go cold."

- Navigate to `/reports`
- Show the revenue trend chart (Nov → Apr, trending up) and the 3-month AI forecast

---

## Step 5 — Nova AI Query (1 min)
**Press `Cmd+K`** (or the search bar at the top)

Type: *"Which deals are at risk this week?"*
→ Nova responds with specific deal names, health scores, and a suggested action

Type: *"Who are my hottest leads right now?"*
→ Nova lists them by name with scores

**Say:** "Any rep or manager can ask the pipeline a natural language question. Nova has full context — every contact, deal, and agent action."

---

## Step 6 — Agents (30 sec)
**Navigate to:** `/agents`

- Show 6 agents — Semantic Sorter, Lead Scorer, Email Composer, Call Summarizer, Pipeline Optimizer, Sentiment Analyzer
- Click into **Lead Scorer** — show accuracy 91%, retrained on last 90 days, F1 score
- Click into **Call Summarizer** — show it's processing right now

**Say:** "These agents run on a schedule or are triggered by events. The Lead Scorer just retrained itself overnight and improved 3 points. No human touched it."

---

## Closing line
> "Traditional CRMs are expensive databases. NovaCRM is an active participant in your sales process. We're currently in beta with 3 teams — looking for the right seed partner to accelerate the go-to-market."

---

## Likely investor questions

**"How does the AI actually work?"**
> Lead scoring uses XGBoost trained on your historical conversion data. Semantic tagging uses sentence-transformer embeddings. Email, briefs, and query use Claude — the same model powering Claude.ai. Everything runs on your data, in your workspace.

**"What's the data privacy story?"**
> All customer data stays in your Postgres instance — we never train on it. The only external calls are to Anthropic's API for generative features, and those are stateless.

**"How does this compare to Salesforce/HubSpot?"**
> They're built for data entry. NovaCRM is built for automation. We connect to your existing Gmail/Slack and start extracting value in hours, not months. Our target is teams that are currently *not* using a CRM because setup friction is too high.

**"What's the revenue model?"**
> SaaS, per-seat. $49/user/month for the core platform, $149/user for the AI tier (agents + Nova query). Target ACV: $15K–$80K for SMB/mid-market.
