---
type: object
cluster: intelligence
universe: live
status: verified
entity: apps/api/app/models/clarity_score.py
---

# ClarityScore

The per-message AI communication-clarity rating (class `ClarityScore`, table `clarity_scores`).

## Why this shape

A 1:1 sidecar row keyed by `message_id` (unique, nullable) rather than a column on `messages`, so an expensive Claude scoring pass attaches (or is absent) per message without bloating the hot messages row, and carries its own `rationale` and `model_used` provenance. Nullable `score`/`message_id` let a row exist before/without a resolved score.

## Shape

- `id` UUID PK; `workspace_id` FK→workspaces CASCADE (not null); `message_id` FK→messages CASCADE (nullable, UNIQUE — enforces 1:1); `score` int nullable; `rationale` nullable; `model_used` not null default "claude-sonnet-4-6"; `created_at` tz server_default now()
- 1:1 relationship `message` back_populates `Message.clarity_score` (uselist=False)

Citations: `apps/api/app/models/clarity_score.py:11-23`

## Connected to

- **owns:** nothing.
- **owned-by:** Workspace, Message (unique 1:1).
- **joins:** Message — outer-joined for score display across `routers/ai.py` (:725, :2291, :6752) and eager-loaded `routers/messages.py:82`.
- **looks-like-but-is-not:** not a deal/lead score; scores message text quality only. Distinct from `deal_health` and lead engagement scores.

## If you change this

- **Hits:** writers — `workers/ingest.py:583,722`, `routers/messages.py:97`; readers — `routers/ai.py` (:725, :1516, :1669, :2291, :4286, :6752), `routers/messages.py` (`ClarityScoreNested`); logic in `services/clarity.py`.
- **Does not hit:** deal health, KPI, agents, metric templates.

## Surfaces

| Surface | Role |
|---|---|
| workers/ingest.py | writes (on message ingest) |
| routers/messages.py | writes + reads (nested in response) |
| routers/ai.py | reads (joins score into digests) |
| services/clarity.py | computes score via Claude |

## See

- Source: `apps/api/app/models/clarity_score.py`
