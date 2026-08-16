import type { Edge } from '@xyflow/react'

type ConnectionDetailProps = {
  edge: Edge
  reverse: (edge: Edge) => Promise<void>
  remove: (edge: Edge) => Promise<void>
}

export function ConnectionDetail({ edge, reverse, remove }: ConnectionDetailProps) {
  return (
    <div className="detail">
      <h2>Connection</h2>
      <p>
        {edge.source} → {edge.target}
      </p>
      <button onClick={() => void reverse(edge)}>Reverse direction</button>
      <button className="danger" onClick={() => void remove(edge)}>
        Delete connection
      </button>
    </div>
  )
}
