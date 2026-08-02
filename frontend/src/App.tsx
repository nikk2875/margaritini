import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Background,
  Controls,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node as FlowNode,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { api, type Node, type Project, type Task } from './api/client'
import './App.css'

const toFlowNode = (node: Node): FlowNode => ({
  id: node.id,
  position: { x: node.canvas_x, y: node.canvas_y },
  data: { label: node.text },
  className: node.node_type === 'action' ? 'action-node' : node.parent_id ? 'secondary-goal-node' : 'primary-goal-node',
})

function App() {
  const [project, setProject] = useState<Project | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [domainNodes, setDomainNodes] = useState<Node[]>([])
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<FlowNode>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null)
  const [planName, setPlanName] = useState('')
  const [editingPlanName, setEditingPlanName] = useState(false)
  const [tasks, setTasks] = useState<Task[]>([])
  const [error, setError] = useState('')
  const [printPlan, setPrintPlan] = useState(false)
  const [planTasks, setPlanTasks] = useState<Record<string, Task[]>>({})
  const [planTaskStyles, setPlanTaskStyles] = useState<Record<string, 'numbered' | 'bulleted'>>({})
  const importInput = useRef<HTMLInputElement>(null)
  const activeProjectId = useRef<string | null>(null)
  const containmentEdges = useMemo(() => domainNodes.filter((node) => node.parent_id).map((node) => ({ id: `containment-${node.id}`, source: node.parent_id!, target: node.id, type: 'smoothstep', selectable: false, focusable: false, style: { stroke: '#98a2b3', strokeDasharray: '5 5' } })), [domainNodes])

  const load = useCallback(async (projectId?: string) => {
    try {
      // A project is created for a new installation, but never seeded with nodes.
      let available = await api.projects()
      const targetId = projectId ?? activeProjectId.current
      let first = targetId ? available.find((item) => item.id === targetId) : available[0]
      if (!first && available.length) first = available[0]
      if (!first) { first = await api.createProject('Untitled plan'); available = [first, ...available] }
      const [loadedNodes, loadedEdges] = await Promise.all([api.nodes(first.id), api.edges(first.id)])
      setProjects(available)
      activeProjectId.current = first.id
      setProject(first)
      setDomainNodes(loadedNodes)
      setFlowNodes(loadedNodes.map(toFlowNode))
      setEdges(loadedEdges.map((edge) => ({ id: edge.id, source: edge.predecessor_id, target: edge.successor_id, markerEnd: { type: 'arrowclosed' } })))
      setError('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to connect to the API')
    }
  }, [setEdges, setFlowNodes])

  useEffect(() => { void load() }, [load])
  useEffect(() => { setPlanName(project?.name ?? ''); setEditingPlanName(false) }, [project])
  const selected = useMemo(() => domainNodes.find((node) => node.id === selectedId) ?? null, [domainNodes, selectedId])
  const selectedEdge = useMemo(() => edges.find((edge) => edge.id === selectedEdgeId) ?? null, [edges, selectedEdgeId])
  useEffect(() => {
    if (selected?.node_type === 'action') void api.tasks(selected.id).then(setTasks).catch((cause) => setError(cause.message))
    else setTasks([])
  }, [selected])

  const addNode = async () => {
    if (!project) return
    try {
      const anchor = domainNodes.length ? domainNodes.reduce((total, item) => ({ x: total.x + item.canvas_x, y: total.y + item.canvas_y }), { x: 0, y: 0 }) : { x: -10, y: 50 }
      const node = await api.createNode(project.id, {
        text: 'Untitled primary goal', node_type: 'goal',
        canvas_x: anchor.x / Math.max(domainNodes.length, 1) + 170, canvas_y: anchor.y / Math.max(domainNodes.length, 1) + 70,
      })
      setDomainNodes((current) => [...current, node])
      setFlowNodes((current) => [...current, toFlowNode(node)])
      setSelectedId(node.id)
      setSelectedEdgeId(null)
      setError('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create goal') }
  }

  const addSecondaryGoal = async (parent: Node) => {
    if (!project) return
    try {
      const node = await api.createNode(project.id, {
        text: 'Untitled secondary goal', node_type: 'goal', parent_id: parent.id,
        canvas_x: parent.canvas_x + 180, canvas_y: parent.canvas_y + 70,
      })
      setDomainNodes((current) => [...current, node])
      setFlowNodes((current) => [...current, toFlowNode(node)])
      setSelectedId(node.id)
      setError('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create secondary goal') }
  }

  const addAction = async (parent: Node) => {
    if (!project) return
    try {
      const node = await api.createNode(project.id, {
        text: 'Untitled action', node_type: 'action', parent_id: parent.id,
        canvas_x: parent.canvas_x + 170, canvas_y: parent.canvas_y + 100,
      })
      setDomainNodes((current) => [...current, node])
      setFlowNodes((current) => [...current, toFlowNode(node)])
      setSelectedId(node.id)
      setError('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create action') }
  }

  const onConnect = async (connection: Connection) => {
    if (!project || !connection.source || !connection.target) return
    try {
      const edge = await api.createEdge(project.id, connection.source, connection.target)
      setEdges((current) => addEdge({ id: edge.id, ...connection, markerEnd: { type: 'arrowclosed' } }, current))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create dependency') }
  }

  const deleteConnection = async (edge: Edge) => {
    try {
      await api.deleteEdge(edge.id)
      setEdges((current) => current.filter((item) => item.id !== edge.id))
      setSelectedEdgeId(null)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not delete connection') }
  }

  const reverseConnection = async (edge: Edge) => {
    if (!project) return
    try {
      await api.deleteEdge(edge.id)
      let replacement
      try { replacement = await api.createEdge(project.id, edge.target, edge.source) }
      catch (cause) {
        await api.createEdge(project.id, edge.source, edge.target).catch(() => undefined)
        await load()
        throw cause
      }
      setEdges((current) => current.map((item) => item.id === edge.id ? { id: replacement.id, source: replacement.predecessor_id, target: replacement.successor_id, markerEnd: { type: 'arrowclosed' } } : item))
      setSelectedEdgeId(replacement.id)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not reverse connection') }
  }

  const persistPosition = async (_: unknown, node: FlowNode) => {
    try {
      await api.updateNode(node.id, { canvas_x: node.position.x, canvas_y: node.position.y })
      setDomainNodes((current) => current.map((item) => item.id === node.id ? { ...item, canvas_x: node.position.x, canvas_y: node.position.y } : item))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save node position') }
  }

  const createProject = async () => {
    const name = prompt('Project name', 'Untitled plan')
    if (!name?.trim()) return
    try { const created = await api.createProject(name.trim()); await load(created.id) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create project') }
  }

  const deleteProject = async () => {
    if (!project || !confirm(`Delete project “${project.name}” and all of its contents?`)) return
    try { await api.deleteProject(project.id); await load() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not delete project') }
  }

  const exportProject = async () => {
    if (!project) return
    try {
      const data = await api.exportProject(project.id)
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
      const link = document.createElement('a')
      link.href = url
      link.download = `${project.name.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'project'}.json`
      link.click()
      URL.revokeObjectURL(url)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not export project') }
  }

  const importProject = async (file: File | undefined) => {
    if (!file) return
    try {
      const created = await api.importProject(JSON.parse(await file.text()))
      await load(created.id)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load project file') }
  }

  const openPrintPlan = async () => {
    try {
      const actions = domainNodes.filter((node) => node.node_type === 'action')
      const taskLists = await Promise.all(actions.map(async (action) => [action.id, await api.tasks(action.id), (await api.taskStyle(action.id)).display_style] as const))
      setPlanTasks(Object.fromEntries(taskLists.map(([id, actionTasks]) => [id, actionTasks])))
      setPlanTaskStyles(Object.fromEntries(taskLists.map(([id, , style]) => [id, style])))
      setPrintPlan(true)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create project plan') }
  }

  const savePlanName = async () => {
    if (!project || !planName.trim()) return
    try { const updated = await api.updateProject(project.id, planName.trim()); setProject(updated); setProjects((current) => current.map((item) => item.id === updated.id ? updated : item)); setEditingPlanName(false) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not rename plan') }
  }

  return <main>
    <header><strong>Task Planner</strong><select className="project-picker" value={project?.id ?? ''} onChange={(event) => void load(event.target.value)}>{projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{editingPlanName ? <input className="plan-name-input" autoFocus value={planName} onChange={(event) => setPlanName(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void savePlanName(); if (event.key === 'Escape') { setPlanName(project?.name ?? ''); setEditingPlanName(false) } }} /> : <button className="plan-name-button" onClick={() => setEditingPlanName(true)}>{project?.name ?? 'Loading…'}</button>}<div className="project-actions"><button onClick={() => void createProject()}>New project</button><button onClick={() => void exportProject()}>Export project</button><button onClick={() => importInput.current?.click()}>Load project</button><input ref={importInput} className="file-input" type="file" accept="application/json,.json" onChange={(event) => { void importProject(event.target.files?.[0]); event.target.value = '' }} /><button className="delete-project" onClick={() => void deleteProject()}>Delete project</button></div><button onClick={() => void addNode()}>Add primary goal</button><button onClick={() => void openPrintPlan()}>Print plan</button></header>
    {error && <p className="error">{error}</p>}
    <section className="workspace">{printPlan ? <PlanView project={project} nodes={domainNodes} edges={edges} tasks={planTasks} taskStyles={planTaskStyles} close={() => setPrintPlan(false)} /> : <><div className="canvas"><ReactFlow nodes={flowNodes} edges={[...containmentEdges, ...edges]} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} onNodeClick={(_, node) => { setSelectedId(node.id); setSelectedEdgeId(null) }} onEdgeClick={(_, edge) => { if (!edge.id.startsWith('containment-')) { setSelectedId(null); setSelectedEdgeId(edge.id) } }} onPaneClick={() => { setSelectedId(null); setSelectedEdgeId(null) }} onNodeDragStop={persistPosition} fitView><Background /><Controls /></ReactFlow></div><aside className="right-pane">{selected ? <Detail node={selected} tasks={tasks} refresh={load} reloadTasks={() => api.tasks(selected.id).then(setTasks)} addSecondaryGoal={addSecondaryGoal} addAction={addAction} close={() => setSelectedId(null)} setError={setError} /> : selectedEdge && <ConnectionDetail edge={selectedEdge} reverse={reverseConnection} remove={deleteConnection} />}</aside></>}</section>
  </main>
}

function dependencyOrder(nodes: Node[], edges: Edge[]) {
  const ids = new Set(nodes.map((node) => node.id))
  const outgoing = new Map(nodes.map((node) => [node.id, [] as string[]]))
  const indegree = new Map(nodes.map((node) => [node.id, 0]))
  for (const edge of edges) if (ids.has(edge.source) && ids.has(edge.target)) { outgoing.get(edge.source)!.push(edge.target); indegree.set(edge.target, indegree.get(edge.target)! + 1) }
  const byName = (left: Node, right: Node) => left.text.localeCompare(right.text)
  const remaining = new Map(nodes.map((node) => [node.id, node]))
  const ordered: Node[] = []
  while (remaining.size) {
    const next = [...remaining.values()].filter((node) => indegree.get(node.id) === 0).sort(byName)[0] ?? [...remaining.values()].sort(byName)[0]
    ordered.push(next); remaining.delete(next.id)
    for (const target of outgoing.get(next.id) ?? []) indegree.set(target, indegree.get(target)! - 1)
  }
  return ordered
}

function PlanView({ project, nodes, edges, tasks, taskStyles, close }: { project: Project | null; nodes: Node[]; edges: Edge[]; tasks: Record<string, Task[]>; taskStyles: Record<string, 'numbered' | 'bulleted'>; close: () => void }) {
  const children = (parentId: string, type: 'goal' | 'action') => dependencyOrder(nodes.filter((node) => node.parent_id === parentId && node.node_type === type), edges)
  const primary = dependencyOrder(nodes.filter((node) => node.node_type === 'goal' && !node.parent_id), edges)
  const taskLines = (action: Node, indent: string) => (tasks[action.id] ?? []).map((task, index) => {
    const marker = taskStyles[action.id] === 'numbered' ? `${index + 1}.` : '-'
    return `${indent}${marker} ${task.is_completed ? `~~${task.text}~~` : task.text}`
  })
  const actionMarkdown = (action: Node, indent: string) => [`${indent}- ${action.text}`, ...taskLines(action, `${indent}  `)]
  const secondaryMarkdown = (goal: Node, indent: string) => [`${indent}- ${goal.text}`, ...(goal.description ? [`${indent}  ${goal.description}`] : []), ...children(goal.id, 'action').flatMap((action) => actionMarkdown(action, `${indent}  `))]
  const markdown = ['# ' + (project?.name ?? 'Project plan'), '', ...primary.flatMap((goal) => ['- ' + goal.text, ...(goal.description ? ['  ' + goal.description] : []), ...children(goal.id, 'goal').flatMap((secondary) => secondaryMarkdown(secondary, '  ')), ...children(goal.id, 'action').flatMap((action) => actionMarkdown(action, '  ')), ''])].join('\n')
  const exportMarkdown = () => { const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown' })); const link = document.createElement('a'); link.href = url; link.download = `${project?.name ?? 'project-plan'}.md`; link.click(); URL.revokeObjectURL(url) }
  const actionView = (action: Node) => <li key={action.id}><strong>{action.text}</strong>{(tasks[action.id] ?? []).length > 0 && (taskStyles[action.id] === 'numbered' ? <ol>{tasks[action.id].map((task) => <li className={task.is_completed ? 'completed' : ''} key={task.id}>{task.text}</li>)}</ol> : <ul>{tasks[action.id].map((task) => <li className={task.is_completed ? 'completed' : ''} key={task.id}>{task.text}</li>)}</ul>)}</li>
  const secondaryView = (goal: Node) => <li key={goal.id}><strong>{goal.text}</strong>{goal.description && <p>{goal.description}</p>}<ul>{children(goal.id, 'action').map(actionView)}</ul></li>
  return <div className="plan-view"><div className="plan-actions"><button onClick={close}>Back to canvas</button><button onClick={exportMarkdown}>Export Markdown</button></div><h1>{project?.name ?? 'Project plan'}</h1>{primary.length ? <ul>{primary.map((goal) => <li key={goal.id}><strong>{goal.text}</strong>{goal.description && <p>{goal.description}</p>}<ul>{children(goal.id, 'goal').map(secondaryView)}{children(goal.id, 'action').map(actionView)}</ul></li>)}</ul> : <p>No primary goals.</p>}</div>
}

function Detail({ node, tasks, refresh, reloadTasks, addSecondaryGoal, addAction, close, setError }: { node: Node; tasks: Task[]; refresh: () => Promise<void>; reloadTasks: () => Promise<void>; addSecondaryGoal: (parent: Node) => Promise<void>; addAction: (parent: Node) => Promise<void>; close: () => void; setError: (value: string) => void }) {
  const [text, setText] = useState(node.text)
  const [description, setDescription] = useState(node.description)
  const [editingTitle, setEditingTitle] = useState(false)
  const [taskText, setTaskText] = useState('')
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null)
  const [editingTaskText, setEditingTaskText] = useState('')
  const [style, setStyle] = useState<'numbered' | 'bulleted'>('bulleted')
  useEffect(() => { setText(node.text); setDescription(node.description); setEditingTitle(false); if (node.node_type === 'action') void api.taskStyle(node.id).then((settings) => setStyle(settings.display_style)) }, [node])
  const save = async () => { try { await api.updateNode(node.id, { text }); await refresh(); setEditingTitle(false) } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save node') } }
  const saveDescription = async () => { try { await api.updateNode(node.id, { description }); await refresh() } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save description') } }
  const remove = async () => { if (confirm(`Delete ${node.text} and all its children?`)) { await api.deleteNode(node.id); close(); await refresh() } }
  const addTask = async () => { if (!taskText.trim()) return; await api.createTask(node.id, taskText); setTaskText(''); await reloadTasks() }
  const saveTaskText = async (task: Task) => { if (!editingTaskText.trim()) return; await api.updateTask(task.id, { text: editingTaskText.trim() }); setEditingTaskId(null); await reloadTasks() }
  const reorderTask = async (index: number, direction: -1 | 1) => { const destination = index + direction; if (destination < 0 || destination >= tasks.length) return; const order = [...tasks]; [order[index], order[destination]] = [order[destination], order[index]]; await api.reorderTasks(node.id, order.map((task) => task.id)); await reloadTasks() }
  return <div className="detail"><button className="close" onClick={close}>×</button><label>Title{editingTitle ? <input autoFocus value={text} onChange={(event) => setText(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void save(); if (event.key === 'Escape') { setText(node.text); setEditingTitle(false) } }} /> : <button className="title-button" onClick={() => setEditingTitle(true)}>{text}</button>}</label>{node.node_type === 'goal' && <><label>Description<textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Add goal details" /></label><button onClick={() => void saveDescription()}>Save description</button></>}{node.node_type === 'goal' && !node.parent_id && <button onClick={() => void addSecondaryGoal(node)}>Add secondary goal</button>}{node.node_type === 'goal' && <button onClick={() => void addAction(node)}>Add action</button>}{(node.node_type === 'action' || node.parent_id) && <button onClick={() => void api.convert(node.id, node.node_type !== 'action').then(refresh).catch((cause) => setError(cause.message))}>Convert to {node.node_type === 'action' ? 'goal' : 'action'}</button>}
    {node.node_type === 'action' && <div className="tasks"><h2>Tasks</h2><label>List style<select value={style} onChange={(event) => { const value = event.target.value as 'numbered' | 'bulleted'; setStyle(value); void api.setTaskStyle(node.id, value) }}><option value="bulleted">Bulleted</option><option value="numbered">Numbered</option></select></label>{tasks.map((task, index) => <div className="task" key={task.id}>{style === 'numbered' && <span>{index + 1}.</span>}<input type="checkbox" checked={task.is_completed} onChange={() => void api.updateTask(task.id, { is_completed: !task.is_completed }).then(reloadTasks)} />{editingTaskId === task.id ? <input className="task-edit" autoFocus value={editingTaskText} onChange={(event) => setEditingTaskText(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void saveTaskText(task); if (event.key === 'Escape') setEditingTaskId(null) }} /> : <button className={`task-text ${task.is_completed ? 'completed' : ''}`} onClick={() => { setEditingTaskId(task.id); setEditingTaskText(task.text) }}>{task.text}</button>}{style === 'numbered' && <><button disabled={index === 0} onClick={() => void reorderTask(index, -1)}>↑</button><button disabled={index === tasks.length - 1} onClick={() => void reorderTask(index, 1)}>↓</button></>}<button onClick={() => void api.deleteTask(task.id).then(reloadTasks)}>×</button></div>)}<div><input placeholder="Add a task" value={taskText} onChange={(event) => setTaskText(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && void addTask()} /><button onClick={() => void addTask()}>Add</button></div></div>}
    <button className="danger" onClick={() => void remove()}>Delete node</button></div>
}
function ConnectionDetail({ edge, reverse, remove }: { edge: Edge; reverse: (edge: Edge) => Promise<void>; remove: (edge: Edge) => Promise<void> }) {
  return <div className="detail"><h2>Connection</h2><p>{edge.source} → {edge.target}</p><button onClick={() => void reverse(edge)}>Reverse direction</button><button className="danger" onClick={() => void remove(edge)}>Delete connection</button></div>
}

export default App
