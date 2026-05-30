import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall } from '@/lib/frappe'
import { useEffect, useState, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Zap, TrendingUp, TrendingDown, Users, DollarSign, ChevronRight, AlertCircle,
  CheckCircle2, XCircle, Plus, Eye, Pause, Play, Ticket, Search, Filter,
  ArrowRight, BarChart3, Megaphone
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

// ─── Types ──────────────────────────────────────────────────────

interface BoostCampaign {
  name: string
  campaign_name: string
  status: string
  package_tier: string
  budget_total: number
  impressions: number
  coupons_redeemed: number
  coupons_claimed: number
  amount_spent_meta: number
  cost_per_redemption: number
  launch_date: string | null
  end_date: string | null
  offer_amount: number
  coupon_code: string
  is_first_campaign: boolean
  location_grade: string
}

interface OverviewData {
  campaigns: BoostCampaign[]
  active_count: number
  total_campaigns: number
  total_spend: number
  total_redemptions: number
  avg_cost_per_redemption: number
}

interface PrereqCheck {
  check: string
  label: string
  passed: boolean
  details: string
}

interface PrereqData {
  score: number
  passed: boolean
  checks: PrereqCheck[]
  location_grade: string
}

// ─── Constants ──────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  Draft: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  'Pending Payment': 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  Submitted: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  'Meta Review': 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  Live: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  Completed: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  Paused: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  Failed: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  Cancelled: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
}

const AVG_BILL = 600

// ─── Component ──────────────────────────────────────────────────

export default function BoostOverview() {
  const { selectedRestaurant } = useRestaurant()
  const navigate = useNavigate()
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [prereqs, setPrereqs] = useState<PrereqData | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')

  const { call: fetchOverview } = useFrappePostCall('flamezo_backend.flamezo.api.boost.get_boost_overview')
  const { call: fetchPrereqs } = useFrappePostCall('flamezo_backend.flamezo.api.boost.check_prerequisites')

  useEffect(() => {
    if (!selectedRestaurant) return
    setLoading(true)
    Promise.all([
      fetchOverview({ restaurant_id: selectedRestaurant }).then((r: any) => r?.message?.data || r?.data).catch(() => null),
      fetchPrereqs({ restaurant_id: selectedRestaurant }).then((r: any) => r?.message?.data || r?.data).catch(() => null),
    ]).then(([ov, pr]) => {
      setOverview(ov)
      setPrereqs(pr)
      setLoading(false)
    })
  }, [selectedRestaurant])

  const filteredCampaigns = useMemo(() => {
    if (!overview?.campaigns) return []
    return overview.campaigns.filter(c => {
      const matchesSearch = !searchQuery || c.campaign_name.toLowerCase().includes(searchQuery.toLowerCase()) || c.coupon_code.toLowerCase().includes(searchQuery.toLowerCase())
      const matchesStatus = statusFilter === 'all' || c.status === statusFilter
      return matchesSearch && matchesStatus
    })
  }, [overview?.campaigns, searchQuery, statusFilter])

  const totalClaimed = useMemo(() => overview?.campaigns.reduce((s, c) => s + (c.coupons_claimed || 0), 0) || 0, [overview])
  const avgRoi = useMemo(() => {
    if (!overview || overview.total_spend === 0) return 0
    return Math.round((overview.total_redemptions * AVG_BILL) / overview.total_spend * 10) / 10
  }, [overview])

  const canCreate = prereqs?.passed ?? false

  // ─── Loading ──────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Skeleton className="h-10 w-48" />
          <Skeleton className="h-10 w-36" />
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
        <Skeleton className="h-96 rounded-xl" />
      </div>
    )
  }

  // ─── Render ───────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-orange-500 to-amber-600 flex items-center justify-center shadow-lg shadow-orange-500/20">
            <Zap className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Boost</h1>
            <p className="text-sm text-muted-foreground">Run Meta ads to drive walk-in customers</p>
          </div>
        </div>
        <Button
          onClick={() => navigate('/boost/new')}
          disabled={!canCreate}
          className="gap-2 bg-gradient-to-r from-orange-500 to-amber-600 hover:from-orange-600 hover:to-amber-700 text-white shadow-lg shadow-orange-500/20"
        >
          <Plus className="h-4 w-4" /> New Campaign
        </Button>
      </div>

      {/* Prerequisites Banner */}
      {prereqs && !prereqs.passed && (
        <Card className="border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/20">
          <CardContent className="pt-5 pb-4">
            <div className="flex items-start gap-4">
              {/* Progress Circle */}
              <div className="relative h-16 w-16 shrink-0">
                <svg className="h-16 w-16 -rotate-90" viewBox="0 0 36 36">
                  <path d="M18 2.0845a 15.9155 15.9155 0 0 1 0 31.831a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none" stroke="currentColor" strokeWidth="3" className="text-amber-200 dark:text-amber-800" />
                  <path d="M18 2.0845a 15.9155 15.9155 0 0 1 0 31.831a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none" stroke="currentColor" strokeWidth="3" className="text-amber-500"
                    strokeDasharray={`${prereqs.score}, 100`} strokeLinecap="round" />
                </svg>
                <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-amber-700 dark:text-amber-300">
                  {prereqs.score}%
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-amber-800 dark:text-amber-200 flex items-center gap-2">
                  <AlertCircle className="h-4 w-4" /> Complete prerequisites to unlock Boost
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 mt-3">
                  {prereqs.checks.map(c => (
                    <div key={c.check} className="flex items-center gap-2 text-sm">
                      {c.passed ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0" /> : <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />}
                      <span className={cn('truncate', c.passed ? 'text-muted-foreground' : 'font-medium')}>{c.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* KPI Cards */}
      {overview && overview.total_campaigns > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          <StatCard icon={<DollarSign className="h-4 w-4" />} label="Total Spend" value={`₹${overview.total_spend.toLocaleString()}`} />
          <StatCard icon={<Users className="h-4 w-4" />} label="Walk-ins" value={String(overview.total_redemptions)} highlight />
          <StatCard icon={<TrendingDown className="h-4 w-4" />} label="Cost/Walk-in"
            value={overview.total_redemptions > 0 ? `₹${Math.round(overview.avg_cost_per_redemption)}` : '—'} />
          <StatCard icon={<Zap className="h-4 w-4" />} label="Active" value={String(overview.active_count)} />
          <StatCard icon={<TrendingUp className="h-4 w-4" />} label="Avg ROI" value={avgRoi > 0 ? `${avgRoi}x` : '—'} good={avgRoi >= 3} />
          <StatCard icon={<Ticket className="h-4 w-4" />} label="Claimed" value={String(totalClaimed)} />
        </div>
      )}

      {/* Campaign List */}
      {overview && overview.total_campaigns > 0 ? (
        <Card>
          <CardHeader className="pb-4">
            <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
              <CardTitle className="text-base">Your Campaigns</CardTitle>
              <div className="flex items-center gap-2">
                <div className="relative flex-1 sm:w-56">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input placeholder="Search campaigns..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                    className="pl-8 h-9 text-sm" />
                </div>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-32 h-9 text-sm">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    <SelectItem value="Live">Live</SelectItem>
                    <SelectItem value="Draft">Draft</SelectItem>
                    <SelectItem value="Completed">Completed</SelectItem>
                    <SelectItem value="Paused">Paused</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs font-bold uppercase tracking-wider">Campaign</TableHead>
                    <TableHead className="text-xs font-bold uppercase tracking-wider">Status</TableHead>
                    <TableHead className="text-xs font-bold uppercase tracking-wider">Budget</TableHead>
                    <TableHead className="text-xs font-bold uppercase tracking-wider text-right">Walk-ins</TableHead>
                    <TableHead className="text-xs font-bold uppercase tracking-wider text-right">Cost/Walk-in</TableHead>
                    <TableHead className="w-10" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredCampaigns.map(c => {
                    const spentPct = c.budget_total > 0 ? Math.min(100, Math.round((c.amount_spent_meta / (c.budget_total * 0.7)) * 100)) : 0
                    return (
                      <TableRow key={c.name} className="cursor-pointer group" onClick={() => {
                        // Draft/Pending Payment campaigns → open in wizard to continue
                        if (c.status === 'Draft' || c.status === 'Pending Payment') {
                          const step = c.status === 'Pending Payment' ? 4 : 3
                          navigate(`/boost/new?id=${c.name}&step=${step}`)
                        } else {
                          navigate(`/boost/campaign?id=${c.name}`)
                        }
                      }}>
                        <TableCell>
                          <div>
                            <p className="font-medium text-sm">{c.campaign_name}</p>
                            <p className="text-xs text-muted-foreground">{c.package_tier} · ₹{c.offer_amount} off</p>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary" className={cn('text-[10px] font-medium', STATUS_COLORS[c.status])}>
                            {c.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="w-24">
                            <div className="flex justify-between text-[10px] text-muted-foreground mb-0.5">
                              <span>₹{Math.round(c.amount_spent_meta)}</span>
                              <span>₹{c.budget_total.toLocaleString()}</span>
                            </div>
                            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                              <div className="h-full bg-orange-500 rounded-full transition-all" style={{ width: `${spentPct}%` }} />
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <span className="font-semibold text-sm">{c.coupons_redeemed}</span>
                        </TableCell>
                        <TableCell className="text-right">
                          <span className="text-sm text-muted-foreground">
                            {c.coupons_redeemed > 0 ? `₹${Math.round(c.cost_per_redemption)}` : '—'}
                          </span>
                        </TableCell>
                        <TableCell>
                          <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                        </TableCell>
                      </TableRow>
                    )
                  })}
                  {filteredCampaigns.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                        No campaigns match your filters
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      ) : (
        /* Empty State */
        <Card className="py-16">
          <CardContent className="text-center">
            <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-orange-100 to-amber-100 dark:from-orange-950/40 dark:to-amber-950/40 flex items-center justify-center mx-auto mb-5">
              <Zap className="h-8 w-8 text-orange-500" />
            </div>
            <h2 className="text-xl font-bold mb-2">No campaigns yet</h2>
            <p className="text-sm text-muted-foreground mb-6 max-w-sm mx-auto">
              Create your first Boost campaign to drive new walk-in customers from Instagram and Facebook ads.
            </p>
            {canCreate ? (
              <Button onClick={() => navigate('/boost/new')} className="gap-2 bg-gradient-to-r from-orange-500 to-amber-600 text-white">
                <Plus className="h-4 w-4" /> Create First Campaign
              </Button>
            ) : (
              <p className="text-xs text-muted-foreground">Complete prerequisites above to get started</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Quick Actions */}
      {overview && overview.total_campaigns > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Link to="/boost/redeem" className="group">
            <Card className="hover:border-orange-300 dark:hover:border-orange-700 transition-colors">
              <CardContent className="pt-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-9 w-9 rounded-lg bg-orange-100 dark:bg-orange-950/40 flex items-center justify-center">
                    <Ticket className="h-4 w-4 text-orange-600" />
                  </div>
                  <div>
                    <p className="font-medium text-sm">Redeem Coupon</p>
                    <p className="text-xs text-muted-foreground">Scan or enter a customer's Boost code</p>
                  </div>
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-orange-500 transition-colors" />
              </CardContent>
            </Card>
          </Link>
          <Link to="/boost/new" className="group">
            <Card className="hover:border-orange-300 dark:hover:border-orange-700 transition-colors">
              <CardContent className="pt-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-9 w-9 rounded-lg bg-orange-100 dark:bg-orange-950/40 flex items-center justify-center">
                    <Megaphone className="h-4 w-4 text-orange-600" />
                  </div>
                  <div>
                    <p className="font-medium text-sm">New Campaign</p>
                    <p className="text-xs text-muted-foreground">Launch a new ad to attract customers</p>
                  </div>
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-orange-500 transition-colors" />
              </CardContent>
            </Card>
          </Link>
        </div>
      )}
    </div>
  )
}

// ─── Stat Card ──────────────────────────────────────────────────

function StatCard({ icon, label, value, highlight, good }: {
  icon: React.ReactNode; label: string; value: string; highlight?: boolean; good?: boolean
}) {
  return (
    <Card className={cn(
      'transition-all',
      highlight && 'border-orange-200 dark:border-orange-800 bg-orange-50/50 dark:bg-orange-950/20'
    )}>
      <CardContent className="pt-4 pb-3">
        <div className="flex items-center gap-1.5 text-muted-foreground mb-1.5">
          {icon}
          <span className="text-[11px] font-medium uppercase tracking-wider">{label}</span>
        </div>
        <p className={cn(
          'text-2xl font-bold',
          highlight && 'text-orange-600',
          good && 'text-emerald-600'
        )}>{value}</p>
      </CardContent>
    </Card>
  )
}
