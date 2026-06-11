import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

interface BillLine { label: string; value: number; type: string }

const money = (v: number | undefined | null) =>
  `₹${Math.abs(Number(v || 0)).toLocaleString('en-IN')}`

/**
 * Public, token-secured order receipt for MERCHANTS.
 * Opened from the WhatsApp "View Full Order" button → /flamezo_backend/o/:token.
 * No login required (backend get_order_receipt is allow_guest, token-secured).
 */
export default function OrderReceipt() {
  const { token } = useParams<{ token: string }>()
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!token) return
    let alive = true
    fetch(
      `/api/method/flamezo_backend.flamezo.api.orders.get_order_receipt?token=${encodeURIComponent(token)}`,
      { credentials: 'include', headers: { Accept: 'application/json' } },
    )
      .then((r) => r.json())
      .then((json) => {
        if (!alive) return
        const payload = json?.message ?? json
        if (payload?.success) setData(payload.data)
        else setError(payload?.error || 'Order not found')
      })
      .catch(() => { if (alive) setError('Could not load this order.') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [token])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="w-10 h-10 rounded-full border-[3px] border-muted border-t-primary animate-spin" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background px-6 text-center">
        <p className="text-lg font-black text-foreground">Order not found</p>
        <p className="text-sm text-muted-foreground mt-1">{error || 'This link may have expired.'}</p>
      </div>
    )
  }

  const order = data.order || {}
  const items: any[] = order.items || []
  const bill: BillLine[] = order.billDetails || []
  const notes: string[] = order.cookingRequests || []
  const orderType: string = order.orderType || 'dine_in'
  const fulfil =
    orderType === 'dine_in'
      ? (order.tableNumber ? `Dine-in · Table ${order.tableNumber}` : 'Dine-in')
      : orderType === 'takeaway' ? 'Takeaway' : 'Delivery'
  const paidOnline = data.paymentMethod === 'pay_online'

  return (
    <div className="min-h-screen bg-background pb-10">
      {/* Restaurant header */}
      <div className="px-5 pt-7 pb-5 flex items-center gap-3 max-w-md mx-auto">
        {data.restaurant?.logo ? (
          <img src={data.restaurant.logo} alt="" className="w-11 h-11 rounded-xl object-cover" />
        ) : null}
        <div>
          <p className="text-[15px] font-black text-foreground leading-tight">{data.restaurant?.name || 'Flamezo'}</p>
          <p className="text-[12px] text-muted-foreground">New order</p>
        </div>
      </div>

      <div className="max-w-md mx-auto px-4">
        <div className="rounded-2xl bg-card border border-border shadow-sm overflow-hidden">
          {/* Order header */}
          <div className="px-5 py-4 border-b border-border flex items-center justify-between">
            <div>
              <p className="text-[11px] font-black uppercase tracking-wider text-muted-foreground">Order</p>
              <p className="text-xl font-black text-foreground">#{order.orderNumber || order.id}</p>
            </div>
            <span
              className={`text-[12px] font-black px-3 py-1.5 rounded-full ${
                paidOnline ? 'bg-green-500/10 text-green-600' : 'bg-primary/10 text-primary'
              }`}
            >
              {paidOnline ? 'Paid online' : 'Collect at counter'}
            </span>
          </div>

          {/* Customer + fulfilment */}
          <div className="px-5 py-4 border-b border-border space-y-1">
            <p className="text-[14px] font-bold text-foreground">
              {order.customer?.name || 'Guest'}{order.customer?.phone ? ` · ${order.customer.phone}` : ''}
            </p>
            <p className="text-[13px] text-muted-foreground">{fulfil}</p>
          </div>

          {/* Items */}
          <div className="px-5 py-4 border-b border-border">
            <p className="text-[11px] font-black uppercase tracking-wider text-muted-foreground mb-2.5">Items</p>
            <div className="space-y-2.5">
              {items.map((it, i) => (
                <div key={i} className="flex items-start justify-between gap-3">
                  <div className="flex gap-2 min-w-0">
                    <span className="text-[14px] font-black text-primary">{it.quantity}×</span>
                    <div className="min-w-0">
                      <p className="text-[14px] font-semibold text-foreground leading-tight">{it.dish?.name || 'Item'}</p>
                      {Array.isArray(it.customizations) && it.customizations.length > 0 && (
                        <p className="text-[12px] text-muted-foreground">
                          {it.customizations.map((c: any) => c.name || c).join(', ')}
                        </p>
                      )}
                    </div>
                  </div>
                  <span className="text-[14px] font-bold text-foreground shrink-0">{money(it.totalPrice ?? it.unitPrice)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Cooking notes */}
          {notes.length > 0 && (
            <div className="px-5 py-4 border-b border-border">
              <p className="text-[11px] font-black uppercase tracking-wider text-muted-foreground mb-1.5">Notes</p>
              <p className="text-[13px] text-foreground/80">{notes.join(' · ')}</p>
            </div>
          )}

          {/* Bill breakdown */}
          <div className="px-5 py-4">
            <p className="text-[11px] font-black uppercase tracking-wider text-muted-foreground mb-2.5">Bill</p>
            <div className="space-y-2">
              {bill.map((line, i) => {
                const isTotal = line.type === 'total'
                const isDiscount = line.type === 'discount'
                return (
                  <div key={i} className={`flex items-center justify-between ${isTotal ? 'pt-2 mt-1 border-t border-border' : ''}`}>
                    <span className={isTotal ? 'text-[15px] font-black text-foreground' : 'text-[13px] text-muted-foreground'}>{line.label}</span>
                    <span
                      className={`${isTotal ? 'text-[16px] font-black text-foreground' : 'text-[13px] font-semibold'} ${isDiscount ? 'text-green-600' : 'text-foreground/90'}`}
                    >
                      {isDiscount ? '−' : ''}{money(line.value)}
                    </span>
                  </div>
                )
              })}
            </div>

            {/* Coupon / loyalty / cashback context */}
            {(data.coupon || data.loyaltyCoinsRedeemed > 0 || data.coinsEarned > 0) && (
              <div className="mt-3 pt-3 border-t border-dashed border-border space-y-1">
                {data.coupon && (
                  <p className="text-[12px] text-muted-foreground">Coupon applied: <span className="font-bold text-foreground/80">{data.coupon}</span></p>
                )}
                {data.loyaltyCoinsRedeemed > 0 && (
                  <p className="text-[12px] text-muted-foreground">Loyalty redeemed: <span className="font-bold text-foreground/80">{data.loyaltyCoinsRedeemed} coins</span></p>
                )}
                {data.coinsEarned > 0 && (
                  <p className="text-[12px] text-muted-foreground">Customer earns: <span className="font-bold text-primary">{data.coinsEarned} coins</span> cashback</p>
                )}
              </div>
            )}
          </div>
        </div>

        <p className="text-center text-[11px] text-muted-foreground mt-5">Powered by Flamezo</p>
      </div>
    </div>
  )
}
