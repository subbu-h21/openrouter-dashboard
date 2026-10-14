import { displayName, keyOf, NULL_KEY, shortName } from '../colors.js'

export const RANGES = [
  { key: '1h', label: '1H' },
  { key: '1d', label: '1D' },
  { key: '7d', label: '7D' },
  { key: '1m', label: '1M' },
  { key: '3m', label: '3M' },
  { key: '1y', label: '1Y' },
  { key: 'all', label: 'All' },
]

export const DIMENSIONS = [
  { key: 'model', label: 'Model' },
  { key: 'api_key', label: 'API key' },
  { key: 'provider', label: 'Provider' },
  { key: 'app', label: 'App' },
  { key: 'user', label: 'Creator' },
  { key: 'finish_reason', label: 'Finish reason' },
]

export const FILTERS = [
  { key: 'api_key', label: 'API key' },
  { key: 'model', label: 'Model' },
  { key: 'provider', label: 'Provider' },
  { key: 'app', label: 'App' },
  { key: 'finish_reason', label: 'Finish reason' },
]

export function Segmented({ options, value, onChange, label }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          role="radio"
          aria-checked={value === o.key}
          className={value === o.key ? 'active' : ''}
          onClick={() => onChange(o.key)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Select({ label, value, onChange, children }) {
  return (
    <label className="select">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {children}
      </select>
    </label>
  )
}

export function FilterBar({ filters, setFilters, options }) {
  const active = FILTERS.filter((f) => filters[f.key])
  return (
    <>
      {FILTERS.map((f) => {
        const values = options?.[f.key] || []
        return (
          <Select
            key={f.key}
            label={f.label}
            value={filters[f.key] || ''}
            onChange={(v) => setFilters({ ...filters, [f.key]: v || undefined })}
          >
            <option value="">All</option>
            {values.map((o) => {
              const k = keyOf(o.value)
              return (
                <option key={k} value={k}>
                  {shortName(f.key, k)}
                </option>
              )
            })}
          </Select>
        )
      })}
      {active.length > 0 && (
        <button type="button" className="ghost" onClick={() => setFilters({})}>
          Clear filters
        </button>
      )}
    </>
  )
}

export function ActiveFilterNote({ filters }) {
  const active = FILTERS.filter((f) => filters[f.key])
  if (!active.length) return null
  return (
    <p className="filter-note">
      Filtered to{' '}
      {active.map((f, i) => (
        <span key={f.key}>
          {i > 0 && ', '}
          {f.label.toLowerCase()} <strong>{filters[f.key] === NULL_KEY ? displayName(f.key, null) : filters[f.key]}</strong>
        </span>
      ))}
    </p>
  )
}
