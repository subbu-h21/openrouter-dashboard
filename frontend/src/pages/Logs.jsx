import { useEffect, useState } from 'react'
import { api, buildQuery, tzOffsetMinutes } from '../api.js'
import { displayName, shortName } from '../colors.js'
import { ActiveFilterNote, FilterBar, RANGES, Segmented } from '../components/Controls.jsx'
import Money from '../components/Money.jsx'
import { compact, dateTime, int, ms } from '../format.js'

const PAGE_SIZE = 50

const SORTABLE = { ts: 'Time', cost: 'Cost', tokens: 'Tokens', latency: 'Latency', throughput: 'Speed' }

export default function Logs({ filters, setFilters, options, dataVersion }) {
  const [range, setRange] = useState('all')
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState({ key: 'ts', dir: 'desc' })
  const [page, setPage] = useState(1)
  const [state, setState] = useState({ loading: true })

  // Debounce the ID search box.
  useEffect(() => {
    const t = setTimeout(() => setQuery(search.trim()), 300)
    return () => clearTimeout(t)
  }, [search])

  useEffect(() => setPage(1), [range, query, sort, filters])

  const params = { range, tz: tzOffsetMinutes(), q: query, ...filters }

  useEffect(() => {
    let cancelled = false
    setState((s) => ({ ...s, loading: true, error: null }))
    api(`/logs${buildQuery({ ...params, sort: sort.key, direction: sort.dir, page, page_size: PAGE_SIZE })}`)
      .then((data) => !cancelled && setState({ loading: false, data }))
      .catch((e) => !cancelled && setState((s) => ({ ...s, loading: false, error: e.message })))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range, query, sort, page, filters, dataVersion])

  const data = state.data
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  const header = (key, label, className = 'num') =>
    SORTABLE[key] ? (
      <th
        className={`${className} sortable`}
        onClick={() => setSort((s) => (s.key === key ? { key, dir: s.dir === 'desc' ? 'asc' : 'desc' } : { key, dir: 'desc' }))}
        aria-sort={sort.key === key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}
      >
        {label}
        {sort.key === key ? (sort.dir === 'asc' ? ' ↑' : ' ↓') : ''}
      </th>
    ) : (
      <th className={className}>{label}</th>
    )

  return (
    <div className="page">
      <div className="toolbar">
        <Segmented label="Time range" options={RANGES} value={range} onChange={setRange} />
        <FilterBar filters={filters} setFilters={setFilters} options={options} />
        <label className="select search">
          <span>Generation ID</span>
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="gen-…" />
        </label>
        <a className="button-link" href={`/api/logs.csv${buildQuery(params)}`}>Export CSV</a>
        {state.loading && <span className="muted small">Loading…</span>}
      </div>
      <ActiveFilterNote filters={filters} />
      {state.error && <div className="error-banner">{state.error}</div>}

      <section className="card">
        <header className="table-header">
          <h3>Requests</h3>
          {data && <span className="muted small">{int(data.total)} total</span>}
        </header>
        <div className="table-scroll">
          <table className="data-table logs-table">
            <thead>
              <tr>
                {header('ts', 'Time', '')}
                <th>Model</th>
                <th>API key</th>
                <th>Provider</th>
                <th>App</th>
                {header('tokens', 'Tokens')}
                {header('cost', 'Cost')}
                {header('latency', 'Latency')}
                {header('throughput', 'Speed')}
                <th>Finish</th>
              </tr>
            </thead>
            <tbody>
              {data?.rows.length === 0 && (
                <tr>
                  <td colSpan={10} className="empty">No requests match</td>
                </tr>
              )}
              {data?.rows.map((r) => (
                <tr key={r.id} title={r.id}>
                  <td className="nowrap">{dateTime(r.ts)}</td>
                  <td className="name-cell" title={r.model}>{shortName('model', r.model)}</td>
                  <td className="nowrap">{displayName('api_key', r.api_key)}</td>
                  <td className="nowrap">{displayName('provider', r.provider)}</td>
                  <td className="nowrap">{displayName('app', r.app)}</td>
                  <td className="num nowrap" title={`${int(r.tokens_prompt)} prompt · ${int(r.tokens_completion)} completion${r.tokens_reasoning ? ` (${int(r.tokens_reasoning)} reasoning)` : ''}${r.tokens_cached ? ` · ${int(r.tokens_cached)} cached` : ''}`}>
                    {r.tokens_prompt == null && r.tokens_completion == null ? '—' : `${compact(r.tokens_prompt ?? 0)} → ${compact(r.tokens_completion ?? 0)}`}
                  </td>
                  <td className="num"><Money v={r.cost} precise /></td>
                  <td className="num" title={r.ttft_ms != null ? `First token after ${ms(r.ttft_ms)}` : undefined}>{ms(r.latency_ms)}</td>
                  <td className="num nowrap">{r.throughput != null ? `${r.throughput.toFixed(0)} tps` : '—'}</td>
                  <td className="nowrap">{displayName('finish_reason', r.finish_reason)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <footer className="pager">
          <button type="button" className="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Previous</button>
          <span className="muted small">Page {page} of {pages}</span>
          <button type="button" className="ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next →</button>
        </footer>
      </section>
    </div>
  )
}
