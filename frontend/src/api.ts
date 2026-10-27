// Typed mirror of the FastAPI contract in backend/app/schemas.py.
// Everything is origin-relative: Vite proxies /api in development, Vercel
// routes it to the Python function in production, and the Docker Compose stack
// puts both behind the same nginx. No build-time API URL to get wrong.

export interface HourRow {
  start_time: string
  local_time: string
  forecast_mw: number | null
  actual_mw: number | null
  error_mw: number | null
  lead_hours: number | null
  band_low_mw: number | null
  band_high_mw: number | null
}

export interface Summary {
  hours: number
  days?: number
  mean_actual_mw?: number
  mean_forecast_mw?: number
  mae_mw?: number
  rmse_mw?: number
  bias_mw?: number
  nmae_pct_of_capacity?: number
  nmae_pct_of_mean_output?: number
  max_over_forecast_mw?: number
  max_under_forecast_mw?: number
  share_hours_short_pct?: number
  gross_misprocurement_mwh?: number
  net_misprocurement_mwh?: number
  error_quantiles_mw?: Record<string, number>
}

export interface CoverRow {
  confidence_pct: number
  buffer_mw: number
  realised_cover_pct: number
  residual_short_hours: number
  carry_cost_mwh: number
}

export interface DayResponse {
  delivery_date: string
  deadline_local: string
  deadline_utc: string
  vintage_publish_time: string | null
  vintage_age_minutes: number | null
  forecast_horizon_hours: number | null
  band_method: string
  band_confidence_pct: number
  hours: HourRow[]
  summary: Summary
  cover: CoverRow[]
}

export interface BiasCorrection {
  available: boolean
  lookback_days?: number
  scored_hours?: number
  mean_correction_mw?: number
  raw?: Summary
  corrected?: Summary
  mae_reduction_pct?: number
  rmse_reduction_pct?: number
}

export interface AccuracyResponse {
  window: {
    decision_from: string
    decision_to: string
    delivery_from: string
    delivery_to: string
    deadline_local: string
    scored_hours: number
  }
  summary: Summary
  persistence: {
    available: boolean
    naive_rmse_mw?: number
    naive_mae_mw?: number
    forecast_rmse_mw?: number
    skill_score_pct?: number
  }
  bias_correction: BiasCorrection
  cover: CoverRow[]
  histogram: { centre_mw: number; count: number; share_pct: number }[]
  by_hour_of_day: {
    hour: number
    mae_mw: number
    bias_mw: number
    p10_mw: number
    p90_mw: number
    mean_actual_mw: number
  }[]
  by_day: {
    delivery_date: string
    publish_time: string
    mae_mw: number
    bias_mw: number
    rmse_mw: number
    mean_actual_mw: number
    mean_forecast_mw: number
    net_misprocurement_mwh: number
    worst_hour_error_mw: number
  }[]
  by_output_band: {
    band_label: string
    hours: number
    mae_mw: number
    bias_mw: number
    p90_mw: number
  }[]
}

export interface LeadTimeResponse {
  by_lead_time: { label: string; mae_mw: number; rmse_mw: number; bias_mw: number }[]
  by_publication_run: {
    run_utc: string
    hours: number
    mae_mw: number
    rmse_mw: number
    bias_mw: number
  }[]
}

export interface Meta {
  data: Record<string, unknown>
  market_timezone: string
  default_deadline_local: string
  decision_window: { from: string; to: string }
  delivery_window: { from: string; to: string }
  windfor_runs_utc: string[]
  forecast_publications: number
  actual_half_hours: number
  sign_convention: string
}

async function get<T>(path: string, params: Record<string, string> = {}): Promise<T> {
  const qs = new URLSearchParams(params).toString()
  const res = await fetch(`/api${path}${qs ? `?${qs}` : ''}`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `Request failed (${res.status})`)
  }
  return res.json() as Promise<T>
}

export const api = {
  meta: () => get<Meta>('/meta'),
  day: (date: string, deadline: string, confidence = 0.8) =>
    get<DayResponse>('/day', { date, deadline, confidence: String(confidence) }),
  accuracy: (deadline: string, from: string, to: string) =>
    get<AccuracyResponse>('/accuracy', { deadline, from, to }),
  leadtime: () => get<LeadTimeResponse>('/leadtime'),
}
