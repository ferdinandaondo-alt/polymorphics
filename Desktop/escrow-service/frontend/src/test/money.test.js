import { describe, expect, it } from 'vitest'
import { estimateFee, formatMoney, toMinor } from '../money'
import { parseDate } from '../labels'

describe('money', () => {
  it('converts typed amounts to integer minor units without float errors', () => {
    expect(toMinor('150.00', 'USD')).toBe(15000)
    expect(toMinor('150', 'USD')).toBe(15000)
    expect(toMinor('0.1', 'USD')).toBe(10)
    expect(toMinor('0.07', 'USD')).toBe(7)
    expect(toMinor(' 12.5 ', 'USD')).toBe(1250)
    expect(toMinor('19.99', 'USD')).toBe(1999)     // 19.99 * 100 = 1998.9999999999998 with floats
  })
  it('rejects anything that is not a clean positive amount', () => {
    for (const bad of ['', 'abc', '0', '0.00', '-5', '1.234', '1,000', '1e3', '12.', '.5', null, undefined]) {
      expect(toMinor(bad, 'USD')).toBeNull()
    }
  })
  it('respects currencies with no decimals', () => {
    expect(toMinor('500', 'JPY')).toBe(500)
    expect(toMinor('500.5', 'JPY')).toBeNull()
    expect(formatMoney(500, 'JPY')).toContain('500')
  })
  it('formats minor units for display', () => {
    expect(formatMoney(51250, 'USD')).toBe('$512.50')
    expect(formatMoney(5, 'USD')).toBe('$0.05')
  })
  it('estimates the fee exactly like the server (half-up, integer)', () => {
    expect(estimateFee(50000, 250)).toBe(1250)
    expect(estimateFee(10001, 250)).toBe(250)
    expect(estimateFee(1, 250)).toBe(0)
  })
  it('treats timestamps without a timezone as UTC', () => {
    expect(parseDate('2026-01-01T10:00:00').toISOString()).toBe('2026-01-01T10:00:00.000Z')
    expect(parseDate('2026-01-01T10:00:00+00:00').toISOString()).toBe('2026-01-01T10:00:00.000Z')
    expect(parseDate(null)).toBeNull()
  })
})
