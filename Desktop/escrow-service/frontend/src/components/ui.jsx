import { STATUS_LABEL, STEPS, STEP_LABEL } from '../labels'

export function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABEL[status] || status}</span>
}

export function Alert({ kind = 'error', children }) {
  if (!children) return null
  return <div className={`alert alert-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</div>
}

export function Loading({ what = 'Loading…' }) {
  return <p className="muted" role="status">{what}</p>
}

export function Stepper({ status }) {
  const idx = STEPS.indexOf(status)
  const reached = (i) => (idx === -1 ? false : i <= idx)
  return (
    <ol className="stepper" aria-label="Progress">
      {STEPS.map((s, i) => (
        <li key={s} className={reached(i) ? 'done' : ''}>
          <span className="dot">{i + 1}</span>
          <span className="step-label">{STEP_LABEL[s]}</span>
        </li>
      ))}
    </ol>
  )
}

export function Stat({ label, value, hint }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  )
}

// Staff actions need a written reason (the backend requires one and records it in the audit log).
export function askReason(message) {
  const r = window.prompt(`${message}\n\nA reason is required and is saved in the audit log.`)
  if (r === null) return null
  const reason = r.trim()
  if (reason.length < 3) { window.alert('Please enter a reason (at least 3 characters).'); return null }
  return reason
}
