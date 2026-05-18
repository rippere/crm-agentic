import { demoMessages, demoTasks, demoConnectors, demoDeals, demoContacts } from './demo-data'

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

const FASTAPI_URL = process.env.NEXT_PUBLIC_FASTAPI_URL || 'http://localhost:8000'
const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE === 'true'

async function apiFetch(path: string, options: RequestInit = {}, token?: string) {
  const res = await fetch(`${FASTAPI_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (!res.ok) throw new Error(`API error ${res.status}`)
  return res.json()
}

export const apiClient = {
  // Agents
  listAgents: (token: string) => {
    if (isDemoMode) return Promise.resolve([])
    return apiFetch('/agents', {}, token)
  },
  triggerAgent: (agentId: string, token: string) => {
    if (isDemoMode) return Promise.resolve({ job_id: `demo-job-${agentId}` })
    return apiFetch(`/agents/${agentId}/run`, { method: 'POST' }, token)
  },
  updateAgent: (agentId: string, data: { status?: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: agentId, ...data })
    return apiFetch(`/agents/${agentId}`, { method: 'PATCH', body: JSON.stringify(data) }, token)
  },

  // Connectors
  getConnectors: (workspaceId: string, token: string) => {
    if (isDemoMode) return Promise.resolve(demoConnectors)
    return apiFetch(`/workspaces/${workspaceId}/connectors`, {}, token)
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

  // Tasks
  getTasks: (workspaceId: string, token: string) => {
    if (isDemoMode) return Promise.resolve(demoTasks)
    return apiFetch(`/workspaces/${workspaceId}/tasks`, {}, token)
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
  listDeals: (workspaceId: string, token: string, stage?: string) => {
    if (isDemoMode) return Promise.resolve(demoDeals)
    const params = stage && stage !== 'all' ? `?stage=${stage}` : ''
    return apiFetch(`/workspaces/${workspaceId}/deals${params}`, {}, token)
  },
  createDeal: (workspaceId: string, data: { title?: string; company?: string; contact_id?: string; value?: number; stage?: string; ml_win_probability?: number; expected_close?: string; notes?: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: `demo-deal-${Date.now()}`, workspace_id: workspaceId, stage: 'lead', ...data })
    return apiFetch(`/workspaces/${workspaceId}/deals`, { method: 'POST', body: JSON.stringify(data) }, token)
  },
  getDeal: (workspaceId: string, dealId: string, token: string) => {
    if (isDemoMode) return Promise.resolve(null)
    return apiFetch(`/workspaces/${workspaceId}/deals/${dealId}`, {}, token)
  },
  updateDeal: (workspaceId: string, dealId: string, data: { title?: string; company?: string; value?: number; stage?: string; ml_win_probability?: number; expected_close?: string; notes?: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: dealId, ...data })
    return apiFetch(`/workspaces/${workspaceId}/deals/${dealId}`, { method: 'PATCH', body: JSON.stringify(data) }, token)
  },
  deleteDeal: (workspaceId: string, dealId: string, token: string) => {
    if (isDemoMode) return Promise.resolve()
    return apiFetch(`/workspaces/${workspaceId}/deals/${dealId}`, { method: 'DELETE' }, token)
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
    if (isDemoMode) return Promise.resolve([])
    const params = new URLSearchParams({ q: query, limit: '15' })
    return apiFetch(`/workspaces/${workspaceId}/contacts/search?${params}`, {}, token)
  },
  triggerEmbedContacts: (workspaceId: string, token: string) => {
    if (isDemoMode) return Promise.resolve({ job_id: 'demo-embed', status: 'queued' })
    return apiFetch(`/workspaces/${workspaceId}/contacts/embed`, { method: 'POST' }, token)
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
  listActivity: (workspaceId: string, token: string, limit = 50) => {
    if (isDemoMode) return Promise.resolve([])
    return apiFetch(`/workspaces/${workspaceId}/activity?limit=${limit}`, {}, token)
  },
  createActivity: (workspaceId: string, data: { type: string; agent_name: string; description: string; meta?: string; severity?: string }, token: string) => {
    if (isDemoMode) return Promise.resolve({ id: `demo-activity-${Date.now()}`, ...data })
    return apiFetch(`/workspaces/${workspaceId}/activity`, { method: 'POST', body: JSON.stringify(data) }, token)
  },

  // AI query
  aiQuery: (workspaceId: string, query: string, token: string) => {
    if (isDemoMode) return Promise.resolve({
      answer: `Nova here. Your pipeline looks healthy — 6 active deals, $1.2M in value. The TechCorp deal in Negotiation has a health score of 32, meaning it hasn't moved in a while. I'd suggest reaching out to James Whitfield to re-engage. You can use the AI Search on /contacts to find similar prospects, or check the Deal Health Alerts on /dashboard for a full stale-deal view.`
    })
    return apiFetch(`/workspaces/${workspaceId}/ai/query`, { method: 'POST', body: JSON.stringify({ query }) }, token)
  },
}
