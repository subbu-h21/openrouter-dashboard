import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { shortName } from '../colors.js'
import Money from '../components/Money.jsx'
import { int, isoToTs, relative } from '../format.js'

const FLAG_INFO = {
  deleted: { label: 'Not in key list', tone: 'critical', title: "OpenRouter's key list no longer includes this key (deleted, or moved to another workspace). Its usage history is kept." },
  disabled: { label: 'Disabled', tone: 'critical' },
  expired: { label: 'Expired', tone: 'critical' },
  near_limit: { label: 'Near limit', tone: 'warning' },
  no_limit: { label: 'No spend limit', tone: 'info', title: 'This key can spend your whole credit balance.' },
  no_expiry: { label: 'No expiry', tone: 'info' },
  unused_30d: { label: 'Unused 30d', tone: 'info' },
  duplicate_name: { label: 'Duplicate name', tone: 'warning', title: 'OpenRouter usage data identifies keys by name, so the request-based columns combine every key with this name. Today/week/month/all-time come from OpenRouter per key and are exact.' },
}
const TONE_ICON = { critical: '●', warning: '▲', info: '○' }

function Flags({ flags }) {
  return (
    <div className="flags">
      {flags.map((f) => {
        const info = FLAG_INFO[f] || { label: f, tone: 'info' }
        return (
          <span key={f} className={`flag flag-${info.tone}`} title={info.title}>
            <span aria-hidden="true">{TONE_ICON[info.tone]}</span> {info.label}
          </span>
        )
      })}
    </div>
  )
}

function LimitMeter({ k }) {
  if (k.limit_usd == null) return <span className="muted">No limit</span>
  const used = Math.max(0, k.limit_usd - (k.limit_remaining ?? k.limit_usd))
  const share = k.limit_usd > 0 ? Math.min(1, used / k.limit_usd) : 1
  const tone = share >= 0.9 ? 'critical' : share >= 0.7 ? 'warning' : 'ok'
  return (
    <div className="limit">
      <div className="limit-text">
        <Money v={used} /> / <Money v={k.limit_usd} />
        {k.limit_reset && <span className="muted"> · resets {k.limit_reset}</span>}
      </div>
      <div className={`meter meter-${tone}`} role="meter" aria-valuemin={0} aria-valuemax={k.limit_usd} aria-valuenow={used}>
        <span style={{ width: `${share * 100}%` }} />
      </div>
    </div>
  )
}

export default function Keys({ onOpenKey, dataVersion }) {
  const [state, setState] = useState({ loading: true })

  useEffect(() => {
    let cancelled = false
    api('/keys')
      .then((data) => !cancelled && setState({ loading: false, keys: data.keys }))
      .catch((e) => !cancelled && setState({ loading: false, error: e.message }))
    return () => {
      cancelled = true
    }
  }, [dataVersion])

  const keys = state.keys || []

  return (
    <div className="page">
      {state.error && <div className="error-banner">{state.error}</div>}
      <section className="card">
        <header className="table-header">
          <h3>API keys</h3>
          <span className="muted small">
            Usage today/week/month comes from OpenRouter's own counters; spend columns are computed from synced requests.
            Click a key to see its activity.
          </span>
        </header>
        <div className="table-scroll">
          <table className="data-table keys-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Limit</th>
                <th className="num">Today</th>
                <th className="num">This week</th>
                <th className="num">This month</th>
                <th className="num">Last 30 days</th>
                <th className="num">All time</th>
                <th className="num">Requests (30d)</th>
                <th>Top model (30d)</th>
                <th>Last used</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {state.loading && (
                <tr><td colSpan={11} className="empty">Loading…</td></tr>
              )}
              {!state.loading && keys.length === 0 && (
                <tr><td colSpan={11} className="empty">No keys synced yet</td></tr>
              )}
              {keys.map((k) => (
                <tr key={k.hash || `deleted:${k.name}`} className="clickable" onClick={() => onOpenKey(k.name)}>
                  <td className="name-cell">
                    <div className="key-name">{k.name}</div>
                    {k.label && <div className="muted small mono">{k.label}</div>}
                  </td>
                  <td><LimitMeter k={k} /></td>
                  <td className="num">{k.hash ? <Money v={k.usage_daily} /> : '—'}</td>
                  <td className="num">{k.hash ? <Money v={k.usage_weekly} /> : '—'}</td>
                  <td className="num">{k.hash ? <Money v={k.usage_monthly} /> : '—'}</td>
                  <td className="num"><Money v={k.stats?.cost_30d ?? 0} /></td>
                  <td className="num"><Money v={k.hash ? k.usage : k.stats?.cost_all} /></td>
                  <td className="num">{int(k.stats?.requests_30d ?? 0)}</td>
                  <td className="nowrap" title={k.top_model_30d || ''}>{k.top_model_30d ? shortName('model', k.top_model_30d) : '—'}</td>
                  <td className="nowrap">{relative(isoToTs(k.last_used_at) || k.stats?.last_request_ts)}</td>
                  <td><Flags flags={k.flags} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
