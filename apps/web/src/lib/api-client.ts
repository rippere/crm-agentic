import { demoMessages, demoTasks, demoConnectors, demoDeals, demoContacts } from './demo-data'
import type { KpiSnapshot, Commitment, CommitmentWeekStats } from './types'

// ─── Contact-aware demo stubs ─────────────────────────────────────────────────
const DEMO_CONTACT_BRIEFS: Record<string, { contact_name: string; brief: string }> = {
  'c-001': {
    contact_name: 'Sarah Chen',
    brief: `**Who they are**\nSarah Chen is VP of Engineering at TechCorp Solutions — a technical buyer with 8+ years at the company and the internal champion for the platform expansion deal. She drives adoption and owns the evaluation process.\n\n**Current deal status & risks**\nThe TechCorp Platform Expansion deal ($145K, Negotiation) is healthy at 78. Legal review completed last week; team is finalizing SLA uptime terms before sign-off. Close date is May 15.\n\n**Conversation highlights**\n- 3 meetings in the last 30 days, strong engagement\n- Opened 8 of your last 10 emails\n- Last thread: SLA uptime guarantee language\n\n**Recommended talking points**\n- Confirm the SLA language satisfies their internal compliance bar\n- Offer a 30-day post-launch success review as a trust signal\n- Ask if legal needs any additional documentation before May 15\n\n**Watch-out signals**\n- No new blockers flagged, but confirm champion has board sponsorship before assuming a clean close`,
  },
  'c-002': {
    contact_name: 'Marcus Rivera',
    brief: `**Who they are**\nMarcus Rivera is Chief Revenue Officer at Global Finance Inc. — a decision-maker with direct budget authority for a $250K enterprise suite deal. He requested custom pricing and has confirmed executive sponsorship internally.\n\n**Current deal status & risks**\nThe Global Finance Enterprise Suite deal ($250K, Proposal) has a health score of 35 — stalled for 21 days since the custom proposal was sent. Board sign-off is the stated blocker, but radio silence this long is a churn signal.\n\n**Conversation highlights**\n- Demo was well-received; Marcus requested pricing within 24h\n- Last touchpoint: custom proposal sent 3 weeks ago\n- No reply to 2 follow-up emails\n\n**Recommended talking points**\n- Acknowledge the board timeline and offer to provide an executive summary they can use internally\n- Reference a comparable win (financial services, $200K+) to de-risk the committee decision\n- Propose a 60-day pilot with an exit clause to lower the perceived commitment risk\n\n**Watch-out signals**\n- 21-day silence is the single biggest risk — this meeting is a re-engagement call, not a progress call\n- If board approval is 4+ weeks away, negotiate a LOI to hold pipeline position`,
  },
  'c-003': {
    contact_name: 'Priya Nair',
    brief: `**Who they are**\nPriya Nair is CEO & Co-Founder of StartupBase — a growth-stage founder evaluating the platform for her 40-person team. She's highly self-directed and visited the pricing page 4 times without converting.\n\n**Current deal status & risks**\nNo active deal yet — Priya is a warm lead (score 62). Downloaded the whitepaper, attended the webinar, clear buying intent. The blocker is likely pricing sensitivity or uncertainty about ROI for a startup-stage team.\n\n**Conversation highlights**\n- Attended the Q1 product webinar, asked about API integrations\n- Downloaded the Enterprise whitepaper (startup, not startup tier)\n- 4 pricing page visits in 30 days\n\n**Recommended talking points**\n- Lead with the startup tier and growth path — she's evaluating at enterprise price points but likely needs a bridge\n- Reference 2 comparable YC/early-stage companies using the platform\n- Ask about her team's current toolchain to surface the integration story\n\n**Watch-out signals**\n- Pricing page visits without conversion often mean sticker shock — lead with value, not features`,
  },
  'c-004': {
    contact_name: 'James Whitfield',
    brief: `**Who they are**\nJames Whitfield is Managing Director at Accelarate Partners — a long-term customer who just renewed a 2-year contract ($88K) and expanded from 12 to 20 seats. He's referred 2 prospects already and is your strongest advocate.\n\n**Current deal status & risks**\nDeal closed won. This is a relationship maintenance call. Primary opportunity: upsell the analytics module (referenced in renewal notes) and ask for formal referral introductions.\n\n**Conversation highlights**\n- Renewed 2-year contract in April, added analytics module\n- Expanded seat count 40%\n- Referred 2 prospects organically (Devon Park at Nexus AI, 1 untracked)\n\n**Recommended talking points**\n- Thank him for the referrals and ask if there are 2–3 more contacts in his network who'd benefit\n- Propose a joint case study or testimonial (high NPS implies willingness)\n- Check in on the analytics module onboarding — early wins compound retention\n\n**Watch-out signals**\n- None. This is a net-positive relationship — the only risk is under-nurturing an advocate`,
  },
}

const DEMO_EMAIL_STUBS: Record<string, { subject: string; body: string }> = {
  'c-002': {
    subject: 'Global Finance Enterprise Suite — Board Summary + Pilot Option',
    body: `Hi Marcus,\n\nI wanted to follow up on the custom proposal we sent over — I know board timelines can shift, and I wanted to make it easy for your team to move forward on your schedule.\n\nTwo things that might help:\n\n1. **Executive summary**: I've put together a one-page board summary covering ROI benchmarks from two comparable financial services deployments ($200K+ ARR). Happy to tailor the numbers to your specific use case if useful.\n\n2. **60-day pilot option**: If the board wants to validate before full commitment, we can structure a time-boxed pilot at reduced scope — with a clear exit clause, no long-term lock-in. Several of our enterprise clients used this path before signing.\n\nThe Global Finance Enterprise Suite deal is exactly the kind of deployment we've built for. I'd love to find 20 minutes this week to unblock whatever's sitting between you and the board sign-off.\n\nDoes Thursday or Friday work?\n\nBest,\nAlex`,
  },
  'c-001': {
    subject: 'TechCorp Platform Expansion — SLA Final Terms',
    body: `Hi Sarah,\n\nThank you for the continued momentum on the Platform Expansion — your team's diligence through the legal review has been great to work with.\n\nI wanted to send over the finalized SLA language addressing the uptime guarantee points flagged in our last call. The key updates:\n\n- **99.9% uptime SLA** with prorated credit structure starting at 0.1% downtime\n- **24h P1 response SLA** with dedicated escalation path\n- **Monthly service reviews** built into the contract\n\nIf your legal team needs any clarification on the indemnification clause or the data residency terms, I can have our solutions team on a 30-minute call by end of this week.\n\nLooking forward to getting this across the finish line before May 15.\n\nBest,\nAlex`,
  },
}

const DEMO_REVENUE_HISTORY = [
  { revenue: 62400 },
  { revenue: 71200 },
  { revenue: 68800 },
  { revenue: 84500 },
  { revenue: 94300 },
  { revenue: 109700 },
  { revenue: 98200 },
  { revenue: 118400 },
  { revenue: 127600 },
  { revenue: 135000 },
  { revenue: 141800 },
  { revenue: 152300 },
]

const DEMO_CONTACT_TIMELINES: Record<string, Array<{ id: string; type: string; title: string; body: string; ts: string; meta: Record<string, unknown> }>> = {
  'c-001': [
    { id: 'evt-sc-1', type: 'activity', title: 'legal_review_complete', body: 'Legal team signed off on contract terms. SLA uptime clause accepted with minor modification.', ts: new Date(Date.now() - 86400000).toISOString(), meta: { agent_name: 'Pipeline Optimizer', severity: 'success' } },
    { id: 'evt-sc-2', type: 'deal_stage', title: 'Deal: TechCorp Platform Expansion', body: 'Stage: negotiation · Value: $145,000 · Close: May 15', ts: new Date(Date.now() - 259200000).toISOString(), meta: { stage: 'negotiation', value: 145000 } },
    { id: 'evt-sc-3', type: 'message', title: 'Re: SLA Terms and Uptime Guarantees', body: 'Looks good overall — legal just needs clarity on the indemnification clause before we sign.', ts: new Date(Date.now() - 432000000).toISOString(), meta: { sender: 'sarah.chen@techcorp.com' } },
    { id: 'evt-sc-4', type: 'activity', title: 'email_opened', body: 'Opened: "Platform Expansion — Final Proposal" (8th email opened this month)', ts: new Date(Date.now() - 604800000).toISOString(), meta: { agent_name: 'Gmail', severity: 'info' } },
  ],
  'c-002': [
    { id: 'evt-mr-1', type: 'activity', title: 'follow_up_sent', body: 'Follow-up email sent — no reply in 21 days. Deal health flagged as stale.', ts: new Date(Date.now() - 172800000).toISOString(), meta: { agent_name: 'Pipeline Optimizer', severity: 'warning' } },
    { id: 'evt-mr-2', type: 'message', title: 'Re: Enterprise Suite Pricing', body: 'This looks strong. I need to bring it to the board next cycle — will follow up by end of month.', ts: new Date(Date.now() - 1814400000).toISOString(), meta: { sender: 'mrivera@globalfinance.io' } },
    { id: 'evt-mr-3', type: 'deal_stage', title: 'Deal: Global Finance Enterprise Suite', body: 'Stage: proposal · Value: $250,000 · Health: 35 (stale)', ts: new Date(Date.now() - 2073600000).toISOString(), meta: { stage: 'proposal', value: 250000 } },
    { id: 'evt-mr-4', type: 'activity', title: 'demo_completed', body: 'Product demo completed — Marcus attended with 2 team members. Strong positive signal.', ts: new Date(Date.now() - 2678400000).toISOString(), meta: { agent_name: 'Lead Scorer', severity: 'success' } },
  ],
  'c-004': [
    { id: 'evt-jw-1', type: 'activity', title: 'contract_signed', body: 'Renewed 2-year contract. Seat count expanded from 12 → 20. Analytics module added.', ts: new Date(Date.now() - 3888000000).toISOString(), meta: { agent_name: 'Pipeline Optimizer', severity: 'success' } },
    { id: 'evt-jw-2', type: 'activity', title: 'referral_sent', body: 'James referred Devon Park (Nexus AI CTO) via direct introduction email.', ts: new Date(Date.now() - 1296000000).toISOString(), meta: { agent_name: 'Gmail', severity: 'info' } },
    { id: 'evt-jw-3', type: 'deal_stage', title: 'Deal: Accelarate Renewal + Upsell', body: 'Stage: closed_won · Value: $88,000', ts: new Date(Date.now() - 3888000000).toISOString(), meta: { stage: 'closed_won', value: 88000 } },
  ],
}

const DEMO_DEAL_CONTACT_MAP: Record<string, string> = {
  'd-001': 'c-001', // Sarah Chen
  'd-002': 'c-002', // Marcus Rivera
  'd-003': 'c-004', // James Whitfield
  'd-004': 'c-005', // Amara Osei
  'd-005': 'c-006', // Lena Kowalski
  'd-008': 'c-007', // Devon Park
}

const DEMO_DEAL_TIMELINES: Record<string, Array<{ id: string; type: string; title: string; body: string; ts: string; meta: Record<string, unknown> }>> = {
  'd-001': [
    { id: 'dt-001-1', type: 'activity', title: 'Pipeline Optimizer', body: 'Legal review complete. SLA uptime clause accepted with minor modification. Deal on track for May 15 close.', ts: new Date(Date.now() - 86400000).toISOString(), meta: { severity: 'success' } },
    { id: 'dt-001-2', type: 'deal_moved', title: 'System', body: "Deal 'TechCorp Platform Expansion' updated → negotiation", ts: new Date(Date.now() - 259200000).toISOString(), meta: { severity: 'info' } },
    { id: 'dt-001-3', type: 'message', title: 'Gmail', body: 'Inbound: Re: SLA Terms and Uptime Guarantees — legal just needs clarity on the indemnification clause.', ts: new Date(Date.now() - 432000000).toISOString(), meta: { severity: 'info' } },
    { id: 'dt-001-4', type: 'activity', title: 'Lead Scorer', body: 'Contact score updated to 91 (hot). Signals: 3 meetings in 30 days, opened 8/10 emails.', ts: new Date(Date.now() - 604800000).toISOString(), meta: { severity: 'success' } },
  ],
  'd-002': [
    { id: 'dt-002-1', type: 'activity', title: 'Pipeline Optimizer', body: 'Deal health flagged: 21 days without stage change. Follow-up email sent.', ts: new Date(Date.now() - 172800000).toISOString(), meta: { severity: 'warning' } },
    { id: 'dt-002-2', type: 'message', title: 'Gmail', body: 'Inbound: Re: Enterprise Suite Pricing — "I need to bring it to the board next cycle."', ts: new Date(Date.now() - 1814400000).toISOString(), meta: { severity: 'info' } },
    { id: 'dt-002-3', type: 'deal_moved', title: 'System', body: "Deal 'Global Finance Enterprise Suite' updated → proposal", ts: new Date(Date.now() - 2073600000).toISOString(), meta: { severity: 'info' } },
    { id: 'dt-002-4', type: 'activity', title: 'Lead Scorer', body: 'Demo completed. Marcus attended with 2 team members. Score raised to 78 (hot).', ts: new Date(Date.now() - 2678400000).toISOString(), meta: { severity: 'success' } },
  ],
  'd-003': [
    { id: 'dt-003-1', type: 'deal_moved', title: 'System', body: "Deal 'Accelarate Renewal + Upsell' updated → closed_won", ts: new Date(Date.now() - 3888000000).toISOString(), meta: { severity: 'success' } },
    { id: 'dt-003-2', type: 'activity', title: 'Pipeline Optimizer', body: 'Renewed 2-year contract signed. Seat count expanded from 12 → 20. Analytics module added.', ts: new Date(Date.now() - 3888000000).toISOString(), meta: { severity: 'success' } },
  ],
  'd-006': [
    { id: 'dt-006-1', type: 'activity', title: 'Pipeline Optimizer', body: 'Deal health critical: score 22. No stage change in 45 days. Re-qualification recommended.', ts: new Date(Date.now() - 86400000).toISOString(), meta: { severity: 'warning' } },
    { id: 'dt-006-2', type: 'activity', title: 'Lead Scorer', body: 'Contact last visited website 30 days ago. Low engagement signal.', ts: new Date(Date.now() - 604800000).toISOString(), meta: { severity: 'warning' } },
    { id: 'dt-006-3', type: 'deal_moved', title: 'System', body: "Deal 'ScalePath Japan Starter' created in discovery", ts: new Date(Date.now() - 1728000000).toISOString(), meta: { severity: 'info' } },
  ],
}

const FASTAPI_URL = process.env.NEXT_PUBLIC_FASTAPI_URL || 'http://localhost:8000'
const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE === 'true'

async function apiFetch(path: string, options: RequestInit = {}, token?: string, isFormData = false) {
  let res: Response
  try {
    const headers: Record<string, string> = {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers as Record<string, string> | undefined),
    }
    if (!isFormData) headers['Content-Type'] = 'application/json'
    res = await fetch(`${FASTAPI_URL}${path}`, {
      ...options,
      headers,
    })
  } catch (err) {
    // Network/CORS failure — fetch rejects with a TypeError and no status. Log it so
    // silent breakage (e.g. the API's CORS allowlist missing the current origin after
    // a domain change) is observable instead of vanishing into a caller's .catch().
    console.error(`[api] ${options.method ?? 'GET'} ${FASTAPI_URL}${path} failed (network/CORS):`, err)
    throw err
  }
  if (!res.ok) {
    console.error(`[api] ${options.method ?? 'GET'} ${path} → ${res.status}`)
    throw new Error(`API error ${res.status}`)
  }
  return res.json()
}

// ─── Demo data for the Life / accountability dashboard ───────────────────────
// Deterministic-ish sample arrays so /life demos nicely without a live ledger.
// Intentionally leaves gaps (missing days, null kept_rate weeks) to mirror the
// honest "no zero-fill fabrication" behaviour of the real collector.
const DEMO_KPI_SPECS: Array<{ domain: string; metric: string; base: number; amp: number; skip: number }> = [
  { domain: 'engineering', metric: 'git_commits', base: 6, amp: 5, skip: 6 },   // weekends mostly off
  { domain: 'engineering', metric: 'sessions', base: 3, amp: 2, skip: 6 },
  { domain: 'knowledge', metric: 'records.main', base: 4, amp: 3, skip: 5 },
  { domain: 'knowledge', metric: 'records.neuroscience', base: 2, amp: 2, skip: 4 },
  { domain: 'knowledge', metric: 'records.content', base: 1, amp: 2, skip: 3 },
  { domain: 'knowledge', metric: 'topics_distilled', base: 3, amp: 3, skip: 5 },
  { domain: 'knowledge', metric: 'api_cost_usd', base: 8, amp: 6, skip: 6 },
  { domain: 'product', metric: 'crm_users', base: 42, amp: 4, skip: 6 },
  { domain: 'product', metric: 'tribe_corpus_videos', base: 120, amp: 8, skip: 5 },
  { domain: 'product', metric: 'tribe_avg_score', base: 71, amp: 6, skip: 5 },
  { domain: 'life', metric: 'records.personal', base: 2, amp: 2, skip: 3 },
  { domain: 'life', metric: 'records.finance', base: 1, amp: 2, skip: 2 },
]

function demoKpiSnapshots(opts?: { fromDate?: string; toDate?: string; domain?: string; metric?: string }): KpiSnapshot[] {
  const today = new Date()
  const from = opts?.fromDate ? new Date(opts.fromDate) : new Date(today.getTime() - 89 * 86400000)
  const out: KpiSnapshot[] = []
  const days = Math.max(1, Math.round((today.getTime() - from.getTime()) / 86400000) + 1)
  for (const spec of DEMO_KPI_SPECS) {
    if (opts?.domain && spec.domain !== opts.domain) continue
    if (opts?.metric && spec.metric !== opts.metric) continue
    for (let i = 0; i < days; i++) {
      const d = new Date(from.getTime() + i * 86400000)
      const seed = (d.getDate() + d.getMonth() * 31 + spec.metric.length * 7) % 7
      // Honest gaps: some days have no snapshot for this metric (no zero-fill).
      if (seed > spec.skip) continue
      const dow = d.getDay()
      const weekendDamp = (dow === 0 || dow === 6) ? 0.4 : 1
      const raw = spec.base + Math.round(((seed * 9301 + 49297) % (spec.amp + 1)) * weekendDamp)
      const value = spec.metric === 'api_cost_usd' || spec.metric === 'tribe_avg_score'
        ? Math.round((raw + (seed % 3) * 0.5) * 100) / 100
        : Math.max(0, raw)
      out.push({
        id: `demo-kpi-${spec.metric}-${i}`,
        workspace_id: 'demo-workspace-1',
        date: d.toISOString().slice(0, 10),
        domain: spec.domain,
        metric: spec.metric,
        value,
        meta: spec.metric === 'git_commits'
          ? { 'crm-agentic': Math.round(value * 0.5), 'tribe-social': Math.round(value * 0.3), 'alfred-v2': Math.round(value * 0.2) }
          : {},
      })
    }
  }
  return out
}

const DEMO_COMMITMENTS: Commitment[] = [
  { id: 'dc-1', workspace_id: 'demo-workspace-1', external_id: 'auto-ship-life-page-20260603', title: 'Ship the /life accountability dashboard', kind: 'auto', source: 'sessions/2026-06-03-crm.md', declared_at: new Date(Date.now() - 2 * 86400000).toISOString(), due_date: new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10), status: 'open', evidence: null, scored_at: null },
  { id: 'dc-2', workspace_id: 'demo-workspace-1', external_id: 'auto-rls-ledger-20260531', title: 'Enable RLS on the ledger tables', kind: 'auto', source: 'sessions/2026-05-31-api.md', declared_at: new Date(Date.now() - 5 * 86400000).toISOString(), due_date: null, status: 'kept', evidence: 'Commit b134efc enabled RLS on kpi_snapshots + commitments following the 008 pattern.', scored_at: new Date(Date.now() - 1 * 86400000).toISOString() },
  { id: 'dc-3', workspace_id: 'demo-workspace-1', external_id: 'explicit-write-retro-tests-20260529', title: 'Write integration tests for the retro scorer', kind: 'explicit', source: null, declared_at: new Date(Date.now() - 7 * 86400000).toISOString(), due_date: new Date(Date.now() - 2 * 86400000).toISOString().slice(0, 10), status: 'broken', evidence: 'No test files added under apps/api/tests/ for the scorer by the due date.', scored_at: new Date(Date.now() - 1 * 86400000).toISOString() },
  { id: 'dc-4', workspace_id: 'demo-workspace-1', external_id: 'auto-tribe-rescore-20260528', title: 'Re-score the tribe-social v2 corpus on RunPod', kind: 'auto', source: 'sessions/2026-05-28-tribe.md', declared_at: new Date(Date.now() - 8 * 86400000).toISOString(), due_date: null, status: 'kept', evidence: 'RunPod job completed; 137 videos rescored, avg 71.4.', scored_at: new Date(Date.now() - 6 * 86400000).toISOString() },
  { id: 'dc-5', workspace_id: 'demo-workspace-1', external_id: 'auto-distill-neuro-20260527', title: 'Distill the week\'s neuroscience reading into the vault', kind: 'auto', source: 'sessions/2026-05-27-research.md', declared_at: new Date(Date.now() - 9 * 86400000).toISOString(), due_date: null, status: 'dropped', evidence: 'Deprioritised in favour of the ledger API work.', scored_at: new Date(Date.now() - 7 * 86400000).toISOString() },
  { id: 'dc-6', workspace_id: 'demo-workspace-1', external_id: 'explicit-daily-finance-log-20260526', title: 'Log a daily finance record for the week', kind: 'explicit', source: null, declared_at: new Date(Date.now() - 10 * 86400000).toISOString(), due_date: new Date(Date.now() - 3 * 86400000).toISOString().slice(0, 10), status: 'open', evidence: null, scored_at: null },
]

function demoCommitments(opts?: { status?: string; kind?: string }): Commitment[] {
  let rows = DEMO_COMMITMENTS
  if (opts?.status) rows = rows.filter((c) => c.status === opts.status)
  if (opts?.kind) rows = rows.filter((c) => c.kind === opts.kind)
  return rows
}

function demoCommitmentStats(weeks: number): CommitmentWeekStats[] {
  const today = new Date()
  const day = today.getUTCDay()
  const mondayOffset = (day + 6) % 7
  const thisMonday = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - mondayOffset))
  const out: CommitmentWeekStats[] = []
  for (let i = weeks - 1; i >= 0; i--) {
    const wk = new Date(thisMonday.getTime() - i * 7 * 86400000)
    const seed = (wk.getUTCDate() + wk.getUTCMonth() * 4) % 7
    // Early weeks have no scored outcomes yet -> declared but kept_rate null (a gap).
    const noOutcomes = i > weeks - 4
    const declared = noOutcomes ? seed % 3 : 2 + (seed % 4)
    const kept = noOutcomes ? 0 : Math.min(declared, 1 + (seed % 3))
    const broken = noOutcomes ? 0 : Math.max(0, Math.min(declared - kept, seed % 2))
    const dropped = noOutcomes ? 0 : (seed === 6 ? 1 : 0)
    const open = Math.max(0, declared - kept - broken - dropped)
    const denom = kept + broken
    out.push({
      week_start: wk.toISOString().slice(0, 10),
      declared,
      kept,
      broken,
      dropped,
      open,
      kept_rate: denom ? Math.round((kept / denom) * 100) / 100 : null,
    })
  }
  return out
}

export const apiClient = {
  // Agents
  listAgents: (token: string) => {
    if (isDemoMode) return Promise.resolve([])
    return apiFetch('/agents', {}, token)
  },
  // Returns { job_id } on a real dispatch, or { not_implemented: true, detail }
  // when the agent type has no on-demand task (HTTP 501) so the caller can skip
  // starting the job poller instead of polling a job that was never created.
  triggerAgent: async (
    agentId: string,
    token: string,
  ): Promise<{ job_id?: string; not_implemented?: boolean; detail?: string }> => {
    if (isDemoMode) return { job_id: `demo-job-${agentId}` }
    const res = await fetch(`${FASTAPI_URL}/agents/${agentId}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    })
    if (res.status === 501) {
      let detail = 'This agent runs via its own flow, not an on-demand job.'
      try { detail = (await res.json())?.detail ?? detail } catch { /* keep default */ }
      return { not_implemented: true, detail }
    }
    if (!res.ok) {
      console.error(`[api] POST /agents/${agentId}/run → ${res.status}`)
      throw new Error(`API error ${res.status}`)
    }
    return res.json()
  },
  updateAgent: (agentId: string, data: { status?: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: agentId, ...data })
    return apiFetch(`/agents/${agentId}`, { method: 'PATCH', body: JSON.stringify(data) }, token)
  },
  /**
   * Fetch the last `limit` activity events for a specific agent.
   * Falls back to filtering workspace activity by agent_id meta tag.
   */
  getAgentActivity: (workspaceId: string, agentId: string, token: string, limit = 7) => {
    if (isDemoMode) return Promise.resolve([])
    return apiFetch(
      `/workspaces/${workspaceId}/activity?agent_id=${agentId}&limit=${limit}`,
      {},
      token
    )
  },

  // Connectors
  getConnectors: (workspaceId: string, token: string) => {
    if (isDemoMode) return Promise.resolve(demoConnectors)
    return apiFetch(`/workspaces/${workspaceId}/connectors`, {}, token)
  },
  getConnectorStatus: (workspaceId: string, connectorId: string, token: string) => {
    if (isDemoMode) {
      const c = demoConnectors.find(x => x.id === connectorId)
      return Promise.resolve({ id: connectorId, service: c?.service ?? 'gmail', status: 'active', external_email: 'demo@example.com', message_count: c?.message_count ?? 0, task_count: 0, last_sync: c?.last_sync ?? null, created_at: new Date().toISOString() })
    }
    return apiFetch(`/workspaces/${workspaceId}/connectors/${connectorId}/status`, {}, token)
  },
  getGmailAuthUrl: (_workspaceId: string, _token: string) => {
    if (isDemoMode) return Promise.resolve({ auth_url: '#' })
    return apiFetch(`/workspaces/${_workspaceId}/connectors/gmail/auth`, {}, _token)
  },
  triggerGmailSync: (_workspaceId: string, _token: string) => {
    if (isDemoMode) return Promise.resolve({ status: 'ok' })
    return apiFetch(`/workspaces/${_workspaceId}/connectors/gmail/sync`, { method: 'POST' }, _token)
  },
  getSlackAuthUrl: (_workspaceId: string, _token: string) => {
    if (isDemoMode) return Promise.resolve({ auth_url: '#' })
    return apiFetch(`/workspaces/${_workspaceId}/connectors/slack/auth`, {}, _token)
  },
  triggerSlackSync: (_workspaceId: string, _token: string) => {
    if (isDemoMode) return Promise.resolve({ status: 'ok' })
    return apiFetch(`/workspaces/${_workspaceId}/connectors/slack/sync`, { method: 'POST' }, _token)
  },
  deleteConnector: (_workspaceId: string, _connectorId: string, _token: string) => {
    if (isDemoMode) return Promise.resolve({ status: 'ok' })
    return apiFetch(`/workspaces/${_workspaceId}/connectors/${_connectorId}`, { method: 'DELETE' }, _token)
  },

  // Messages
  getMessages: (workspaceId: string, token: string) => {
    if (isDemoMode) return Promise.resolve(demoMessages)
    return apiFetch(`/workspaces/${workspaceId}/messages`, {}, token)
  },
  scoreClarity: (workspaceId: string, messageId: string, token: string) => {
    if (isDemoMode) return Promise.resolve({ message_id: messageId, score: 72, rationale: 'Message is clear and well-structured with specific action items.', model_used: 'claude-sonnet-4-6' })
    return apiFetch(`/workspaces/${workspaceId}/messages/${messageId}/score-clarity`, { method: 'POST' }, token)
  },
  reprocessMessages: (workspaceId: string, token: string) => {
    if (isDemoMode) return Promise.resolve({ job_id: 'demo-reprocess' })
    return apiFetch(`/workspaces/${workspaceId}/messages/reprocess`, { method: 'POST' }, token)
  },

  // CSV export (returns a Blob for browser download)
  exportContactsCsv: async (workspaceId: string, token: string): Promise<Blob> => {
    if (isDemoMode) {
      const { demoContacts } = require('./demo-data')
      const rows = [
        ['id', 'name', 'email', 'company', 'role', 'status', 'ml_score', 'revenue', 'created_at'],
        ...demoContacts.map((c: Record<string, unknown>) => [c.id, c.name, c.email, c.company, c.role, c.status, (c.mlScore as Record<string, unknown>)?.value ?? 0, c.revenue, c.createdAt]),
      ]
      const csv = rows.map((r) => r.join(',')).join('\n')
      return new Blob([csv], { type: 'text/csv' })
    }
    const res = await fetch(`${FASTAPI_URL}/workspaces/${workspaceId}/contacts/export`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`Export failed: ${res.status}`)
    return res.blob()
  },
  exportDealsCsv: async (workspaceId: string, token: string): Promise<Blob> => {
    if (isDemoMode) {
      const { demoDeals } = require('./demo-data')
      const rows = [
        ['id', 'title', 'company', 'contact_name', 'value', 'stage', 'ml_win_probability', 'health_score', 'expected_close', 'created_at'],
        ...demoDeals.map((d: Record<string, unknown>) => [d.id, d.title, d.company, d.contactName, d.value, d.stage, d.mlWinProbability, d.healthScore, d.expectedClose, d.createdAt]),
      ]
      const csv = rows.map((r) => (r as unknown[]).join(',')).join('\n')
      return new Blob([csv], { type: 'text/csv' })
    }
    const res = await fetch(`${FASTAPI_URL}/workspaces/${workspaceId}/deals/export`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`Export failed: ${res.status}`)
    return res.blob()
  },

  // Tasks
  getTasks: (workspaceId: string, token: string, opts?: { contactId?: string; projectId?: string }) => {
    if (isDemoMode) {
      let tasks = demoTasks as unknown as Array<Record<string, unknown>>
      if (opts?.contactId) tasks = tasks.filter(t => t.contact_id === opts.contactId)
      return Promise.resolve(tasks)
    }
    const params = new URLSearchParams()
    if (opts?.contactId) params.set('contact_id', opts.contactId)
    if (opts?.projectId) params.set('project_id', opts.projectId)
    const qs = params.toString()
    return apiFetch(`/workspaces/${workspaceId}/tasks${qs ? `?${qs}` : ''}`, {}, token)
  },
  createTask: (workspaceId: string, data: Record<string, unknown>, token: string) => {
    if (isDemoMode) {
      const created = { id: `demo-task-${Date.now()}`, status: 'open', ...data }
      return Promise.resolve(created)
    }
    return apiFetch(`/workspaces/${workspaceId}/tasks`, { method: 'POST', body: JSON.stringify(data) }, token)
  },
  updateTask: (workspaceId: string, taskId: string, data: Record<string, unknown>, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: taskId, ...data })
    return apiFetch(`/workspaces/${workspaceId}/tasks/${taskId}`, { method: 'PUT', body: JSON.stringify(data) }, token)
  },
  deleteTask: (workspaceId: string, taskId: string, token: string) => {
    if (isDemoMode) return Promise.resolve()
    return apiFetch(`/workspaces/${workspaceId}/tasks/${taskId}`, { method: 'DELETE' }, token)
  },

  // Contacts
  listContacts: (workspaceId: string, token: string, opts?: { status?: string; q?: string }) => {
    if (isDemoMode) return Promise.resolve([])
    const params = new URLSearchParams()
    if (opts?.status && opts.status !== 'all') params.set('status', opts.status)
    if (opts?.q) params.set('q', opts.q)
    const qs = params.toString()
    return apiFetch(`/workspaces/${workspaceId}/contacts${qs ? `?${qs}` : ''}`, {}, token)
  },
  composeEmail: (workspaceId: string, contactId: string, token: string) => {
    if (isDemoMode) {
      const stub = DEMO_EMAIL_STUBS[contactId]
      if (stub) return Promise.resolve(stub)
      const contact = demoContacts.find(c => c.id === contactId)
      const name = contact?.name?.split(' ')[0] ?? 'there'
      const company = contact?.company ?? 'your organization'
      return Promise.resolve({
        subject: 'Following up on our conversation',
        body: `Hi ${name},\n\nI wanted to follow up on our recent discussion about how we can help ${company} move forward.\n\nBased on what you shared, I believe we have a strong match for your needs. I'd love to schedule 30 minutes this week to walk through a tailored approach and answer any questions your team has.\n\nDoes Thursday or Friday work for you?\n\nBest,\nAlex`,
      })
    }
    return apiFetch(`/workspaces/${workspaceId}/contacts/${contactId}/compose`, { method: 'POST' }, token)
  },
  scoreContact: (workspaceId: string, contactId: string, token: string) => {
    if (isDemoMode) return Promise.resolve({ score: 85, label: 'hot', trend: 'up' })
    return apiFetch(`/workspaces/${workspaceId}/contacts/${contactId}/score`, { method: 'POST' }, token)
  },
  enrichContact: (workspaceId: string, contactId: string, token: string) => {
    if (isDemoMode) return Promise.resolve({ status: 'queued', fields_updated: ['company', 'role', 'semantic_tags'] })
    return apiFetch(`/workspaces/${workspaceId}/contacts/${contactId}/enrich`, { method: 'POST' }, token)
  },
  createContact: (workspaceId: string, data: { name: string; email?: string; company?: string; role?: string; status?: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: `demo-contact-${Date.now()}`, workspace_id: workspaceId, status: 'lead', ...data })
    return apiFetch(`/workspaces/${workspaceId}/contacts`, { method: 'POST', body: JSON.stringify(data) }, token)
  },
  getContact: (workspaceId: string, contactId: string, token: string) => {
    if (isDemoMode) return Promise.resolve(null)
    return apiFetch(`/workspaces/${workspaceId}/contacts/${contactId}`, {}, token)
  },
  updateContact: (workspaceId: string, contactId: string, data: { name?: string; email?: string; company?: string; role?: string; status?: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: contactId, ...data })
    return apiFetch(`/workspaces/${workspaceId}/contacts/${contactId}`, { method: 'PATCH', body: JSON.stringify(data) }, token)
  },
  deleteContact: (workspaceId: string, contactId: string, token: string) => {
    if (isDemoMode) return Promise.resolve()
    return apiFetch(`/workspaces/${workspaceId}/contacts/${contactId}`, { method: 'DELETE' }, token)
  },

  // Calls
  uploadCall: (workspaceId: string, formData: FormData, token: string) => {
    if (isDemoMode) return Promise.resolve({ call_summary_id: `demo-call-${Date.now()}`, job_id: 'demo-job', status: 'processing' })
    return fetch(`${FASTAPI_URL}/workspaces/${workspaceId}/calls/upload`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    }).then((r) => { if (!r.ok) throw new Error(`API error ${r.status}`); return r.json() })
  },
  getCalls: (workspaceId: string, token: string) => {
    if (isDemoMode) return Promise.resolve([
      { id: 'call-001', contact_id: null, title: 'Q2 Strategy Review', duration_seconds: 1847, summary: 'Discussed Q2 roadmap priorities, alignment on enterprise expansion, and headcount planning for the engineering org.', action_items: [{ owner: 'Sarah', task: 'Send updated roadmap doc', due: '2024-05-10' }, { owner: 'Marcus', task: 'Schedule headcount review with HR', due: '2024-05-08' }], participants: 'Sarah Chen, Marcus Rivera', call_date: new Date(Date.now() - 86400000).toISOString(), processing: false },
      { id: 'call-002', contact_id: null, title: 'TechCorp Deal Sync', duration_seconds: 924, summary: 'TechCorp confirmed interest in the enterprise tier. Legal review expected to complete by end of week. Price sensitivity is low.', action_items: [{ owner: 'You', task: 'Send final SLA draft', due: '2024-05-12' }], participants: 'James Whitfield, Claire Dupont', call_date: new Date(Date.now() - 172800000).toISOString(), processing: false },
      { id: 'call-003', contact_id: null, title: 'Onboarding — BuildRight', duration_seconds: 0, summary: '', action_items: [], participants: 'Amara Osei', call_date: new Date().toISOString(), processing: true },
    ])
    return apiFetch(`/workspaces/${workspaceId}/calls`, {}, token)
  },
  getCall: (workspaceId: string, callId: string, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: callId, transcript: 'This is a demo transcript of the call recording.', summary: 'Demo summary.', action_items: [], processing: false })
    return apiFetch(`/workspaces/${workspaceId}/calls/${callId}`, {}, token)
  },
  deleteCall: (workspaceId: string, callId: string, token: string) => {
    if (isDemoMode) return Promise.resolve({})
    return apiFetch(`/workspaces/${workspaceId}/calls/${callId}`, { method: 'DELETE' }, token)
  },

  // Deals
  listDeals: (workspaceId: string, token: string, opts?: { stage?: string; contactId?: string }) => {
    if (isDemoMode) {
      let deals = demoDeals as unknown as Array<Record<string, unknown>>
      if (opts?.stage && opts.stage !== 'all') deals = deals.filter(d => d.stage === opts.stage)
      if (opts?.contactId) deals = deals.filter(d => d.contact_id === opts.contactId)
      return Promise.resolve(deals)
    }
    const params = new URLSearchParams()
    if (opts?.stage && opts.stage !== 'all') params.set('stage', opts.stage)
    if (opts?.contactId) params.set('contact_id', opts.contactId)
    const qs = params.toString()
    return apiFetch(`/workspaces/${workspaceId}/deals${qs ? `?${qs}` : ''}`, {}, token)
  },
  createDeal: (workspaceId: string, data: { title?: string; company?: string; contact_id?: string; value?: number; stage?: string; ml_win_probability?: number; expected_close?: string; notes?: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: `demo-deal-${Date.now()}`, workspace_id: workspaceId, stage: 'lead', ...data })
    return apiFetch(`/workspaces/${workspaceId}/deals`, { method: 'POST', body: JSON.stringify(data) }, token)
  },
  getDeal: (workspaceId: string, dealId: string, token: string) => {
    if (isDemoMode) {
      const deal = demoDeals.find((d) => d.id === dealId)
      if (!deal) return Promise.resolve(null)
      return Promise.resolve({
        id: deal.id,
        workspace_id: workspaceId,
        title: deal.title,
        company: deal.company,
        contact_name: deal.contactName,
        contact_id: DEMO_DEAL_CONTACT_MAP[deal.id] ?? null,
        value: deal.value,
        stage: deal.stage,
        ml_win_probability: deal.mlWinProbability,
        health_score: deal.healthScore,
        expected_close: deal.expectedClose,
        assigned_agent: deal.assignedAgent,
        notes: deal.notes,
        created_at: deal.createdAt,
      })
    }
    return apiFetch(`/workspaces/${workspaceId}/deals/${dealId}`, {}, token)
  },
  getDealTimeline: (workspaceId: string, dealId: string, token: string) => {
    if (isDemoMode) {
      return Promise.resolve(DEMO_DEAL_TIMELINES[dealId] ?? [])
    }
    return apiFetch(`/workspaces/${workspaceId}/deals/${dealId}/timeline`, {}, token)
  },
  updateDeal: (workspaceId: string, dealId: string, data: { title?: string; company?: string; value?: number; stage?: string; ml_win_probability?: number; expected_close?: string; notes?: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: dealId, ...data })
    return apiFetch(`/workspaces/${workspaceId}/deals/${dealId}`, { method: 'PATCH', body: JSON.stringify(data) }, token)
  },
  deleteDeal: (workspaceId: string, dealId: string, token: string) => {
    if (isDemoMode) return Promise.resolve()
    return apiFetch(`/workspaces/${workspaceId}/deals/${dealId}`, { method: 'DELETE' }, token)
  },
  bulkDealAction: (workspaceId: string, data: { action: 'move_stage' | 'delete'; deal_ids: string[]; stage?: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ action: data.action, updated: data.deal_ids.length, deal_ids: data.deal_ids })
    return apiFetch(`/workspaces/${workspaceId}/deals/bulk`, { method: 'POST', body: JSON.stringify(data) }, token)
  },

  // Deal health
  triggerDealHealth: (workspaceId: string, token: string) => {
    if (isDemoMode) return Promise.resolve({ job_id: 'demo-health', status: 'queued' })
    return apiFetch(`/workspaces/${workspaceId}/deals/health`, { method: 'POST' }, token)
  },
  getStaleDeals: (workspaceId: string, token: string, threshold = 40) => {
    if (isDemoMode) {
      const { demoDeals } = require('./demo-data')
      return Promise.resolve(
        demoDeals
          .filter((d: { healthScore: number; stage: string }) =>
            d.healthScore <= threshold && !['closed_won', 'closed_lost'].includes(d.stage)
          )
          .sort((a: { healthScore: number }, b: { healthScore: number }) => a.healthScore - b.healthScore)
          .slice(0, 5)
          .map((d: { id: string; title: string; company: string; stage: string; value: number; healthScore: number }) => ({
            id: d.id, title: d.title, company: d.company,
            stage: d.stage, value: d.value, health_score: d.healthScore,
            signals: ['Stale — no recent activity'],
          }))
      )
    }
    return apiFetch(`/workspaces/${workspaceId}/deals/stale?threshold=${threshold}`, {}, token)
  },

  getPipelineSuggestions: (workspaceId: string, token: string) => {
    if (isDemoMode) return Promise.resolve([
      { deal_id: 'demo-1', title: 'Acme Corp Expansion', company: 'Acme Corp', stage: 'proposal', value: 48000, action: 'follow_up', reason: 'No stage change in 24 days', priority: 'high' },
      { deal_id: 'demo-2', title: 'TechStart Series A', company: 'TechStart', stage: 'negotiation', value: 22000, action: 'review', reason: 'Win probability only 28% — consider re-qualifying', priority: 'medium' },
    ])
    return apiFetch(`/workspaces/${workspaceId}/pipeline/suggestions`, {}, token)
  },

  sendEmail: (workspaceId: string, contactId: string, payload: { to: string; subject: string; body: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ message_id: 'demo-msg', status: 'sent', to: payload.to })
    return apiFetch(`/workspaces/${workspaceId}/contacts/${contactId}/send-email`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }, token)
  },

  getMeetingBrief: (workspaceId: string, contactId: string, token: string) => {
    if (isDemoMode) {
      const stub = DEMO_CONTACT_BRIEFS[contactId]
      if (stub) return Promise.resolve({ contact_id: contactId, ...stub })
      const contact = demoContacts.find(c => c.id === contactId)
      const name = contact?.name ?? 'this contact'
      const company = contact?.company ?? 'their organization'
      const role = contact?.role ?? 'their role'
      return Promise.resolve({
        contact_id: contactId,
        contact_name: name,
        brief: `**Who they are**\n${name} is ${role} at ${company}.\n\n**Current deal status & risks**\nReview their latest activity and deal history before this meeting.\n\n**Recommended talking points**\n- Understand their current priorities and timeline\n- Identify any blockers to moving forward\n- Confirm next steps and owner\n\n**Watch-out signals**\n- Check engagement trends — declining open rates or response times are early churn signals`,
      })
    }
    return apiFetch(`/workspaces/${workspaceId}/contacts/${contactId}/brief`, { method: 'POST' }, token)
  },

  getContactTimeline: (workspaceId: string, contactId: string, token: string) => {
    if (isDemoMode) {
      const timeline = DEMO_CONTACT_TIMELINES[contactId]
      if (timeline) return Promise.resolve(timeline)
      const contact = demoContacts.find(c => c.id === contactId)
      const email = contact?.email ?? 'contact@example.com'
      return Promise.resolve([
        { id: `evt-${contactId}-1`, type: 'activity', title: 'email_sent', body: `Follow-up email sent to ${email}.`, ts: new Date(Date.now() - 86400000).toISOString(), meta: { agent_name: 'Gmail', severity: 'info' } },
        { id: `evt-${contactId}-2`, type: 'message', title: 'Inbound inquiry', body: 'Thank you for reaching out — looking forward to connecting.', ts: new Date(Date.now() - 259200000).toISOString(), meta: { sender: email } },
      ])
    }
    return apiFetch(`/workspaces/${workspaceId}/contacts/${contactId}/timeline`, {}, token)
  },

  updateContactStatus: (workspaceId: string, contactId: string, contactStatus: string, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: contactId, status: contactStatus })
    return apiFetch(`/workspaces/${workspaceId}/contacts/${contactId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status: contactStatus }),
    }, token)
  },

  getDealHistory: (workspaceId: string, token: string, months = 6) => {
    if (isDemoMode) {
      const now = new Date()
      const abbr = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
      return Promise.resolve(
        Array.from({ length: months }, (_, i) => {
          const d = new Date(now.getFullYear(), now.getMonth() - (months - 1 - i), 1)
          const historyIdx = DEMO_REVENUE_HISTORY.length - months + i
          return { month: abbr[d.getMonth()], revenue: DEMO_REVENUE_HISTORY[Math.max(0, historyIdx)].revenue }
        })
      )
    }
    return apiFetch(`/workspaces/${workspaceId}/deals/history?months=${months}`, {}, token)
  },

  // Semantic search
  semanticSearchContacts: (workspaceId: string, query: string, token: string) => {
    if (isDemoMode) {
      const q = query.toLowerCase()
      const results = demoContacts
        .filter((c) =>
          c.name.toLowerCase().includes(q) ||
          c.company.toLowerCase().includes(q) ||
          (c.role ?? '').toLowerCase().includes(q) ||
          c.email.toLowerCase().includes(q)
        )
        .slice(0, 8)
        .map((c, i) => ({
          id: c.id,
          name: c.name,
          email: c.email,
          company: c.company,
          role: c.role,
          status: c.status,
          ml_score: { value: c.mlScore.value, label: c.mlScore.label, trend: c.mlScore.trend },
          revenue: c.revenue,
          deal_count: c.deals,
          similarity: Math.round((Math.max(0.5, 0.97 - i * 0.07)) * 10000) / 10000,
        }))
      return Promise.resolve(results)
    }
    const params = new URLSearchParams({ q: query, limit: '15' })
    return apiFetch(`/workspaces/${workspaceId}/contacts/search?${params}`, {}, token)
  },
  triggerEmbedContacts: (workspaceId: string, token: string) => {
    if (isDemoMode) return Promise.resolve({ job_id: 'demo-embed', status: 'queued', contacts_total: demoContacts.length })
    return apiFetch(`/workspaces/${workspaceId}/contacts/embed-all`, { method: 'POST' }, token)
  },

  // Workspace
  createWorkspace: (data: { name: string; slug: string; mode: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: crypto.randomUUID(), ...data })
    return apiFetch('/workspaces', { method: 'POST', body: JSON.stringify(data) }, token)
  },
  getWorkspace: (workspaceId: string, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: workspaceId, name: 'Demo Workspace', slug: 'demo', mode: 'both' })
    return apiFetch(`/workspaces/${workspaceId}`, {}, token)
  },
  updateWorkspace: (workspaceId: string, data: { name?: string; mode?: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: workspaceId, ...data })
    return apiFetch(`/workspaces/${workspaceId}`, { method: 'PATCH', body: JSON.stringify(data) }, token)
  },

  inviteTeammate: (workspaceId: string, email: string, token: string) => {
    if (isDemoMode) return Promise.resolve({ status: 'invited', email })
    return apiFetch(`/workspaces/${workspaceId}/invite`, { method: 'POST', body: JSON.stringify({ email }) }, token)
  },

  // Activity events
  listActivity: (workspaceId: string, token: string, opts?: { limit?: number; offset?: number; eventType?: string }): Promise<Array<{ id: string; type: string | null; agent_name: string | null; description: string | null; meta: string | null; severity: string; created_at: string }>> => {
    if (isDemoMode) {
      const DEMO_ACTIVITIES = [
        { id: 'act-1', type: 'contact_created', agent_name: 'System', description: 'New contact added: Sarah Chen', meta: '', severity: 'info', created_at: new Date(Date.now() - 600000).toISOString() },
        { id: 'act-2', type: 'email_sent', agent_name: 'Gmail', description: 'Email sent to sarah.chen@techcorp.com: TechCorp Platform Expansion — SLA Final Terms', meta: '', severity: 'success', created_at: new Date(Date.now() - 1800000).toISOString() },
        { id: 'act-3', type: 'deal_moved', agent_name: 'System', description: "Deal 'Global Finance Enterprise Suite' updated → proposal", meta: '', severity: 'info', created_at: new Date(Date.now() - 3600000).toISOString() },
        { id: 'act-4', type: 'contact_created', agent_name: 'System', description: 'New contact added: Marcus Rivera', meta: '', severity: 'info', created_at: new Date(Date.now() - 7200000).toISOString() },
        { id: 'act-5', type: 'agent_run', agent_name: 'Lead Scorer', description: 'Lead scoring completed for 8 contacts — 3 upgraded to hot', meta: '', severity: 'success', created_at: new Date(Date.now() - 10800000).toISOString() },
        { id: 'act-6', type: 'deal_moved', agent_name: 'System', description: "Deal 'TechCorp Platform Expansion' updated → negotiation", meta: '', severity: 'info', created_at: new Date(Date.now() - 18000000).toISOString() },
        { id: 'act-7', type: 'contact_updated', agent_name: 'System', description: 'Contact updated: Priya Nair flagged as prospect', meta: '', severity: 'warning', created_at: new Date(Date.now() - 21600000).toISOString() },
        { id: 'act-8', type: 'agent_run', agent_name: 'Email Composer', description: 'Draft generated for contact c-002: subject "Global Finance Enterprise Suite — Board Summary"', meta: '', severity: 'success', created_at: new Date(Date.now() - 28800000).toISOString() },
        { id: 'act-9', type: 'contact_created', agent_name: 'System', description: 'New contact added: James Whitfield', meta: '', severity: 'info', created_at: new Date(Date.now() - 36000000).toISOString() },
        { id: 'act-10', type: 'deal_moved', agent_name: 'System', description: "Deal 'Accelarate Renewal + Upsell' updated → closed_won", meta: '', severity: 'success', created_at: new Date(Date.now() - 43200000).toISOString() },
        { id: 'act-11', type: 'agent_run', agent_name: 'Pipeline Optimizer', description: 'Deal health flagged: 21 days without stage change on Global Finance deal', meta: '', severity: 'warning', created_at: new Date(Date.now() - 86400000).toISOString() },
        { id: 'act-12', type: 'contact_deleted', agent_name: 'System', description: 'Contact removed: Old Lead', meta: '', severity: 'warning', created_at: new Date(Date.now() - 129600000).toISOString() },
        { id: 'act-13', type: 'email_sent', agent_name: 'Gmail', description: 'Email sent to james.whitfield@accelarate.com: Renewal — Upsell Proposal', meta: '', severity: 'success', created_at: new Date(Date.now() - 172800000).toISOString() },
        { id: 'act-14', type: 'agent_run', agent_name: 'Sentiment Analyzer', description: 'Sentiment analysis completed: 12 messages scored (avg positive 0.72)', meta: '', severity: 'info', created_at: new Date(Date.now() - 216000000).toISOString() },
        { id: 'act-15', type: 'contact_created', agent_name: 'System', description: 'New contact added: Devon Park', meta: '', severity: 'info', created_at: new Date(Date.now() - 259200000).toISOString() },
      ]
      const { offset = 0, limit = 50, eventType } = opts ?? {}
      let data = eventType ? DEMO_ACTIVITIES.filter(a => a.type === eventType) : DEMO_ACTIVITIES
      data = data.slice(offset, offset + limit)
      return Promise.resolve(data)
    }
    const params = new URLSearchParams()
    params.set('limit', String(opts?.limit ?? 50))
    if (opts?.offset) params.set('offset', String(opts.offset))
    if (opts?.eventType) params.set('event_type', opts.eventType)
    return apiFetch(`/workspaces/${workspaceId}/activity?${params}`, {}, token)
  },
  createActivity: (workspaceId: string, data: { type: string; agent_name: string; description: string; meta?: string; severity?: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: `demo-activity-${Date.now()}`, ...data })
    return apiFetch(`/workspaces/${workspaceId}/activity`, { method: 'POST', body: JSON.stringify(data) }, token)
  },

  // Projects
  listProjects: (workspaceId: string, token: string) => {
    if (isDemoMode) return Promise.resolve([])
    return apiFetch(`/workspaces/${workspaceId}/projects`, {}, token)
  },
  getProject: (workspaceId: string, projectId: string, token: string) => {
    if (isDemoMode) return Promise.resolve(null)
    return apiFetch(`/workspaces/${workspaceId}/projects/${projectId}`, {}, token)
  },
  createProject: (workspaceId: string, data: { name: string; description?: string; status?: string; contact_id?: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: `demo-project-${Date.now()}`, workspace_id: workspaceId, status: 'active', created_at: new Date().toISOString(), updated_at: new Date().toISOString(), ...data })
    return apiFetch(`/workspaces/${workspaceId}/projects`, { method: 'POST', body: JSON.stringify(data) }, token)
  },
  deleteProject: (workspaceId: string, projectId: string, token: string) => {
    if (isDemoMode) return Promise.resolve()
    return apiFetch(`/workspaces/${workspaceId}/projects/${projectId}`, { method: 'DELETE' }, token)
  },
  getProjectTasks: (workspaceId: string, projectId: string, token: string) => {
    if (isDemoMode) return Promise.resolve([])
    return apiFetch(`/workspaces/${workspaceId}/tasks?project_id=${projectId}`, {}, token)
  },

  // Contact CSV import
  importContactsCsv: (workspaceId: string, file: File, token: string): Promise<{ imported: number; skipped: number; errors: string[] }> => {
    if (isDemoMode) return Promise.resolve({ imported: 0, skipped: 0, errors: ['Demo mode: import not available'] })
    const form = new FormData()
    form.append('file', file)
    return apiFetch(`/workspaces/${workspaceId}/contacts/import`, { method: 'POST', body: form }, token, true)
  },

  // Contact merge
  mergeContacts: (workspaceId: string, data: { primary_id: string; duplicate_id: string }, token: string): Promise<{ primary_id: string; duplicate_id: string; tasks_reassigned: number; messages_reassigned: number; deals_reassigned: number }> => {
    if (isDemoMode) return Promise.resolve({ primary_id: data.primary_id, duplicate_id: data.duplicate_id, tasks_reassigned: 0, messages_reassigned: 0, deals_reassigned: 1 })
    return apiFetch(`/workspaces/${workspaceId}/contacts/merge`, { method: 'POST', body: JSON.stringify(data) }, token)
  },

  // Bulk contact delete
  bulkContactAction: (workspaceId: string, data: { action: 'delete'; contact_ids: string[] }, token: string): Promise<{ action: string; deleted: number; contact_ids: string[] }> => {
    if (isDemoMode) return Promise.resolve({ action: data.action, deleted: data.contact_ids.length, contact_ids: data.contact_ids })
    return apiFetch(`/workspaces/${workspaceId}/contacts/bulk`, { method: 'POST', body: JSON.stringify(data) }, token)
  },

  // Deal forecast
  getDealForecast: (workspaceId: string, token: string, monthsAhead = 6): Promise<{ month: string; value: number; deal_count: number }[]> => {
    if (isDemoMode) {
      const now = new Date()
      return Promise.resolve(
        Array.from({ length: monthsAhead }, (_, i) => {
          const d = new Date(now.getFullYear(), now.getMonth() + i, 1)
          const label = d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
          const seed = d.getMonth() + d.getFullYear()
          const value = [145000, 95000, 210000, 68000, 175000, 130000][i % 6]
          const deal_count = [2, 1, 3, 1, 2, 2][i % 6]
          return { month: label, value: Math.round(value + ((seed * 7919) % 30000) - 15000), deal_count }
        })
      )
    }
    return apiFetch(`/workspaces/${workspaceId}/deals/forecast?months_ahead=${monthsAhead}`, {}, token)
  },

  // Deal probability trend
  getDealProbabilityTrend: (workspaceId: string, dealId: string, token: string): Promise<{ date: string; probability: number }[]> => {
    if (isDemoMode) {
      const now = Date.now()
      return Promise.resolve(
        Array.from({ length: 20 }, (_, i) => {
          const dt = new Date(now - (19 - i) * 86400000)
          const frac = i / 19
          const jitter = ((dealId.charCodeAt(0) * (i + 1)) % 11) - 5
          return {
            date: dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
            probability: Math.max(5, Math.min(95, Math.round(25 + 45 * frac + jitter))),
          }
        })
      )
    }
    return apiFetch(`/workspaces/${workspaceId}/deals/${dealId}/probability-trend`, {}, token)
  },

  // Global search across contacts, deals, and tasks
  globalSearch: (workspaceId: string, q: string, token: string): Promise<{
    contacts: Array<{ id: string; name: string; email: string; company: string; role: string; status: string }>;
    deals: Array<{ id: string; title: string; company: string; value: number; stage: string }>;
    tasks: Array<{ id: string; title: string; status: string; due_date: string | null; contact_id: string | null }>;
  }> => {
    if (isDemoMode) {
      const lq = q.toLowerCase()
      const contacts = demoContacts
        .filter(c =>
          c.name.toLowerCase().includes(lq) ||
          (c.company ?? '').toLowerCase().includes(lq) ||
          (c.email ?? '').toLowerCase().includes(lq)
        )
        .slice(0, 5)
        .map(c => ({ id: c.id, name: c.name, email: c.email ?? '', company: c.company ?? '', role: c.role ?? '', status: c.status }))
      const deals = (demoDeals as unknown as Array<Record<string, unknown>>)
        .filter(d => ((d.title as string) ?? '').toLowerCase().includes(lq) || ((d.company as string) ?? '').toLowerCase().includes(lq))
        .slice(0, 5)
        .map(d => ({ id: d.id as string, title: (d.title as string) ?? '', company: (d.company as string) ?? '', value: (d.value as number) ?? 0, stage: (d.stage as string) ?? '' }))
      const tasks = (demoTasks as unknown as Array<Record<string, unknown>>)
        .filter(t => ((t.title as string) ?? '').toLowerCase().includes(lq))
        .slice(0, 5)
        .map(t => ({ id: t.id as string, title: (t.title as string) ?? '', status: (t.status as string) ?? 'open', due_date: (t.due_date as string) ?? null, contact_id: (t.contact_id as string) ?? null }))
      return Promise.resolve({ contacts, deals, tasks })
    }
    return apiFetch(`/workspaces/${workspaceId}/search?q=${encodeURIComponent(q)}&limit=5`, {}, token)
  },

  // AI query
  aiQuery: (workspaceId: string, query: string, token: string) => {
    if (isDemoMode) return Promise.resolve({
      answer: `Nova here. Across your 5 open deals ($517K in pipeline), two need attention this week. The Global Finance Enterprise Suite deal ($250K, Proposal) is your biggest risk — health score 35, stalled 21 days with no reply to the last two follow-ups. ScalePath Japan Starter ($18K, Discovery) is lower at 22 but earlier-stage. I'd prioritize re-engaging Marcus Rivera at Global Finance — open his Pre-Meeting Brief for a ready-made re-engagement plan. You can also check the full Deal Health Alerts on /dashboard.`
    })
    return apiFetch(`/workspaces/${workspaceId}/ai/query`, { method: 'POST', body: JSON.stringify({ query }) }, token)
  },

  // ─── Life / Accountability ledger ───────────────────────────────────────────
  // Daily KPI snapshots pushed by the local collector. Optional date-range /
  // domain / metric filters map straight to query params.
  getKpi: (
    workspaceId: string,
    token: string,
    opts?: { fromDate?: string; toDate?: string; domain?: string; metric?: string },
  ): Promise<KpiSnapshot[]> => {
    if (isDemoMode) return Promise.resolve(demoKpiSnapshots(opts))
    const params = new URLSearchParams()
    if (opts?.fromDate) params.set('from_date', opts.fromDate)
    if (opts?.toDate) params.set('to_date', opts.toDate)
    if (opts?.domain) params.set('domain', opts.domain)
    if (opts?.metric) params.set('metric', opts.metric)
    const qs = params.toString()
    return apiFetch(`/workspaces/${workspaceId}/kpi${qs ? `?${qs}` : ''}`, {}, token)
  },

  // Commitments list, newest first. Optional status / kind / declared_at window.
  getCommitments: (
    workspaceId: string,
    token: string,
    opts?: { status?: string; kind?: string; since?: string; until?: string },
  ): Promise<Commitment[]> => {
    if (isDemoMode) return Promise.resolve(demoCommitments(opts))
    const params = new URLSearchParams()
    if (opts?.status) params.set('status', opts.status)
    if (opts?.kind) params.set('kind', opts.kind)
    if (opts?.since) params.set('since', opts.since)
    if (opts?.until) params.set('until', opts.until)
    const qs = params.toString()
    return apiFetch(`/workspaces/${workspaceId}/commitments${qs ? `?${qs}` : ''}`, {}, token)
  },

  // Per ISO-week kept/broken rollup over the last `weeks` weeks (one row per week,
  // zero-filled by the API; kept_rate is null on weeks with no scored outcomes).
  getCommitmentStats: (
    workspaceId: string,
    token: string,
    weeks = 12,
  ): Promise<CommitmentWeekStats[]> => {
    if (isDemoMode) return Promise.resolve(demoCommitmentStats(weeks))
    return apiFetch(`/workspaces/${workspaceId}/commitments/stats?weeks=${weeks}`, {}, token)
  },

  // Idempotent create-or-update keyed on external_id. Used by the "declare a
  // commitment" form (kind 'explicit') and by the retro harvest (kind 'auto').
  upsertCommitmentByExternal: (
    workspaceId: string,
    externalId: string,
    data: {
      title: string
      kind?: string
      source?: string | null
      declared_at: string
      due_date?: string | null
      status?: string | null
      evidence?: string | null
      scored_at?: string | null
    },
    token: string,
  ): Promise<{ commitment: Commitment; created: boolean }> => {
    if (isDemoMode) {
      return Promise.resolve({
        commitment: {
          id: `demo-commitment-${Date.now()}`,
          workspace_id: workspaceId,
          external_id: externalId,
          title: data.title,
          kind: data.kind ?? 'auto',
          source: data.source ?? null,
          declared_at: data.declared_at,
          due_date: data.due_date ?? null,
          status: data.status ?? 'open',
          evidence: data.evidence ?? null,
          scored_at: data.scored_at ?? null,
        },
        created: true,
      })
    }
    return apiFetch(
      `/workspaces/${workspaceId}/commitments/by-external/${encodeURIComponent(externalId)}`,
      { method: 'PUT', body: JSON.stringify(data) },
      token,
    )
  },

  // Partial update of a single commitment (e.g. status='dropped').
  patchCommitment: (
    workspaceId: string,
    commitmentId: string,
    data: { title?: string; status?: string; evidence?: string; scored_at?: string; due_date?: string },
    token: string,
  ): Promise<Commitment> => {
    if (isDemoMode) return Promise.resolve({ id: commitmentId, ...data } as unknown as Commitment)
    return apiFetch(
      `/workspaces/${workspaceId}/commitments/${commitmentId}`,
      { method: 'PATCH', body: JSON.stringify(data) },
      token,
    )
  },
}
