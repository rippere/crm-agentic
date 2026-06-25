# Phase 2 — Evidence: Postgres RLS is inert at runtime (no DB-level tenant isolation)

**Verdict: PROVEN**
**Date:** 2026-06-03
**Target DB:** Supabase project `ilfibxflnelssllgszex` (aws-1-us-west-2 pooler, port 5432, db `postgres`)
**Connection role used by the API (`api` service `DATABASE_URL`):** `postgres` (table OWNER, `rolbypassrls = t`)

This is the product owner's own infrastructure; authorized read-only validation. No data was modified.

---

## 1. How DATABASE_URL was obtained

```
cd /mnt/external/Projects/crm-agentic && \
  /home/rippere/.local/share/mise/installs/node/25.2.1/bin/railway variables --service api --json \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('DATABASE_URL=' + d.get('DATABASE_URL','<MISSING>'))"
```
Output:
```
DATABASE_URL=postgresql+asyncpg://postgres.ilfibxflnelssllgszex:REDACTED-ROTATE-ME@aws-1-us-west-2.pooler.supabase.com:5432/postgres
```
Connection string used for psql (stripped `+asyncpg`):
```
postgresql://postgres.ilfibxflnelssllgszex:REDACTED-ROTATE-ME@aws-1-us-west-2.pooler.supabase.com:5432/postgres
```
psql client: `psql (PostgreSQL) 18.4`.

Note: the username `postgres.ilfibxflnelssllgszex` is the Supabase pooler tenant-routing format; the effective DB role is `postgres` (confirmed below). The API authenticates to Postgres as this single shared role for ALL tenants. No per-request DB role switching and no per-request JWT/GUC is set.

---

## 2. Connection role + JWT/tenant context

Command:
```
psql "<URL>" -A -F '|' \
  -c "SELECT current_user, session_user;" \
  -c "SELECT current_setting('request.jwt.claims', true);" \
  -c "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user;"
```
Observed output:
```
current_user|session_user
postgres|postgres
(1 row)

jwt_claims
<empty / NULL>
(1 row)

rolname|rolsuper|rolbypassrls
postgres|f|t
(1 row)
```

Interpretation:
- `current_user = session_user = postgres`. The API talks to the DB as the **`postgres` role**.
- `rolbypassrls = t` -> this role **bypasses ALL row-level security policies** unconditionally.
- `request.jwt.claims` is **empty** at runtime for this connection -> no tenant identity is injected at the DB layer. Every RLS policy below relies on `auth.uid()` which reads this claim; with it empty, `auth.uid()` returns NULL.

---

## 3. RLS flags on target tables

Command:
```
psql "<URL>" -A -F '|' -c "SELECT n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE c.relname IN ('contacts','deals','tasks','call_summaries','messages') AND c.relkind='r'
  ORDER BY c.relname;"
```
Observed output:
```
schema|relname|rls_enabled|rls_forced
public|call_summaries|t|f
public|contacts|t|f
public|deals|t|f
public|messages|t|f
public|tasks|t|f
(5 rows)
```

Interpretation: `relrowsecurity = t` (RLS enabled) but `relforcerowsecurity = f` (NOT forced) on every table. **For the table-owner role, non-forced RLS is not applied.** Combined with `rolbypassrls = t`, the policies are skipped on two independent grounds.

---

## 4. Full policy list (pg_policies)

Command:
```
psql "<URL>" -A -F '|' -c "SELECT schemaname, tablename, policyname, cmd, roles::text
  FROM pg_policies ORDER BY tablename, policyname;"
```
Observed output:
```
schemaname|tablename|policyname|cmd|roles
public|activity_events|activity_events_policy|ALL|{public}
public|agents|agents_policy|ALL|{public}
public|clarity_scores|clarity_scores_policy|ALL|{public}
public|connectors|connectors_policy|ALL|{public}
public|contacts|contacts_policy|ALL|{public}
public|deals|deals_policy|ALL|{public}
public|messages|messages_policy|ALL|{public}
public|metric_templates|metric_templates_policy|ALL|{public}
public|projects|projects_policy|ALL|{public}
public|tasks|tasks_policy|ALL|{public}
public|users|users_insert|INSERT|{authenticated}
public|users|users_select|SELECT|{authenticated}
public|workspaces|workspaces_insert|INSERT|{authenticated}
public|workspaces|workspaces_select|SELECT|{authenticated}
(14 rows)
```

**`call_summaries` is NOT in this list -> it has ZERO policies** (confirmed separately below). RLS is enabled on `call_summaries` with no policy, so a constrained role would be denied-all — but the `postgres` owner/BYPASSRLS role reads it freely.

`call_summaries` policy count:
```
psql "<URL>" -c "SELECT count(*) FROM pg_policies WHERE tablename='call_summaries';"
-> policy_count_for_call_summaries = 0
```

The policies that DO exist for the tenant tables are scoped to the `{public}` role and reference `auth.uid()`. Example (contacts) USING expression:
```
psql "<URL>" -c "SELECT polname, pg_get_expr(polqual, polrelid) FROM pg_policy WHERE polrelid='public.contacts'::regclass;"
-> contacts_policy | (workspace_id = ( SELECT users.workspace_id FROM users WHERE (users.supabase_uid = auth.uid())))
```
This policy WOULD isolate tenants correctly IF evaluated under a non-owner role carrying a real JWT. It is not — the API uses the owner role with no JWT, so the policy never runs.

---

## 5. DECISIVE TEST — unfiltered multi-tenant SELECT as the API role

Command:
```
psql "<URL>" -A -F '|' -c "SELECT count(*) AS total_rows, count(distinct workspace_id) AS distinct_workspaces FROM contacts;"
```
Observed output:
```
total_rows|distinct_workspaces
7|2
(1 row)
```

Per-table (deals/tasks/messages/call_summaries):
```
tbl            | total | distinct_workspaces
deals          |   8   | 2
tasks          |   0   | 0
messages       |  200  | 1
call_summaries |   0   | 0
```

Breakdown of the workspaces visible in `contacts` with NO filter:
```
psql "<URL>" -c "SELECT workspace_id, count(*) FROM contacts GROUP BY workspace_id ORDER BY workspace_id;"
workspace_id                         | count
583e7c4e-902d-4748-a79c-ddada5e43a89 |   6
9dbfbe4d-2e0d-4fca-944c-6960bf6b586d |   1
```

These are confirmed real, distinct tenant workspaces:
```
psql "<URL>" -c "SELECT id, name FROM workspaces ORDER BY id;"
id                                   | name
583e7c4e-902d-4748-a79c-ddada5e43a89 | Demo Workspace
9dbfbe4d-2e0d-4fca-944c-6960bf6b586d | CRM
cd7196e7-1442-4408-b1cb-61bc4bb5f858 | test
```

**Result: a single unfiltered query, run as the exact role the API uses, returns rows spanning 2 distinct real workspaces (`Demo Workspace` and `CRM`) for both `contacts` and `deals`.** There is no DB-level tenant isolation. If the application layer ever omits a `WHERE workspace_id = ...` clause (or an attacker reaches a code path that does), every tenant's data is returned.

---

## 6. Conclusion

**PROVEN — Postgres RLS is inert at runtime.**

- API DB role = `postgres`, `rolbypassrls = t` (and table-owner).
- RLS enabled but NOT forced (`relforcerowsecurity = f`) on contacts/deals/tasks/messages/call_summaries.
- `request.jwt.claims` empty at runtime; `auth.uid()` is NULL -> all `{public}` policies are non-functional for this connection.
- `call_summaries` has **0 policies** (RLS enabled, no policy) — relies 100% on app-layer filtering.
- Decisive unfiltered SELECT returned data from **2 distinct workspaces** (7 contacts / 2 ws; 8 deals / 2 ws), demonstrating zero DB-enforced isolation.

Tenant isolation in NovaCRM is therefore entirely dependent on application-layer `WHERE workspace_id` filtering. The database provides no backstop. Any missing/buggy filter, SQL-injection sink, or service-role-key exposure = full cross-tenant data exposure.

### Remediation
1. Stop connecting the API as `postgres`. Create a dedicated non-superuser, NON-`BYPASSRLS` login role (e.g. `app_authenticated`) that is NOT the table owner, and use it in the API `DATABASE_URL`.
2. `ALTER TABLE ... FORCE ROW LEVEL SECURITY;` on all tenant tables (defends even against the owner).
3. Inject tenant context per request: set `request.jwt.claims` / `SET LOCAL role` (or use Supabase PostgREST/`authenticated` role semantics) so `auth.uid()` resolves and policies evaluate.
4. Add a policy to `call_summaries` (currently RLS-enabled with no policy = deny-all for constrained roles, but it has no protection today because the owner role bypasses it).
5. Keep app-layer `workspace_id` filters as defense-in-depth, but do not rely on them as the sole control.
