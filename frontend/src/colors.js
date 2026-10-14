// Series colours follow the entity, not its rank in the current view: the all-time top
// entities of a dimension own fixed palette slots, others borrow free slots per view.

export const OTHER = '__other__'
export const NULL_KEY = '__null__'
const SLOTS = 8

export const keyOf = (value) => (value === null || value === undefined ? NULL_KEY : value)

export function assignSlots(seriesKeys, allTimeOrder = []) {
  const fixed = new Map()
  allTimeOrder.slice(0, SLOTS).forEach((v, i) => fixed.set(keyOf(v), i))
  const slots = {}
  const used = new Set()
  for (const k of seriesKeys) {
    if (k !== OTHER && fixed.has(k)) {
      slots[k] = fixed.get(k)
      used.add(slots[k])
    }
  }
  let next = 0
  for (const k of seriesKeys) {
    if (k === OTHER || k in slots) continue
    while (used.has(next)) next++
    slots[k] = next < SLOTS ? next : null
    used.add(next)
  }
  return slots
}

export const slotColor = (slot) => (slot === null || slot === undefined ? 'var(--series-other)' : `var(--series-${slot + 1})`)

const DIM_NULL_LABEL = { app: 'Unknown app', finish_reason: 'No finish reason', origin: 'No origin', user: 'Unknown user' }

export function displayName(dim, key) {
  if (key === OTHER) return 'Other'
  if (key === NULL_KEY || key === null || key === undefined || key === '') return DIM_NULL_LABEL[dim] || '(none)'
  return String(key)
}

// "google/gemini-3.7-flash-20260813" -> "google/gemini-3.7-flash"
export function shortName(dim, key) {
  const name = displayName(dim, key)
  return dim === 'model' ? name.replace(/-\d{8}$/, '') : name
}
