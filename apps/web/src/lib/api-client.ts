import { demoMessages, demoTasks, demoConnectors } from './demo-data'

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
  triggerAgent: (agentId: string, token: string) => {
    if (isDemoMode) return Promise.resolve({ job_id: `demo-job-${agentId}` })
    return apiFetch(`/agents/${agentId}/run`, { method: 'POST' }, token)
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

  // Contacts
  composeEmail: (workspaceId: string, contactId: string, token: string) => {
    if (isDemoMode) {
      return Promise.resolve({
        subject: 'Re: Partnership Opportunity',
        body: 'Hi,\n\nThank you for reaching out about the enterprise plan. Based on what you shared, I believe we can deliver exactly the outcome you\'re looking for.\n\nI\'d love to schedule a 30-minute call this week to walk through our approach and answer any questions your team may have.\n\nWould Thursday at 3pm or Friday at 10am work for you?\n\nLooking forward to connecting.\n\nBest regards,\nThe Acme Corp Team',
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
    if (isDemoMode) return Promise.resolve({
      contact_id: contactId,
      contact_name: 'Demo Contact',
      brief: `**Who they are**\nJames Whitfield is the Head of Procurement at TechCorp, with 12 years in enterprise software buying. He prioritizes ROI and vendor reliability over features.\n\n**Current deal status & risks**\nThe TechCorp Enterprise deal (Negotiation, $48K) has stalled for 24 days. Legal review is pending and James has been less responsive over the past week — a churn signal.\n\n**Conversation highlights**\n- Last email discussed SLA terms and uptime guarantees\n- Call on 2024-05-02 confirmed strong interest but flagged a competing vendor\n\n**Recommended talking points**\n- Lead with the 99.9% SLA and reference customer success stories\n- Address the competitor by focusing on integration depth\n- Propose a 30-day pilot to de-risk the decision\n\n**Watch-out signals**\n- Delayed responses may indicate internal prioritization shift\n- Legal review duration suggests committee buy-in needed — ask for a champion`
    })
    return apiFetch(`/workspaces/${workspaceId}/contacts/${contactId}/brief`, { method: 'POST' }, token)
  },

  getContactTimeline: (workspaceId: string, contactId: string, token: string) => {
    if (isDemoMode) return Promise.resolve([
      { id: 'evt-1', type: 'message', title: 'Re: Partnership Opportunity', body: 'Thank you for reaching out...', ts: new Date(Date.now() - 86400000).toISOString(), meta: { sender: 'contact@example.com' } },
      { id: 'evt-2', type: 'deal_stage', title: 'Deal: Enterprise Expansion', body: 'Stage: proposal · Value: $48,000', ts: new Date(Date.now() - 172800000).toISOString(), meta: { stage: 'proposal', value: 48000 } },
      { id: 'evt-3', type: 'activity', title: 'email_sent', body: 'Email sent to contact@example.com: Re: Partnership Opportunity', ts: new Date(Date.now() - 3600000).toISOString(), meta: { agent_name: 'Gmail', severity: 'success' } },
    ])
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
          return { month: abbr[d.getMonth()], revenue: Math.round(50000 + Math.random() * 100000) }
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

  inviteTeammate: (workspaceId: string, email: string, token: string) => {
    if (isDemoMode) return Promise.resolve({ status: 'invited', email })
    return apiFetch(`/workspaces/${workspaceId}/invite`, { method: 'POST', body: JSON.stringify({ email }) }, token)
  },

  // AI query
  aiQuery: (workspaceId: string, query: string, token: string) => {
    if (isDemoMode) return Promise.resolve({
      answer: `Nova here. Your pipeline looks healthy — 6 active deals, $1.2M in value. The TechCorp deal in Negotiation has a health score of 32, meaning it hasn't moved in a while. I'd suggest reaching out to James Whitfield to re-engage. You can use the AI Search on /contacts to find similar prospects, or check the Deal Health Alerts on /dashboard for a full stale-deal view.`
    })
    return apiFetch(`/workspaces/${workspaceId}/ai/query`, { method: 'POST', body: JSON.stringify({ query }) }, token)
  },
}
