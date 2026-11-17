export const STATUS_LABEL = {
  draft: 'Awaiting acceptance', accepted: 'Awaiting payment', funded: 'Funded', delivered: 'Delivered',
  released: 'Released', refunded: 'Refunded', disputed: 'In dispute', cancelled: 'Cancelled', expired: 'Expired',
}
export const STEPS = ['draft', 'accepted', 'funded', 'delivered', 'released']
export const STEP_LABEL = { draft: 'Created', accepted: 'Accepted', funded: 'Funded', delivered: 'Delivered', released: 'Released' }

// A deal where it's this user's turn to act.
export function needsMyAction(t, userId) {
  if (t.status === 'draft') return t.created_by_id !== userId
  if (t.status === 'accepted') return t.buyer_id === userId
  if (t.status === 'funded') return t.seller_id === userId
  if (t.status === 'delivered') return t.buyer_id === userId
  return false
}
export const isFinished = (t) => ['released', 'refunded', 'cancelled', 'expired'].includes(t.status)

// Ledger account names -> words a person understands.
export function accountLabel(account) {
  if (account === 'escrow_holding') return 'Escrow'
  if (account === 'platform_revenue') return 'Platform fee'
  if (account.startsWith('buyer_external')) return "Buyer's payment method"
  if (account.startsWith('seller_payable')) return "Seller's balance"
  return account
}
export const ENTRY_LABEL = { funding: 'Funding', release: 'Release', refund: 'Refund', fee: 'Fee', payout: 'Payout', adjustment: 'Adjustment' }

// The API sends UTC timestamps; some databases omit the timezone marker, so add it when missing.
export const parseDate = (iso) => (iso ? new Date(/Z$|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z') : null)
export const fmtDate = (iso) => (iso ? parseDate(iso).toLocaleString() : '—')
