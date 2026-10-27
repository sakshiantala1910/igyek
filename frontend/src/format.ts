export const mw = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined || Number.isNaN(v)
    ? '—'
    : `${v.toLocaleString('en-GB', { maximumFractionDigits: digits })} MW`

export const gwh = (v: number | null | undefined) =>
  v === null || v === undefined
    ? '—'
    : `${(v / 1000).toLocaleString('en-GB', { maximumFractionDigits: 1 })} GWh`

export const pct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? '—' : `${v.toFixed(digits)}%`

export const signedMw = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${mw(v)}`

export const shortDate = (iso: string) =>
  new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })

export const ukTime = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString('en-GB', {
        timeZone: 'Europe/London',
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—'
