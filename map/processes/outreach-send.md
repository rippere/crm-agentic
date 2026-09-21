---
type: process
status: verified
consumes: [Campaign, LeadSegment, Lead, Sequence, SequenceStep, SequenceEnrollment, EngagementEvent, Connector]
produces: [SequenceEnrollment, EngagementEvent, sent email/SMS, ActivityEvent]
---

# outreach-send

Launching a campaign enrolls its segment's leads into a sequence, and a beat-driven ticker walks each enrollment step by step, gating human-approval steps and sending the rest.

## Input → Movement → Output

`POST /campaigns/{id}/launch` flips the campaign active and enqueues `enroll_campaign`, which resolves the segment (static join or live dynamic filter) and inserts one `sequence_enrollment` per lead (ON CONFLICT DO NOTHING). Every 5 minutes `tick_sequences_all` fans out per workspace to `tick_sequences`, which selects due enrollments whose parent campaign is active, loads the current SequenceStep, and either completes/stops it, parks a pending Claude/template draft for approval (`status='waiting'`, a 'queued' EngagementEvent), or sends via the guarded Gmail/SMS boundary (a 'sent' EngagementEvent), advancing `current_step` and `next_run_at`.

## Why this shape

The sender is a beat worker, not a request handler, because drips must fire on their own delayed schedule (`next_run_at = now + delay_hours`) long after any HTTP call ended, and every external send sits behind a patchable guarded boundary so unit tests run with no credentials/network (`workers/sequence_sender.py:34-36`, `_deliver:163`). The HITL gate parks a draft as `waiting` and detects approval structurally: an 'approved' EngagementEvent newer than `last_sent_at` (`sequence_sender.py:286-309`), written by `POST /outreach/{id}/approve`. Enrollment is a separate task from ticking because segment resolution over a large leads table is unbounded.

## Steps

1. Launch enqueues enroll — `routers/campaigns.py:348-353`.
2. enroll_campaign resolves segment (static/dynamic) + inserts enrollments — `workers/campaign_enroll.py:87-176`.
3. Beat fan-out `tick_sequences_all` → per-workspace `tick_sequences` — `workers/sequence_sender.py:468-478`.
4. Select due enrollments (active/waiting, next_run_at≤now, campaign active) — `sequence_sender.py:228-244`.
5. stop_on_reply / quiet-hours / walk-off-end — `sequence_sender.py:332-351`.
6. HITL gate: park pending draft as 'waiting' + 'queued' event — `sequence_sender.py:355-381`.
7. Send via guarded Gmail/SMS boundary, write 'sent' event, advance step, re-score lead — `sequence_sender.py:383-425`.
8. Approve/reject flip enrollment + write approved event — `routers/outreach.py:362-479`; pending queue `outreach.py:239-304`.
9. followup_sequences (separate HITL track): stale-deal Slack Block-Kit approval — `workers/followup_sequences.py:195` (`check_stale_deals_hitl`).

## Trigger

- `enroll_campaign` — API-invoked on launch (`campaigns.py:351`).
- `tick_sequences_all` — beat "tick-sequences" `crontab(minute="*/5")` (`celery_app.py:52-58`).
- `check_stale_deals_hitl` — beat "daily-hitl-followup" `crontab(hour=9, minute=0)` (`celery_app.py:42-46`).

## If you change this

- **Hits:** `services/gmail_client.py` (`send_message`, shared with followup_sequences); `services/outreach_stats.py` (reply-rate from thread_ids); engagement_score (each send enqueues a re-score, `sequence_sender.py:421`); Campaign/Sequence/SequenceStep/SequenceEnrollment/EngagementEvent/LeadSegment models; `routers/outreach.py` + `sequences.py`; the engagement webhook `outreach.py:557` drives stop_on_reply.
- **Does not hit:** auth, transcribe, discovery (though it consumes discovery-sourced leads).

## Surfaces

| Surface | Role |
|---|---|
| `/campaigns/{id}/launch` | kick off enrollment |
| Celery beat (every 5 min) | drive the send ticker |
| `/outreach/pending` + approve/reject | human HITL gate |
| Gmail connector | actual delivery channel |

## See

- Objects: [[Campaign]], [[LeadSegment]], [[Sequence]], [[SequenceStep]], [[SequenceEnrollment]], [[EngagementEvent]]
- Source: `apps/api/app/workers/sequence_sender.py`, `apps/api/app/workers/campaign_enroll.py`
