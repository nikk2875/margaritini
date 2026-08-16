import type { Edge } from '@xyflow/react'
import type { Node, Project, Task, TaskStyle } from '../api/client'
import { downloadBlob, safeFileName } from '../lib/download'
import { childrenOf, planMarkdown, primaryGoals, type PlanContent } from '../lib/plan'

type PlanViewProps = {
  project: Project | null
  nodes: Node[]
  edges: Edge[]
  tasks: Record<string, Task[]>
  taskStyles: Record<string, TaskStyle>
  close: () => void
}

export function PlanView({ project, nodes, edges, tasks, taskStyles, close }: PlanViewProps) {
  const projectName = project?.name ?? 'Project plan'
  const content: PlanContent = { projectName, nodes, edges, tasks, taskStyles }

  const exportMarkdown = () =>
    downloadBlob(
      new Blob([planMarkdown(content)], { type: 'text/markdown' }),
      safeFileName(projectName, 'md', 'project-plan'),
    )

  const taskList = (action: Node) => {
    const actionTasks = tasks[action.id] ?? []
    if (!actionTasks.length) return null
    const items = actionTasks.map((task) => (
      <li className={task.is_completed ? 'completed' : ''} key={task.id}>
        {task.text}
      </li>
    ))
    return taskStyles[action.id] === 'numbered' ? <ol>{items}</ol> : <ul>{items}</ul>
  }

  const actionView = (action: Node) => (
    <li key={action.id}>
      <strong>{action.text}</strong>
      {taskList(action)}
    </li>
  )

  const secondaryView = (goal: Node) => (
    <li key={goal.id}>
      <strong>{goal.text}</strong>
      {goal.description && <p>{goal.description}</p>}
      <ul>{childrenOf(content, goal.id, 'action').map(actionView)}</ul>
    </li>
  )

  const goals = primaryGoals(content)

  return (
    <div className="plan-view">
      <div className="plan-actions">
        <button onClick={close}>Back to canvas</button>
        <button onClick={exportMarkdown}>Export Markdown</button>
      </div>
      <h1>{projectName}</h1>
      {goals.length ? (
        <ul>
          {goals.map((goal) => (
            <li key={goal.id}>
              <strong>{goal.text}</strong>
              {goal.description && <p>{goal.description}</p>}
              <ul>
                {childrenOf(content, goal.id, 'goal').map(secondaryView)}
                {childrenOf(content, goal.id, 'action').map(actionView)}
              </ul>
            </li>
          ))}
        </ul>
      ) : (
        <p>No primary goals.</p>
      )}
    </div>
  )
}
