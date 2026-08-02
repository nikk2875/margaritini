const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api'

export type NodeType = 'goal' | 'action'
export type Node = { id: string; project_id: string; parent_id: string | null; node_type: NodeType; text: string; description: string; canvas_x: number; canvas_y: number }
export type Edge = { id: string; project_id: string; predecessor_id: string; successor_id: string }
export type Project = { id: string; name: string }
export type ProjectExport = { format_version: 1; name: string; nodes: (Omit<Node, 'project_id'>)[]; dependencies: { predecessor_id: string; successor_id: string }[]; tasks: Task[]; task_settings: { action_id: string; display_style: 'numbered' | 'bulleted' }[] }
export type Task = { id: string; action_id: string; text: string; is_completed: boolean; position: number }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? 'Request failed')
  return response.status === 204 ? undefined as T : response.json()
}
export const api = {
  projects: () => request<Project[]>('/projects'),
  createProject: (name: string) => request<Project>('/projects', { method: 'POST', body: JSON.stringify({ name }) }),
  updateProject: (id: string, name: string) => request<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
  exportProject: (id: string) => request<ProjectExport>(`/projects/${id}/export`),
  importProject: (data: ProjectExport) => request<Project>('/projects/import', { method: 'POST', body: JSON.stringify(data) }),
  nodes: (projectId: string) => request<Node[]>(`/projects/${projectId}/nodes`),
  createNode: (projectId: string, body: Partial<Node> & { text: string }) => request<Node>(`/projects/${projectId}/nodes`, { method: 'POST', body: JSON.stringify(body) }),
  updateNode: (id: string, body: Partial<Node>) => request<Node>(`/nodes/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteNode: (id: string) => request<void>(`/nodes/${id}`, { method: 'DELETE' }),
  convert: (id: string, action: boolean) => request<Node>(`/nodes/${id}/convert-to-${action ? 'action' : 'goal'}`, { method: 'POST' }),
  edges: (projectId: string) => request<Edge[]>(`/projects/${projectId}/dependencies`),
  createEdge: (projectId: string, predecessor_id: string, successor_id: string) => request<Edge>(`/projects/${projectId}/dependencies`, { method: 'POST', body: JSON.stringify({ predecessor_id, successor_id }) }),
  deleteEdge: (id: string) => request<void>(`/dependencies/${id}`, { method: 'DELETE' }),
  tasks: (id: string) => request<Task[]>(`/actions/${id}/tasks`),
  createTask: (id: string, text: string) => request<Task>(`/actions/${id}/tasks`, { method: 'POST', body: JSON.stringify({ text }) }),
  updateTask: (id: string, body: Partial<Task>) => request<Task>(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteTask: (id: string) => request<void>(`/tasks/${id}`, { method: 'DELETE' }),
  reorderTasks: (id: string, task_ids: string[]) => request<Task[]>(`/actions/${id}/tasks/reorder`, { method: 'PUT', body: JSON.stringify({ task_ids }) }),
  taskStyle: (id: string) => request<{ display_style: 'numbered' | 'bulleted' }>(`/actions/${id}/task-settings`),
  setTaskStyle: (id: string, display_style: 'numbered' | 'bulleted') => request(`/actions/${id}/task-settings`, { method: 'PUT', body: JSON.stringify({ display_style }) }),
}
