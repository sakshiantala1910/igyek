import type { ReactNode } from 'react'

export function Stat({
  label,
  value,
  sub,
  tone = 'neutral',
}: {
  label: string
  value: string
  sub?: string
  tone?: 'neutral' | 'short' | 'long'
}) {
  const toneClass =
    tone === 'short' ? 'text-short' : tone === 'long' ? 'text-long' : 'text-slate-100'
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className={`stat mt-2 ${toneClass}`}>{value}</div>
      {sub && <div className="mt-1 text-sm text-muted">{sub}</div>}
    </div>
  )
}

export function Panel({
  title,
  hint,
  children,
  right,
}: {
  title: string
  hint?: string
  children: ReactNode
  right?: ReactNode
}) {
  return (
    <section className="card">
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          {hint && <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">{hint}</p>}
        </div>
        {right}
      </header>
      {children}
    </section>
  )
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 p-10 text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-edge border-t-wind" />
      {label}
    </div>
  )
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-short/40 bg-short/10 p-5 text-sm text-short">
      {message}
    </div>
  )
}

export const chartAxis = {
  stroke: '#8a9ab5',
  fontSize: 12,
}

export const tooltipStyle = {
  contentStyle: {
    background: '#111a2e',
    border: '1px solid #1f2b45',
    borderRadius: '0.5rem',
    fontSize: 12,
  },
  labelStyle: { color: '#8a9ab5' },
}
