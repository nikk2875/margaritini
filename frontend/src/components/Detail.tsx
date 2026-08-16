import { useEffect, useState } from 'react'
import { api, type Node, type Task, type TaskStyle } from '../api/client'

type DetailProps = {
  projectId: string
  node: Node
  tasks: Task[]
  refresh: () => Promise<void>
  reloadTasks: () => Promise<void>
  addSecondaryGoal: (parent: Node) => Promise<void>
  addAction: (parent: Node) => Promise<void>
  close: () => void
  setError: (value: string) => void
}

export function Detail({
  projectId,
  node,
  tasks,
  refresh,
  reloadTasks,
  addSecondaryGoal,
  addAction,
  close,
  setError,
}: DetailProps) {
  const [text, setText] = useState(node.text)
  const [description, setDescription] = useState(node.description)
  const [editingTitle, setEditingTitle] = useState(false)
  const [taskText, setTaskText] = useState('')
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null)
  const [editingTaskText, setEditingTaskText] = useState('')
  const [style, setStyle] = useState<TaskStyle>('bulleted')

  useEffect(() => {
    setText(node.text)
    setDescription(node.description)
    setEditingTitle(false)
    if (node.node_type === 'action') {
      void api
        .taskStyle(projectId, node.id)
        .then((settings) => setStyle(settings.display_style))
        .catch(() => setStyle('bulleted'))
    }
  }, [node, projectId])

  const report = (cause: unknown, fallback: string) =>
    setError(cause instanceof Error ? cause.message : fallback)

  const save = async () => {
    try {
      await api.updateNode(projectId, node.id, { text })
      await refresh()
      setEditingTitle(false)
    } catch (cause) {
      report(cause, 'Could not save node')
    }
  }

  const saveDescription = async () => {
    try {
      await api.updateNode(projectId, node.id, { description })
      await refresh()
    } catch (cause) {
      report(cause, 'Could not save description')
    }
  }

  const remove = async () => {
    if (!confirm(`Delete ${node.text} and all its children?`)) return
    try {
      await api.deleteNode(projectId, node.id)
      close()
      await refresh()
    } catch (cause) {
      report(cause, 'Could not delete node')
    }
  }

  const convert = async () => {
    try {
      await api.convert(projectId, node.id, node.node_type !== 'action')
      await refresh()
    } catch (cause) {
      report(cause, 'Could not convert node')
    }
  }

  const addTask = async () => {
    if (!taskText.trim()) return
    try {
      await api.createTask(projectId, node.id, taskText.trim())
      setTaskText('')
      await reloadTasks()
    } catch (cause) {
      report(cause, 'Could not add the task')
    }
  }

  const saveTaskText = async (task: Task) => {
    if (!editingTaskText.trim()) return
    try {
      await api.updateTask(projectId, task.id, { text: editingTaskText.trim() })
      setEditingTaskId(null)
      await reloadTasks()
    } catch (cause) {
      report(cause, 'Could not save the task')
    }
  }

  const toggleTask = async (task: Task) => {
    try {
      await api.updateTask(projectId, task.id, { is_completed: !task.is_completed })
      await reloadTasks()
    } catch (cause) {
      report(cause, 'Could not update the task')
    }
  }

  const removeTask = async (task: Task) => {
    try {
      await api.deleteTask(projectId, task.id)
      await reloadTasks()
    } catch (cause) {
      report(cause, 'Could not delete the task')
    }
  }

  const changeStyle = async (value: TaskStyle) => {
    setStyle(value)
    try {
      await api.setTaskStyle(projectId, node.id, value)
    } catch (cause) {
      report(cause, 'Could not change the task style')
    }
  }

  const reorderTask = async (index: number, direction: -1 | 1) => {
    const destination = index + direction
    if (destination < 0 || destination >= tasks.length) return
    const order = [...tasks]
    ;[order[index], order[destination]] = [order[destination], order[index]]
    try {
      await api.reorderTasks(projectId, node.id, order.map((task) => task.id))
      await reloadTasks()
    } catch (cause) {
      report(cause, 'Could not reorder the tasks')
    }
  }

  return (
    <div className="detail">
      <button className="close" onClick={close}>
        ×
      </button>
      <label>
        Title
        {editingTitle ? (
          <input
            autoFocus
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void save()
              if (event.key === 'Escape') {
                setText(node.text)
                setEditingTitle(false)
              }
            }}
          />
        ) : (
          <button className="title-button" onClick={() => setEditingTitle(true)}>
            {text}
          </button>
        )}
      </label>

      {node.node_type === 'goal' && (
        <>
          <label>
            Description
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Add goal details"
            />
          </label>
          <button onClick={() => void saveDescription()}>Save description</button>
        </>
      )}
      {node.node_type === 'goal' && !node.parent_id && (
        <button onClick={() => void addSecondaryGoal(node)}>Add secondary goal</button>
      )}
      {node.node_type === 'goal' && <button onClick={() => void addAction(node)}>Add action</button>}
      {(node.node_type === 'action' || node.parent_id) && (
        <button onClick={() => void convert()}>
          Convert to {node.node_type === 'action' ? 'goal' : 'action'}
        </button>
      )}

      {node.node_type === 'action' && (
        <div className="tasks">
          <h2>Tasks</h2>
          <label>
            List style
            <select value={style} onChange={(event) => void changeStyle(event.target.value as TaskStyle)}>
              <option value="bulleted">Bulleted</option>
              <option value="numbered">Numbered</option>
            </select>
          </label>
          {tasks.map((task, index) => (
            <div className="task" key={task.id}>
              {style === 'numbered' && <span>{index + 1}.</span>}
              <input type="checkbox" checked={task.is_completed} onChange={() => void toggleTask(task)} />
              {editingTaskId === task.id ? (
                <input
                  className="task-edit"
                  autoFocus
                  value={editingTaskText}
                  onChange={(event) => setEditingTaskText(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void saveTaskText(task)
                    if (event.key === 'Escape') setEditingTaskId(null)
                  }}
                />
              ) : (
                <button
                  className={`task-text ${task.is_completed ? 'completed' : ''}`}
                  onClick={() => {
                    setEditingTaskId(task.id)
                    setEditingTaskText(task.text)
                  }}
                >
                  {task.text}
                </button>
              )}
              {style === 'numbered' && (
                <>
                  <button disabled={index === 0} onClick={() => void reorderTask(index, -1)}>
                    ↑
                  </button>
                  <button disabled={index === tasks.length - 1} onClick={() => void reorderTask(index, 1)}>
                    ↓
                  </button>
                </>
              )}
              <button onClick={() => void removeTask(task)}>×</button>
            </div>
          ))}
          <div>
            <input
              placeholder="Add a task"
              value={taskText}
              onChange={(event) => setTaskText(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && void addTask()}
            />
            <button onClick={() => void addTask()}>Add</button>
          </div>
        </div>
      )}

      <button className="danger" onClick={() => void remove()}>
        Delete node
      </button>
    </div>
  )
}
