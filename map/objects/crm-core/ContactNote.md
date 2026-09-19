---
type: object
cluster: crm-core
universe: live
status: verified
entity: apps/api/app/models/contact_note.py
---

# ContactNote

An append-only note on a contact (UI "Notes" on a contact); class `ContactNote`, table `contact_notes`.

## Why this shape

Deliberately immutable/append-only — each note is a new row (no update/delete), forming a chronological thread; it has no `updated_at` and a `Text` body, so AI context-builders can read the full note history for a contact ordered by `created_at`.

## Shape

- PK `id`; `workspace_id` FK → workspaces (CASCADE); `contact_id` FK → contacts (CASCADE, NOT NULL); `body` Text; `author` nullable; `created_at` only (no updated_at).

Citations: `apps/api/app/models/contact_note.py:20`, `:21`, `:24`, `:27`, `:28`, `:29`

## Connected to

- **owns:** nothing (leaf, append-only).
- **owned-by:** Contact via `contact_id` (CASCADE — deleted with the contact) and Workspace.
- **joins:** none.
- **looks-like-but-is-not:** `DealNote` (deal_note.py) — the identical-shaped sibling keyed to `deal_id`; grabbing the wrong one mis-attaches the note.

## If you change this

- **Hits:** routers/contacts.py (list/create notes, engagement rollups), routers/ai.py (heavy reader — context, cadence, engagement scoring).
- **Does not hit:** DealNote consumers, and no worker/service.

## Surfaces

| Surface | Role |
|---|---|
| routers/contacts.py | reads / writes |
| routers/ai.py | reads (context + engagement/cadence signals) |

## See

- Source: `apps/api/app/models/contact_note.py`
