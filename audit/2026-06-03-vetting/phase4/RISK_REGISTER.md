# NovaCRM — Phase 4 Risk Register

**Date:** 2026-06-03 · **Scope:** the seven confirmed findings + the claims-integrity workstream.
**Method:** each row scored on **Likelihood** (how readily a real party reaches it) × **Impact**
(blast radius if it fires), yielding a Risk band. Scores reflect *current prod state* (e.g. F1 is
High likelihood because the secret is absent **now**). Evidence is in `../phase2/`; the consolidated
narrative is in `REMEDIATION_REPORT.md`.

Scale: Likelihood / Impact ∈ {Low, Med, High}. Risk = combined band {Sev-1 … Sev-4},
Sev-1 highest.

---

## Scored register

| ID | Finding | Likelihood | Impact | Risk | Precondition to fire | Residual control today |
|----|---------|-----------|--------|------|----------------------|------------------------|
| **F1** | Gmail Pub/Sub webhook fails open | **High** — secret absent in prod now; route unauthenticated; email addresses discoverable | **Med** — forced-sync / ingest-trigger amplification; resource/cost abuse; no data read | **Sev-1** | Know/guess a connected mailbox address; POST a Pub/Sub-shaped body | **Status: MERGED** (`76839ee`) — code fails closed when the secret is unset. **Ops residual:** `GMAIL_WEBHOOK_SECRET` + `GMAIL_PUBSUB_TOPIC` still unset in Railway, so the webhook now rejects everything (Gmail push ingest inert until set). |
| **F2** | Workspace rebind via client-writable `user_metadata` | **Med** — needs an account (open signup) + a known/leaked target `workspace_id` (UUID) | **High** — full read+write of victim tenant as admin | **Sev-1** | Sign up; obtain target ws UUID (leaks in API responses / invites / onboarding); self-write metadata | **Status: MERGED** — `dependencies.py` binds workspace only from server-only `app_metadata`; user-writable metadata no longer trusted. **Ops residual:** `app_metadata` backfill for existing users + cutover confirmation. |
| **F3** | DB RLS inert (no enforced isolation backstop) | **Low (direct)** — not directly reachable; it is the *absence* of a backstop | **High** — converts any app-layer miss / injection / key-leak into full cross-tenant exposure | **Sev-2** | Any other defect (F2/F4-class) or a service-key exposure to be reachable | **Status: OPEN** — `013_force_rls.sql` shipped but INERT (API still connects as a shared `BYPASSRLS` role; `call_summaries` still effectively policy-free at runtime). Sole control remains app-layer `WHERE workspace_id` filters. Code prep in progress (lane `rls-dos`), behind a flag until the ops role-swap. |
| **F4** | `GET /jobs/{id}` unscoped job-result read | **Med** — authenticated; needs a foreign job_id (UUIDv4, not enumerable, but leaks via logs/referrers/screenshots) | **Med** — cross-tenant disclosure of a single job result payload (scores, ingest output, transcripts) | **Sev-2** | Valid account + knowledge/leakage of a foreign job_id | **Status: MERGED** (`76839ee`, PR #2) — `get_job_status` reads the owning workspace from the dispatch marker (`_job_owner_workspace`) and returns 404 on mismatch. Auth gate + per-job owner check now enforce isolation. |
| **F5** | Rate limiter one global bucket; no per-tenant spend cap | **Med** — any authenticated tenant; reprocess endpoint un-limited | **Med** — cross-tenant route throttling + unbounded model spend + 2-slot worker starvation | **Sev-3** | Valid account; hammer reprocess / AI endpoints | **Status: OPEN** — `limiter.py` keys on IP (`request.state.user` never set) so it degrades to one global bucket; no per-tenant spend cap; reprocess unbounded. Code prep in progress (lane `rls-dos`). |
| **F6** | Celery beat scheduled jobs crash (scheduled agents inert) | **High** — fires on **every** nightly schedule | **Med** — availability of the headline automation: no deal-health scoring, no proactive follow-ups; silent (deals pinned at 100) | **Sev-2** | None — it is already failing nightly | **Status: MERGED** — `beat_schedule` now points at the no-arg fan-out dispatchers `optimize_pipeline_all` / `compute_deal_health_all`. **Residual:** verify a scheduled cycle runs SUCCESS and recomputes a `health_score` off the default 100 in prod. |
| **F7** | Contact deletion orphans linked PII | **High** — every contact deletion; default behavior | **Med** — residual PII (emails, bodies, transcripts) after a "successful" deletion; GDPR right-to-erasure failure | **Sev-2** | Delete any contact | **Status: OPEN** — `delete_contact` still only does `db.delete(contact)` (docstring falsely claims cascade); linked `messages` / `call_summaries` PII left orphaned. Fix in progress (lane `delete-cascade`). |
| **CLAIM** | Unsubstantiated landing claims (SOC2 / uptime / GDPR / 94.7% / model lineup) | **High** — public; any buyer, regulator, or investor reads them | **High** — FTC §5 deception exposure (no breach/intent needed); enterprise-procurement disqualification; investor-diligence credibility | **Sev-1** | None — already public | **Status: PARTIALLY FIXED** — compliance badges (SOC 2 / 99.9% uptime / GDPR) removed earlier; fabricated ML lineup (94.7% accuracy / XGBoost / RoBERTa / GPT-4o / LightGBM / F1 0.947) **still live** on `apps/web/src/app/page.tsx`. Fix in progress (lane `claims`). |

---

## Risk-band rationale

- **Sev-1 (act this week): F1, F2, CLAIM.** F1 is the only zero-credential live-reachable defect — its
  code fix is now MERGED (fail-closed) and only the ops env-var set remains. F2 is full tenant takeover;
  its code fix is now MERGED (server-only `app_metadata`) and only the `app_metadata` backfill/cutover
  remains. CLAIM is public, high-liability, and cheap — no engineering, just copy; the compliance badges
  are removed but the fabricated ML lineup is still live.
- **Sev-2 (act in 30 days): F3, F4, F6, F7.** Tenant-isolation backstop + the proven app-layer miss
  it backstops — F4 is now MERGED (per-job owner check); F3 remains OPEN (RLS shipped but inert behind
  the shared `BYPASSRLS` role, pending the ops role-swap). The scheduled automation F6 is now MERGED
  (fan-out dispatchers; prod cycle still to be verified). F7 (the erasure defect that also fixes the
  GDPR claim's substance) remains OPEN.
- **Sev-3 (act in 60 days): F5.** Real but needs an authenticated actor and yields cost/availability
  abuse rather than data exposure; deferred behind the isolation work.

## Likelihood notes (honest caveats from validation)

- **F1** is rated High likelihood specifically because the prod env var is **absent today** — if the
  secret were set, the code-level bug would be configuration-mitigated (the same shape as the
  refuted Slack-events finding). The fix must therefore *both* set the secret *and* make the code
  fail closed + add a startup guard, so re-opening is not one missing env var away.
- **F4** likelihood is Med, not High: job_ids are high-entropy UUIDv4, so the exposure is
  IDOR-via-leakage, not trivial enumeration. It is still a real authenticated cross-tenant
  disclosure and must not rely on UUID unguessability as the control.
- **F5** magnitudes are from static analysis (no live load/spend test was authorized); the
  global-bucket and dead-per-user-key behaviors *are* empirically proven against the real limiter.
- **F3** direct likelihood is Low by design — it is scored on Impact because it is the *missing
  second layer*. Its true cost is realized only in combination with another defect, which is exactly
  why it must not be deferred indefinitely.

## Refuted / closed (zero residual risk — recorded so they are not re-scored)

| Item | Disposition |
|------|-------------|
| Slack Events webhook fail-open | Secret set in prod → 401. Latent only if a deploy loses it (add startup guard with F1). |
| CORS reflection | Not reflected. Closed. |
| Browser anon direct-read | Auth API calls, not anon table reads. Closed. |
| Slack-interactions HITL missing ws filter (FINDING 2) | LOW/latent; gated behind fail-closed HMAC with server-minted ids. Fix opportunistically with F2/F3. |
```