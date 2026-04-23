const FASTAPI_URL = process.env.NEXT_PUBLIC_FASTAPI_URL || 'http://localhost:8000'

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
  triggerAgent: (agentId: string, token: string) =>
    apiFetch(`/agents/${agentId}/run`, { method: 'POST' }, token),

  // Connectors
  getConnectors: (workspaceId: string, token: string) =>
    apiFetch(`/workspaces/${workspaceId}/connectors`, {}, token),
  getGmailAuthUrl: (workspaceId: string, token: string) =>
    apiFetch(`/workspaces/${workspaceId}/connectors/gmail/auth`, {}, token),
  triggerGmailSync: (workspaceId: string, token: string) =>
    apiFetch(`/workspaces/${workspaceId}/connectors/gmail/sync`, { method: 'POST' }, token),
  deleteConnector: (workspaceId: string, connectorId: string, token: string) =>
    apiFetch(`/workspaces/${workspaceId}/connectors/${connectorId}`, { method: 'DELETE' }, token),

  // Messages
  getMessages: (workspaceId: string, token: string) =>
    apiFetch(`/workspaces/${workspaceId}/messages`, {}, token),

  // Tasks
  getTasks: (workspaceId: string, token: string) =>
    apiFetch(`/workspaces/${workspaceId}/tasks`, {}, token),
  createTask: (workspaceId: string, data: Record<string, unknown>, token: string) =>
    apiFetch(`/workspaces/${workspaceId}/tasks`, { method: 'POST', body: JSON.stringify(data) }, token),
  updateTask: (workspaceId: string, taskId: string, data: Record<string, unknown>, token: string) =>
    apiFetch(`/workspaces/${workspaceId}/tasks/${taskId}`, { method: 'PUT', body: JSON.stringify(data) }, token),

  // Contacts
  composeEmail: (workspaceId: string, contactId: string, token: string) =>
    apiFetch(`/workspaces/${workspaceId}/contacts/${contactId}/compose`, { method: 'POST' }, token),
  scoreContact: (workspaceId: string, contactId: string, token: string) =>
    apiFetch(`/workspaces/${workspaceId}/contacts/${contactId}/score`, { method: 'POST' }, token),
}
