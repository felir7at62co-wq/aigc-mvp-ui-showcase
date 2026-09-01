import type { ReactNode } from 'react'

export function Card({ title, actions, className = '', children }: {
  title?: string
  actions?: ReactNode
  className?: string
  children: ReactNode
}) {
  return (
    <section className={`glass-panel card ${className}`.trim()}>
      {(title || actions) && (
        <header className="card-header">
          {title && <h3 className="card-title">{title}</h3>}
          {actions}
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
  )
}
