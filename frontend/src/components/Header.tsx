import { useRef } from 'react'
import type { Project } from '../api/client'

type HeaderProps = {
  project: Project | null
  projects: Project[]
  planName: string
  editingPlanName: boolean
  setPlanName: (value: string) => void
  setEditingPlanName: (value: boolean) => void
  savePlanName: () => Promise<void>
  selectProject: (id: string) => void
  createProject: () => Promise<void>
  exportProject: () => Promise<void>
  importProject: (file: File | undefined) => Promise<void>
  deleteProject: () => Promise<void>
  addPrimaryGoal: () => Promise<void>
  openPrintPlan: () => Promise<void>
}

export function Header({
  project,
  projects,
  planName,
  editingPlanName,
  setPlanName,
  setEditingPlanName,
  savePlanName,
  selectProject,
  createProject,
  exportProject,
  importProject,
  deleteProject,
  addPrimaryGoal,
  openPrintPlan,
}: HeaderProps) {
  const importInput = useRef<HTMLInputElement>(null)

  return (
    <header>
      <strong>Margaritini</strong>
      <select
        className="project-picker"
        value={project?.id ?? ''}
        onChange={(event) => selectProject(event.target.value)}
      >
        {projects.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
      {editingPlanName ? (
        <input
          className="plan-name-input"
          autoFocus
          value={planName}
          onChange={(event) => setPlanName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') void savePlanName()
            if (event.key === 'Escape') {
              setPlanName(project?.name ?? '')
              setEditingPlanName(false)
            }
          }}
        />
      ) : (
        <button className="plan-name-button" onClick={() => setEditingPlanName(true)}>
          {project?.name ?? 'Loading…'}
        </button>
      )}
      <div className="project-actions">
        <button onClick={() => void createProject()}>New project</button>
        <button onClick={() => void exportProject()}>Export project</button>
        <button onClick={() => importInput.current?.click()}>Load project</button>
        <input
          ref={importInput}
          className="file-input"
          type="file"
          accept="application/json,.json"
          onChange={(event) => {
            void importProject(event.target.files?.[0])
            event.target.value = ''
          }}
        />
        <button className="delete-project" onClick={() => void deleteProject()}>
          Delete project
        </button>
      </div>
      <button onClick={() => void addPrimaryGoal()}>Add primary goal</button>
      <button onClick={() => void openPrintPlan()}>Print plan</button>
    </header>
  )
}
