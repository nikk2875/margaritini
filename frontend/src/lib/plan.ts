import type { Edge } from '@xyflow/react'
import type { Node, Task, TaskStyle } from '../api/client'

/** Sibling order: dependencies first, then alphabetically for free choices. */
export function dependencyOrder(nodes: Node[], edges: Edge[]): Node[] {
  const ids = new Set(nodes.map((node) => node.id))
  const outgoing = new Map(nodes.map((node) => [node.id, [] as string[]]))
  const indegree = new Map(nodes.map((node) => [node.id, 0]))
  for (const edge of edges) {
    if (ids.has(edge.source) && ids.has(edge.target)) {
      outgoing.get(edge.source)!.push(edge.target)
      indegree.set(edge.target, indegree.get(edge.target)! + 1)
    }
  }
  const byName = (left: Node, right: Node) => left.text.localeCompare(right.text)
  const remaining = new Map(nodes.map((node) => [node.id, node]))
  const ordered: Node[] = []
  while (remaining.size) {
    const ready = [...remaining.values()].filter((node) => indegree.get(node.id) === 0).sort(byName)
    const next = ready[0] ?? [...remaining.values()].sort(byName)[0]
    ordered.push(next)
    remaining.delete(next.id)
    for (const target of outgoing.get(next.id) ?? []) indegree.set(target, indegree.get(target)! - 1)
  }
  return ordered
}

export type PlanContent = {
  projectName: string
  nodes: Node[]
  edges: Edge[]
  tasks: Record<string, Task[]>
  taskStyles: Record<string, TaskStyle>
}

export function childrenOf(content: PlanContent, parentId: string, type: 'goal' | 'action'): Node[] {
  return dependencyOrder(
    content.nodes.filter((node) => node.parent_id === parentId && node.node_type === type),
    content.edges,
  )
}

export function primaryGoals(content: PlanContent): Node[] {
  return dependencyOrder(
    content.nodes.filter((node) => node.node_type === 'goal' && !node.parent_id),
    content.edges,
  )
}

/** Nested Markdown outline matching the rendered plan. */
export function planMarkdown(content: PlanContent): string {
  const taskLines = (action: Node, indent: string) =>
    (content.tasks[action.id] ?? []).map((task, index) => {
      const marker = content.taskStyles[action.id] === 'numbered' ? `${index + 1}.` : '-'
      return `${indent}${marker} ${task.is_completed ? `~~${task.text}~~` : task.text}`
    })
  const actionLines = (action: Node, indent: string) => [`${indent}- ${action.text}`, ...taskLines(action, `${indent}  `)]
  const secondaryLines = (goal: Node, indent: string) => [
    `${indent}- ${goal.text}`,
    ...(goal.description ? [`${indent}  ${goal.description}`] : []),
    ...childrenOf(content, goal.id, 'action').flatMap((action) => actionLines(action, `${indent}  `)),
  ]
  return [
    `# ${content.projectName}`,
    '',
    ...primaryGoals(content).flatMap((goal) => [
      `- ${goal.text}`,
      ...(goal.description ? [`  ${goal.description}`] : []),
      ...childrenOf(content, goal.id, 'goal').flatMap((secondary) => secondaryLines(secondary, '  ')),
      ...childrenOf(content, goal.id, 'action').flatMap((action) => actionLines(action, '  ')),
      '',
    ]),
  ].join('\n')
}
