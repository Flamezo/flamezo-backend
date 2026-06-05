import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useFrappeAuth, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { NumberInput } from '@/components/ui/number-input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { OrderDetailsDialog } from '@/components/OrderDetailsDialog'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import {
  ChevronLeft, RefreshCw, Trash2, Coins, Phone, Calendar,
  ShoppingBag, Star, Gift, ArrowUpRight, ArrowDownLeft,
  Video, UserCheck, UserX, Wallet, TrendingUp, Store,
  Plus, Minus, Ticket, Users, ExternalLink, ChevronRight,
  Eye,
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface FullProfile {
  customer: {
    id: string; name: string; phone: string; email: string
    birthday: string | null; created: string; verified_at: string | null
  }
  stats: {
    total_orders: number; total_spend: number; loyalty_balance: number
    lifetime_earned: number; total_redeemed: number; restaurants_visited: number
  }
  orders: any[]
  table_bookings: any[]
  banquet_bookings: any[]
  loyalty: { balance: number; lifetime_earned: number; entries: any[] }
  referral: {
    referred_by: {
      referrer_id: string; referrer_name: string; referrer_phone: string
      orders_credited: number; cashback_total: number; status: string
    } | null
    referrals_made: any[]
  }
  ugc: any[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmt      = (n: number) => n.toLocaleString('en-IN')
const fmtR     = (n: number) => `₹${n.toLocaleString('en-IN')}`
const fmtDate  = (s: string) => s ? new Date(s).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
const fmtDateTime = (s: string) => s ? new Date(s).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'

function StatCard({ icon: Icon, label, value, sub, accent }: {
  icon: React.ComponentType<{ className?: string }>
  label: string; value: string; sub?: string; accent?: string
}) {
  return (
    <div className={cn('rounded-xl border p-4 flex flex-col gap-1', accent || 'border-border bg-card')}>
      <div className="flex items-center gap-2 text-muted-foreground text-xs font-medium uppercase tracking-wide">
        <Icon className="w-3.5 h-3.5" />
        {label}
      </div>
      <p className="text-2xl font-bold text-foreground">{value}</p>
      {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
    </div>
  )
}

// ── UGC Detail Dialog ─────────────────────────────────────────────────────────

function UGCDetailDialog({ ugc, open, onClose }: { ugc: any | null; open: boolean; onClose: () => void }) {
  if (!ugc) return null

  const statusColor = (s: string) =>
    s === 'credited'  ? 'text-green-700 bg-green-50 border-green-200' :
    s === 'rejected'  ? 'text-red-600 bg-red-50 border-red-200' :
    s === 'expired'   ? 'text-gray-500 bg-gray-50' :
    'text-amber-700 bg-amber-50 border-amber-200'

  const timeline = [
    { label: 'Offer Started',  ts: ugc.submission_date },
    { label: 'Story Shared',   ts: ugc.story_shared_at },
    { label: 'Story Verified', ts: ugc.story_verified_at },
    { label: 'Proof Submitted',ts: ugc.proof_submitted_at },
  ].filter(t => t.ts)

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Video className="w-4 h-4 text-primary" /> UGC Submission
          </DialogTitle>
          <DialogDescription>
            {ugc.restaurant_name} · <Badge variant="secondary" className={cn('text-[10px]', statusColor(ugc.status))}>{ugc.status}</Badge>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">

          {/* Summary */}
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-md border px-3 py-2.5 space-y-1.5">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Cashback</p>
              <p className="text-xl font-bold text-green-600">{ugc.cashback_coins > 0 ? `+₹${ugc.cashback_coins}` : '—'}</p>
            </div>
            <div className="rounded-md border px-3 py-2.5 space-y-1.5">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Order Amount</p>
              <p className="text-xl font-bold">{fmtR(ugc.order_amount)}</p>
            </div>
          </div>

          {/* Proof video */}
          {ugc.proof_video_url && (
            <div className="rounded-md border px-3 py-2.5">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Proof</p>
              <a
                href={ugc.proof_video_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm text-primary hover:underline">
                <Eye className="w-4 h-4" /> View Proof Video/Screenshot
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          )}

          {/* AI Analysis */}
          {(ugc.ai_view_count || ugc.ai_confidence || ugc.ai_tamper_signals) && (
            <div className="rounded-md border px-3 py-2.5 space-y-1.5 text-sm">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">AI Analysis</p>
              {ugc.ai_view_count > 0 && <div className="flex justify-between"><span className="text-muted-foreground">View Count Detected</span><span className="font-semibold">{fmt(ugc.ai_view_count)}</span></div>}
              {ugc.ai_confidence && <div className="flex justify-between"><span className="text-muted-foreground">Confidence</span><span className="font-semibold">{(ugc.ai_confidence * 100).toFixed(0)}%</span></div>}
              {ugc.ai_provider && <div className="flex justify-between"><span className="text-muted-foreground">Provider</span><span>{ugc.ai_provider}</span></div>}
              {ugc.ai_tamper_signals && (
                <div className="mt-1.5">
                  <span className="text-muted-foreground text-xs block mb-0.5">Tamper Signals</span>
                  <p className="text-xs bg-muted rounded px-2 py-1.5">{ugc.ai_tamper_signals}</p>
                </div>
              )}
            </div>
          )}

          {/* Review notes */}
          {(ugc.review_notes || ugc.rejection_reason) && (
            <div className="rounded-md border px-3 py-2.5 space-y-1.5 text-sm">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Review</p>
              {ugc.review_notes && <p className="text-xs bg-muted rounded px-2 py-1.5">{ugc.review_notes}</p>}
              {ugc.rejection_reason && (
                <p className="text-xs bg-red-50 text-red-700 rounded px-2 py-1.5 dark:bg-red-950/20">
                  Rejection: {ugc.rejection_reason}
                </p>
              )}
            </div>
          )}

          {/* Timeline */}
          {timeline.length > 0 && (
            <div className="rounded-md border px-3 py-2.5">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Timeline</p>
              <div className="space-y-2">
                {timeline.map((t, i) => (
                  <div key={i} className="flex items-center gap-3 text-sm">
                    <div className="w-2 h-2 rounded-full bg-primary shrink-0" />
                    <span className="text-muted-foreground w-32 shrink-0">{t.label}</span>
                    <span className="text-xs">{fmtDateTime(t.ts)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function AdminCustomerDetail() {
  const { id: customerId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { currentUser } = useFrappeAuth()

  const [isAdmin, setIsAdmin] = useState(false)
  const [profile, setProfile] = useState<FullProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'overview' | 'orders' | 'loyalty' | 'referral' | 'ugc'>('overview')

  // Detail dialogs
  const [orderDialogName, setOrderDialogName] = useState<string | null>(null)
  const [ugcDialogItem, setUgcDialogItem]     = useState<any | null>(null)

  // Loyalty / adjust
  const [adjustOpen, setAdjustOpen] = useState(false)
  const [adjCoins, setAdjCoins]     = useState('')
  const [adjReason, setAdjReason]   = useState('Manual Adjustment')
  const [adjType, setAdjType]       = useState<'Earn' | 'Redeem'>('Earn')
  const [adjRestaurant, setAdjRestaurant] = useState('')
  const [adjusting, setAdjusting]   = useState(false)

  const [deleteOpen, setDeleteOpen]     = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState('')
  const [deleting, setDeleting]         = useState(false)

  const { call: fetchProfile } = useFrappePostCall('flamezo_backend.flamezo.api.admin.admin_get_customer_full_profile')
  const { call: adjustLoyalty } = useFrappePostCall('flamezo_backend.flamezo.api.admin.admin_adjust_customer_loyalty')
  const { call: deleteCustomer } = useFrappePostCall('flamezo_backend.flamezo.api.admin.admin_delete_customer')

  useEffect(() => {
    if (!currentUser) return
    const win = window as any
    const roles: string[] = win.frappe?.boot?.user_roles || win.frappe?.boot?.user?.roles || []
    setIsAdmin(currentUser === 'Administrator' || roles.includes('Flamezo Supervisor') || roles.includes('System Manager'))
  }, [currentUser])

  useEffect(() => { if (customerId) load() }, [customerId])

  async function load() {
    setLoading(true)
    try {
      const res: any = await fetchProfile({ customer_id: customerId })
      if (res.message?.success) setProfile(res.message.data)
      else toast.error(res.message?.error || 'Failed to load profile')
    } catch { toast.error('Failed to load profile') }
    finally { setLoading(false) }
  }

  async function handleAdjust() {
    if (!adjCoins || !adjRestaurant) return
    setAdjusting(true)
    try {
      const res: any = await adjustLoyalty({
        customer_id: customerId, restaurant_id: adjRestaurant,
        coins: parseInt(adjCoins), reason: adjReason, transaction_type: adjType,
      })
      if (res.message?.success) {
        toast.success(`${adjType === 'Earn' ? 'Credited' : 'Deducted'} ₹${adjCoins} loyalty cash`)
        setAdjustOpen(false); setAdjCoins(''); load()
      } else { toast.error(res.message?.error || 'Failed') }
    } catch { toast.error('Failed') }
    finally { setAdjusting(false) }
  }

  async function handleDelete() {
    if (!profile || deleteConfirm !== profile.customer.phone) return
    setDeleting(true)
    try {
      const res: any = await deleteCustomer({ customer_id: customerId })
      if (res.message?.success) { toast.success('Customer deleted'); navigate('/admin/customers', { replace: true }) }
      else { toast.error(res.message?.error || 'Failed to delete') }
    } catch { toast.error('Failed to delete') }
    finally { setDeleting(false) }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-full text-muted-foreground py-32">
      <RefreshCw className="w-5 h-5 animate-spin mr-2" /> Loading customer profile…
    </div>
  )

  if (!profile) return (
    <div className="flex flex-col items-center justify-center h-full py-32 text-muted-foreground">
      <p className="text-lg font-semibold mb-2">Customer not found</p>
      <Button variant="outline" onClick={() => navigate('/admin/customers')}>
        <ChevronLeft className="w-4 h-4 mr-1" /> Back to list
      </Button>
    </div>
  )

  const { customer, stats, orders, table_bookings, loyalty, referral, ugc } = profile
  const visitedRestaurants = [...new Map(orders.map((o: any) => [o.restaurant, o.restaurant_name])).entries()]

  const tabs: { id: typeof activeTab; label: string; icon: React.ComponentType<{ className?: string }>; count?: number }[] = [
    { id: 'overview',  label: 'Overview',  icon: UserCheck },
    { id: 'orders',    label: 'Orders',    icon: ShoppingBag, count: orders.length },
    { id: 'loyalty',   label: 'Loyalty',   icon: Wallet,      count: loyalty.entries.length },
    { id: 'referral',  label: 'Referral',  icon: UserX,       count: referral.referrals_made.length },
    { id: 'ugc',       label: 'UGC',       icon: Video,       count: ugc.length },
  ]

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Top bar ── */}
      <div className="flex items-center justify-between px-6 py-4 border-b shrink-0">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground" onClick={() => navigate('/admin/customers')}>
            <ChevronLeft className="w-4 h-4" /> Customer Management
          </Button>
          <span className="text-muted-foreground">/</span>
          <span className="font-semibold text-sm">{customer.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="gap-1.5 text-xs" onClick={load} disabled={loading}>
            <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} /> Refresh
          </Button>
          {isAdmin && (
            <>
              <Button variant="outline" size="sm" className="gap-1.5 text-xs" onClick={() => setAdjustOpen(true)}>
                <Coins className="w-3.5 h-3.5" /> Adjust Loyalty
              </Button>
              <Button variant="outline" size="sm" className="gap-1.5 text-xs text-red-600 hover:text-red-700 hover:bg-red-50" onClick={() => setDeleteOpen(true)}>
                <Trash2 className="w-3.5 h-3.5" /> Delete
              </Button>
            </>
          )}
        </div>
      </div>

      {/* ── Customer header ── */}
      <div className="px-6 py-5 border-b shrink-0 bg-muted/30">
        <div className="flex items-start gap-5">
          <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center text-primary font-black text-2xl shrink-0">
            {(customer.name || '?')[0].toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-xl font-bold">{customer.name}</h1>
              {customer.verified_at && (
                <Badge variant="outline" className="text-green-600 border-green-300 bg-green-50 dark:bg-green-950/20 text-[10px]">Verified</Badge>
              )}
            </div>
            <div className="flex items-center gap-4 mt-1.5 text-sm text-muted-foreground flex-wrap">
              <span className="flex items-center gap-1.5"><Phone className="w-3.5 h-3.5" />{customer.phone || '—'}</span>
              {customer.birthday && <span className="flex items-center gap-1.5"><Calendar className="w-3.5 h-3.5" />Born {fmtDate(customer.birthday)}</span>}
              <span>Joined {fmtDate(customer.created)}</span>
              {customer.email && <span>{customer.email}</span>}
            </div>
          </div>
          <div className="shrink-0 text-right">
            <div className="text-2xl font-black text-primary">{fmtR(stats.loyalty_balance)}</div>
            <div className="text-xs text-muted-foreground">Cash Balance</div>
          </div>
        </div>
      </div>

      {/* ── Tabs ── */}
      <div className="flex border-b px-6 shrink-0 overflow-x-auto bg-background">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)}
            className={cn(
              'flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors',
              activeTab === t.id ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
            )}>
            <t.icon className="w-3.5 h-3.5" />
            {t.label}
            {t.count !== undefined && t.count > 0 && (
              <span className="ml-1 bg-muted text-muted-foreground rounded-full text-[10px] px-1.5 py-0.5">{t.count}</span>
            )}
          </button>
        ))}
      </div>

      {/* ── Tab content ── */}
      <div className="flex-1 overflow-y-auto px-6 py-6">

        {/* OVERVIEW */}
        {activeTab === 'overview' && (
          <div className="space-y-6 max-w-5xl">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              <StatCard icon={ShoppingBag}   label="Total Orders"    value={fmt(stats.total_orders)}        sub={fmtR(stats.total_spend) + ' spent'} />
              <StatCard icon={Store}         label="Restaurants"     value={fmt(stats.restaurants_visited)} sub="unique visited" />
              <StatCard icon={Wallet}        label="Cash Balance"    value={fmtR(stats.loyalty_balance)}    sub="spendable now" accent="border-primary/30 bg-primary/5" />
              <StatCard icon={TrendingUp}    label="Lifetime Earned" value={fmtR(stats.lifetime_earned)} />
              <StatCard icon={ArrowDownLeft} label="Total Redeemed"  value={fmtR(stats.total_redeemed)} />
              <StatCard icon={Gift}          label="UGC Claims"      value={fmt(ugc.length)}               sub={`${ugc.filter((u: any) => u.status === 'credited').length} credited`} />
            </div>

            {orders.length > 0 && (
              <Card>
                <CardHeader className="pb-2 pt-4 px-4">
                  <p className="text-sm font-semibold flex items-center gap-2"><ShoppingBag className="w-4 h-4 text-primary" />Recent Orders</p>
                </CardHeader>
                <CardContent className="px-4 pb-4">
                  <div className="space-y-1">
                    {orders.slice(0, 5).map((o: any) => (
                      <div key={o.name}
                        onClick={() => setOrderDialogName(o.name)}
                        className="flex items-center justify-between py-2 px-2 -mx-2 border-b last:border-0 text-sm cursor-pointer hover:bg-muted/50 rounded-md transition-colors">
                        <div>
                          <span className="font-medium">{o.restaurant_name}</span>
                          <span className="text-muted-foreground ml-2 text-xs">{fmtDate(o.creation)}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold">{fmtR(o.total)}</span>
                          <Badge variant={o.status === 'completed' ? 'default' : 'secondary'} className="text-[10px]">{o.status}</Badge>
                          <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
                        </div>
                      </div>
                    ))}
                  </div>
                  {orders.length > 5 && (
                    <button onClick={() => setActiveTab('orders')} className="mt-2 text-xs text-primary hover:underline">
                      View all {orders.length} orders →
                    </button>
                  )}
                </CardContent>
              </Card>
            )}

            {referral.referred_by && (
              <Card className="border-blue-200 dark:border-blue-800">
                <CardContent className="px-4 py-4 flex items-center gap-3">
                  <UserCheck className="w-5 h-5 text-blue-500 shrink-0" />
                  <div>
                    <p className="text-sm font-medium">Referred by <span className="text-primary">{referral.referred_by.referrer_name}</span></p>
                    <p className="text-xs text-muted-foreground">
                      {referral.referred_by.referrer_phone} · ₹{referral.referred_by.cashback_total} earned · {referral.referred_by.orders_credited} orders credited · {referral.referred_by.status}
                    </p>
                  </div>
                  {referral.referred_by.referrer_id && (
                    <Button variant="ghost" size="sm" className="ml-auto gap-1 text-xs"
                      onClick={() => navigate(`/admin/customers/${encodeURIComponent(referral.referred_by!.referrer_id)}`)}>
                      View <ChevronRight className="w-3.5 h-3.5" />
                    </Button>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {/* ORDERS */}
        {activeTab === 'orders' && (
          <div className="space-y-4 max-w-6xl">
            {orders.length === 0
              ? <p className="text-muted-foreground text-sm py-12 text-center">No orders yet</p>
              : (
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Order #</TableHead>
                        <TableHead>Restaurant</TableHead>
                        <TableHead>Total</TableHead>
                        <TableHead>Cash Redeemed</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Date</TableHead>
                        {orders[0]?.customer_rating !== undefined && <TableHead>Rating</TableHead>}
                        <TableHead />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {orders.map((o: any) => (
                        <TableRow key={o.name}
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => setOrderDialogName(o.name)}>
                          <TableCell className="font-mono text-xs">{o.order_number || o.name}</TableCell>
                          <TableCell className="text-sm">{o.restaurant_name}</TableCell>
                          <TableCell className="font-semibold">{fmtR(o.total)}</TableCell>
                          <TableCell>
                            {o.loyalty_coins_redeemed > 0
                              ? <Badge variant="secondary" className="text-rose-600 bg-rose-50">−₹{o.loyalty_coins_redeemed}</Badge>
                              : <span className="text-muted-foreground text-xs">—</span>}
                          </TableCell>
                          <TableCell>
                            <Badge variant={o.status === 'completed' ? 'default' : 'secondary'} className="text-[10px]">{o.status}</Badge>
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">{fmtDateTime(o.creation)}</TableCell>
                          {o.customer_rating !== undefined && (
                            <TableCell>
                              {o.customer_rating
                                ? <span className="flex items-center gap-0.5 text-xs"><Star className="w-3 h-3 text-yellow-400 fill-yellow-400" />{o.customer_rating}</span>
                                : <span className="text-muted-foreground">—</span>}
                            </TableCell>
                          )}
                          <TableCell className="w-8 text-muted-foreground">
                            <ChevronRight className="w-4 h-4" />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )
            }

            {table_bookings.length > 0 && (
              <>
                <p className="text-sm font-semibold flex items-center gap-2 mt-6"><Ticket className="w-4 h-4 text-primary" />Table Bookings ({table_bookings.length})</p>
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Booking #</TableHead>
                        <TableHead>Restaurant</TableHead>
                        <TableHead>Date</TableHead>
                        <TableHead>Time</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {table_bookings.map((b: any) => (
                        <TableRow key={b.name}>
                          <TableCell className="font-mono text-xs">{b.booking_number || b.name}</TableCell>
                          <TableCell>{b.restaurant_name}</TableCell>
                          <TableCell className="text-sm">{fmtDate(b.date)}</TableCell>
                          <TableCell className="text-xs">{b.time_slot || '—'}</TableCell>
                          <TableCell><Badge variant="secondary" className="text-[10px]">{b.status}</Badge></TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </>
            )}
          </div>
        )}

        {/* LOYALTY */}
        {activeTab === 'loyalty' && (
          <div className="space-y-5 max-w-5xl">
            <div className="grid grid-cols-3 gap-3">
              <StatCard icon={Wallet}        label="Spendable Balance" value={fmtR(loyalty.balance)}          accent="border-primary/30 bg-primary/5" />
              <StatCard icon={ArrowUpRight}  label="Lifetime Earned"   value={fmtR(loyalty.lifetime_earned)} />
              <StatCard icon={ArrowDownLeft} label="Total Redeemed"    value={fmtR(stats.total_redeemed)} />
            </div>

            {loyalty.entries.length === 0
              ? <p className="text-muted-foreground text-sm py-12 text-center">No loyalty transactions yet</p>
              : (
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Type</TableHead>
                        <TableHead>Reason</TableHead>
                        <TableHead>Restaurant</TableHead>
                        <TableHead>Coins</TableHead>
                        <TableHead>Expiry</TableHead>
                        <TableHead>Date</TableHead>
                        <TableHead />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {loyalty.entries.map((e: any) => {
                        const isOrderRef = e.reference_doctype === 'Order' && e.reference_name
                        return (
                          <TableRow key={e.name}
                            className={cn(isOrderRef && 'cursor-pointer hover:bg-muted/50')}
                            onClick={() => isOrderRef && setOrderDialogName(e.reference_name)}>
                            <TableCell>
                              <Badge variant="secondary" className={cn('text-[10px]',
                                e.transaction_type === 'Earn'
                                  ? 'text-green-700 bg-green-50 border-green-200'
                                  : 'text-rose-700 bg-rose-50 border-rose-200'
                              )}>
                                {e.transaction_type === 'Earn'
                                  ? <Plus className="w-2.5 h-2.5 inline mr-0.5" />
                                  : <Minus className="w-2.5 h-2.5 inline mr-0.5" />}
                                {e.transaction_type}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-xs">{e.reason}</TableCell>
                            <TableCell className="text-xs text-muted-foreground">{e.restaurant_name}</TableCell>
                            <TableCell className="font-semibold">
                              <span className={e.transaction_type === 'Earn' ? 'text-green-600' : 'text-rose-600'}>
                                {e.transaction_type === 'Earn' ? '+' : '−'}₹{e.coins}
                              </span>
                            </TableCell>
                            <TableCell className="text-xs text-muted-foreground">{e.expiry_date ? fmtDate(e.expiry_date) : '—'}</TableCell>
                            <TableCell className="text-xs text-muted-foreground">{fmtDate(e.posting_date)}</TableCell>
                            <TableCell className="w-6">
                              {isOrderRef && <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </div>
              )
            }
          </div>
        )}

        {/* REFERRAL */}
        {activeTab === 'referral' && (
          <div className="space-y-5 max-w-5xl">
            <Card>
              <CardHeader className="pb-2 pt-4 px-4">
                <p className="text-sm font-semibold flex items-center gap-2"><UserCheck className="w-4 h-4 text-primary" />Referred By</p>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                {referral.referred_by ? (
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-1.5 text-sm">
                      <p><span className="text-muted-foreground">Name:</span> <span className="font-medium">{referral.referred_by.referrer_name}</span></p>
                      <p><span className="text-muted-foreground">Phone:</span> {referral.referred_by.referrer_phone}</p>
                      <p><span className="text-muted-foreground">Orders credited:</span> {referral.referred_by.orders_credited} / 16</p>
                      <p><span className="text-muted-foreground">Cashback earned:</span> <span className="font-semibold text-primary">₹{referral.referred_by.cashback_total}</span></p>
                      <p><span className="text-muted-foreground">Status:</span> <Badge variant="secondary" className="text-[10px]">{referral.referred_by.status}</Badge></p>
                    </div>
                    {referral.referred_by.referrer_id && (
                      <Button variant="outline" size="sm" className="shrink-0 gap-1.5 text-xs"
                        onClick={() => navigate(`/admin/customers/${encodeURIComponent(referral.referred_by!.referrer_id)}`)}>
                        View Profile <ExternalLink className="w-3 h-3" />
                      </Button>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">This customer was not referred by anyone.</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2 pt-4 px-4">
                <p className="text-sm font-semibold flex items-center gap-2"><Users className="w-4 h-4 text-primary" />Referrals Made ({referral.referrals_made.length})</p>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                {referral.referrals_made.length === 0
                  ? <p className="text-sm text-muted-foreground">No referrals made yet</p>
                  : (
                    <div className="rounded-md border">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Referee</TableHead>
                            <TableHead>Phone</TableHead>
                            <TableHead>Orders Credited</TableHead>
                            <TableHead>Cashback Earned</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Since</TableHead>
                            <TableHead />
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {referral.referrals_made.map((r: any) => (
                            <TableRow key={r.referee}
                              className="cursor-pointer hover:bg-muted/50"
                              onClick={() => navigate(`/admin/customers/${encodeURIComponent(r.referee)}`)}>
                              <TableCell className="font-medium text-sm">{r.referee_name}</TableCell>
                              <TableCell className="text-sm">{r.referee_phone}</TableCell>
                              <TableCell>{r.orders_credited} / 16</TableCell>
                              <TableCell className="font-semibold text-primary">₹{r.cashback_total}</TableCell>
                              <TableCell><Badge variant="secondary" className="text-[10px]">{r.status}</Badge></TableCell>
                              <TableCell className="text-xs text-muted-foreground">{fmtDate(r.activated_on)}</TableCell>
                              <TableCell className="w-8 text-muted-foreground">
                                <ChevronRight className="w-4 h-4" />
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )
                }
              </CardContent>
            </Card>
          </div>
        )}

        {/* UGC */}
        {activeTab === 'ugc' && (
          <div className="max-w-5xl">
            {ugc.length === 0
              ? <p className="text-muted-foreground text-sm py-12 text-center">No UGC submissions yet</p>
              : (
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Restaurant</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Order Amount</TableHead>
                        <TableHead>Cashback</TableHead>
                        <TableHead>AI Views</TableHead>
                        <TableHead>Submitted</TableHead>
                        <TableHead />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {ugc.map((u: any) => (
                        <TableRow key={u.name}
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => setUgcDialogItem(u)}>
                          <TableCell className="text-sm font-medium">{u.restaurant_name}</TableCell>
                          <TableCell>
                            <Badge variant="secondary" className={cn('text-[10px]',
                              u.status === 'credited'  ? 'text-green-700 bg-green-50 border-green-200' :
                              u.status === 'rejected'  ? 'text-red-600 bg-red-50 border-red-200' :
                              u.status === 'expired'   ? 'text-gray-500 bg-gray-50' :
                              'text-amber-700 bg-amber-50 border-amber-200'
                            )}>
                              {u.status}
                            </Badge>
                          </TableCell>
                          <TableCell>{fmtR(u.order_amount)}</TableCell>
                          <TableCell>
                            {u.cashback_coins > 0
                              ? <span className="font-semibold text-green-600">₹{u.cashback_coins}</span>
                              : <span className="text-muted-foreground text-xs">—</span>}
                          </TableCell>
                          <TableCell className="text-sm">
                            {u.ai_view_count > 0
                              ? <span className="font-medium">{fmt(u.ai_view_count)}</span>
                              : <span className="text-muted-foreground text-xs">—</span>}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">{fmtDateTime(u.submission_date)}</TableCell>
                          <TableCell className="w-8 text-muted-foreground">
                            <ChevronRight className="w-4 h-4" />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )
            }
          </div>
        )}

      </div>

      {/* ── Order Detail Dialog (reuses shared OrderDetailsDialog component) ── */}
      <OrderDetailsDialog
        orderId={orderDialogName}
        open={!!orderDialogName}
        onOpenChange={v => !v && setOrderDialogName(null)}
      />

      {/* ── UGC Detail Dialog ── */}
      <UGCDetailDialog
        ugc={ugcDialogItem}
        open={!!ugcDialogItem}
        onClose={() => setUgcDialogItem(null)}
      />

      {/* ── Adjust Loyalty Modal ── */}
      <Dialog open={adjustOpen} onOpenChange={setAdjustOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Adjust Loyalty Cash</DialogTitle>
            <DialogDescription>Manual adjustment for {customer.name}. Max ₹500 per action.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Restaurant</Label>
              <Select value={adjRestaurant} onValueChange={setAdjRestaurant}>
                <SelectTrigger><SelectValue placeholder="Select restaurant" /></SelectTrigger>
                <SelectContent>
                  {visitedRestaurants.map(([id, name]) => (
                    <SelectItem key={id} value={id}>{name as string}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Type</Label>
              <Select value={adjType} onValueChange={(v) => setAdjType(v as 'Earn' | 'Redeem')}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="Earn">Add Cash (+)</SelectItem>
                  <SelectItem value="Redeem">Remove Cash (−)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Amount (₹)</Label>
              <NumberInput value={adjCoins} onChange={e => setAdjCoins(e.target.value)} placeholder="0" min={1} max={500} />
            </div>
            <div>
              <Label>Reason</Label>
              <Input value={adjReason} onChange={e => setAdjReason(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAdjustOpen(false)}>Cancel</Button>
            <Button onClick={handleAdjust} disabled={adjusting || !adjCoins || !adjRestaurant}>
              {adjusting ? 'Saving…' : 'Confirm'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Delete Modal ── */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-red-600 flex items-center gap-2"><Trash2 className="w-4 h-4" />Delete Customer</DialogTitle>
            <DialogDescription>
              This is irreversible. All orders, bookings, loyalty entries, referral relationships, and UGC submissions will be permanently deleted.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-sm">Type the customer's phone number to confirm: <span className="font-mono font-bold">{customer.phone}</span></p>
            <Input value={deleteConfirm} onChange={e => setDeleteConfirm(e.target.value)} placeholder="Enter phone number" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting || deleteConfirm !== customer.phone}>
              {deleting ? 'Deleting…' : 'Delete Customer'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  )
}
