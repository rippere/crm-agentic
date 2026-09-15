---
type: object
cluster: tenancy
universe: live
status: verified
entity: apps/api/app/models/user.py
---

# User

A workspace member identity (class `User`, table `users`), mapping a Supabase auth identity to a tenant.

## Why this shape

The bridge between external auth (Supabase JWT `sub` → `supabase_uid`) and internal tenancy: it holds the `workspace_id` that `get_current_user` resolves on every request, making the User row — not the JWT — the source of truth for which tenant a caller belongs to. `role` ("member"/"admin") layers coarse authz on top.

## Shape

- `id` UUID PK default uuid4
- `supabase_uid` UUID NOT NULL UNIQUE (the JWT `sub` claim; lookup key)
- `workspace_id` UUID FK→workspaces CASCADE, NULLABLE (a user can transiently have no workspace)
- `email` nullable; `role` NOT NULL default "member"; `created_at` tz NOT NULL server_default now()
- relationship to Workspace (`back_populates="users"`)

Citations: `apps/api/app/models/user.py:11-22`

## Connected to

- **owns:** nothing structurally, but the User's `workspace_id` scopes every read/write the user performs
- **owned-by:** Workspace (via `workspace_id` FK, CASCADE) — `user.py:16`
- **joins:** Workspace; indirectly the whole schema through the resolved workspace_id
- **looks-like-but-is-not:** not the Supabase auth user (that lives in GoTrue; this is the local mirror keyed by `supabase_uid`), and not an Agent (agents are workspace-owned bots, not identities)

## If you change this

- **Hits:** `supabase_uid` uniqueness + `workspace_id` are the core of `get_current_user` (`dependencies.py:18-107`), which auto-provisions on first hit and derives every downstream tenant scope. `role` drives `require_admin` (`dependencies.py:110-119`) and the invite gate (`routers/auth.py:191-193`). Enforcement point is `get_workspace_id` (`dependencies.py:122-131`). **Deliberate rule:** an existing user's `workspace_id` is NEVER overwritten from the JWT; new binding trusts ONLY server-only `app_metadata` (`routers/auth.py:32-44`, `100-103`) — the documented fix for a cross-tenant IDOR via forgeable `user_metadata`.
- **Does not hit:** Workspace's own columns; changing User alters who maps in, not the tenant row.

## Surfaces

| Surface | Role |
|---|---|
| POST /auth/verify | writes (first-login provisioning) |
| GET /me | reads (profile + role) |
| get_current_user / require_admin (dependency) | reads (every authed request) |
| POST /workspaces/{id}/invite | reads role; writes invitee binding via Supabase app_metadata |

## See

- Source: `apps/api/app/models/user.py`
