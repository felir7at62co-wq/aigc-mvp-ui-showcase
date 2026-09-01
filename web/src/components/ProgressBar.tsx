export function ProgressBar({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(100, value))
  return (
    <div className="progress-track">
      <div
        className="progress-fill"
        data-testid="progress-fill"
        style={{ width: `${clamped}%` }}
      />
    </div>
  )
}
