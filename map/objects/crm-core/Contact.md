---
type: object
cluster: crm-core
universe: live
status: verified
entity: apps/api/app/models/contact.py
---

# Contact

The core person/account record (UI "Contacts"); class `Contact`, table `contacts`.

## Why this shape

It is the hub the whole CRM hangs off — it carries denormalized rollups (`ml_score`, `revenue`, `deal_count`, `last_activity`) and a 384-dim `embedding` so lists, scoring and semantic search read one row without joins.

## Shape

- PK `id` (UUID); `workspace_id` FK → workspaces (CASCADE); `status` default "lead"; `ml_score`/`semantic_tags` JSONB; `revenue` Numeric, `deal_count` Integer; `embedding` Vector(384), nullable; timestamps.

Citations: `apps/api/app/models/contact.py:16`, `:17`, `:23`, `:24`, `:29`

## Connected to

- **owns:** Deal (contact_id), Task (contact_id), Message, Project (contact_id), ContactNote (contact_id) — all point here.
- **owned-by:** Workspace via `workspace_id` → workspaces (`:17`, `:34`).
- **joins:** none (no association table); M2M-free.
- **looks-like-but-is-not:** `Lead` (models/lead.py) — the pre-qualification/discovery record, a different table; don't grab it for CRM contacts.

## If you change this

- **Hits:** routers/contacts.py, routers/search.py, routers/mcp_server.py, routers/deals.py, routers/ai.py; workers/embed_contacts.py, workers/score_contact.py, workers/enrich_contact.py, workers/ingest.py, workers/followup_sequences.py.
- **Does not hit:** Lead / lead-scoring path (leads.py, import_leads.py) — separate model.

## Surfaces

| Surface | Role |
|---|---|
| routers/contacts.py | reads / writes |
| routers/search.py, mcp_server.py, ai.py | reads |
| workers/embed_contacts.py, score_contact.py, enrich_contact.py | writes (rollups/embedding) |
| workers/ingest.py | writes (creates from inbound) |

## See

- Source: `apps/api/app/models/contact.py`
