---
type: object
cluster: crm-core
universe: live
status: verified
entity: apps/api/app/models/commitment.py
---

# Commitment

An accountability record — something declared and later scored kept/broken (UI "Commitments"); class `Commitment`, table `commitments`.

## Why this shape

It is not a to-do but a promise-ledger row: `declared_at`, `due_date`, `status` (open/kept/broken/dropped) and `evidence`/`scored_at` support the weekly kept-vs-broken retro stats; `external_id` (vault rel_path+line) makes session-record harvest idempotent.

## Shape

- PK `id`; `workspace_id` FK → workspaces (CASCADE); `external_id` for harvest idempotency; `title` NOT NULL; `kind` default "auto"; `declared_at` NOT NULL; `due_date` Date; `status` default "open"; `evidence`, `scored_at` nullable.

Citations: `apps/api/app/models/commitment.py:15`, `:16`, `:18`, `:19`, `:21`, `:23`, `:24`, `:25`

## Connected to

- **owns:** nothing.
- **owned-by:** Workspace via `workspace_id` only — notably NO contact_id/deal_id FK (stands alone).
- **joins:** none.
- **looks-like-but-is-not:** `Task` (task.py) — the assignable to-do with entity FKs; Commitment has none of those and is scored, not assigned.

## If you change this

- **Hits:** routers/commitments.py (full CRUD, by-external upsert, weekly `/commitments/stats`).
- **Does not hit:** any worker or service — no background writer touches it; router-fed only (harvested externally via the upsert endpoint).

## Surfaces

| Surface | Role |
|---|---|
| routers/commitments.py | reads / writes |

## See

- Source: `apps/api/app/models/commitment.py`
