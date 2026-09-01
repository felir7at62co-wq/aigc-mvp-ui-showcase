import { useEffect, type MouseEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Card } from './Card'

export function CreateProjectModal({ title, onClose, children }: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [onClose])

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) onClose()
  }

  return createPortal(
    <div
      className="project-create-backdrop"
      data-testid="create-project-backdrop"
      onClick={handleBackdropClick}
    >
      <div
        className="project-create-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <Card title={title}>{children}</Card>
      </div>
    </div>,
    document.body,
  )
}
