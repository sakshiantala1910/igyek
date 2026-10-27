import { useEffect, useState } from 'react'

import { api, type Meta } from './api'
import { AccuracyView } from './components/AccuracyView'
import { DeskView } from './components/DeskView'
import { ErrorBox, Spinner } from './components/ui'

type Tab = 'desk' | 'accuracy'

const TABS: { id: Tab; label: string; blurb: string }[] = [
  {
    id: 'desk',
    label: 'Day-ahead desk',
    blurb: 'The forecast as it stood at gate closure, with a plausible outturn range',
  },
  {
    id: 'accuracy',
    label: 'Forecast accuracy',
    blurb: 'How wrong it was across every January decision, and what to do about it',
  },
]

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('desk')
  const [deadline, setDeadline] = useState('09:30')

  useEffect(() => {
    api.meta().then(setMeta).catch((e) => setError(e.message))
  }, [])

  if (error) {
    return (
      <div className="mx-auto max-w-2xl p-10">
        <ErrorBox message={`Could not reach the API: ${error}`} />
      </div>
    )
  }
  if (!meta) return <Spinner label="Loading…" />

  const active = TABS.find((t) => t.id === tab)!

  return (
    <div className="min-h-screen">
      <header className="border-b border-edge bg-panel/60">
        <div className="mx-auto max-w-[1400px] px-6 py-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">
                Windsight
                <span className="ml-3 text-sm font-normal text-muted">
                  GB day-ahead wind procurement
                </span>
              </h1>
              <p className="mt-1 text-sm text-muted">
                Elexon BMRS WINDFOR forecasts vs FUELHH metered wind outturn ·{' '}
                {meta.forecast_publications} forecast publications ·{' '}
                {meta.actual_half_hours.toLocaleString('en-GB')} settlement periods ·{' '}
                decisions {meta.decision_window.from} to {meta.decision_window.to}
              </p>
            </div>
            <label className="text-right">
              <span className="label">Auction gate closure</span>
              <select
                value={deadline}
                onChange={(e) => setDeadline(e.target.value)}
                className="mt-2 block rounded-lg border border-edge bg-ink px-3 py-2 text-sm"
              >
                <option value="09:30">09:30 — N2EX day-ahead</option>
                <option value="09:20">09:20 — EPEX SPOT GB day-ahead</option>
                <option value="11:00">11:00 — later cut-off</option>
                <option value="15:30">15:30 — intraday review</option>
              </select>
            </label>
          </div>

          <nav className="mt-5 flex gap-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`rounded-t-lg px-4 py-2 text-sm font-medium transition ${
                  tab === t.id
                    ? 'bg-ink text-slate-100'
                    : 'text-muted hover:text-slate-200'
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-6 py-6">
        <p className="mb-5 text-sm text-muted">{active.blurb}</p>
        {tab === 'desk' ? (
          <DeskView
            deadline={deadline}
            deliveryFrom={meta.delivery_window.from}
            deliveryTo={meta.delivery_window.to}
          />
        ) : (
          <AccuracyView
            deadline={deadline}
            decisionFrom={meta.decision_window.from}
            decisionTo={meta.decision_window.to}
          />
        )}

        <footer className="mt-10 border-t border-edge pt-5 text-xs leading-relaxed text-muted">
          <p>
            <strong className="text-slate-300">Sign convention.</strong>{' '}
            {meta.sign_convention}
          </p>
          <p className="mt-2">
            <strong className="text-slate-300">Method.</strong> WINDFOR is hourly and FUELHH is
            half-hourly, so outturn is averaged up to the hour rather than the forecast being
            interpolated down. Delivery days are local-clock days in {meta.market_timezone}. For
            each day the forecast used is the latest WINDFOR run published strictly before gate
            closure on D-1 — the only one a trader could actually have seen.
          </p>
        </footer>
      </main>
    </div>
  )
}
