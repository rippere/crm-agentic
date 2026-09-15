# Object index — one line per noun

Regenerated, not hand-drifted. `universe` in parens; ghosts marked.

## crm-core
- **Contact** (live) — core person/account; the hub everything hangs off. → `crm-core/Contact.md`
- **Deal** (live) — pipeline opportunity; stage/value/health/win-prob. → `crm-core/Deal.md`
- **Task** (live) — polymorphic to-do (message/contact/deal/project FKs). → `crm-core/Task.md`
- **Project** (live) — thin workstream grouping Tasks. → `crm-core/Project.md`
- **Commitment** (live) — kept/broken accountability ledger row. → `crm-core/Commitment.md`
- **ContactNote** (live) — append-only note on a contact. → `crm-core/ContactNote.md`
- **DealNote** (live) — append-only note on a deal. → `crm-core/DealNote.md`
- **ActivityEvent** (live) — human-readable audit/activity feed. → `crm-core/ActivityEvent.md`

## comms
- **Message** (live) — ingested email/Slack message; comms substrate. → `comms/Message.md`
- **CallSummary** (live) — Whisper transcript + Claude summary of a call. → `comms/CallSummary.md`
- **Connector** (live) — encrypted OAuth link to Gmail/Slack. → `comms/Connector.md`
- **WebhookLog** (live) — inbound-webhook audit receipt. → `comms/WebhookLog.md`
- **EngagementEvent** (live) — append-only scoring signal (open/click/reply/send). → `comms/EngagementEvent.md`

## lead-engine
- **Lead** (live) — raw pre-CRM prospect; cluster hub. → `lead-engine/Lead.md`
- **LeadSegment** (live) — static list or dynamic-filter audience. → `lead-engine/LeadSegment.md`
- **LeadSegmentMember** (live) — Lead↔Segment join (static only). → `lead-engine/LeadSegmentMember.md`
- **DiscoveryRun** (live) — market-discovery job bookkeeping. → `lead-engine/DiscoveryRun.md`
- **Campaign** (live) — scheduled send: segment × sequence. → `lead-engine/Campaign.md`

## sequences
- **Sequence** (live) — reusable multi-step outreach template. → `sequences/Sequence.md`
- **SequenceStep** (live) — one rung: channel, delay, template, approval gate. → `sequences/SequenceStep.md`
- **SequenceEnrollment** (live) — mutable cursor of a lead through a sequence. → `sequences/SequenceEnrollment.md`

## intelligence
- **ClarityScore** (live) — 1:1 per-message AI clarity rating. → `intelligence/ClarityScore.md`
- **KpiSnapshot** (live) — dated workspace metric time-series. → `intelligence/KpiSnapshot.md`
- **Agent** (live) — AI-agent config + cached dashboard state. → `intelligence/Agent.md`
- **DealHealthHistory** (GHOST) — read endpoints exist, zero writers; live score is Deal.health_score. → `intelligence/DealHealthHistory.md`
- **MetricTemplate** (GHOST) — fully unwired, registry-only. → `intelligence/MetricTemplate.md`

## tenancy
- **Workspace** (live) — tenant root; parent of ~25 tables via workspace_id. → `tenancy/Workspace.md`
- **User** (live) — Supabase identity ↔ workspace binding. → `tenancy/User.md`
