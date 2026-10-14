import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { displayName, keyOf, OTHER, shortName, slotColor } from '../colors.js'
import { bucketLabel, bucketTitle } from '../format.js'

// Rectangle with rounded top corners only (data end rounded, baseline square).
function roundedTopPath(x, y, w, h, r) {
  r = Math.max(0, Math.min(r, h, w / 2))
  return `M${x},${y + h}L${x},${y + r}Q${x},${y} ${x + r},${y}L${x + w - r},${y}Q${x + w},${y} ${x + w},${y + r}L${x + w},${y + h}Z`
}

function Segment({ x, y, width, height, payload, seriesId, order, color }) {
  if (!height || height <= 0 || !width) return null
  const top = [...order].reverse().find((id) => payload?.[id] > 0)
  const d = top === seriesId ? roundedTopPath(x, y, width, height, 4) : `M${x},${y}h${width}v${height}h${-width}Z`
  return <path d={d} className="bar-segment" style={{ fill: color }} />
}

function ChartTooltip({ active, payload, label, kind, series, dim, format }) {
  if (!active || !payload?.length) return null
  const byId = Object.fromEntries(series.map((s) => [s.id, s]))
  const items = payload
    .filter((p) => p.value > 0)
    .sort((a, b) => b.value - a.value)
  const total = items.reduce((sum, p) => sum + p.value, 0)
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-title">{bucketTitle(label, kind)}</div>
      {items.length === 0 && <div className="muted">No usage</div>}
      {items.map((p) => {
        const s = byId[p.dataKey]
        return (
          <div className="chart-tooltip-row" key={p.dataKey}>
            <span className="swatch" style={{ background: s.color }} />
            <span className="chart-tooltip-name" title={displayName(dim, s.key)}>
              {shortName(dim, s.key)}
            </span>
            <span className="num">{format(p.value)}</span>
          </div>
        )
      })}
      {items.length > 1 && (
        <div className="chart-tooltip-row chart-tooltip-total">
          <span />
          <span>Total</span>
          <span className="num">{format(total)}</span>
        </div>
      )}
    </div>
  )
}

export default function StackedBarChart({ title, metric, timeseries, dim, slots, format, axisFormat }) {
  const data = timeseries.metrics[metric]
  const kind = timeseries.kind
  const series = timeseries.series.map((s) => ({ ...s, total: s.totals[metric], color: slotColor(slots[keyOf(s.key)]) }))
  const order = series.map((s) => s.id)
  // Legend: this chart's non-zero series, largest first, "Other" last.
  const legend = series
    .filter((s) => s.total > 0)
    .sort((a, b) => (a.key === OTHER) - (b.key === OTHER) || b.total - a.total)
  return (
    <section className="card chart-card">
      <header className="chart-header">
        <h3>{title}</h3>
        <div className="chart-total">{format(data.total)}</div>
      </header>
      <div className="chart-body">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data.points} margin={{ top: 8, right: 4, left: 0, bottom: 0 }} barCategoryGap="18%">
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="t"
              tickFormatter={(t) => bucketLabel(t, kind)}
              tickLine={false}
              minTickGap={18}
              tick={{ fontSize: 11 }}
            />
            <YAxis
              tickFormatter={axisFormat}
              width={56}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11 }}
              allowDecimals
            />
            <Tooltip
              content={<ChartTooltip kind={kind} series={series} dim={dim} format={format} />}
              cursor={{ className: 'chart-cursor' }}
              isAnimationActive={false}
            />
            {series.map((s) => (
              <Bar
                key={s.id}
                dataKey={s.id}
                stackId="stack"
                maxBarSize={24}
                isAnimationActive={false}
                shape={(props) => <Segment {...props} seriesId={s.id} order={order} color={s.color} />}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      {legend.length > 0 ? (
        <ul className="legend">
          {legend.map((s) => (
            <li key={s.id} title={displayName(dim, s.key)}>
              <span className="swatch" style={{ background: s.color }} />
              <span className="legend-name">{shortName(dim, s.key)}</span>
              <span className="legend-value">{format(s.total)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty">No usage in this period</p>
      )}
    </section>
  )
}
