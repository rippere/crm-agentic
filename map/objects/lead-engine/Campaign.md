---
type: object
cluster: lead-engine
universe: live
status: verified
entity: apps/api/app/models/campaign.py
---

# Campaign

An outbound send targeting a segment via a sequence (table `campaigns`); the WHAT/WHEN of outreach.

## Why this shape

Ties the two upstream nouns together: `segment_id`→LeadSegment (audience) and `sequence_id`→sequences (message flow), both SET NULL so a deleted segment/sequence doesn't orphan-delete campaign history. `status` (draft→scheduled→…) plus scheduled/started/completed timestamps drive the lifecycle; the schedule endpoint enqueues `enroll_campaign`, which resolves the segment's leads and writes SequenceEnrollment rows. `stats`/`settings` JSONB hold per-campaign counters and config.

## Shape

- `id` uuid PK; `workspace_id` FK→workspaces CASCADE (not null)
- `segment_id` FK→lead_segments SET NULL (nullable); `sequence_id` FK→sequences SET NULL (nullable)
- `name` not null; `status` default "draft"; `channel` default "email"
- `scheduled_at`/`started_at`/`completed_at` nullable; `stats`/`settings` JSONB; created/updated

Citations: `apps/api/app/models/campaign.py:11`, `:18`, `:21`, `:25`

## Connected to

- **owns:** SequenceEnrollment rows keyed by campaign_id (created by enroll worker; listed campaigns.py:444)
- **owned-by:** Workspace (CASCADE)
- **joins:** LeadSegment (segment_id) and Sequence (sequence_id); reaches Leads through the segment at enroll time
- **looks-like-but-is-not:** Sequence — a Sequence is the reusable step template; a Campaign is one scheduled execution of it against a specific segment.

## If you change this

- **Hits:** `routers/campaigns.py` (CampaignResponse, CRUD, `_hydrate_campaign_from_row`:103, schedule route:321 → enroll_campaign.delay:351), `workers/campaign_enroll.py:113,125`
- **Does not hit:** Lead/LeadSegmentMember schemas; DiscoveryRun

## Surfaces

| Surface | Role |
|---|---|
| routers/campaigns.py | reads / writes (CRUD, schedule, enrollments list) |
| workers/campaign_enroll.py | reads (campaign → segment → enrollments) |

## See

- Source: `apps/api/app/models/campaign.py`
