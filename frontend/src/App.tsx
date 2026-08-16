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
import { api, type Node, type Project, type Task, type TaskStyle } from './api/client'
import { ConnectionDetail } from './components/ConnectionDetail'
import { Detail } from './components/Detail'
import { Header } from './components/Header'
import { PlanView } from './components/PlanView'
import { downloadBlob, safeFileName } from './lib/download'
import { readProjectFile } from './lib/projectFile'
import './App.css'

const toFlowNode = (node: Node): FlowNode => ({
  id: node.id,
  position: { x: node.canvas_x, y: node.canvas_y },
  data: { label: node.text },
  className:
    node.node_type === 'action'
      ? 'action-node'
      : node.parent_id
        ? 'secondary-goal-node'
        : 'primary-goal-node',
})

const toFlowEdge = (edge: { id: string; predecessor_id: string; successor_id: string }): Edge => ({
  id: edge.id,
  source: edge.predecessor_id,
  target: edge.successor_id,
  markerEnd: { type: 'arrowclosed' } as Edge['markerEnd'],
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
  const [planTaskStyles, setPlanTaskStyles] = useState<Record<string, TaskStyle>>({})
  const activeProjectId = useRef<string | null>(null)

  const containmentEdges = useMemo(
    () =>
      domainNodes
        .filter((node) => node.parent_id)
        .map((node) => ({
          id: `containment-${node.id}`,
          source: node.parent_id!,
          target: node.id,
          type: 'smoothstep',
          selectable: false,
          focusable: false,
          style: { stroke: '#98a2b3', strokeDasharray: '5 5' },
        })),
    [domainNodes],
  )

  const report = useCallback(
    (cause: unknown, fallback: string) => setError(cause instanceof Error ? cause.message : fallback),
    [],
  )

  const load = useCallback(
    async (projectId?: string) => {
      try {
        // A project is created for a new installation, but never seeded with nodes.
        let available = await api.projects()
        const targetId = projectId ?? activeProjectId.current
        let first = targetId ? available.find((item) => item.id === targetId) : available[0]
        if (!first && available.length) first = available[0]
        if (!first) {
          first = await api.createProject('Untitled plan')
          available = [first, ...available]
        }
        const [loadedNodes, loadedEdges] = await Promise.all([api.nodes(first.id), api.edges(first.id)])
        setProjects(available)
        activeProjectId.current = first.id
        setProject(first)
        setDomainNodes(loadedNodes)
        setFlowNodes(loadedNodes.map(toFlowNode))
        setEdges(loadedEdges.map(toFlowEdge))
        setError('')
      } catch (cause) {
        report(cause, 'Unable to connect to the API')
      }
    },
    [report, setEdges, setFlowNodes],
  )

  useEffect(() => {
    void load()
  }, [load])
  useEffect(() => {
    setPlanName(project?.name ?? '')
    setEditingPlanName(false)
  }, [project])

  const selected = useMemo(
    () => domainNodes.find((node) => node.id === selectedId) ?? null,
    [domainNodes, selectedId],
  )
  const selectedEdge = useMemo(
    () => edges.find((edge) => edge.id === selectedEdgeId) ?? null,
    [edges, selectedEdgeId],
  )

  useEffect(() => {
    if (project && selected?.node_type === 'action') {
      void api
        .tasks(project.id, selected.id)
        .then(setTasks)
        .catch((cause) => report(cause, 'Could not load tasks'))
    } else setTasks([])
  }, [project, report, selected])

  const appendNode = (node: Node) => {
    setDomainNodes((current) => [...current, node])
    setFlowNodes((current) => [...current, toFlowNode(node)])
    setSelectedId(node.id)
    setSelectedEdgeId(null)
    setError('')
  }

  const addPrimaryGoal = async () => {
    if (!project) return
    try {
      const anchor = domainNodes.length
        ? domainNodes.reduce((total, item) => ({ x: total.x + item.canvas_x, y: total.y + item.canvas_y }), {
            x: 0,
            y: 0,
          })
        : { x: -10, y: 50 }
      const spread = Math.max(domainNodes.length, 1)
      appendNode(
        await api.createNode(project.id, {
          text: 'Untitled primary goal',
          node_type: 'goal',
          canvas_x: anchor.x / spread + 170,
          canvas_y: anchor.y / spread + 70,
        }),
      )
    } catch (cause) {
      report(cause, 'Could not create goal')
    }
  }

  const addSecondaryGoal = async (parent: Node) => {
    if (!project) return
    try {
      appendNode(
        await api.createNode(project.id, {
          text: 'Untitled secondary goal',
          node_type: 'goal',
          parent_id: parent.id,
          canvas_x: parent.canvas_x + 180,
          canvas_y: parent.canvas_y + 70,
        }),
      )
    } catch (cause) {
      report(cause, 'Could not create secondary goal')
    }
  }

  const addAction = async (parent: Node) => {
    if (!project) return
    try {
      appendNode(
        await api.createNode(project.id, {
          text: 'Untitled action',
          node_type: 'action',
          parent_id: parent.id,
          canvas_x: parent.canvas_x + 170,
          canvas_y: parent.canvas_y + 100,
        }),
      )
    } catch (cause) {
      report(cause, 'Could not create action')
    }
  }

  const onConnect = async (connection: Connection) => {
    if (!project || !connection.source || !connection.target) return
    try {
      const edge = await api.createEdge(project.id, connection.source, connection.target)
      setEdges((current) => addEdge({ ...toFlowEdge(edge), ...connection, id: edge.id }, current))
    } catch (cause) {
      report(cause, 'Could not create dependency')
    }
  }

  const deleteConnection = async (edge: Edge) => {
    if (!project) return
    try {
      await api.deleteEdge(project.id, edge.id)
      setEdges((current) => current.filter((item) => item.id !== edge.id))
      setSelectedEdgeId(null)
    } catch (cause) {
      report(cause, 'Could not delete connection')
    }
  }

  const reverseConnection = async (edge: Edge) => {
    if (!project) return
    try {
      // The API swaps the direction in one transaction, so nothing can be lost.
      const reversed = await api.reverseEdge(project.id, edge.id)
      setEdges((current) => current.map((item) => (item.id === edge.id ? toFlowEdge(reversed) : item)))
      setSelectedEdgeId(reversed.id)
    } catch (cause) {
      report(cause, 'Could not reverse connection')
    }
  }

  const persistPosition = async (_: unknown, node: FlowNode) => {
    if (!project) return
    try {
      await api.updateNode(project.id, node.id, { canvas_x: node.position.x, canvas_y: node.position.y })
      setDomainNodes((current) =>
        current.map((item) =>
          item.id === node.id ? { ...item, canvas_x: node.position.x, canvas_y: node.position.y } : item,
        ),
      )
    } catch (cause) {
      report(cause, 'Could not save node position')
    }
  }

  const createProject = async () => {
    const name = prompt('Project name', 'Untitled plan')
    if (!name?.trim()) return
    try {
      const created = await api.createProject(name.trim())
      await load(created.id)
    } catch (cause) {
      report(cause, 'Could not create project')
    }
  }

  const deleteProject = async () => {
    if (!project || !confirm(`Delete project “${project.name}” and all of its contents?`)) return
    try {
      await api.deleteProject(project.id)
      activeProjectId.current = null
      await load()
    } catch (cause) {
      report(cause, 'Could not delete project')
    }
  }

  const exportProject = async () => {
    if (!project) return
    try {
      const data = await api.exportProject(project.id)
      downloadBlob(
        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
        safeFileName(project.name, 'json'),
      )
    } catch (cause) {
      report(cause, 'Could not export project')
    }
  }

  const importProject = async (file: File | undefined) => {
    if (!file) return
    try {
      const created = await api.importProject(await readProjectFile(file))
      await load(created.id)
    } catch (cause) {
      report(cause, 'Could not load project file')
    }
  }

  const openPrintPlan = async () => {
    if (!project) return
    try {
      const actions = domainNodes.filter((node) => node.node_type === 'action')
      const taskLists = await Promise.all(
        actions.map(
          async (action) =>
            [
              action.id,
              await api.tasks(project.id, action.id),
              (await api.taskStyle(project.id, action.id)).display_style,
            ] as const,
        ),
      )
      setPlanTasks(Object.fromEntries(taskLists.map(([id, actionTasks]) => [id, actionTasks])))
      setPlanTaskStyles(Object.fromEntries(taskLists.map(([id, , style]) => [id, style])))
      setPrintPlan(true)
    } catch (cause) {
      report(cause, 'Could not create project plan')
    }
  }

  const savePlanName = async () => {
    if (!project || !planName.trim()) return
    try {
      const updated = await api.updateProject(project.id, planName.trim())
      setProject(updated)
      setProjects((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      setEditingPlanName(false)
    } catch (cause) {
      report(cause, 'Could not rename plan')
    }
  }

  return (
    <main>
      <Header
        project={project}
        projects={projects}
        planName={planName}
        editingPlanName={editingPlanName}
        setPlanName={setPlanName}
        setEditingPlanName={setEditingPlanName}
        savePlanName={savePlanName}
        selectProject={(id) => void load(id)}
        createProject={createProject}
        exportProject={exportProject}
        importProject={importProject}
        deleteProject={deleteProject}
        addPrimaryGoal={addPrimaryGoal}
        openPrintPlan={openPrintPlan}
      />
      {error && <p className="error">{error}</p>}
      <section className="workspace">
        {printPlan ? (
          <PlanView
            project={project}
            nodes={domainNodes}
            edges={edges}
            tasks={planTasks}
            taskStyles={planTaskStyles}
            close={() => setPrintPlan(false)}
          />
        ) : (
          <>
            <div className="canvas">
              <ReactFlow
                nodes={flowNodes}
                edges={[...containmentEdges, ...edges]}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeClick={(_, node) => {
                  setSelectedId(node.id)
                  setSelectedEdgeId(null)
                }}
                onEdgeClick={(_, edge) => {
                  if (!edge.id.startsWith('containment-')) {
                    setSelectedId(null)
                    setSelectedEdgeId(edge.id)
                  }
                }}
                onPaneClick={() => {
                  setSelectedId(null)
                  setSelectedEdgeId(null)
                }}
                onNodeDragStop={persistPosition}
                fitView
              >
                <Background />
                <Controls />
              </ReactFlow>
            </div>
            <aside className="right-pane">
              {project && selected ? (
                <Detail
                  projectId={project.id}
                  node={selected}
                  tasks={tasks}
                  refresh={load}
                  reloadTasks={() => api.tasks(project.id, selected.id).then(setTasks)}
                  addSecondaryGoal={addSecondaryGoal}
                  addAction={addAction}
                  close={() => setSelectedId(null)}
                  setError={setError}
                />
              ) : (
                selectedEdge && (
                  <ConnectionDetail
                    edge={selectedEdge}
                    reverse={reverseConnection}
                    remove={deleteConnection}
                  />
                )
              )}
            </aside>
          </>
        )}
      </section>
    </main>
  )
}

export default App
