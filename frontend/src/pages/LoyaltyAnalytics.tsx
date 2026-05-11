import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappeGetCall } from '@/lib/frappe'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  TrendingUp, TrendingDown, Users, Coins, Clock, BarChart3,
  Gift, Zap, Star, AlertTriangle, ArrowUpRight
} from 'lucide-react'
import { cn } from '@/lib/utils'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Summary {
  total_coins_issued: number
  total_coins_redeemed: number
  active_customers: number
  customers_expiring_soon: number
  redemption_rate_percent: number
  avg_balance: number
  today_redeemed_restaurant: number
}

interface EarnReason {
  reason: string
  total_coins: number
  count: number
}

interface TopEarner {
  customer: string
  name: string
  phone: string
  lifetime_coins: number
}

interface ExpiringSoon {
  customer: string
  name: string
  phone: string
  net_balance: number
  earliest_expiry: string | null
}

interface DayPoint {
  date: string
  earned: number
  redeemed: number
}

interface AnalyticsData {
  summary: Summary
  earn_by_reason: EarnReason[]
  top_earners: TopEarner[]
  expiring_soon: ExpiringSoon[]
  daily_trend: DayPoint[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const REASON_ICONS: Record<string, React.ReactNode> = {
  'Order':           <Zap className="w-3.5 h-3.5 text-orange-500" />,
  'Welcome Bonus':   <Star className="w-3.5 h-3.5 text-yellow-500" />,
  'Referral Share':  <Users className="w-3.5 h-3.5 text-blue-500" />,
  'Referral Order':  <Users className="w-3.5 h-3.5 text-blue-400" />,
  'Birthday Bonus':  <Gift className="w-3.5 h-3.5 text-pink-500" />,
  'Manual Adjustment': <ArrowUpRight className="w-3.5 h-3.5 text-slate-500" />,
}

function daysUntil(dateStr: string | null): number {
  if (!dateStr) return 999
  const diff = new Date(dateStr).getTime() - new Date().setHours(0, 0, 0, 0)
  return Math.ceil(diff / 86400000)
}

function fmt(n: number) {
  return n >= 1000 ? `₹${(n / 1000).toFixed(1)}k` : `₹${n}`
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({
  label, value, sub, icon, highlight, warn,
}: {
  label: string
  value: string | number
  sub?: string
  icon: React.ReactNode
  highlight?: boolean
  warn?: boolean
}) {
  return (
    <Card className={cn(
      'relative overflow-hidden',
      highlight && 'border-primary/30 bg-primary/5',
      warn && 'border-amber-300/60 bg-amber-50/40 dark:border-amber-700/40 dark:bg-amber-900/10',
    )}>
      <CardContent className="p-4 flex items-start gap-3">
        <div className={cn(
          'w-9 h-9 rounded-lg flex items-center justify-center shrink-0',
          highlight ? 'bg-primary/15' : warn ? 'bg-amber-100 dark:bg-amber-900/30' : 'bg-muted',
        )}>
          {icon}
        </div>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground truncate">{label}</p>
          <p className="text-2xl font-bold leading-tight">{value}</p>
          {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  )
}

// ── Mini bar chart (pure CSS) ─────────────────────────────────────────────────

function MiniTrend({ data }: { data: DayPoint[] }) {
  if (!data.length) return <p className="text-xs text-muted-foreground py-4 text-center">No data yet</p>

  const last14 = data.slice(-14)
  const maxVal  = Math.max(...last14.map(d => Math.max(d.earned, d.redeemed)), 1)

  return (
    <div className="space-y-2">
      <div className="flex items-end gap-1 h-24">
        {last14.map((d, i) => (
          <div key={i} className="flex-1 flex flex-col items-center gap-0.5 h-full justify-end">
            {/* Earned bar */}
            <div
              className="w-full rounded-sm bg-primary/60"
              style={{ height: `${(d.earned / maxVal) * 100}%`, minHeight: d.earned ? 2 : 0 }}
              title={`${d.date}: ₹${d.earned} earned`}
            />
            {/* Redeemed bar */}
            <div
              className="w-full rounded-sm bg-blue-400/60"
              style={{ height: `${(d.redeemed / maxVal) * 100}%`, minHeight: d.redeemed ? 2 : 0 }}
              title={`${d.date}: ₹${d.redeemed} redeemed`}
            />
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
        <span>{last14[0]?.date?.slice(5)}</span>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-primary/60 inline-block" /> Earned</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-blue-400/60 inline-block" /> Redeemed</span>
        </div>
        <span>{last14[last14.length - 1]?.date?.slice(5)}</span>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function LoyaltyAnalytics() {
  const { selectedRestaurant } = useRestaurant()

  const { data: raw, isLoading } = useFrappeGetCall(
    'dinematters.dinematters.api.loyalty.get_loyalty_analytics',
    selectedRestaurant ? { restaurant_id: selectedRestaurant } : undefined,
    selectedRestaurant ? `LoyaltyAnalytics-${selectedRestaurant}` : undefined,
  )

  const res = (raw as any)?.message ?? (raw as any)
  const ok: AnalyticsData | null = res?.success ? res.data : null

  const s = ok?.summary

  // 30-day totals from trend
  const trend30Earn   = ok?.daily_trend.reduce((a, d) => a + d.earned,   0) ?? 0
  const trend30Redeem = ok?.daily_trend.reduce((a, d) => a + d.redeemed, 0) ?? 0

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-12">

      {/* Header */}
      <div className="flex items-center gap-3">
        <BarChart3 className="w-7 h-7 text-primary" />
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Loyalty Analytics</h1>
          <p className="text-sm text-muted-foreground">Programme health at a glance — all time + last 30 days</p>
        </div>
      </div>

      {/* ── Summary KPIs ──────────────────────────────────────────────── */}
      {isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : !ok ? (
        <Card className="border-destructive/30 bg-destructive/5">
          <CardContent className="p-6 text-sm text-destructive">
            Failed to load analytics. Please refresh.
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Total Cash Issued"
              value={fmt(s!.total_coins_issued)}
              sub="all time, settled"
              icon={<Coins className="w-4 h-4 text-primary" />}
              highlight
            />
            <StatCard
              label="Total Cash Redeemed"
              value={fmt(s!.total_coins_redeemed)}
              sub={`${s!.redemption_rate_percent}% redemption rate`}
              icon={<TrendingDown className="w-4 h-4 text-blue-500" />}
            />
            <StatCard
              label="Active Customers"
              value={s!.active_customers}
              sub="have earned at least once"
              icon={<Users className="w-4 h-4 text-green-500" />}
            />
            <StatCard
              label="Avg Wallet Balance"
              value={`₹${s!.avg_balance}`}
              sub="per customer with balance"
              icon={<TrendingUp className="w-4 h-4 text-orange-500" />}
            />
            <StatCard
              label="Expiring in 7 Days"
              value={s!.customers_expiring_soon}
              sub="customers need a nudge"
              icon={<Clock className="w-4 h-4 text-amber-500" />}
              warn={s!.customers_expiring_soon > 0}
            />
            <StatCard
              label="Issued (30 days)"
              value={fmt(trend30Earn)}
              sub="last 30 days"
              icon={<Zap className="w-4 h-4 text-orange-400" />}
            />
            <StatCard
              label="Redeemed (30 days)"
              value={fmt(trend30Redeem)}
              sub="last 30 days"
              icon={<Gift className="w-4 h-4 text-blue-400" />}
            />
            <StatCard
              label="Today's Redemptions"
              value={fmt(s!.today_redeemed_restaurant)}
              sub="across all customers"
              icon={<BarChart3 className="w-4 h-4 text-slate-500" />}
            />
          </div>

          {/* ── Daily Trend ──────────────────────────────────────────────── */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-primary" />
                Last 14 Days — Earn vs Redeem
              </CardTitle>
              <CardDescription>Daily coin volumes (settled transactions only)</CardDescription>
            </CardHeader>
            <CardContent>
              <MiniTrend data={ok.daily_trend} />
            </CardContent>
          </Card>

          {/* ── Earn Breakdown + Top Earners ─────────────────────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Zap className="w-4 h-4 text-orange-500" />
                  Coins Issued by Reason
                </CardTitle>
                <CardDescription>Where customers earn the most</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {ok.earn_by_reason.length === 0 && (
                  <p className="text-sm text-muted-foreground">No data yet.</p>
                )}
                {ok.earn_by_reason.map((r) => {
                  const pct = s!.total_coins_issued
                    ? Math.round((r.total_coins / s!.total_coins_issued) * 100)
                    : 0
                  return (
                    <div key={r.reason}>
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="flex items-center gap-1.5 text-sm">
                          {REASON_ICONS[r.reason] ?? <Coins className="w-3.5 h-3.5 text-muted-foreground" />}
                          {r.reason}
                        </span>
                        <span className="text-sm font-semibold tabular-nums">
                          {fmt(r.total_coins)}
                          <span className="text-xs text-muted-foreground ml-1">({pct}%)</span>
                        </span>
                      </div>
                      <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full rounded-full bg-primary/60"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  )
                })}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Star className="w-4 h-4 text-yellow-500" />
                  Top 5 Earners
                </CardTitle>
                <CardDescription>By lifetime coins earned at your restaurant</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {ok.top_earners.length === 0 && (
                  <p className="text-sm text-muted-foreground">No data yet.</p>
                )}
                {ok.top_earners.map((c, i) => (
                  <div key={c.customer} className="flex items-center gap-3">
                    <span className={cn(
                      'w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0',
                      i === 0 ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30' :
                      i === 1 ? 'bg-slate-100 text-slate-600 dark:bg-slate-800' :
                      i === 2 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30' :
                                'bg-muted text-muted-foreground'
                    )}>
                      {i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{c.name}</p>
                      <p className="text-xs text-muted-foreground">{c.phone}</p>
                    </div>
                    <span className="text-sm font-bold tabular-nums text-primary">
                      {fmt(c.lifetime_coins)}
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>

          {/* ── Expiring Soon ────────────────────────────────────────────── */}
          {ok.expiring_soon.length > 0 && (
            <Card className="border-amber-300/60 dark:border-amber-700/40">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                  Coins Expiring in 7 Days
                  <Badge className="ml-1 text-xs bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 border-amber-300 dark:border-amber-700">
                    {ok.expiring_soon.length} customers
                  </Badge>
                </CardTitle>
                <CardDescription>
                  These customers have unspent cash about to expire — consider sending them a nudge via WhatsApp or push
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {ok.expiring_soon.map((c) => {
                    const d = daysUntil(c.earliest_expiry)
                    return (
                      <div key={c.customer} className="flex items-center justify-between py-1.5 border-b last:border-0">
                        <div className="min-w-0">
                          <p className="text-sm font-medium truncate">{c.name}</p>
                          <p className="text-xs text-muted-foreground">{c.phone}</p>
                        </div>
                        <div className="flex items-center gap-3 shrink-0">
                          <span className="text-sm font-semibold tabular-nums">₹{c.net_balance}</span>
                          <Badge variant="outline" className={cn(
                            'text-xs',
                            d === 0 ? 'border-red-400 text-red-600 bg-red-50 dark:bg-red-900/20' :
                            d <= 2  ? 'border-amber-400 text-amber-700 bg-amber-50 dark:bg-amber-900/20' :
                                      'border-yellow-400 text-yellow-700 bg-yellow-50 dark:bg-yellow-900/20'
                          )}>
                            {d === 0 ? 'Today' : d === 1 ? 'Tomorrow' : `${d} days`}
                          </Badge>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
