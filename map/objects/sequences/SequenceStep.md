---
type: object
cluster: sequences
universe: live
status: verified
entity: apps/api/app/models/sequence_step.py
---

# SequenceStep

One rung of a sequence (class `SequenceStep`, table `sequence_steps`) — the per-step channel, delay, and message template.

## Why this shape

Steps are a separate row (not a JSON array on Sequence) because the sender fetches exactly one step by `(sequence_id, step_order)` per tick and the router edits/appends/deletes them individually, recomputing `Sequence.step_count`. `delay_hours` encodes the cadence gap the sender adds to `next_run_at`. `requires_approval` (default True) is the HITL gate — the sender parks the enrollment as `waiting` instead of sending; `ai_generate` flips the body to Claude-drafted at send time.

## Shape

- `id` uuid PK; `workspace_id` FK→workspaces CASCADE (not null)
- `sequence_id` FK→sequences CASCADE (not null)
- `step_order` int not null (0-based, normalized by router)
- `channel` not null default "email"; `delay_hours` int not null default 0
- `subject` nullable; `body_template` Text not null default ""
- `requires_approval` Bool not null default True; `ai_generate` Bool not null default False; created/updated

Citations: `apps/api/app/models/sequence_step.py:11-33`

## Connected to

- **owns:** nothing
- **owned-by:** Sequence (CASCADE); Workspace
- **joins:** matched at runtime to a SequenceEnrollment by `step_order == enrollment.current_step`
- **looks-like-but-is-not:** not the sent artifact — the send is recorded as an EngagementEvent (`workers/sequence_sender.py:362,388`); `body_template` is a template, not the rendered body

## If you change this

- **Hits:** `routers/sequences.py` (SequenceStepResponse, `_load_ordered_steps` :213-224, PUT replace :395, append :460, delete :553); `workers/sequence_sender.py:262-270` (`_load_step`); `routers/outreach.py:130-173` (`_draft_for_step`/`_ai_draft_body` read subject/body_template/ai_generate/requires_approval; pending-draft scan :272-275)
- **Does not hit:** `workers/campaign_enroll.py` (enrolls leads, never reads steps); `workers/followup_sequences.py`

## Surfaces

| Surface | Role |
|---|---|
| routers/sequences.py | reads / writes (step CRUD, order normalization) |
| routers/outreach.py | reads (draft rendering + approval flag) |
| workers/sequence_sender.py | reads (current step per tick) |

## See

- Source: `apps/api/app/models/sequence_step.py`
