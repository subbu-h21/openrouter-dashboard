import { useEffect, useMemo, useState } from 'react'
import { api, buildQuery, tzOffsetMinutes } from '../api.js'
import { assignSlots, displayName, keyOf, OTHER, shortName, slotColor } from '../colors.js'
import { ActiveFilterNote, DIMENSIONS, FilterBar, FILTERS, RANGES, Segmented, Select } from '../components/Controls.jsx'
import StackedBarChart from '../components/StackedBarChart.jsx'
import Money from '../components/Money.jsx'
import { compact, int, moneyText, ms, pct, relative } from '../format.js'

const RANGE_NOUN = { '1h': 'hour', '1d': '24 hours', '7d': '7 days', '1m': '30 days', '3m': '13 weeks', '1y': '12 months' }

function Delta({ current, previous, range }) {
  if (previous === null || previous === undefined || range === 'all') return null
  if (!previous) return <span className="delta">no usage in previous {RANGE_NOUN[range]}</span>
  const change = (current - previous) / previous
  const arrow = change > 0 ? '↑' : change < 0 ? '↓' : '→'
  return (
    <span className="delta">
      {arrow} {pct(Math.abs(change))} vs previous {RANGE_NOUN[range]}
    </span>
  )
}

function StatTile({ label, value, children }) {
  return (
    <div className="card stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <div className="stat-sub">{children}</div>
    </div>
  )
}

const COLUMNS = [
  { key: 'cost', label: 'Spend', fmt: (v) => <Money v={v} /> },
  { key: 'requests', label: 'Requests', fmt: int },
  { key: 'tokens_prompt', label: 'Prompt tokens', fmt: compact },
  { key: 'tokens_completion', label: 'Completion tokens', fmt: compact },
  { key: 'tokens_reasoning', label: 'Reasoning', fmt: compact },
  { key: 'tokens_cached', label: 'Cached', fmt: compact },
  { key: 'avg_latency_ms', label: 'Avg latency', fmt: ms },
  { key: 'avg_throughput', label: 'Tokens/s', fmt: (v) => (v == null ? '—' : v.toFixed(0)) },
  { key: 'last_ts', label: 'Last used', fmt: relative },
]

function BreakdownTable({ rows, dim, slots, filters, setFilters }) {
  const [sort, setSort] = useState({ key: 'cost', dir: 'desc' })
  const totalCost = rows.reduce((s, r) => s + (r.cost || 0), 0)
  const filterable = FILTERS.some((f) => f.key === dim)
  const sorted = useMemo(() => {
    const out = [...rows]
    out.sort((a, b) => {
      const av = a[sort.key] ?? -Infinity
      const bv = b[sort.key] ?? -Infinity
      return sort.dir === 'asc' ? av - bv : bv - av
    })
    return out
  }, [rows, sort])

  const toggleSort = (key) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'desc' ? 'asc' : 'desc' } : { key, dir: 'desc' }))

  return (
    <section className="card">
      <header className="table-header">
        <h3>By {DIMENSIONS.find((d) => d.key === dim)?.label.toLowerCase()}</h3>
        {filterable && <span className="muted small">Click a row to filter to it</span>}
      </header>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th className="num">Share</th>
              {COLUMNS.map((c) => (
                <th key={c.key} className="num sortable" onClick={() => toggleSort(c.key)} aria-sort={sort.key === c.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}>
                  {c.label}
                  {sort.key === c.key ? (sort.dir === 'asc' ? ' ↑' : ' ↓') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length + 2} className="empty">No usage in this period</td>
              </tr>
            )}
            {sorted.map((r) => {
              const k = keyOf(r.key)
              const share = totalCost > 0 ? (r.cost || 0) / totalCost : 0
              const selected = filters[dim] === k
              return (
                <tr
                  key={k}
                  className={filterable ? `clickable${selected ? ' selected' : ''}` : ''}
                  onClick={filterable ? () => setFilters({ ...filters, [dim]: selected ? undefined : k }) : undefined}
                >
                  <td className="name-cell" title={displayName(dim, r.key)}>
                    <span className="swatch" style={{ background: slotColor(slots[k]) }} />
                    {shortName(dim, r.key)}
                  </td>
                  <td className="num">
                    <span className="share">
                      <span className="share-bar" style={{ width: `${Math.max(share * 100, share > 0 ? 2 : 0)}%` }} />
                    </span>
                    {pct(share)}
                  </td>
                  {COLUMNS.map((c) => (
                    <td key={c.key} className="num">{c.fmt(r[c.key])}</td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default function Activity({ range, setRange, groupBy, setGroupBy, filters, setFilters, options, dataVersion }) {
  const [state, setState] = useState({ loading: true })

  useEffect(() => {
    let cancelled = false
    const qs = buildQuery({ range, tz: tzOffsetMinutes(), group_by: groupBy, ...filters })
    setState((s) => ({ ...s, loading: true, error: null }))
    Promise.all([api(`/summary${qs}`), api(`/timeseries${qs}`), api(`/breakdown${qs}`)])
      .then(([summary, timeseries, breakdown]) => {
        if (!cancelled) setState({ loading: false, summary, timeseries, breakdown })
      })
      .catch((e) => !cancelled && setState((s) => ({ ...s, loading: false, error: e.message })))
    return () => {
      cancelled = true
    }
  }, [range, groupBy, filters, dataVersion])

  const { summary, timeseries, breakdown } = state

  // One colour per charted entity; table rows that fall into "Other" get the Other colour.
  const slots = useMemo(() => {
    if (!timeseries) return {}
    const keys = timeseries.series.map((s) => keyOf(s.key)).filter((k) => k !== OTHER)
    return assignSlots(keys, options?.[groupBy]?.map((o) => o.value))
  }, [timeseries, options, groupBy])

  const cur = summary?.current
  const credits = summary?.credits

  return (
    <div className="page">
      <div className="toolbar">
        <Segmented label="Time range" options={RANGES} value={range} onChange={setRange} />
        <Select label="Group by" value={groupBy} onChange={setGroupBy}>
          {DIMENSIONS.map((d) => (
            <option key={d.key} value={d.key}>{d.label}</option>
          ))}
        </Select>
        <FilterBar filters={filters} setFilters={setFilters} options={options} />
        {state.loading && <span className="muted small">Loading…</span>}
      </div>
      <ActiveFilterNote filters={filters} />
      {state.error && <div className="error-banner">{state.error}</div>}

      {summary && (
        <div className="stats">
          <StatTile label="Spend" value={<Money v={cur.cost} />}>
            <Delta current={cur.cost} previous={summary.previous?.cost} range={range} />
          </StatTile>
          <StatTile label="Requests" value={int(cur.requests)}>
            <Delta current={cur.requests} previous={summary.previous?.requests} range={range} />
          </StatTile>
          <StatTile label="Tokens" value={compact(cur.tokens)}>
            {compact(cur.tokens_prompt)} prompt · {compact(cur.tokens_completion)} completion
          </StatTile>
          <StatTile label="Avg latency" value={ms(cur.avg_latency_ms)}>
            {cur.avg_throughput != null ? `${cur.avg_throughput.toFixed(0)} tokens/s avg` : ''}
          </StatTile>
          <StatTile label="Credits remaining" value={credits ? <Money v={credits.remaining} /> : '—'}>
            {credits &&
              (credits.days_left != null
                ? `≈ ${credits.days_left < 1 ? '<1 day' : `${Math.floor(credits.days_left)} day${Math.floor(credits.days_left) === 1 ? '' : 's'}`} left at ${moneyText(credits.avg_daily_spend_7d)}/day (7-day avg, all keys)`
                : `of ${moneyText(credits.total_credits)} purchased`)}
          </StatTile>
        </div>
      )}

      {timeseries && (
        <div className="charts">
          <StackedBarChart title="Spend" metric="cost" timeseries={timeseries} dim={groupBy} slots={slots}
            format={(v) => <Money v={v} />} axisFormat={(v) => (v === 0 ? '$0' : `$${v < 1 ? v.toFixed(2) : compact(v)}`)} />
          <StackedBarChart title="Tokens" metric="tokens" timeseries={timeseries} dim={groupBy} slots={slots}
            format={compact} axisFormat={compact} />
          <StackedBarChart title="Requests" metric="requests" timeseries={timeseries} dim={groupBy} slots={slots}
            format={int} axisFormat={compact} />
        </div>
      )}

      {breakdown && (
        <BreakdownTable rows={breakdown.rows} dim={groupBy} slots={slots} filters={filters} setFilters={setFilters} />
      )}
    </div>
  )
}
