---
type: object
cluster: crm-core
universe: live
status: verified
entity: apps/api/app/models/deal_note.py
---

# DealNote

An append-only note on a deal (UI "Notes" on a deal); class `DealNote`, table `deal_notes`.

## Why this shape

Same append-only design as ContactNote — immutable rows, `Text` body, `created_at` only — so deal-context and velocity queries (weekly deal_notes counts) can replay the full commentary thread without worrying about edits.

## Shape

- PK `id`; `workspace_id` FK → workspaces (CASCADE); `deal_id` FK → deals (CASCADE, NOT NULL); `body` Text; `author` nullable; `created_at` only.

Citations: `apps/api/app/models/deal_note.py:20`, `:21`, `:24`, `:27`, `:28`, `:29`

## Connected to

- **owns:** nothing (leaf, append-only).
- **owned-by:** Deal via `deal_id` (CASCADE) and Workspace.
- **joins:** none (though ai.py joins it to Deal ad hoc for workspace-wide note sweeps, `apps/api/app/routers/ai.py:3335`).
- **looks-like-but-is-not:** `ContactNote` (contact_note.py) — identical shape keyed to `contact_id`.

## If you change this

- **Hits:** routers/deals.py (list/create notes, velocity/activity counts), routers/ai.py (very heavy reader — deal context/summary).
- **Does not hit:** ContactNote consumers, and no worker/service.

## Surfaces

| Surface | Role |
|---|---|
| routers/deals.py | reads / writes |
| routers/ai.py | reads (deal context/summaries) |

## See

- Source: `apps/api/app/models/deal_note.py`
