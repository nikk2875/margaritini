import type { ProjectExport } from '../api/client'

export const MAX_PROJECT_FILE_BYTES = 5_000_000

/** Imported files are untrusted: check size and shape before sending them on. */
export async function readProjectFile(file: File): Promise<ProjectExport> {
  if (file.size > MAX_PROJECT_FILE_BYTES) throw new Error('That project file is too large to load')
  let parsed: unknown
  try {
    parsed = JSON.parse(await file.text())
  } catch {
    throw new Error('Not a valid project file')
  }
  if (!isProjectExport(parsed)) throw new Error('Not a valid project file')
  return parsed
}

function isProjectExport(value: unknown): value is ProjectExport {
  if (typeof value !== 'object' || value === null) return false
  const document = value as Record<string, unknown>
  return (
    document.format_version === 1 &&
    typeof document.name === 'string' &&
    Array.isArray(document.nodes) &&
    Array.isArray(document.dependencies) &&
    Array.isArray(document.tasks) &&
    Array.isArray(document.task_settings)
  )
}
