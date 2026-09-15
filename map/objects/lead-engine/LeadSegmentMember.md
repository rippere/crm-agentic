---
type: object
cluster: lead-engine
universe: live
status: verified
entity: apps/api/app/models/lead_segment_member.py
---

# LeadSegmentMember

The join row binding a Lead into a static LeadSegment (table `lead_segment_members`).

## Why this shape

Pure associative table for static segments only — dynamic segments never materialize members (they resolve by filter at enroll time). Carries its own `workspace_id` (redundant with both parents but keeps every query workspace-scoped without a second join) and `added_at` for provenance. All three FKs CASCADE so deleting a lead, segment, or workspace cleans up membership.

## Shape

- `id` uuid PK; `workspace_id` FK→workspaces CASCADE (not null)
- `segment_id` FK→lead_segments CASCADE (not null)
- `lead_id` FK→leads CASCADE (not null)
- `added_at` timestamptz server_default now() (no updated_at — insert-only)

Citations: `apps/api/app/models/lead_segment_member.py:11`, `:18`, `:21`, `:24`

## Connected to

- **owns:** nothing (leaf join row)
- **owned-by:** LeadSegment (CASCADE) and Lead (CASCADE); Workspace (CASCADE)
- **joins:** IS the M2M edge between Lead and LeadSegment
- **looks-like-but-is-not:** SequenceEnrollment — that tracks a lead's progress through a campaign's steps; this is static-list membership only, no state.

## If you change this

- **Hits:** `routers/segments.py:194` (member list join), `:261` (dedup query), add-members insert path; `workers/campaign_enroll.py:104` (static resolution); `routers/leads.py:32` (imported)
- **Does not hit:** dynamic segments (bypass this table); Campaign/DiscoveryRun

## Surfaces

| Surface | Role |
|---|---|
| routers/segments.py | reads / writes (list, add, dedup) |
| workers/campaign_enroll.py | reads (static segment → lead_ids) |

## See

- Source: `apps/api/app/models/lead_segment_member.py`
