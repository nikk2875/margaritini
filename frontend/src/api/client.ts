const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api'
const API_TOKEN = import.meta.env.VITE_API_TOKEN as string | undefined

export type NodeType = 'goal' | 'action'
export type TaskStyle = 'numbered' | 'bulleted'
export type Node = {
  id: string
  project_id: string
  parent_id: string | null
  node_type: NodeType
  text: string
  description: string
  canvas_x: number
  canvas_y: number
}
export type Edge = { id: string; project_id: string; predecessor_id: string; successor_id: string }
export type Project = { id: string; name: string }
export type Task = { id: string; action_id: string; text: string; is_completed: boolean; position: number }
export type ProjectExport = {
  format_version: 1
  name: string
  nodes: Omit<Node, 'project_id'>[]
  dependencies: { predecessor_id: string; successor_id: string }[]
  tasks: Task[]
  task_settings: { action_id: string; display_style: TaskStyle }[]
}

function headers(): Record<string, string> {
  const value: Record<string, string> = { 'Content-Type': 'application/json' }
  if (API_TOKEN) value['X-Margaritini-Token'] = API_TOKEN
  return value
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, { headers: headers(), ...init })
  if (!response.ok) {
    const detail = (await response.json().catch(() => null))?.detail
    throw new Error(typeof detail === 'string' ? detail : 'Request failed')
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

const project = (projectId: string) => `/projects/${encodeURIComponent(projectId)}`
const nodePath = (projectId: string, nodeId: string) => `${project(projectId)}/nodes/${encodeURIComponent(nodeId)}`
const actionPath = (projectId: string, actionId: string) => `${project(projectId)}/actions/${encodeURIComponent(actionId)}`

export const api = {
  projects: () => request<Project[]>('/projects'),
  createProject: (name: string) => request<Project>('/projects', { method: 'POST', body: JSON.stringify({ name }) }),
  updateProject: (id: string, name: string) => request<Project>(project(id), { method: 'PATCH', body: JSON.stringify({ name }) }),
  deleteProject: (id: string) => request<void>(project(id), { method: 'DELETE' }),
  exportProject: (id: string) => request<ProjectExport>(`${project(id)}/export`),
  importProject: (data: ProjectExport) => request<Project>('/projects/import', { method: 'POST', body: JSON.stringify(data) }),

  nodes: (projectId: string) => request<Node[]>(`${project(projectId)}/nodes`),
  createNode: (projectId: string, body: Partial<Node> & { text: string }) =>
    request<Node>(`${project(projectId)}/nodes`, { method: 'POST', body: JSON.stringify(body) }),
  updateNode: (projectId: string, id: string, body: Partial<Node>) =>
    request<Node>(nodePath(projectId, id), { method: 'PATCH', body: JSON.stringify(body) }),
  deleteNode: (projectId: string, id: string) => request<void>(nodePath(projectId, id), { method: 'DELETE' }),
  convert: (projectId: string, id: string, toAction: boolean) =>
    request<Node>(`${nodePath(projectId, id)}/convert-to-${toAction ? 'action' : 'goal'}`, { method: 'POST' }),

  edges: (projectId: string) => request<Edge[]>(`${project(projectId)}/dependencies`),
  createEdge: (projectId: string, predecessor_id: string, successor_id: string) =>
    request<Edge>(`${project(projectId)}/dependencies`, { method: 'POST', body: JSON.stringify({ predecessor_id, successor_id }) }),
  reverseEdge: (projectId: string, id: string) =>
    request<Edge>(`${project(projectId)}/dependencies/${encodeURIComponent(id)}/reverse`, { method: 'POST' }),
  deleteEdge: (projectId: string, id: string) =>
    request<void>(`${project(projectId)}/dependencies/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  tasks: (projectId: string, actionId: string) => request<Task[]>(`${actionPath(projectId, actionId)}/tasks`),
  createTask: (projectId: string, actionId: string, text: string) =>
    request<Task>(`${actionPath(projectId, actionId)}/tasks`, { method: 'POST', body: JSON.stringify({ text }) }),
  updateTask: (projectId: string, id: string, body: Partial<Task>) =>
    request<Task>(`${project(projectId)}/tasks/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteTask: (projectId: string, id: string) =>
    request<void>(`${project(projectId)}/tasks/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  reorderTasks: (projectId: string, actionId: string, task_ids: string[]) =>
    request<Task[]>(`${actionPath(projectId, actionId)}/tasks/reorder`, { method: 'PUT', body: JSON.stringify({ task_ids }) }),
  taskStyle: (projectId: string, actionId: string) =>
    request<{ display_style: TaskStyle }>(`${actionPath(projectId, actionId)}/task-settings`),
  setTaskStyle: (projectId: string, actionId: string, display_style: TaskStyle) =>
    request<{ display_style: TaskStyle }>(`${actionPath(projectId, actionId)}/task-settings`, { method: 'PUT', body: JSON.stringify({ display_style }) }),
}
