import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall } from '@/lib/frappe'
import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import {
  ChevronLeft, CheckCircle2, XCircle, ScanLine, Zap, Ticket, Calendar, Hash
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

interface RedeemResult {
  success: boolean
  message: string
  discount?: number
  campaign_name?: string
}

interface QuickStats {
  today: number
  week: number
  total: number
}

export default function BoostRedeem() {
  const { selectedRestaurant } = useRestaurant()
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [billAmount, setBillAmount] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<RedeemResult | null>(null)
  const [stats, setStats] = useState<QuickStats>({ today: 0, week: 0, total: 0 })
  const [recentRedemptions, setRecentRedemptions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const { call: redeemCoupon } = useFrappePostCall('flamezo_backend.flamezo.api.boost.redeem_boost_coupon')
  const { call: fetchOverview } = useFrappePostCall('flamezo_backend.flamezo.api.boost.get_boost_overview')

  // Load stats on mount
  useEffect(() => {
    if (!selectedRestaurant) return
    fetchOverview({ restaurant_id: selectedRestaurant })
      .then((r: any) => {
        const data = r?.message?.data || r?.data
        if (data) {
          setStats({
            today: 0, // We approximate from campaign data
            week: data.total_redemptions,
            total: data.total_redemptions,
          })
          // Get recent campaigns with redemptions
          const withRedemptions = (data.campaigns || [])
            .filter((c: any) => c.coupons_redeemed > 0)
            .slice(0, 5)
          setRecentRedemptions(withRedemptions)
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [selectedRestaurant])

  const handleRedeem = async () => {
    if (!selectedRestaurant || !code.trim()) return
    setSubmitting(true); setResult(null)
    try {
      const res: any = await redeemCoupon({
        restaurant_id: selectedRestaurant,
        coupon_code: code.trim().toUpperCase(),
        bill_amount: billAmount ? parseFloat(billAmount) : undefined,
        redemption_method: 'Staff Entry',
      })
      const data = res?.message?.data || res?.data
      setResult({ success: true, message: data.message, discount: data.discount, campaign_name: data.campaign_name })
      setCode(''); setBillAmount('')
      setStats(s => ({ ...s, today: s.today + 1, total: s.total + 1 }))
      toast.success(`₹${data.discount} discount applied!`)
    } catch (e: any) {
      setResult({ success: false, message: e?.message || 'Invalid coupon code' })
      toast.error('Invalid coupon code')
    } finally { setSubmitting(false) }
  }

  return (
    <div className="max-w-lg space-y-6">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1.5 text-[11px] font-bold tracking-widest uppercase text-muted-foreground/60 mb-2">
        <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
        <ChevronRight className="h-3 w-3" />
        <Link to="/boost" className="hover:text-foreground transition-colors">Boost</Link>
        <ChevronRight className="h-3 w-3" />
        <span className="text-foreground">Redeem Coupon</span>
      </nav>

      {/* Back */}
      <Button variant="ghost" size="sm" onClick={() => navigate('/boost')} className="-ml-2 gap-1">
        <ChevronLeft className="h-4 w-4" /> Back to Boost
      </Button>

      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-orange-500 to-amber-600 flex items-center justify-center shadow-lg shadow-orange-500/20">
          <ScanLine className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Redeem Coupon</h1>
          <p className="text-sm text-muted-foreground">Enter the customer's Boost coupon code</p>
        </div>
      </div>

      {/* Quick Stats */}
      {!loading && (
        <div className="grid grid-cols-3 gap-3">
          <Card className="border-none bg-card shadow-sm"><CardContent className="pt-3 pb-2 text-center">
            <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Today</p>
            <p className="text-2xl font-bold text-orange-600">{stats.today}</p>
          </CardContent></Card>
          <Card className="border-none bg-card shadow-sm"><CardContent className="pt-3 pb-2 text-center">
            <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">This Week</p>
            <p className="text-2xl font-bold">{stats.week}</p>
          </CardContent></Card>
          <Card className="border-none bg-card shadow-sm"><CardContent className="pt-3 pb-2 text-center">
            <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Total</p>
            <p className="text-2xl font-bold">{stats.total}</p>
          </CardContent></Card>
        </div>
      )}

      {/* Result Banner */}
      {result && (
        <Card className={cn(
          'animate-in zoom-in-95 duration-300 border-none shadow-sm',
          result.success ? 'bg-emerald-50 dark:bg-emerald-950/20' : 'bg-red-50 dark:bg-red-950/20'
        )}>
          <CardContent className="pt-4 pb-3 flex items-start gap-3">
            {result.success ? (
              <div className="h-8 w-8 rounded-full bg-emerald-500 flex items-center justify-center shrink-0">
                <CheckCircle2 className="h-5 w-5 text-white" />
              </div>
            ) : (
              <div className="h-8 w-8 rounded-full bg-red-500 flex items-center justify-center shrink-0">
                <XCircle className="h-5 w-5 text-white" />
              </div>
            )}
            <div>
              <p className={cn('font-semibold', result.success ? 'text-emerald-800 dark:text-emerald-200' : 'text-red-800 dark:text-red-200')}>
                {result.success ? 'Coupon Redeemed!' : 'Redemption Failed'}
              </p>
              <p className={cn('text-sm mt-0.5', result.success ? 'text-emerald-600' : 'text-red-600')}>
                {result.message}
              </p>
              {result.campaign_name && <p className="text-xs text-muted-foreground mt-1">Campaign: {result.campaign_name}</p>}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Redeem Form */}
      <Card className="border-none bg-card shadow-sm">
        <CardContent className="pt-6 space-y-4">
          <div>
            <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Coupon Code</Label>
            <Input
              value={code} onChange={e => setCode(e.target.value.toUpperCase())}
              placeholder="BOOST-XXXXX-XXXXXX"
              className="mt-1.5 text-center font-mono text-lg tracking-wider h-12"
              onKeyDown={e => e.key === 'Enter' && handleRedeem()}
              autoFocus
            />
          </div>
          <div>
            <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Bill Amount (optional)</Label>
            <div className="relative mt-1.5">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">₹</span>
              <Input
                type="number" value={billAmount} onChange={e => setBillAmount(e.target.value)}
                placeholder="Total bill" className="pl-7 text-center text-lg h-12"
                onKeyDown={e => e.key === 'Enter' && handleRedeem()}
              />
            </div>
            <p className="text-[11px] text-muted-foreground mt-1">Helps track revenue from Boost campaigns</p>
          </div>
          <Button onClick={handleRedeem} disabled={!code.trim() || submitting} size="lg"
            className="w-full gap-2 bg-gradient-to-r from-orange-500 to-amber-600 text-white h-12 text-base">
            {submitting ? <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" /> : <ScanLine className="h-5 w-5" />}
            {submitting ? 'Verifying...' : 'Redeem Coupon'}
          </Button>
        </CardContent>
      </Card>

      {/* Recent Activity */}
      {recentRedemptions.length > 0 && (
        <Card className="border-none bg-card shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Active Campaigns</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {recentRedemptions.map((c: any) => (
              <div key={c.name} className="flex items-center justify-between p-3 rounded-lg border text-sm">
                <div>
                  <p className="font-medium">{c.campaign_name}</p>
                  <p className="text-xs text-muted-foreground">{c.coupon_code}</p>
                </div>
                <Badge variant="secondary">{c.coupons_redeemed} walk-ins</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Tips */}
      <Card className="border-none bg-card shadow-sm">
        <CardContent className="pt-4 pb-3">
          <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">Tips for Staff</p>
          <ul className="text-xs text-muted-foreground space-y-1">
            <li>• Ask the customer to show their coupon code from their phone</li>
            <li>• Enter the bill amount for better revenue tracking</li>
            <li>• Each coupon can be used multiple times (unlimited)</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
