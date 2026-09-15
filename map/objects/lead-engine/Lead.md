---
type: object
cluster: lead-engine
universe: live
status: verified
entity: apps/api/app/models/lead.py
---

# Lead

The raw top-of-funnel prospect record (product word "Lead" == table `leads`), pre-CRM-contact.

## Why this shape

Central hub of the cluster: every other noun either produces leads (DiscoveryRun), groups them (LeadSegment/Member), or targets them (Campaign). Nullable `contact_id` (SET NULL) encodes the bot-to-human handoff — a lead lives independently until `promote_lead` mints a Contact and back-links it. `external_id` + workspace scoping is the dedup key import/discovery upserts collide on (index_elements=[workspace_id, external_id]).

## Shape

- `id` uuid PK; `workspace_id` FK→workspaces CASCADE (not null)
- `contact_id` FK→contacts SET NULL (nullable — pre-promotion leads have none)
- `name/email/phone/company/title` nullable strings
- `source` not null default "import" (import|manual|web|api|referral|event|discovery)
- `stage` not null default "new"; `score` int default 0; `score_detail` JSONB
- `owner_id` FK→users SET NULL; `custom_fields` JSONB; `external_id` string; `last_engaged_at`; created/updated

Citations: `apps/api/app/models/lead.py:11`, `:18`, `:26`, `:34`

## Connected to

- **owns:** the promotion path creates a Contact (+ optional Deal) FROM a lead (`routers/leads.py:516`,`:531`)
- **owned-by:** Workspace (CASCADE); optionally a User (owner_id)
- **joins:** LeadSegmentMember (M2M into LeadSegment); DiscoveryRun produces leads by side-effect (source='discovery')
- **looks-like-but-is-not:** Contact — a Lead is the raw un-curated prospect; Contact is the human-curated CRM record it promotes into. Different table.

## If you change this

- **Hits:** `routers/leads.py` (LeadResponse, funnel/import/export/promote), `routers/segments.py:189-205`, `workers/import_leads.py:118`, `workers/discovery.py:176`, `workers/campaign_enroll.py:55-82` (dynamic-filter resolution reads Lead.stage/source/score/custom_fields)
- **Does not hit:** DiscoveryRun/LeadSegment/Campaign own tables (no schema coupling; referenced by id or side-effect)

## Surfaces

| Surface | Role |
|---|---|
| routers/leads.py | reads / writes (CRUD, import, export, promote) |
| workers/import_leads.py, discovery.py | writes (bulk + discovered upsert) |
| routers/segments.py, workers/campaign_enroll.py | reads (membership + filter) |

## See

- Source: `apps/api/app/models/lead.py`
