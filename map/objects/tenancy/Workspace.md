---
type: object
cluster: tenancy
universe: live
status: verified
entity: apps/api/app/models/workspace.py
---

# Workspace

The tenant boundary of NovaCRM (product word "workspace" = class `Workspace`, table `workspaces`).

## Why this shape

Root of the multi-tenant model: the single object every other row hangs off via a `workspace_id` FK, so isolation is achieved by scoping all queries to one workspace. It carries only tenant identity (`name`, `slug`) and a `mode` toggle ("sales" default) selecting the operating profile — deliberately thin because its real weight is being the parent everything references.

## Shape

- `id` UUID PK, `default=uuid.uuid4` (server-generated — never from user input, a deliberate anti-IDOR choice)
- `name` String NOT NULL; `slug` String NOT NULL UNIQUE
- `mode` String NOT NULL default "sales"; `created_at` DateTime(tz) NOT NULL server_default now()
- ORM back-refs to users, contacts, deals, agents, connectors, messages, tasks

Citations: `apps/api/app/models/workspace.py:11-27`

## Connected to

- **owns:** parent of nearly every other model. Mechanism = each child table carries a `workspace_id` FK back to `workspaces.id`; the model declares seven `relationship(back_populates="workspace")` collections (`workspace.py:21-27`) but the real fan-out is ~25 tables filtering by workspace_id — do not enumerate, the FK column is the contract.
- **owned-by:** nothing (tenancy root)
- **joins:** User (its members), and via shared workspace_id every scoped entity
- **looks-like-but-is-not:** not a User/account and not a Supabase org — it is the local tenant row; the Supabase side only holds a `workspace_id` pointer in server-only `app_metadata`

## If you change this

- **Hits:** column rename/removal ripples through `WorkspaceResponse` (`routers/workspaces.py:16-22`) and create/update/get handlers (`workspaces.py:36-106`). **`workspace_id` is load-bearing across the whole schema**: the isolation contract is enforced at `get_workspace_id` (`dependencies.py:122-131`), which almost every router depends on; direct handlers also gate on `current_user.workspace_id != workspace_id` (`workspaces.py:42`, `:59`). Provisioning seeds `_DEFAULT_AGENTS` per new workspace (`routers/auth.py:18-26`, `140-148`; `dependencies.py:87-88`).
- **Does not hit:** JWT verification itself (`services/auth.py`) — that only produces the Supabase uid; workspace binding is a separate DB-side concern.

## Surfaces

| Surface | Role |
|---|---|
| POST /workspaces (onboarding) | writes (creates + binds current_user) |
| GET/PATCH /workspaces/{id} | reads / writes (self-scoped) |
| get_current_user auto-provision | writes (first-login / IDOR-safe fallback) |
| every scoped router via get_workspace_id | reads (isolation filter) |

## See

- Source: `apps/api/app/models/workspace.py`
