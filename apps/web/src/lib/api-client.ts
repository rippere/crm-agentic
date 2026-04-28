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
}
