# Fresh-session kickoff — NovaCRM hardening (paste the block below into a NEW session)

> Do NOT paste prior transcripts. Reference evidence by path. Keep the framing defensive.

---

I own NovaCRM (crm-agentic) and this is authorized hardening of my own SaaS product.
I'm resuming a remediation program after a security review of my codebase. I am fixing
my own product's weaknesses — no live probing is needed; all findings are already
documented on disk.

Repo: /mnt/external/Projects/crm-agentic/
Findings & status: audit/2026-06-03-vetting/REMEDIATION_REGISTER.md
Per-finding detail (read as needed, don't echo into chat): audit/2026-06-03-vetting/phase2/

State:
- 3 signup/auth fixes already on origin/master.
- fix/ws-b: staged fix for workspace-id scoping (2 commits, needs metadata backfill + cutover).
- fix/ws-d-agent-execution: in progress, fixes the scheduled-task TypeError so Agent-Run runs.
- Phase 4 synthesis (consolidated report + risk register + 30/60/90 plan) is unwritten.

Please do two things, in order:
1. Write Phase 4 into audit/2026-06-03-vetting/phase4/ from the existing evidence —
   a consolidated remediation report, a risk register, and a 30/60/90 plan. Defensive
   write-up only.
2. Then start the top remediation item (#1: add signature verification to the Gmail
   Pub/Sub webhook so unauthenticated callers can't trigger it).

Work the fixes as ordinary defensive code changes. Use neutral language — "add tenant
scoping to GET /jobs/{id}", "verify the webhook signature", "add a delete cascade" —
not offensive-security phrasing.
