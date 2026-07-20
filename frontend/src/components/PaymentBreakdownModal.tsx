/**
 * PaymentBreakdownModal
 * Merchant-only payment detail — a premium right-side Sheet: gradient hero with
 * the bill, an animated proportion bar visualising the split, colour-coded
 * you-vs-Flamezo cards, and a compact audit-style detail list.
 */

import { motion } from 'framer-motion'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Wallet, Tag, ArrowDown, Landmark, ShieldAlert, PieChart } from 'lucide-react'

export interface PaymentBreakdown {
  bill: number
  customerSaved: number
  couponCode: string | null
  merchantGets: number
  flamezoGets: number
  settlementMode: string | null
  estimated?: boolean
}

interface Props {
  open: boolean
  onClose: () => void
  paymentId?: string
  dateLabel?: string
  status?: string
  method?: string
  breakdown?: PaymentBreakdown | null
}

const fmt = (n: number) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n || 0)

const pct = (part: number, whole: number) => (whole > 0 ? Math.round((part / whole) * 100) : 0)

function Row({ label, value, mono }: { label: string; value?: string | null; mono?: boolean }) {
  if (!value) return null
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-2.5">
      <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className={`text-[12.5px] tabular-nums text-right font-semibold text-foreground ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  )
}

export default function PaymentBreakdownModal({ open, onClose, paymentId, dateLabel, status, method, breakdown: b }: Props) {
  const mPct = b ? pct(b.merchantGets, b.bill) : 0
  const fPct = b ? Math.max(0, 100 - mPct) : 0

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="sm:max-w-md bg-background/95 backdrop-blur-xl border-l-0 shadow-[-20px_0_50px_rgba(0,0,0,0.15)] p-0 flex flex-col">
        {/* Dark hero with a subtle brand glow */}
        <div className="relative overflow-hidden bg-gradient-to-br from-slate-900 to-slate-800 px-6 pt-6 pb-7 text-white">
          <div className="absolute -right-12 -top-14 h-48 w-48 rounded-full bg-orange-500/25 blur-3xl" aria-hidden />
          <div className="absolute right-8 -bottom-10 h-40 w-40 rounded-full bg-emerald-500/10 blur-3xl" aria-hidden />
          <Wallet className="absolute right-5 bottom-3 h-16 w-16 opacity-10" aria-hidden />
          <SheetHeader className="relative">
            <div className="flex items-center gap-3">
              <div className="h-11 w-11 rounded-2xl bg-white/20 backdrop-blur flex items-center justify-center shrink-0">
                <Wallet className="h-6 w-6 text-white" />
              </div>
              <div className="min-w-0 text-left">
                <SheetTitle className="text-lg font-bold text-white leading-tight">Payment received</SheetTitle>
                <SheetDescription className="text-[10px] font-bold uppercase tracking-wider text-white/80 font-mono truncate">{paymentId}</SheetDescription>
              </div>
            </div>
          </SheetHeader>

          {b && (
            <motion.div
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
              className="mt-5 relative"
            >
              <p className="text-[10px] uppercase tracking-wider text-white/80 font-bold">Bill amount</p>
              <div className="flex items-end gap-2 mt-0.5">
                <span className="text-4xl font-black tabular-nums tracking-tight">{fmt(b.bill)}</span>
                {status && (
                  <Badge className="mb-1.5 bg-emerald-500 text-white border-none text-[9px] uppercase font-bold tracking-wider">{status}</Badge>
                )}
              </div>
              {b.couponCode ? (
                <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-white/20 backdrop-blur px-2.5 py-1 text-[11px] font-semibold">
                  <Tag className="h-3 w-3" />{b.couponCode} · customer saved {fmt(b.customerSaved)}
                </div>
              ) : (
                <p className="text-[11px] text-white/70 mt-1.5">No offer applied</p>
              )}
            </motion.div>
          )}
        </div>

        <div className="p-6 space-y-5 flex-1 overflow-y-auto">
          {b ? (
            <>
              {/* Split visualisation */}
              <div className="rounded-2xl border bg-card p-4 shadow-sm">
                <div className="flex items-center gap-2 mb-3">
                  <div className="h-7 w-7 rounded-lg bg-orange-500/10 flex items-center justify-center">
                    <PieChart className="h-4 w-4 text-orange-500" />
                  </div>
                  <p className="text-[13px] font-bold">How this payment splits</p>
                </div>

                {/* Proportion bar */}
                <div className="h-3.5 w-full rounded-full bg-muted overflow-hidden flex">
                  <motion.div
                    initial={{ width: 0 }} animate={{ width: `${mPct}%` }} transition={{ duration: 0.6, ease: 'easeOut' }}
                    className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400"
                  />
                  <motion.div
                    initial={{ width: 0 }} animate={{ width: `${fPct}%` }} transition={{ duration: 0.6, ease: 'easeOut', delay: 0.12 }}
                    className="h-full bg-gradient-to-r from-orange-400 to-pink-400"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3 mt-4">
                  <div className="rounded-xl bg-emerald-500/5 border border-emerald-200 dark:border-emerald-900/40 p-3">
                    <div className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-emerald-500" />
                      <p className="text-[9px] uppercase font-black tracking-widest text-emerald-700 dark:text-emerald-400">You get</p>
                    </div>
                    <p className="text-xl font-black tabular-nums text-emerald-700 dark:text-emerald-400 mt-1">{fmt(b.merchantGets)}</p>
                  </div>
                  <div className="rounded-xl bg-muted/40 border p-3">
                    <div className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-gradient-to-r from-orange-400 to-pink-400" />
                      <p className="text-[9px] uppercase font-black tracking-widest text-muted-foreground">Flamezo</p>
                    </div>
                    <p className="text-xl font-black tabular-nums mt-1">{fmt(b.flamezoGets)}</p>
                  </div>
                </div>
              </div>

              {/* Arrow → bank */}
              <div className="flex justify-center -my-1" aria-hidden>
                <div className="rounded-full border bg-background p-1 shadow-sm">
                  <ArrowDown className="h-3.5 w-3.5 text-muted-foreground" />
                </div>
              </div>

              {/* Settled to bank */}
              <div className="flex items-center gap-3 p-4 rounded-2xl border-2 border-emerald-300/60 dark:border-emerald-900/50 bg-gradient-to-r from-emerald-500/10 to-transparent">
                <div className="h-10 w-10 rounded-xl bg-emerald-500/15 flex items-center justify-center shrink-0">
                  <Landmark className="h-5 w-5 text-emerald-600" />
                </div>
                <div className="flex-1">
                  <p className="text-[13px] font-bold">Settled to your bank</p>
                  <p className="text-[11px] text-muted-foreground">Your share is transferred directly</p>
                </div>
                <span className="text-lg font-black tabular-nums text-emerald-700 dark:text-emerald-400">{fmt(b.merchantGets)}</span>
              </div>

              {/* Detail rows */}
              <div className="rounded-2xl border divide-y divide-border/60 bg-card">
                <Row label="Method" value={method ? method.toUpperCase() : undefined} />
                <Row label="Status" value={status} />
                <Row label="Timestamp" value={dateLabel} />
                <Row label="Settlement" value={b.settlementMode || undefined} />
                <Row label="Razorpay ID" value={paymentId} mono />
              </div>

              {b.estimated && (
                <p className="text-[10px] text-muted-foreground leading-snug">
                  * Split estimated from your current success-share % — exact figures are recorded on new orders.
                </p>
              )}
            </>
          ) : (
            <div className="p-4 rounded-2xl border bg-muted/20 text-sm text-muted-foreground">
              A detailed split isn&apos;t available for this payment.
            </div>
          )}
        </div>

        {/* Support note */}
        <div className="px-6 pb-6 mt-auto">
          <div className="p-3 rounded-xl bg-amber-50 border border-amber-100 flex items-start gap-2">
            <ShieldAlert className="h-3.5 w-3.5 text-amber-600 shrink-0 mt-0.5" />
            <p className="text-[10px] text-amber-700 font-bold leading-tight">
              Questions about this payment? Contact Flamezo support with the Payment ID above.
            </p>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
