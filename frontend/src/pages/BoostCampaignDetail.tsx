import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall } from '@/lib/frappe'
import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import {
  ChevronLeft, Eye, MousePointerClick, Ticket, Users, DollarSign,
  Pause, Play, TrendingUp, XCircle, Copy, ExternalLink, Share2,
  Zap, Clock, Calendar, AlertTriangle
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

// ─── Types ──────────────────────────────────────────────────────

interface Redemption {
  redeemed_at: string
  redemption_method: string
  bill_amount: number | null
}

interface CampaignData {
  campaign_id: string; campaign_name: string; status: string
  package_tier: string; budget_total: number; ad_spend_allocated: number
  impressions: number; reach: number; link_clicks: number
  coupons_claimed: number; coupons_redeemed: number
  amount_spent_meta: number; cost_per_redemption: number
  estimated_revenue: number; launch_date: string | null; end_date: string | null
  days_remaining: number; guaranteed_redemptions: number; guarantee_met: boolean
  is_first_campaign: boolean; location_grade: string
  coupon_code: string; offer_amount: number; template_id: string
  redemptions: Redemption[]
}

const STATUS_CONFIG: Record<string, { bg: string; text: string; dot: string }> = {
  Live: { bg: 'bg-emerald-500/10 border-emerald-200 dark:border-emerald-800', text: 'text-emerald-700 dark:text-emerald-300', dot: 'bg-emerald-500 animate-pulse' },
  Paused: { bg: 'bg-orange-500/10 border-orange-200 dark:border-orange-800', text: 'text-orange-700 dark:text-orange-300', dot: 'bg-orange-500' },
  Completed: { bg: 'bg-blue-500/10 border-blue-200 dark:border-blue-800', text: 'text-blue-700 dark:text-blue-300', dot: 'bg-blue-500' },
  Draft: { bg: 'bg-slate-500/10 border-slate-200 dark:border-slate-700', text: 'text-slate-600 dark:text-slate-300', dot: 'bg-slate-400' },
  Submitted: { bg: 'bg-purple-500/10 border-purple-200 dark:border-purple-800', text: 'text-purple-700 dark:text-purple-300', dot: 'bg-purple-500 animate-pulse' },
  Failed: { bg: 'bg-red-500/10 border-red-200 dark:border-red-800', text: 'text-red-700 dark:text-red-300', dot: 'bg-red-500' },
}

const ITEMS_PER_PAGE = 10

// ─── Component ──────────────────────────────────────────────────

export default function BoostCampaignDetail() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const campaignId = searchParams.get('id') || ''
  const [data, setData] = useState<CampaignData | null>(null)
  const [loading, setLoading] = useState(true)
  const [redemptionPage, setRedemptionPage] = useState(1)

  // Dialogs
  const [showPause, setShowPause] = useState(false)
  const [showResume, setShowResume] = useState(false)
  const [showCancel, setShowCancel] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)

  const { call: fetchPerf } = useFrappePostCall('flamezo_backend.flamezo.api.boost.get_boost_performance')
  const { call: pauseApi } = useFrappePostCall('flamezo_backend.flamezo.api.boost.pause_boost_campaign')
  const { call: resumeApi } = useFrappePostCall('flamezo_backend.flamezo.api.boost.resume_boost_campaign')
  const { call: cancelApi } = useFrappePostCall('flamezo_backend.flamezo.api.boost.cancel_boost_campaign')

  useEffect(() => {
    if (!campaignId) return
    fetchPerf({ campaign_id: campaignId })
      .then((r: any) => setData(r?.message?.data || r?.data))
      .catch(() => toast.error('Failed to load campaign'))
      .finally(() => setLoading(false))
  }, [campaignId])

  const handleAction = async (action: 'pause' | 'resume' | 'cancel') => {
    if (!data) return
    setActionLoading(true)
    try {
      const apiMap = { pause: pauseApi, resume: resumeApi, cancel: cancelApi }
      await apiMap[action]({ campaign_id: data.campaign_id })
      const newStatus = action === 'pause' ? 'Paused' : action === 'resume' ? 'Live' : 'Cancelled'
      setData({ ...data, status: newStatus })
      toast.success(`Campaign ${action}d`)
    } catch { toast.error(`Failed to ${action} campaign`) }
    finally { setActionLoading(false); setShowPause(false); setShowResume(false); setShowCancel(false) }
  }

  const copyLink = () => {
    if (!data) return
    const url = `https://flamezo.in/${data.campaign_id.split('-')[1]}/boost-offer?code=${data.coupon_code}`
    navigator.clipboard.writeText(url)
    toast.success('Coupon link copied!')
  }

  // ─── Loading ──────────────────────────────────────────────────

  if (loading) return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-20 rounded-xl" />
      <div className="grid grid-cols-3 gap-4">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>
      <Skeleton className="h-64 rounded-xl" />
    </div>
  )

  if (!data) return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={() => navigate('/boost')}><ChevronLeft className="h-4 w-4 mr-1" /> Back</Button>
      <Card className="py-16"><CardContent className="text-center text-muted-foreground">Campaign not found</CardContent></Card>
    </div>
  )

  const status = STATUS_CONFIG[data.status] || STATUS_CONFIG.Draft
  const budgetPct = data.ad_spend_allocated > 0 ? Math.min(100, Math.round((data.amount_spent_meta / data.ad_spend_allocated) * 100)) : 0
  const ctr = data.impressions > 0 ? (data.link_clicks / data.impressions * 100).toFixed(2) : '0'
  const claimRate = data.link_clicks > 0 ? Math.round(data.coupons_claimed / data.link_clicks * 100) : 0
  const guaranteePct = data.guaranteed_redemptions > 0 ? Math.min(100, Math.round(data.coupons_redeemed / data.guaranteed_redemptions * 100)) : 0

  const paginatedRedemptions = data.redemptions?.slice((redemptionPage - 1) * ITEMS_PER_PAGE, redemptionPage * ITEMS_PER_PAGE) || []
  const totalRedPages = Math.ceil((data.redemptions?.length || 0) / ITEMS_PER_PAGE) || 1

  // ─── Render ───────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1.5 text-[11px] font-bold tracking-widest uppercase text-muted-foreground/60 mb-2">
        <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
        <ChevronRight className="h-3 w-3" />
        <Link to="/boost" className="hover:text-foreground transition-colors">Boost</Link>
        <ChevronRight className="h-3 w-3" />
        <span className="text-foreground">Campaign Details</span>
      </nav>

      <Button variant="ghost" size="sm" onClick={() => navigate('/boost')} className="-ml-2 gap-1">
        <ChevronLeft className="h-4 w-4" /> Back to Boost
      </Button>

      {/* Status Banner */}
      <Card className="border-none bg-card shadow-sm">
        <CardContent className="pt-6 pb-5">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-xl bg-orange-100 dark:bg-orange-950/40 flex items-center justify-center text-orange-600">
                <Zap className="h-5 w-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-xl font-bold text-foreground">{data.campaign_name}</h1>
                  <Badge className={cn('text-[10px] font-bold px-2 py-0.5 rounded-full shadow-sm', status.text, status.bg)}>{data.status}</Badge>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">{data.package_tier} · ₹{data.offer_amount} off</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {data.status === 'Live' && (
                <Button variant="outline" size="sm" onClick={() => setShowPause(true)} className="gap-1.5"><Pause className="h-3.5 w-3.5" /> Pause</Button>
              )}
              {data.status === 'Paused' && (
                <Button size="sm" onClick={() => setShowResume(true)} className="gap-1.5 bg-orange-500 hover:bg-orange-600 text-white"><Play className="h-3.5 w-3.5" /> Resume</Button>
              )}
              {['Draft', 'Pending Payment'].includes(data.status) && (
                <Button variant="outline" size="sm" onClick={() => setShowCancel(true)} className="gap-1.5 text-red-600 border-red-200 hover:bg-red-50"><XCircle className="h-3.5 w-3.5" /> Cancel</Button>
              )}
              <Button variant="outline" size="sm" onClick={copyLink} className="gap-1.5"><Share2 className="h-3.5 w-3.5" /> Share Link</Button>
            </div>
          </div>
          {/* Budget Bar */}
          {data.status === 'Live' && (
            <div className="mt-5 pt-4 border-t border-border/40">
              <div className="flex justify-between items-center text-xs text-muted-foreground mb-1.5">
                <span className="font-semibold text-foreground">₹{Math.round(data.amount_spent_meta).toLocaleString()} spent</span>
                <span className="bg-muted px-2.5 py-0.5 rounded-full font-bold">{data.days_remaining} days left</span>
              </div>
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-orange-500 to-amber-500 rounded-full transition-all duration-500" style={{ width: `${budgetPct}%` }} />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KPICard icon={<Eye className="h-4 w-4" />} label="Impressions" value={data.impressions.toLocaleString()} />
        <KPICard icon={<Users className="h-4 w-4" />} label="Reach" value={data.reach.toLocaleString()} />
        <KPICard icon={<MousePointerClick className="h-4 w-4" />} label="Clicks" value={String(data.link_clicks)} sub={`${ctr}% CTR`} />
        <KPICard icon={<Ticket className="h-4 w-4" />} label="Claimed" value={String(data.coupons_claimed)} sub={`${claimRate}% claim rate`} />
        <KPICard icon={<Users className="h-4 w-4" />} label="Walk-ins" value={String(data.coupons_redeemed)} highlight />
        <KPICard icon={<TrendingUp className="h-4 w-4" />} label="Est. Revenue" value={data.estimated_revenue > 0 ? `₹${data.estimated_revenue.toLocaleString()}` : '—'} good />
      </div>

      {/* Two Column: Guarantee + Coupon */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Guarantee */}
        <Card className="border-none bg-card shadow-sm">
          <CardHeader className="pb-3"><CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Guarantee</CardTitle></CardHeader>
          <CardContent>
            {data.is_first_campaign ? (
              <div className="flex items-start gap-2 text-amber-700 dark:text-amber-300">
                <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                <p className="text-sm">First campaign — calibration mode. Guarantee unlocks from campaign #2.</p>
              </div>
            ) : data.guaranteed_redemptions > 0 ? (
              <div>
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-muted-foreground">Progress</span>
                  <span className="font-semibold">{data.coupons_redeemed} / {data.guaranteed_redemptions}</span>
                </div>
                <div className="h-3 bg-muted rounded-full overflow-hidden">
                  <div className={cn('h-full rounded-full transition-all duration-500', data.guarantee_met ? 'bg-emerald-500' : 'bg-orange-500')}
                    style={{ width: `${guaranteePct}%` }} />
                </div>
                <p className={cn('text-xs mt-2 font-medium', data.guarantee_met ? 'text-emerald-600' : guaranteePct >= 50 ? 'text-orange-600' : 'text-red-600')}>
                  {data.guarantee_met ? 'Guarantee met!' : guaranteePct >= 50 ? 'On track' : 'Behind pace'}
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No guarantee for this campaign</p>
            )}
          </CardContent>
        </Card>

        {/* Coupon Details */}
        <Card className="border-none bg-card shadow-sm">
          <CardHeader className="pb-3"><CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Coupon</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-2 p-3 bg-muted rounded-lg border">
              <span className="text-lg font-mono font-bold text-orange-600 flex-1">{data.coupon_code}</span>
              <button onClick={() => { navigator.clipboard.writeText(data.coupon_code); toast.success('Copied!') }}
                className="p-1.5 rounded hover:bg-background transition-colors"><Copy className="h-4 w-4 text-muted-foreground" /></button>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Offer</span>
              <span className="font-medium">₹{data.offer_amount} off</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Cost/Walk-in</span>
              <span className="font-medium">{data.coupons_redeemed > 0 ? `₹${Math.round(data.cost_per_redemption)}` : '—'}</span>
            </div>
            <Button variant="outline" size="sm" className="w-full gap-1.5" onClick={copyLink}>
              <ExternalLink className="h-3.5 w-3.5" /> Copy Public Claim Link
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Redemption Log */}
      <Card className="border-none bg-card shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Walk-in Log</CardTitle>
            <Badge variant="secondary">{data.redemptions?.length || 0} total</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {data.redemptions && data.redemptions.length > 0 ? (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs font-bold uppercase tracking-wider">#</TableHead>
                    <TableHead className="text-xs font-bold uppercase tracking-wider">Date</TableHead>
                    <TableHead className="text-xs font-bold uppercase tracking-wider">Method</TableHead>
                    <TableHead className="text-xs font-bold uppercase tracking-wider text-right">Bill</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paginatedRedemptions.map((r, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-medium">{(redemptionPage - 1) * ITEMS_PER_PAGE + i + 1}</TableCell>
                      <TableCell className="text-sm">{new Date(r.redeemed_at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</TableCell>
                      <TableCell><Badge variant="secondary" className="text-xs">{r.redemption_method}</Badge></TableCell>
                      <TableCell className="text-right font-medium">{r.bill_amount ? `₹${r.bill_amount}` : '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {totalRedPages > 1 && (
                <div className="flex items-center justify-center gap-2 mt-4">
                  <Button variant="outline" size="sm" disabled={redemptionPage <= 1} onClick={() => setRedemptionPage(p => p - 1)}>
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="text-sm text-muted-foreground">Page {redemptionPage} of {totalRedPages}</span>
                  <Button variant="outline" size="sm" disabled={redemptionPage >= totalRedPages} onClick={() => setRedemptionPage(p => p + 1)}>
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Ticket className="h-8 w-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm">No walk-ins recorded yet</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Confirm Dialogs */}
      <ConfirmDialog open={showPause} onOpenChange={setShowPause} title="Pause Campaign"
        description="This will pause your ads on Meta. You can resume anytime."
        confirmText="Pause" variant="warning" onConfirm={() => handleAction('pause')} loading={actionLoading} />
      <ConfirmDialog open={showResume} onOpenChange={setShowResume} title="Resume Campaign"
        description="Your ads will resume running on Meta."
        confirmText="Resume" onConfirm={() => handleAction('resume')} loading={actionLoading} />
      <ConfirmDialog open={showCancel} onOpenChange={setShowCancel} title="Cancel Campaign"
        description="This will permanently cancel the campaign. This cannot be undone."
        confirmText="Cancel Campaign" variant="destructive" onConfirm={() => handleAction('cancel')} loading={actionLoading} />
    </div>
  )
}

// ─── KPI Card ───────────────────────────────────────────────────

function KPICard({ icon, label, value, sub, highlight, good }: {
  icon: React.ReactNode; label: string; value: string; sub?: string; highlight?: boolean; good?: boolean
}) {
  return (
    <Card className={cn(
      "relative overflow-hidden transition-all duration-300 hover:shadow-lg border-none bg-card shadow-sm",
      highlight && "bg-gradient-to-br from-orange-500 to-amber-600 text-white shadow-lg shadow-orange-500/20"
    )}>
      {highlight && (
        <div className="absolute top-0 right-0 p-3 opacity-10">
          {icon}
        </div>
      )}
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
        <CardTitle className={cn("text-xs font-medium uppercase tracking-wider", highlight ? "text-white/80" : "text-muted-foreground")}>
          {label}
        </CardTitle>
        {!highlight && <div className={cn("text-orange-500", good && "text-emerald-500")}>{icon}</div>}
      </CardHeader>
      <CardContent>
        <p className={cn(
          'text-2xl font-bold tracking-tight',
          highlight ? 'text-white' : good ? 'text-emerald-600' : 'text-foreground'
        )}>{value}</p>
        {sub && (
          <p className={cn("text-[10px] mt-1.5", highlight ? "text-white/70" : "text-muted-foreground")}>
            {sub}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
