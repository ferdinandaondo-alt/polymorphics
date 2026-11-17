// The API stores money as integers in "minor units" (cents). These helpers convert to and from
// what people read and type, using string maths for input so 0.1 + 0.2 style float bugs can't creep in.

export function minorDigits(currency) {
  try {
    return new Intl.NumberFormat('en', { style: 'currency', currency }).resolvedOptions().maximumFractionDigits
  } catch {
    return 2
  }
}

export function formatMoney(minor, currency) {
  const d = minorDigits(currency)
  try {
    return new Intl.NumberFormat('en', { style: 'currency', currency, minimumFractionDigits: d, maximumFractionDigits: d })
      .format(minor / 10 ** d)
  } catch {
    return `${(minor / 10 ** d).toFixed(d)} ${currency}`
  }
}

// "12.50" -> 1250. Returns null for anything that isn't a clean, positive amount.
export function toMinor(input, currency) {
  const d = minorDigits(currency)
  const s = String(input ?? '').trim()
  if (!/^\d+(\.\d+)?$/.test(s)) return null
  const [whole, frac = ''] = s.split('.')
  if (frac.length > d) return null
  const minor = Number(whole) * 10 ** d + Number((frac + '0'.repeat(d)).slice(0, d) || '0')
  return Number.isSafeInteger(minor) && minor > 0 ? minor : null
}

// Mirrors the server's fee rule for the on-screen preview only; the server's number is the real one.
export function estimateFee(amountMinor, feeBps) {
  return Math.floor((amountMinor * feeBps + 5000) / 10000)
}
