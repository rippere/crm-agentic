# NovaCRM/Twin Demo — Readiness & Sequencing

**CRM task:** `mtg20260812-crm-demo-mike-then-zach`
**Owner:** Ben
**Window:** First two weeks of September 2026 (Mike review → fixes → Zach handoff)
**Source of truth:** [[NovaCRM — Betson Meeting Distillation 2026-08-12]]
**Status:** active

---

## 0. The frame (why this sequence exists)

From the 2026-08-12 Ben ↔ Mike Betti meeting:

- **Build for Zach**, the entry-level test client returning **Sept 1** to run the **photo-booth division** as a separate unit ("Zach on an island"). Pro-CRM, wants an AI-forward approach.
- **The bar:** *demonstrable in September, solid in October* — so Zach isn't tempted to grab Salesforce or a cheap off-the-shelf CRM instead.
- **The winning move is the lead-gen / marketing module.** The core of a CRM is *"10,000 leads → a database → a funnel of engagement."* That framing IS Zach's use case. This is the flagship being built this session, and it is what the demo must land.
- **Gating fact:** **Mike will not forward Zach a link until Ben says it's ready.** Mike sees it first. That is the whole reason "ready for Mike" and "ready for Zach" are two different bars.

Two audiences, two bars, one gate between them. Mike is the internal champion doing a sniff-test; Zach is the actual user who must not bounce to Salesforce.

---

## 1. Two acceptance bars — what "ready" means

### Bar A — "Ready for Mike" (internal champion review)

Mike is not the end user. He is deciding *whether this is credible enough to put in front of Zach*. He needs to see that the lead-gen story is real and that nothing embarrasses him when he forwards it. Lower polish tolerance than Zach; higher trust because he already believes in the direction.

**Ready-for-Mike is met when ALL of these are observed true:**

| # | Acceptance criterion | How it's verified |
|---|---|---|
| A1 | The **10k-leads → funnel** narrative can be walked end to end with **zero dead clicks** on the happy path. | Ben click-walks the full path in section 2 live; every step renders. |
| A2 | Data is **photo-booth-division realistic**, not generic Acme SaaS. Company names, contacts, deal sizes, and lead sources read like Zach's world. | Manual scan of `/contacts`, `/pipeline`, lead-gen module — no "Acme Corp / Sarah Chen" placeholder residue on any screen Mike will see. |
| A3 | The **lead-gen module is the centerpiece** and visibly does the thing: ingest a batch of leads → score/segment → drop into a funnel → sequences fire. | The flagship module's core path (section 2, steps 2–4) runs without demo-mode gaps. |
| A4 | **Funnel is populated and sequences are visible** — not empty states, not "0 contacts in stage." | Every funnel stage shows realistic counts; at least one sequence shows enrolled leads mid-flight. |
| A5 | **Obfuscated staging link** works from a clean browser (not localhost), loads in <5s, and carries a **version/staging cue** so it's unmistakably a work-in-progress build, not production. | Open the staging URL in an incognito window on a different machine/network. |
| A6 | A **≤10-min narrated click-path** exists (section 2) that Ben can run cold. | Dry-run once, timed. |

Bar A explicitly does **NOT** require: production auth, real Gmail/AVOS ingest, mobile polish, every agent wired, or Salesforce-coexistence answered. Those are October.

### Bar B — "Ready to forward to Zach" (end-user handoff)

Zach will click around **unsupervised** and is actively comparing against Salesforce/Zoho/HubSpot. Anything broken reads as "not real yet → I'll just buy Salesforce." Higher bar than Mike.

**Ready-for-Zach is met when Bar A holds AND ALL of these additionally hold:**

| # | Acceptance criterion | How it's verified |
|---|---|---|
| B1 | **No broken paths anywhere Zach can reach** — not just the happy path. Every nav item, every clickable card, every stage either works or is cleanly gated with an honest "coming soon," never a crash/blank/500. | Full click-crawl of every reachable route (see checklist §3). |
| B2 | **Self-guided comprehension:** a first-time user reaches the "10k leads → funnel" aha without a narrator. Empty-state copy and the landing view point at the lead-gen module. | Cold-user test — someone who hasn't seen it navigates unaided to the funnel. |
| B3 | **Data survives poking.** Filtering, sorting, opening any lead, opening any deal all return sensible results — no single-record demo that collapses on the second click. | Click 5+ arbitrary leads/deals, apply filters. |
| B4 | **The staging link is stable + obfuscated + honestly labeled** for an unsupervised session over multiple days (Zach returns Sept 1, may look any time). | Link still live and unchanged 48h+ after issue. |
| B5 | **Ben has explicitly said "it's ready"** — the human gate Mike is waiting on. | Ben's go, recorded in the CRM task. |

Bar B is the trigger for Mike forwarding the link. Until B1–B5, the link does not leave Mike's hands.

---

## 2. Demo narrative for Zach — the 10k-leads → funnel click-path

**Persona to seed:** Zach runs the **photo-booth division** as a standalone unit. He's just inherited (or bought) a list of ~10,000 event/venue leads — wedding venues, corporate event planners, party-rental outfits, school/prom coordinators, festival organizers — and needs to turn that raw list into booked photo-booth rentals. He has no CRM today.

**The one sentence:** *"A CRM's whole job is 10,000 leads → a database → a funnel of engagement. Here's yours — and the machine does the sorting and the outreach, you just approve."*

### Click-path (target ≤10 min, this is the spine of both bars)

**Step 0 — Land on the staging link.**
Open the obfuscated staging URL. Version/staging badge visible top corner ("staging · v0.x · sample data"). Sets expectation: this is your build, in progress.

**Step 1 — The raw list exists (the "10,000 leads").**
Navigate to the **lead-gen module**. Show the imported lead pool — a realistic count (seed the number so it reads like 10k, e.g. "9,847 leads") sourced from a batch import. *Say: "This is the list. Yesterday it was a spreadsheet. Now it's a live database."*

**Step 2 — The machine segments it (leads → database).**
Show leads auto-scored and segmented into meaningful buckets for the photo-booth business — e.g. *high-intent (requested a quote)*, *venue partners*, *seasonal/prom*, *cold*. Point at the signals driving a score (event date proximity, budget signal, decision-maker). *Say: "You didn't tag these. The scorer read the signals and did it — and it'll show you why on any lead."* Click one lead to show its signal breakdown.

**Step 3 — The funnel (the money shot).**
Move to the **funnel/pipeline** view. Every stage populated: *New → Contacted → Quoted → Booked*, with realistic counts per stage. This is the "funnel of engagement" made literal. *Say: "This is your business on one screen. 9,800 at the top, the hot ones already moving right."*

**Step 4 — Sequences are running (engagement, human-in-the-loop).**
Show an active **outreach sequence** enrolled with a segment — e.g. a 3-touch sequence to high-intent venue leads. Show a **drafted** first-touch email, personalized to a specific lead's event type, sitting **pending approval** (not auto-sent). *Say: "The system wrote the outreach grounded in each lead's context. Nothing sends until you click approve. This is the part Salesforce charges you $130k a year for and still makes you do by hand."*

**Step 5 — Ask it a question (the AI closer).**
Use the natural-language query: *"Which leads should I chase this week?"* → Nova returns named leads with scores + a suggested action. *Say: "Ask your pipeline anything. It has the full context — every lead, every touch."*

**Closing line:** *"A spreadsheet of 10,000 names is a chore. This is a funnel that sorts itself and drafts your outreach — and it's yours, running today, built for the photo-booth division and nobody else."*

**Contrast beat (only if Salesforce comes up):** don't model on Salesforce — it's the clunkiest, $130k/yr, and still manual. Nova starts producing value in hours, not a 6-month implementation.

---

## 3. Readiness checklist

Print this and check it off before the Mike review, then again before the Zach handoff.

### Data seeding (photo-booth-division realism)
- [ ] Lead pool seeded with a **10k-scale count** of realistic photo-booth leads (wedding venues, event planners, party rental, schools/proms, festivals) — no Acme/generic residue.
- [ ] Lead **names, companies, contacts, event types, budgets, sources** read as real for Zach's world.
- [ ] Leads carry **scoring signals** that make the auto-segmentation defensible (event date, budget, intent, decision-maker).
- [ ] At least 4 meaningful **segments** populated.

### Funnel populated
- [ ] Every funnel stage (New → Contacted → Quoted → Booked, or the module's actual stages) has **realistic non-zero counts**.
- [ ] Stage counts **taper** like a real funnel (fat top, thin bottom) — not uniform.
- [ ] Individual deals/leads open and show a coherent history — survive the second and fifth click.

### Sequences visible
- [ ] At least one **active outreach sequence** with enrolled leads mid-flight.
- [ ] At least one **drafted, personalized, pending-approval** email visible (proves human-in-the-loop).
- [ ] Sequence copy is **photo-booth-relevant**, not generic SaaS.

### No broken paths
- [ ] Full **happy path** (section 2 steps 0–5) runs with zero dead clicks — Bar A.
- [ ] Full **click-crawl of every reachable route** — every nav item, card, stage either works or is honestly gated "coming soon," never crash/blank/500 — Bar B.
- [ ] NL query returns sensible named results for 2+ distinct questions.
- [ ] No console errors that surface as visible breakage on any Zach-reachable screen.

### Staging link (per the Twin task convention)
- [ ] Deployed to an **obfuscated staging URL** (non-guessable path/subdomain), reachable off-localhost.
- [ ] Loads in **<5s** from a clean incognito session on a different network.
- [ ] **Version/staging cue** visible on-screen (badge: "staging · sample data · v0.x") so it can't be mistaken for production.
- [ ] Link is **stable for 48h+** unsupervised (Zach may look any time after Sept 1).
- [ ] No real customer/Betson data and no live-send capability wired to the staging build.

### Human gate
- [ ] Ben has run the cold dry-run end to end and **explicitly marked "ready"** in the CRM task before the link is handed to Mike to forward.

---

## 4. Week-by-week sequence (first two weeks of September)

### Pre-flight (last week of Aug — before the window opens)
- Finish the **lead-gen module** flagship path (this session's build).
- Seed photo-booth data; stand up the obfuscated staging link with the version badge.
- Ben runs the section-2 click-path once, timed — this is the internal gate to even schedule Mike.

### Week 1 (Sept 1–5) — Mike review → fixes
- **Sept 1–2:** Confirm **Bar A** self-check (§1 A1–A6) passes on staging. Do NOT invite Mike until it does.
- **Sept 2–3:** **Mike review.** Walk him the section-2 narrative (or let him self-drive the staging link). Capture every friction point / dead click / "that looks fake" reaction verbatim.
- **Sept 3–5:** **Fix loop.** Burn down Mike's list + any Bar B (B1–B3) gaps found. Re-seed data if anything read as generic. Re-run the full click-crawl after each batch of fixes.
- **End of Week 1 target:** Bar A fully green, Bar B click-crawl green, Mike's notes closed.

### Week 2 (Sept 8–12) — Zach handoff
- **Sept 8–9:** Final **Bar B** pass (§1 B1–B5). Cold-user comprehension test (someone unfamiliar reaches the funnel unaided). Confirm staging link stable 48h.
- **Sept 9–10:** **Ben says "ready"** — record it in the CRM task. This flips the gate.
- **Sept 10–11:** **Mike forwards the obfuscated link to Zach.** Ben stays on standby.
- **Sept 11–12:** Monitor Zach's first unsupervised session; hotfix anything he hits same-day. This is now the *demonstrable-September* milestone banked, with October reserved for "solid."

> Slack rule: if Bar A slips past Sept 5, hold the Zach handoff — better a late-but-clean handoff than Zach's first click landing on a broken path. The gate protects the relationship.

---

## 5. Gating rules (nothing forwarded until X)

1. **The link does not leave Mike's hands until Ben explicitly says "ready."** This is Mike's own stated condition. Ben's word is the gate, not a calendar date.
2. **Ben does not say "ready" until Bar B (§1 B1–B5) is observed true** — full click-crawl clean, cold-user test passed, staging link stable, data realistic. "Ready" means *observed working*, not *should work*.
3. **Mike does not get invited to review until Bar A (§1 A1–A6) is observed true.** Don't burn the champion's first impression on a build with dead clicks.
4. **The lead-gen module is the demo.** If the flagship path isn't landing, nothing else being polished counts as ready — segmentation → funnel → sequences is the spine that wins, per Mike's "10k leads → funnel" framing.
5. **No generic/placeholder data on any screen the audience can reach.** A single "Acme Corp / Sarah Chen" sighting reads as vaporware to a Salesforce-comparing buyer and voids readiness.
6. **Staging only, honestly labeled.** The forwarded artifact is always the obfuscated, version-cued staging link — never localhost, never anything that looks like production, never wired to live send or real Betson data.
7. **September = demonstrable, October = solid.** Do not over-scope Week 1–2 chasing production-readiness. The Sept bar is a clean, believable demo of the lead-gen funnel — not a shipped product. Salesforce-coexistence, AVOS ingest, and real auth are explicitly out of this window.

---

_Grounded in the 2026-08-12 Betti meeting distillation and the existing `DEMO_SCRIPT.md` (which is the internal-showcase script; this document is the Betson/Zach-specific sequencing layer on top of it). The DEMO_SCRIPT's honest-sample-data discipline carries over — no fabricated model/accuracy claims._
