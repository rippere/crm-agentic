# NovaCRM ↔ AVOS/Voss Data Interface — Design & Scoping

- **CRM task:** `mtg20260812-crm-avos-data-interface`
- **Status:** DRAFT for the Friday VOS demo (scoping, not committed contract)
- **Author:** Ben (via NovaCRM engineering)
- **Date:** 2026-08-13
- **Source of record:** `note/NovaCRM — Betson Meeting Distillation 2026-08-12.md` §7 (AVOS/rep-share), Open Questions (AVOS/Voss identity)
- **Codebase reviewed:** `apps/api/app/{models,routers,workers}` (contact/deal models, `contacts.py` import + duplicate-candidates, `workers/ingest.py`)

> **Read this first — what is decided vs. assumed.** Everything about AVOS/Voss's *own* system is
> **assumption** until Friday's demo confirms it (their name/system identity is still an open question
> in the meeting notes). Everything about **NovaCRM's side** — schema, ingest path, where a match lands —
> is **decided** and grounded in the current codebase. The Friday agenda (§5) exists to convert the
> assumptions into a signed contract.

---

## 1. The two datasets and the identity ambiguity

### 1a. What each side plausibly holds

**NovaCRM side (known — this is our codebase).**
- **`contacts`** — leads/prospects/customers. Real columns today: `id (uuid)`, `workspace_id`,
  `name`, `email`, `company`, `role`, `status ∈ {lead, prospect, customer, churned}`, `ml_score (jsonb)`,
  `semantic_tags`, `revenue`, `deal_count`, `embedding (vector(384))`, timestamps.
  **No `phone`, no `external_id`, no `source` column exists yet** — see §2c for the additive migration.
- **`deals`** — pipeline objects tied to a contact by `contact_id` (nullable) plus denormalized
  `company` / `contact_name` strings.
- Contacts are currently created two ways: Gmail ingest auto-creating leads from inbound mail
  (`workers/ingest.py::_link_contact`, matched on **email only**), and CSV upload
  (`POST /workspaces/{workspace_id}/contacts/import`, upserted on **email only**).
- **Zach's photo-booth division** is the target tenant — one NovaCRM `workspace`. The meeting frames
  the CRM's core job as "10,000 leads → a database → a funnel of engagement," so the lead-gen /
  marketing module is the consumer of this interface.

**Betson rep-share side (assumed — confirm Friday).** "Rep-share" in a distribution/vending/amusement
business (Betson's world) most plausibly means **manufacturer rep / sales-rep-attributed account
records**: the roster of customer locations, operators, or accounts with the rep or territory credited
for each, plus sales/commission ("share") figures. Working assumption:
- One row per **account/location** (arcade, operator, route stop, or dealer).
- Fields: account/business name, address, a rep name or rep code, maybe a distributor, and a
  revenue/units/commission-share number over some period.
- **Dirty in exactly the way that needs fuzzy matching:** the same physical business appears as
  "Dave & Buster's #217", "Dave and Busters Times Sq", "D&B TSQ" across feeds — free-text business
  names, no shared stable key with anything in NovaCRM.

AVOS/Voss is **Betson's other external AI consultant**, engaged to do the *ingest + fuzzy naming match*
against this rep-share data. Ben gets a demo of their ingest work Friday.

### 1b. The identity ambiguity to resolve

There are **two distinct ambiguities**; keep them separate.

1. **Vendor/system identity (meeting Open Question).** "AVOS / Avas / Voss" — is it the consultant's
   name, a product/system name, or both ("Voss's feed")? This determines who owns which side of the
   pipe and what "their ingest" produces. **Resolve verbally in the first 5 min Friday.**

2. **Record identity (the actual engineering problem).** NovaCRM `contacts`/`deals` and Betson
   rep-share rows describe **overlapping real-world entities (businesses / operators / people) with no
   shared primary key**. The core question the interface must answer:

   > *Given a rep-share account row, which NovaCRM contact (if any) is the same real-world entity — and
   > with what confidence?*

   This is **entity resolution / record linkage**, not a join. Email is the only clean key NovaCRM has,
   and rep-share data almost certainly has **no email** — so the match must run on **business name +
   location**, which is exactly why fuzzy matching (§3) is the crux.

**Assumption flagged:** that the two datasets are meant to be *linked* (enriched against each other),
not *merged* into one store. Decisive recommendation: **link, don't merge** (§2a). Confirm Friday.

---

## 2. Proposed data-interface contract

### 2a. Direction of flow — recommendation: **AVOS → NovaCRM, one-way to start**

AVOS owns ingest + fuzzy matching; NovaCRM owns the CRM funnel. The clean seam is:

- **Phase 1 (Sept demo):** **AVOS → NovaCRM**, batch, one-way. AVOS delivers rep-share records already
  fuzzy-matched (their specialty) with a candidate NovaCRM key or a "no match" flag. NovaCRM ingests,
  attaches rep-share attribution to contacts/deals, and routes low-confidence matches to a human-review
  queue. No live coupling, no shared DB, nothing to break before Zach sees a demo.
- **Phase 2 (later, optional):** **NovaCRM → AVOS** contact export so AVOS matches against the *current*
  CRM state, plus a **confirm callback** (NovaCRM → AVOS) sending human-review decisions back so their
  matcher learns. Only build this once Phase 1 is observed working.

**Decision: do not let AVOS write directly into NovaCRM's Postgres.** Ingest through a NovaCRM-owned
endpoint/worker so our validation, workspace scoping, and audit trail always apply.

### 2b. Format — recommendation: **newline-delimited JSON (or CSV) batch file, not a live API, for Phase 1**

- NovaCRM already has a CSV contact-import path and a CSV export path — a file drop is the lowest-friction
  thing both sides can produce this week. **Prefer JSON** (JSONL) over CSV because the match payload is
  nested (candidate list + scores + provenance) and CSV flattens badly.
- Transport: whatever's cheapest to agree on Friday — S3/Drive drop, or a signed `POST` of the file to a
  new NovaCRM ingest endpoint (§4). Avoid standing up a bidirectional real-time API for a September demo.
- **One record = one rep-share account** with an embedded match block.

### 2c. Schema — the wire contract (AVOS → NovaCRM)

```jsonc
{
  "avos_record_id":    "string",        // AVOS's stable id for this rep-share row (REQUIRED, dedupe key)
  "source_feed":       "string",        // e.g. "rep-share-2026Q2" (provenance)
  "business_name":     "string",        // raw name as it appears in rep-share (REQUIRED)
  "normalized_name":   "string|null",   // AVOS's cleaned name, if they expose it
  "address":           "string|null",
  "city":              "string|null",
  "state":             "string|null",
  "postal_code":       "string|null",
  "rep_name":          "string|null",   // the credited rep / territory
  "rep_code":          "string|null",
  "email":             "string|null",   // rarely present; when present it's the golden key
  "phone":             "string|null",
  "revenue_share":     "number|null",   // the "share" figure
  "period":            "string|null",   // e.g. "2026-Q2"
  "match": {
    "status":          "matched|review|unmatched",   // AVOS's own verdict (REQUIRED)
    "candidates": [
      {
        "novacrm_contact_id": "uuid|null",  // present only if AVOS was given a CRM export (Phase 2)
        "matched_name":       "string",
        "score":              0.0,          // 0–1, see §3 for how WE recompute/validate
        "method":             "token_set|jaro_winkler|embedding|exact_email"
      }
    ]
  }
}
```

Field-mapping into NovaCRM's model (**where it lands**):

| Wire field | Lands in NovaCRM |
|---|---|
| `business_name` / `normalized_name` | `contacts.company` (and matched against existing `company`/`name`) |
| `email` (if present) | `contacts.email` — clean upsert key, bypasses fuzzy |
| `rep_name` / `rep_code` | **new** `contacts.semantic_tags` entry `rep:<code>` + stored in `external_ref` (see below) |
| `revenue_share` | `contacts.revenue` (or a rep-share-specific field; do **not** clobber CRM-derived revenue — see assumption) |
| `avos_record_id` + `source_feed` | **new** `contacts.external_ref (jsonb)` — provenance, dedupe, re-run idempotency |
| `match.status` / top `score` | drives auto-apply vs. review queue (§3d) |

**Required additive migration (decided, low-risk, backward-compatible):**
- `contacts.external_ref jsonb NOT NULL DEFAULT '{}'::jsonb` — holds
  `{ "avos_record_id": ..., "source_feed": ..., "rep_code": ..., "matched_score": ... }`.
- Add a partial unique index on `(workspace_id, (external_ref->>'avos_record_id'))` where the key is
  present, so re-delivered feeds upsert instead of duplicating (mirrors the message dedupe pattern in
  `ingest.py`).
- **No** new table needed for Phase 1; rep-share attribution rides on `contacts`. A dedicated
  `rep_share_accounts` table is deferred until Betson wants rep-share as a first-class object.

**Assumption flagged:** that `revenue_share` maps onto `contacts.revenue`. It may be a *different* metric
(commission vs. booked revenue). Safer default: **store it in `external_ref.revenue_share` and leave
`contacts.revenue` alone** until Zach/Mike say the two are the same number. Confirm Friday.

---

## 3. Fuzzy naming-match approach (fits NovaCRM's current stack)

NovaCRM already ships a first-cut fuzzy matcher — `GET /workspaces/{id}/contacts/duplicate-candidates`
in `contacts.py` — using `difflib.SequenceMatcher` on lowercased names (weight 0.7) plus same-email-domain
(0.3), threshold 0.65, capped at 300 contacts with an O(n²) inner loop. **That is the pattern to extend,
not reinvent.** Its weaknesses for rep-share matching: `SequenceMatcher` is order-sensitive (bad for
"Dave & Busters Times Sq" vs "Times Square Dave and Busters"), it has no blocking, and it doesn't scale
to 10k leads × a rep-share feed. The upgrade:

### 3a. Normalization (before any scoring)
Lowercase; strip punctuation; expand/standardize `&`↔`and`; drop corporate suffixes (`inc`, `llc`,
`corp`); strip store-number noise (`#217`, `- TSQ`); collapse whitespace. Produce a `normalized_name`
token set. Do this on **both** sides identically — matching quality is dominated by normalization, not by
the metric.

### 3b. Candidate blocking (avoid the O(n²) full cross-join)
Don't score every rep-share row against every contact. Block first:
1. **Exact email match** → immediate accept, skip fuzzy entirely (rare but golden).
2. **Postal-code / state block** → only compare rows sharing a location key when address is present.
3. **Name-token block** → index contacts by their significant tokens; a rep-share row is only compared
   to contacts sharing ≥1 rare token (or a first-3-chars / metaphone key).
4. **(Optional, later) semantic block** — NovaCRM contacts already carry a `vector(384)` `embedding`.
   Embed the rep-share `business_name` and pull top-K nearest contacts via pgvector as candidates. This
   is a natural fit for the existing stack and handles paraphrase-level variation blocking can't.

### 3c. Similarity metric (recommendation: **token-set ratio + Jaro-Winkler, combined**)
Per candidate pair, compute on normalized names:
- **Token-set ratio** (order-independent, handles reordered/extra tokens) — the primary signal for
  multi-word business names.
- **Jaro-Winkler** (rewards shared prefixes, strong on typos/truncations like "Busters"/"Buster").
- Optional Levenshtein/edit-distance as a tie-breaker on short names.
- **Location boost:** +0.15 if postal/state agree (generalizes the existing "same email domain +0.3"
  bump).

Combined score `= max(token_set, jaro_winkler) * 0.85 + location_boost`, clamped to [0,1].

**Library:** add **`rapidfuzz`** (permissive MIT, C-backed, ships `token_set_ratio` + `JaroWinkler`, no
native-build pain). It is **not currently a dependency** — adding it is the one new package this needs.
`rapidfuzz` also replaces the hand-rolled `difflib` path and makes the existing
`duplicate-candidates` endpoint faster and better in the same change. (`jellyfish` is a fine alternative
if a lighter dep is preferred.)

### 3d. Thresholds + human-review queue
Three bands (tune on the first real feed — these are starting points):
- **score ≥ 0.92 → auto-match.** Attach rep-share attribution to the contact automatically.
- **0.75 ≤ score < 0.92 → review queue.** Surface as a candidate pair for a human to confirm/reject —
  reuse the `DuplicateCandidatePair` response shape already in `contacts.py`.
- **score < 0.75 → unmatched.** Create a **new** `contact` (status `lead`) from the rep-share row, tagged
  with its `source_feed`, so nothing is dropped (mirrors ingest's "inbound becomes real pipeline"
  and "weak ties are never deleted" doctrine).

Trust boundary: **prefer NovaCRM's own recomputed score over AVOS's `match.score`** for the auto-apply
decision — AVOS's score is advisory. If AVOS did the matching against a CRM export (Phase 2), we still
re-validate the top candidate before auto-applying. Every auto-match and every human decision writes an
`ActivityEvent` (that model already exists) for audit + eventual match-quality metrics.

---

## 4. Integration point in the current codebase

Concrete, minimal, matches existing patterns:

- **Router:** add `apps/api/app/routers/rep_share.py` (or extend `contacts.py`) exposing
  `POST /workspaces/{workspace_id}/rep-share/ingest` — accepts the JSONL/CSV batch (§2c), auth via the
  existing `get_current_user` + `workspace_id` guard used everywhere in `contacts.py`. Endpoint validates
  and enqueues; it does **not** do the matching inline.
- **Worker:** add `apps/api/app/workers/rep_share_match.py` as a Celery task
  `app.workers.rep_share_match.match_rep_share_feed(workspace_id, payload_ref)`, registered on the existing
  `celery_app`. It follows the exact shape of `workers/ingest.py::_run_sync`: async session via
  `_get_async_session`, dedupe on `external_ref.avos_record_id` (like message `external_id` dedupe),
  block → score → band → write, then `commit`. Long feeds run off the request path just like Gmail sync.
- **Matching service:** add `apps/api/app/services/rep_share_match.py` holding normalization + blocking +
  `rapidfuzz` scoring, so both the new worker and the existing `duplicate-candidates` endpoint call one
  implementation. This is where the `difflib` logic gets upgraded.
- **Model/migration:** `contacts.external_ref jsonb` + the partial unique index (§2c). One Alembic
  migration; additive; safe on the live Zach workspace.
- **Review-queue read path:** extend the existing
  `GET /workspaces/{id}/contacts/duplicate-candidates` (or a sibling `/rep-share/review`) to return the
  0.75–0.92 band, reusing `DuplicateCandidatePair`. Confirm/reject endpoints apply or discard the link and
  emit an `ActivityEvent`.

Nothing here touches the Gmail ingest path, auth, or the deal model — it's a new lane alongside them.

---

## 5. Friday VOS meeting — agenda + questions

**Goal of the meeting:** turn every §1–§3 assumption into a confirmed fact and leave with a one-page
signed data contract. Ben is receiving a demo of AVOS's ingest work.

**Agenda (30–40 min):**
1. **(5 min) Identity + ownership.** Who/what is AVOS/Voss — consultant, product, or both? Who owns which
   side of the pipe?
2. **(10 min) Watch the demo.** What exactly does their ingest produce — a matched file, a live API, a UI?
3. **(10 min) Rep-share dataset walkthrough.** Real columns, real sample rows, volume, refresh cadence.
4. **(10 min) Agree the interface.** Direction (confirm AVOS→NovaCRM one-way for Phase 1), format
   (JSONL vs CSV), field names, transport, who computes the final match score.
5. **(5 min) Next step + owner + date.** Sample file exchanged, migration scheduled, demo-readiness for
   the first two weeks of September.

**Question list (ask these explicitly):**
- *Identity:* Is "AVOS/Voss" the consultant, the system, or both? What's the correct spelling for the record?
- *Dataset:* What is a "rep-share" row — one per account, per location, per rep, per transaction? Send 20
  real sample rows.
- *Keys:* Does rep-share data carry **any** stable identifier NovaCRM could join on (account #, email,
  phone)? Or is business-name the only handle?
- *Match output:* Does your ingest **emit matches**, or just clean/normalized rep-share records? If it
  matches — against **what** target list? (You don't have NovaCRM's contacts yet.)
- *Direction:* Are you expecting NovaCRM to **send you** its contacts to match against, or to **receive**
  your matched output? (We propose the latter for Phase 1.)
- *Format/transport:* JSONL or CSV? File drop (S3/Drive) or an API call? How often — one-time, nightly, on
  demand?
- *Confidence:* Do you expose a per-match **score**, and how is it computed? (We'll re-validate on our side
  before auto-applying — align on thresholds.)
- *Metrics:* Is `revenue_share` booked revenue, commission, or units? Over what period? (Determines whether
  it touches `contacts.revenue`.)
- *Volume + scale:* How many rep-share rows total? (Sizes the blocking strategy.)
- *Duplicates:* Does your feed dedupe itself, or can the same account appear multiple times across feeds?
- *Feedback loop:* Do you want NovaCRM's human confirm/reject decisions back to improve your matcher
  (Phase 2)?

---

## 6. Open questions

- **[Meeting] AVOS/Voss identity** — unresolved until Friday; gates the whole ownership model.
- **What "rep-share" actually is** — the single biggest assumption in this doc (§1a). All schema in §2c is
  provisional until confirmed against real sample rows.
- **Does rep-share carry email/phone/account#?** If yes, fuzzy matching becomes a fallback, not the main
  path — materially simpler.
- **Matching ownership** — does AVOS match against a NovaCRM export (requires Phase-2 NovaCRM→AVOS export
  now, not later), or do they only clean rep-share and NovaCRM does all matching? Recommendation assumes
  **NovaCRM owns the authoritative match**; confirm.
- **`revenue_share` semantics** — commission vs. booked revenue; whether it maps to `contacts.revenue`.
- **Tenant scope** — is this Zach's photo-booth workspace only, or Betson-corporate data too? Affects
  workspace scoping and volume (the meeting says build for Zach, "not 400 other people").
- **Salesforce coexistence (meeting Open Question)** — if rep-share also lives in Betson's Salesforce,
  is NovaCRM the system of record for the matched result or a downstream consumer? Related but separable.
- **Refresh cadence + idempotency** — one-time load vs. recurring feed decides how hard the
  `avos_record_id` dedupe/upsert path must be (built in either way, but re-runs must be safe).

---

### Appendix — grounding references
- `apps/api/app/models/contact.py` — contact schema (no phone/external_id/source today).
- `apps/api/app/models/deal.py` — deal ↔ contact linkage.
- `apps/api/app/routers/contacts.py` — CSV import (email-only upsert, L187), duplicate-candidates
  fuzzy matcher (`difflib`, 0.7 name / 0.3 domain, threshold 0.65, L267–317).
- `apps/api/app/workers/ingest.py` — Celery ingest pattern to mirror: dedupe, async session, off-critical
  enqueue, "never delete weak ties" doctrine.
- `apps/api/app/models/connector.py`, `activity_event.py` — existing provenance/audit surfaces to reuse.
