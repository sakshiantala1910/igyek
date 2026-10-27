import { useEffect, useMemo, useState } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { api, type DayResponse } from '../api'
import { gwh, mw, pct, signedMw, ukTime } from '../format'
import { ErrorBox, Panel, Spinner, Stat, chartAxis, tooltipStyle } from './ui'

interface Props {
  deadline: string
  deliveryFrom: string
  deliveryTo: string
}

export function DeskView({ deadline, deliveryFrom, deliveryTo }: Props) {
  const [date, setDate] = useState('2026-01-15')
  const [confidence, setConfidence] = useState(0.8)
  const [data, setData] = useState<DayResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    setLoading(true)
    setError(null)
    api
      .day(date, deadline, confidence)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(e.message))
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [date, deadline, confidence])

  // Recharts stacks an Area pair to draw a band: the first area is the
  // invisible floor, the second is the visible thickness above it.
  const series = useMemo(
    () =>
      (data?.hours ?? []).map((h) => ({
        hour: h.local_time.slice(11),
        forecast: h.forecast_mw,
        actual: h.actual_mw,
        bandFloor: h.band_low_mw,
        bandSpan:
          h.band_high_mw !== null && h.band_low_mw !== null
            ? h.band_high_mw - h.band_low_mw
            : null,
      })),
    [data],
  )

  const outturnKnown = (data?.summary.hours ?? 0) > 0

  return (
    <div className="space-y-5">
      <div className="card flex flex-wrap items-end gap-6">
        <label className="block">
          <span className="label">Delivery day</span>
          <input
            type="date"
            value={date}
            min={deliveryFrom}
            max={deliveryTo}
            onChange={(e) => setDate(e.target.value)}
            className="mt-2 block rounded-lg border border-edge bg-ink px-3 py-2 text-sm"
          />
        </label>
        <label className="block">
          <span className="label">Uncertainty band</span>
          <select
            value={confidence}
            onChange={(e) => setConfidence(Number(e.target.value))}
            className="mt-2 block rounded-lg border border-edge bg-ink px-3 py-2 text-sm"
          >
            <option value={0.5}>50% central</option>
            <option value={0.8}>80% central</option>
            <option value={0.9}>90% central</option>
          </select>
        </label>
        {data && (
          <div className="ml-auto text-right text-sm">
            <div className="label">Forecast on the desk at gate closure</div>
            <div className="mt-1 font-medium text-wind">
              WINDFOR run {ukTime(data.vintage_publish_time)}
            </div>
            <div className="text-muted">
              published {Math.round((data.vintage_age_minutes ?? 0) / 60)}h before the{' '}
              {data.deadline_local} deadline · horizon up to{' '}
              {Math.round(data.forecast_horizon_hours ?? 0)}h
            </div>
          </div>
        )}
      </div>

      {loading && <Spinner label="Loading delivery day…" />}
      {error && <ErrorBox message={error} />}

      {data && !loading && (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <Stat
              label="Forecast wind, day average"
              value={mw(data.summary.mean_forecast_mw)}
              sub="What the desk planned around"
            />
            <Stat
              label="Outturn, day average"
              value={outturnKnown ? mw(data.summary.mean_actual_mw) : 'Not yet settled'}
              sub="Metered wind (FUELHH)"
            />
            <Stat
              label="Day bias"
              value={signedMw(data.summary.bias_mw)}
              tone={(data.summary.bias_mw ?? 0) > 0 ? 'short' : 'long'}
              sub={
                (data.summary.bias_mw ?? 0) > 0
                  ? 'Forecast ran high — the book was short'
                  : 'Forecast ran low — the book was long'
              }
            />
            <Stat
              label="Mis-procured volume"
              value={gwh(data.summary.net_misprocurement_mwh)}
              tone={(data.summary.net_misprocurement_mwh ?? 0) > 0 ? 'short' : 'long'}
              sub={`${pct(data.summary.share_hours_short_pct)} of hours short`}
            />
          </div>

          <Panel
            title="Day-ahead wind curve and plausible outturn range"
            hint={data.band_method}
          >
            <div className="h-[380px]">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={series} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
                  <CartesianGrid stroke="#1f2b45" vertical={false} />
                  <XAxis dataKey="hour" {...chartAxis} interval={1} />
                  <YAxis
                    {...chartAxis}
                    width={70}
                    tickFormatter={(v) => `${(v / 1000).toFixed(0)}GW`}
                  />
                  <Tooltip
                    {...tooltipStyle}
                    formatter={(value: number, name: string) =>
                      name === 'Plausible range' ? [mw(value), 'Range width'] : [mw(value), name]
                    }
                  />
                  <Legend wrapperStyle={{ fontSize: 12, color: '#8a9ab5' }} />
                  <Area
                    dataKey="bandFloor"
                    stackId="band"
                    stroke="none"
                    fill="transparent"
                    legendType="none"
                    name="floor"
                  />
                  <Area
                    dataKey="bandSpan"
                    stackId="band"
                    stroke="none"
                    fill="#38bdf8"
                    fillOpacity={0.14}
                    name="Plausible range"
                  />
                  <Line
                    dataKey="forecast"
                    stroke="#38bdf8"
                    strokeWidth={2.5}
                    dot={false}
                    name="WINDFOR forecast"
                  />
                  <Line
                    dataKey="actual"
                    stroke="#f8fafc"
                    strokeWidth={2}
                    strokeDasharray="4 3"
                    dot={false}
                    name="Metered outturn"
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <Panel
            title="How much firm cover to buy on top of the wind forecast"
            hint={
              'Empirical quantiles of the signed forecast error over the preceding fortnight. ' +
              'Buy the buffer alongside the day-ahead position and you are short no more often ' +
              'than the tolerance you pick. No distribution is assumed — wind error is skewed ' +
              'and fat-tailed, and a normal fit understates exactly the tail that costs money.'
            }
          >
            <table className="w-full text-sm">
              <thead className="text-left text-muted">
                <tr className="border-b border-edge">
                  <th className="pb-2 font-medium">Tolerance for being short</th>
                  <th className="pb-2 text-right font-medium">Buffer to buy</th>
                  <th className="pb-2 text-right font-medium">Cover achieved</th>
                  <th className="pb-2 text-right font-medium">Hours still short</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {data.cover.map((row) => (
                  <tr key={row.confidence_pct} className="border-b border-edge/50">
                    <td className="py-2">
                      Short at most {(100 - row.confidence_pct).toFixed(0)}% of hours
                    </td>
                    <td className="py-2 text-right font-medium text-wind">
                      {mw(row.buffer_mw)}
                    </td>
                    <td className="py-2 text-right">{pct(row.realised_cover_pct)}</td>
                    <td className="py-2 text-right text-muted">{row.residual_short_hours}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </>
      )}
    </div>
  )
}
