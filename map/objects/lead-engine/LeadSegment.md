---
type: object
cluster: lead-engine
universe: live
status: verified
entity: apps/api/app/models/lead_segment.py
---

# LeadSegment

A named, workspace-scoped grouping of leads (product word "Segment" == table `lead_segments`), either a manual static list or a saved dynamic filter.

## Why this shape

`kind` ("static" vs default — non-"static" treated as dynamic) forks resolution: static segments read the LeadSegmentMember join; dynamic segments store a `filter` JSONB that `campaign_enroll._dynamic_filter_conditions` compiles into a live WHERE over Lead columns. `member_count` is a denormalized cache for list display. This is the reusable audience a Campaign points at.

## Shape

- `id` uuid PK; `workspace_id` FK→workspaces CASCADE (not null)
- `name` not null; `description` Text nullable
- `kind` not null default "static"; `filter` JSONB (dynamic query spec)
- `member_count` int default 0 (denormalized); created/updated

Citations: `apps/api/app/models/lead_segment.py:11`, `:20`, `:21`, `:22`

## Connected to

- **owns:** LeadSegmentMember rows (CASCADE on delete)
- **owned-by:** Workspace (CASCADE)
- **joins:** referenced by Campaign.segment_id (SET NULL); resolves to Leads via member join or dynamic filter
- **looks-like-but-is-not:** Campaign — a Segment is a WHO (audience); a Campaign is a WHAT/WHEN (the send). Segment is reusable across campaigns.

## If you change this

- **Hits:** `routers/segments.py` (SegmentResponse, list/create, add-members static-only guard :247), `workers/campaign_enroll.py:100-108` (static vs dynamic branch), `models/campaign.py:18` (FK)
- **Does not hit:** Lead table schema; DiscoveryRun

## Surfaces

| Surface | Role |
|---|---|
| routers/segments.py | reads / writes (CRUD + membership) |
| workers/campaign_enroll.py | reads (kind/filter to resolve audience) |
| routers/campaigns.py | references (segment_id) |

## See

- Source: `apps/api/app/models/lead_segment.py`
