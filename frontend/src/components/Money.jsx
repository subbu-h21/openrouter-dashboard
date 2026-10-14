import { inr, money } from '../format.js'

// Dollar amount with the rupee equivalent beside it in muted text.
export default function Money({ v, precise = false }) {
  const rupees = Number(v) === 0 ? null : inr(v) // "$0 ₹0" is just noise
  return (
    <span className="money">
      {money(v, { precise })}
      {rupees && <span className="inr">{rupees}</span>}
    </span>
  )
}
