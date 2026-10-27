import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { api, type AccuracyResponse, type LeadTimeResponse } from '../api'
import { gwh, mw, pct, shortDate, signedMw } from '../format'
import { ErrorBox, Panel, Spinner, Stat, chartAxis, tooltipStyle } from './ui'

interface Props {
  deadline: string
  decisionFrom: string
  decisionTo: string
}

export function AccuracyView({ deadline, decisionFrom, decisionTo }: Props) {
  const [data, setData] = useState<AccuracyResponse | null>(null)
  const [lead, setLead] = useState<LeadTimeResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    setLoading(true)
    setError(null)
    Promise.all([api.accuracy(deadline, decisionFrom, decisionTo), api.leadtime()])
      .then(([a, l]) => {
        if (!live) return
        setData(a)
        setLead(l)
      })
      .catch((e) => live && setError(e.message))
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [deadline, decisionFrom, decisionTo])

  if (loading) return <Spinner label="Scoring every hour of the window…" />
  if (error) return <ErrorBox message={error} />
  if (!data) return null

  const s = data.summary
  const bc = data.bias_correction

  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-5">
        <Stat
          label="Mean absolute error"
          value={mw(s.mae_mw)}
          sub={`${pct(s.nmae_pct_of_mean_output)} of mean output`}
        />
        <Stat label="RMSE" value={mw(s.rmse_mw)} sub={`${s.hours} hours scored`} />
        <Stat
          label="Bias"
          value={signedMw(s.bias_mw)}
          tone={(s.bias_mw ?? 0) > 0 ? 'short' : 'long'}
          sub="Forecast minus outturn"
        />
        <Stat
          label="Hours short"
          value={pct(s.share_hours_short_pct)}
          tone="short"
          sub="Wind over-forecast, cover under-bought"
        />
        <Stat
          label="Skill vs persistence"
          value={pct(data.persistence.skill_score_pct)}
          tone="long"
          sub="RMSE improvement on a naive D-2 repeat"
        />
      </div>

      {bc.available && (
        <Panel
          title="The headline finding: most of this error is a lean, not noise"
          hint={
            `Over the window, WINDFOR sat an average of ${signedMw(s.bias_mw)} above metered ` +
            `outturn and was high in ${pct(s.share_hours_short_pct)} of hours. A large part of ` +
            'that gap is definitional rather than meteorological: FUELHH records what the fleet ' +
            'actually delivered after curtailment, while WINDFOR describes the wind that was ' +
            'available. For a procurement desk the cause is secondary — a lean that persists is ' +
            `a lean you can subtract. Applying a trailing ${bc.lookback_days}-day bias ` +
            'correction, computable on the morning of the bid with no look-ahead, gives:'
          }
        >
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-lg border border-edge bg-ink/60 p-4">
              <div className="label">Mean absolute error</div>
              <div className="mt-2 flex items-baseline gap-3">
                <span className="text-2xl font-semibold text-muted line-through">
                  {mw(bc.raw?.mae_mw)}
                </span>
                <span className="text-3xl font-semibold text-long">
                  {mw(bc.corrected?.mae_mw)}
                </span>
              </div>
              <div className="mt-1 text-sm text-long">
                {pct(bc.mae_reduction_pct)} better
              </div>
            </div>
            <div className="rounded-lg border border-edge bg-ink/60 p-4">
              <div className="label">RMSE</div>
              <div className="mt-2 flex items-baseline gap-3">
                <span className="text-2xl font-semibold text-muted line-through">
                  {mw(bc.raw?.rmse_mw)}
                </span>
                <span className="text-3xl font-semibold text-long">
                  {mw(bc.corrected?.rmse_mw)}
                </span>
              </div>
              <div className="mt-1 text-sm text-long">
                {pct(bc.rmse_reduction_pct)} better
              </div>
            </div>
            <div className="rounded-lg border border-edge bg-ink/60 p-4">
              <div className="label">Residual bias</div>
              <div className="mt-2 flex items-baseline gap-3">
                <span className="text-2xl font-semibold text-muted line-through">
                  {signedMw(bc.raw?.bias_mw)}
                </span>
                <span className="text-3xl font-semibold text-long">
                  {signedMw(bc.corrected?.bias_mw)}
                </span>
              </div>
              <div className="mt-1 text-sm text-muted">
                Systematic lean essentially removed
              </div>
            </div>
          </div>
          <p className="mt-4 text-sm text-muted">
            Uncorrected, the window carried {gwh(s.net_misprocurement_mwh)} of net
            under-procurement — volume the desk had to buy back closer to delivery, when it is
            usually dearest.
          </p>
        </Panel>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel
          title="Distribution of forecast error"
          hint="Positive is over-forecast, which leaves the book short. The mass sitting right of zero is the lean."
        >
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.histogram}>
                <CartesianGrid stroke="#1f2b45" vertical={false} />
                <XAxis
                  dataKey="centre_mw"
                  {...chartAxis}
                  tickFormatter={(v) => `${(v / 1000).toFixed(0)}`}
                  label={{ value: 'Error (GW)', position: 'insideBottom', offset: -2, fill: '#8a9ab5', fontSize: 11 }}
                />
                <YAxis {...chartAxis} width={40} />
                <Tooltip {...tooltipStyle} formatter={(v: number) => [`${v} hours`, 'Count']} />
                <ReferenceLine x={0} stroke="#8a9ab5" strokeDasharray="3 3" />
                <Bar dataKey="count">
                  {data.histogram.map((b) => (
                    <Cell key={b.centre_mw} fill={b.centre_mw > 0 ? '#fb7185' : '#34d399'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel
          title="Error by hour of day"
          hint="Bars are mean absolute error; the line is bias. A flat bias across the clock is further evidence of a structural offset rather than a diurnal modelling weakness."
        >
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data.by_hour_of_day}>
                <CartesianGrid stroke="#1f2b45" vertical={false} />
                <XAxis dataKey="hour" {...chartAxis} interval={1} />
                <YAxis {...chartAxis} width={50} tickFormatter={(v) => `${(v / 1000).toFixed(1)}`} />
                <Tooltip {...tooltipStyle} formatter={(v: number, n: string) => [mw(v), n]} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <ReferenceLine y={0} stroke="#8a9ab5" />
                <Bar dataKey="mae_mw" fill="#1e4b6b" name="MAE" />
                <Line dataKey="bias_mw" stroke="#fb7185" strokeWidth={2} dot={false} name="Bias" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel
          title="Error grows with horizon"
          hint="Scored across every WINDFOR publication, not just the one used at gate closure. Confirms the forecast behaves sensibly: nearer runs are better."
        >
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={lead?.by_lead_time ?? []}>
                <CartesianGrid stroke="#1f2b45" vertical={false} />
                <XAxis dataKey="label" {...chartAxis} />
                <YAxis {...chartAxis} width={50} tickFormatter={(v) => `${(v / 1000).toFixed(1)}`} />
                <Tooltip {...tooltipStyle} formatter={(v: number) => [mw(v), 'MAE']} />
                <Bar dataKey="mae_mw" fill="#38bdf8" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel
          title="Error by how windy it actually was"
          hint="Error is not uniform. It is worst in the highest outturn bands — the hours when curtailment binds hardest — so one flat buffer over-buys on calm days and is still short on windy ones."
        >
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data.by_output_band}>
                <CartesianGrid stroke="#1f2b45" vertical={false} />
                <XAxis dataKey="band_label" {...chartAxis} fontSize={10} />
                <YAxis {...chartAxis} width={50} tickFormatter={(v) => `${(v / 1000).toFixed(1)}`} />
                <Tooltip {...tooltipStyle} formatter={(v: number, n: string) => [mw(v), n]} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="mae_mw" fill="#1e4b6b" name="MAE" />
                <Line dataKey="bias_mw" stroke="#fb7185" strokeWidth={2} dot={false} name="Bias" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <Panel
        title="Would waiting for a later run have helped?"
        hint="Each scheduled WINDFOR run, scored only on delivery 12–48h ahead so the comparison is like-for-like. The 07:30 run is the last one available before the 09:30 auction deadline — and on this window it is no worse than the runs that follow it, so there is nothing to be gained by bidding late."
      >
        <div className="h-[250px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={lead?.by_publication_run ?? []}>
              <CartesianGrid stroke="#1f2b45" vertical={false} />
              <XAxis dataKey="run_utc" {...chartAxis} />
              <YAxis {...chartAxis} width={50} tickFormatter={(v) => `${(v / 1000).toFixed(1)}`} />
              <Tooltip
                {...tooltipStyle}
                formatter={(v: number, n: string) => [mw(v), n]}
                labelFormatter={(l) => `${l} UTC run`}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="mae_mw" name="MAE" radius={[3, 3, 0, 0]}>
                {(lead?.by_publication_run ?? []).map((r) => (
                  <Cell key={r.run_utc} fill={r.run_utc === '07:30' ? '#38bdf8' : '#1e4b6b'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <Panel
        title="Every delivery day in the window"
        hint="One row per purchase decision. Sorted by date; the worst days are where a bias correction earns its keep."
      >
        <div className="max-h-[420px] overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-panel text-left text-muted">
              <tr className="border-b border-edge">
                <th className="py-2 font-medium">Delivery</th>
                <th className="py-2 font-medium">Run used</th>
                <th className="py-2 text-right font-medium">Mean forecast</th>
                <th className="py-2 text-right font-medium">Mean outturn</th>
                <th className="py-2 text-right font-medium">MAE</th>
                <th className="py-2 text-right font-medium">Bias</th>
                <th className="py-2 text-right font-medium">Net mis-procured</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {data.by_day.map((d) => (
                <tr key={d.delivery_date} className="border-b border-edge/40">
                  <td className="py-2">{shortDate(d.delivery_date)}</td>
                  <td className="py-2 text-muted">{d.publish_time.slice(11, 16)}</td>
                  <td className="py-2 text-right">{mw(d.mean_forecast_mw)}</td>
                  <td className="py-2 text-right">{mw(d.mean_actual_mw)}</td>
                  <td className="py-2 text-right">{mw(d.mae_mw)}</td>
                  <td
                    className={`py-2 text-right ${d.bias_mw > 0 ? 'text-short' : 'text-long'}`}
                  >
                    {signedMw(d.bias_mw)}
                  </td>
                  <td
                    className={`py-2 text-right ${
                      d.net_misprocurement_mwh > 0 ? 'text-short' : 'text-long'
                    }`}
                  >
                    {gwh(d.net_misprocurement_mwh)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}
