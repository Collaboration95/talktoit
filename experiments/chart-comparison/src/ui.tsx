import type { ReactNode } from 'react'

export function Card({ title, type, children }: { title: string; type: string; children: ReactNode }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      <div className="ctype">{type}</div>
      <div className="chart-box">{children}</div>
    </div>
  )
}
