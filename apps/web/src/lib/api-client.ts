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
  triggerAgent: (agentId: string, token: string) =>
    apiFetch(`/agents/${agentId}/run`, { method: 'POST' }, token),
  getMessages: (workspaceId: string, token: string) =>
    apiFetch(`/workspaces/${workspaceId}/messages`, {}, token),
  getTasks: (workspaceId: string, token: string) =>
    apiFetch(`/workspaces/${workspaceId}/tasks`, {}, token),
}
