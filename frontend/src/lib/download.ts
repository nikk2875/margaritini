/** Strip anything a browser could interpret as a path or control character. */
export function safeFileName(name: string, extension: string, fallback = 'project'): string {
  const cleaned = name
    .normalize('NFKD')
    .replace(/[^a-z0-9]+/gi, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
  return `${cleaned || fallback}.${extension}`
}

/** Browser-standard download; the final location is decided by browser settings. */
export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  // Safari and Firefox abort the download if the object URL is revoked at once.
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
