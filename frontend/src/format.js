// Numbers use en-US grouping and K/M/B suffixes regardless of browser locale.
const NUM_LOCALE = 'en-US'

export function money(v, { precise = false } = {}) {
  if (v === null || v === undefined) return '—'
  const n = Number(v)
  if (n === 0) return '$0'
  const abs = Math.abs(n)
  if (abs < 0.0001) return n < 0 ? '-<$0.0001' : '<$0.0001'
  const digits = precise || abs < 1 ? (abs < 0.01 ? 4 : 3) : 2
  return (n < 0 ? '-$' : '$') + abs.toLocaleString(NUM_LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: digits })
}

// USD -> INR rate from the server (null until loaded or if never fetched).
let usdInr = null
export const setUsdInr = (rate) => {
  usdInr = rate || null
}

// Rupees use Indian digit grouping (₹3,27,100).
export function inr(v) {
  if (usdInr === null || v === null || v === undefined) return null
  const n = Number(v) * usdInr
  if (n === 0) return '₹0'
  const abs = Math.abs(n)
  if (abs < 0.01) return n < 0 ? '-<₹0.01' : '<₹0.01'
  const digits = abs >= 100 ? 0 : 2
  return (n < 0 ? '-₹' : '₹') + abs.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

// "$2.65 (₹252)" for places that need plain text.
export function moneyText(v, options) {
  const rupees = inr(v)
  return rupees ? `${money(v, options)} (${rupees})` : money(v, options)
}

export function compact(v) {
  if (v === null || v === undefined) return '—'
  const n = Number(v)
  if (Math.abs(n) < 1000) return n.toLocaleString(NUM_LOCALE, { maximumFractionDigits: 1 })
  return Intl.NumberFormat(NUM_LOCALE, { notation: 'compact', maximumFractionDigits: 1 }).format(n)
}

export function int(v) {
  if (v === null || v === undefined) return '—'
  return Number(v).toLocaleString(NUM_LOCALE, { maximumFractionDigits: 0 })
}

export function ms(v) {
  if (v === null || v === undefined) return '—'
  return v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}s` : `${Math.round(v)}ms`
}

export function pct(v) {
  if (v === null || v === undefined || !isFinite(v)) return '—'
  return `${(v * 100).toFixed(Math.abs(v) < 0.1 ? 1 : 0)}%`
}

const fmtCache = {}
function dtf(options) {
  const key = JSON.stringify(options)
  return (fmtCache[key] ||= new Intl.DateTimeFormat(undefined, options))
}

// Axis label for a bucket start (unix seconds) at a given bucket kind.
export function bucketLabel(t, kind) {
  const d = new Date(t * 1000)
  switch (kind) {
    case 'minute':
      return dtf({ hour: '2-digit', minute: '2-digit' }).format(d)
    case 'hour':
      return dtf({ hour: 'numeric' }).format(d)
    case 'day':
    case 'week':
      return dtf({ month: 'short', day: 'numeric' }).format(d)
    default:
      return dtf({ month: 'short', year: '2-digit' }).format(d)
  }
}

export function bucketTitle(t, kind) {
  const d = new Date(t * 1000)
  switch (kind) {
    case 'minute':
      return dtf({ month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(d)
    case 'hour':
      return dtf({ month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(d)
    case 'day':
      return dtf({ weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }).format(d)
    case 'week':
      return `Week of ${dtf({ month: 'short', day: 'numeric', year: 'numeric' }).format(d)}`
    default:
      return dtf({ month: 'long', year: 'numeric' }).format(d)
  }
}

export function dateTime(t) {
  if (!t) return '—'
  return dtf({ month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
    .format(new Date(t * 1000))
}

export function relative(t) {
  if (!t) return 'never'
  const s = Math.round(Date.now() / 1000 - t)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  if (s < 30 * 86400) return `${Math.floor(s / 86400)}d ago`
  return dtf({ month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(t * 1000))
}

export const isoToTs = (iso) => (iso ? Math.floor(new Date(iso).getTime() / 1000) : null)
