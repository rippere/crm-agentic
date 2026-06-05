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
| **F1** | Gmail Pub/Sub webhook fails open | **High** — secret absent in prod now; route unauthenticated; email addresses discoverable | **Med** — forced-sync / ingest-trigger amplification; resource/cost abuse; no data read | **Sev-1** | Know/guess a connected mailbox address; POST a Pub/Sub-shaped body | None (fail-open is active) |
| **F2** | Workspace rebind via client-writable `user_metadata` | **Med** — needs an account (open signup) + a known/leaked target `workspace_id` (UUID) | **High** — full read+write of victim tenant as admin | **Sev-1** | Sign up; obtain target ws UUID (leaks in API responses / invites / onboarding); self-write metadata | 403 guard works *until* the rebind; fix staged on `fix/ws-b` |
| **F3** | DB RLS inert (no enforced isolation backstop) | **Low (direct)** — not directly reachable; it is the *absence* of a backstop | **High** — converts any app-layer miss / injection / key-leak into full cross-tenant exposure | **Sev-2** | Any other defect (F2/F4-class) or a service-key exposure to be reachable | App-layer `WHERE workspace_id` filters (sole control) |
| **F4** | `GET /jobs/{id}` unscoped job-result read | **Med** — authenticated; needs a foreign job_id (UUIDv4, not enumerable, but leaks via logs/referrers/screenshots) | **Med** — cross-tenant disclosure of a single job result payload (scores, ingest output, transcripts) | **Sev-2** | Valid account + knowledge/leakage of a foreign job_id | Auth gate (401 without JWT); UUID unguessability (not a real control) |
| **F5** | Rate limiter one global bucket; no per-tenant spend cap | **Med** — any authenticated tenant; reprocess endpoint un-limited | **Med** — cross-tenant route throttling + unbounded model spend + 2-slot worker starvation | **Sev-3** | Valid account; hammer reprocess / AI endpoints | Tiny per-route limits (shared bucket); none on reprocess |
| **F6** | Celery beat scheduled jobs crash (scheduled agents inert) | **High** — fires on **every** nightly schedule | **Med** — availability of the headline automation: no deal-health scoring, no proactive follow-ups; silent (deals pinned at 100) | **Sev-2** | None — it is already failing nightly | Manual admin-triggered runs still work; fix in progress (`fix/ws-d-agent-execution`) |
| **F7** | Contact deletion orphans linked PII | **High** — every contact deletion; default behavior | **Med** — residual PII (emails, bodies, transcripts) after a "successful" deletion; GDPR right-to-erasure failure | **Sev-2** | Delete any contact | None — SET NULL is the default path |
| **CLAIM** | Unsubstantiated landing claims (SOC2 / uptime / GDPR / 94.7% / model lineup) | **High** — public; any buyer, regulator, or investor reads them | **High** — FTC §5 deception exposure (no breach/intent needed); enterprise-procurement disqualification; investor-diligence credibility | **Sev-1** | None — already public | None — copy is live as written |

---

## Risk-band rationale

- **Sev-1 (act this week): F1, F2, CLAIM.** F1 is the only zero-credential live-reachable defect.
  F2 is full tenant takeover with a staged fix that just needs the backfill/cutover finished. CLAIM
  is public, high-liability, and cheap — no engineering, just copy.
- **Sev-2 (act in 30 days): F3, F4, F6, F7.** Tenant-isolation backstop + the proven app-layer miss
  it backstops (F3/F4 land together), the inert scheduled automation (F6, already in progress), and
  the erasure defect that also fixes the GDPR claim's substance (F7).
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