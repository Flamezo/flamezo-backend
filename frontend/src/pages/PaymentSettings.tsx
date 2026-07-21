import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useFrappePostCall } from '@/lib/frappe'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { DatePicker } from '@/components/ui/date-picker'
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '@/components/ui/table'
import { 
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { toast } from 'sonner'
import { format, subDays } from 'date-fns'
import {
  CreditCard,
  Loader2,
  RefreshCcw,
  Search,
  History,
  Download,
  CheckCircle2,
  Clock,
  XCircle,
  Undo2,
  ShieldAlert,
  Info,
  CalendarDays,
  IndianRupee,
  Wallet,
  Sparkles,
  Receipt,
  ChevronRight
} from 'lucide-react'
import { cn } from '@/lib/utils'
import PaymentBreakdownModal from '@/components/PaymentBreakdownModal'

interface PaymentBreakdown {
  bill: number
  customerSaved: number
  couponCode: string | null
  merchantGets: number
  flamezoGets: number
  settlementMode: string | null
  /** "web" | "app" — only app orders carry a success share. */
  paymentSource?: string
  estimated?: boolean
}

interface RazorpayPayment {
  id: string
  amount: number
  currency: string
  status: string
  method: string
  email: string
  contact: string
  created_at: number
  description?: string
  refund_status?: string | null
  amount_refunded?: number
  breakdown?: PaymentBreakdown | null
}

type FilterPreset = 'today' | 'yesterday' | '7d' | '30d' | 'custom'

/** Which sales channel the figures below are scoped to. */
type SourceTab = 'all' | 'web' | 'app'

function SummaryCard({
  title, value, subtext, icon: Icon, accent,
}: {
  title: string
  value: string | number
  subtext: string
  icon: React.ComponentType<{ className?: string }>
  accent?: 'emerald' | 'orange' | 'muted'
}) {
  return (
    <Card className="border-muted/50">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-[11px] uppercase tracking-widest text-muted-foreground font-black">{title}</CardTitle>
        <Icon className={cn(
          'h-4 w-4',
          accent === 'emerald' ? 'text-emerald-500' : accent === 'muted' ? 'text-muted-foreground' : 'text-orange-500',
        )} />
      </CardHeader>
      <CardContent>
        <div className={cn('text-2xl font-black', accent === 'emerald' && 'text-emerald-600 dark:text-emerald-400')}>{value}</div>
        <p className="text-[11px] text-muted-foreground mt-1">{subtext}</p>
      </CardContent>
    </Card>
  )
}

export default function PaymentSettings() {
  const { restaurantId } = useParams()
  const { selectedRestaurant } = useRestaurant()
  const activeRestaurantId = restaurantId || selectedRestaurant

  const [payments, setPayments] = useState<RazorpayPayment[]>([])
  const [detailPayment, setDetailPayment] = useState<RazorpayPayment | null>(null)
  const [loading, setLoading] = useState(true)
  const [isRefunding, setIsRefunding] = useState(false)
  const [refundAmount, setRefundAmount] = useState<string>('')
  const [refundReason, setRefundReason] = useState<string>('requested_by_customer')
  const [selectedPayment, setSelectedPayment] = useState<RazorpayPayment | null>(null)
  
  // Filters
  const today = format(new Date(), 'yyyy-MM-dd')
  const [fromDate, setFromDate] = useState<string>(today)
  const [toDate, setToDate] = useState<string>(today)
  const [activePreset, setActivePreset] = useState<FilterPreset>('today')
  const [sourceTab, setSourceTab] = useState<SourceTab>('all')

  const { call: getPayments } = useFrappePostCall<{ success: boolean; data: { items: RazorpayPayment[] } }>(
    'flamezo_backend.flamezo.api.payments.get_razorpay_payments'
  )
  const { call: refundPayment } = useFrappePostCall(
    'flamezo_backend.flamezo.api.payments.initiate_razorpay_refund'
  )

  const loadPayments = useCallback(async (fDate?: string, tDate?: string) => {
    if (!activeRestaurantId) return
    setLoading(true)
    try {
      const resp: any = await getPayments({ 
        restaurant_id: activeRestaurantId,
        from_date: fDate || fromDate || undefined,
        to_date: tDate || toDate || undefined,
        count: 50
      })
      const body = resp?.message ?? resp
      if (body?.success) {
        setPayments(body.data?.items || [])
      } else {
        toast.error('Failed to fetch transactions', { description: body?.error })
      }
    } catch (e) {
      console.error(e)
      toast.error('Error connecting to Razorpay')
    } finally {
      setLoading(false)
    }
  }, [activeRestaurantId, fromDate, toDate, getPayments])

  useEffect(() => {
    loadPayments()
  }, [activeRestaurantId]) // Only load once on mount or restaurant change

  const applyPreset = (preset: FilterPreset) => {
    setActivePreset(preset)
    let f = today
    let t = today

    if (preset === 'yesterday') {
      f = format(subDays(new Date(), 1), 'yyyy-MM-dd')
      t = f
    } else if (preset === '7d') {
      f = format(subDays(new Date(), 6), 'yyyy-MM-dd')
      t = today
    } else if (preset === '30d') {
      f = format(subDays(new Date(), 29), 'yyyy-MM-dd')
      t = today
    } else if (preset === 'custom') {
      return // Don't trigger load immediately for custom
    }

    setFromDate(f)
    setToDate(t)
    loadPayments(f, t)
  }

  const handleRefund = async () => {
    if (!activeRestaurantId || !selectedPayment) return
    
    setIsRefunding(true)
    try {
      const resp: any = await refundPayment({
        restaurant_id: activeRestaurantId,
        payment_id: selectedPayment.id,
        amount: refundAmount || undefined,
        reason: refundReason
      })
      const body = resp?.message ?? resp
      if (body?.success) {
        toast.success('Refund initiated successfully')
        setSelectedPayment(null)
        setRefundAmount('')
        loadPayments()
      } else {
        toast.error('Refund failed', { description: body?.error })
      }
    } catch (err: any) {
      toast.error('Refund failed')
    } finally {
      setIsRefunding(false)
    }
  }

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
    }).format(amount / 100)
  }

  // Breakdown values already come from the Order in rupees (not paise).
  const formatRs = (amount: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(amount || 0)
  }

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'captured':
        return <Badge className="bg-emerald-500/10 text-emerald-700 border-emerald-200 hover:bg-emerald-500/20 gap-1"><CheckCircle2 className="h-3 w-3" /> Captured</Badge>
      case 'refunded':
        return <Badge variant="secondary" className="gap-1"><Undo2 className="h-3 w-3" /> Refunded</Badge>
      case 'failed':
        return <Badge variant="destructive" className="bg-red-500/10 text-red-700 border-red-200 gap-1"><XCircle className="h-3 w-3" /> Failed</Badge>
      case 'authorized':
        return <Badge variant="outline" className="bg-blue-500/10 text-blue-700 border-blue-200 gap-1"><Clock className="h-3 w-3" /> Authorized</Badge>
      default:
        return <Badge variant="outline">{status}</Badge>
    }
  }

  // Each payment surfaces a transient "created" row and the real "captured" row.
  // Show only the meaningful ones (hide the "created" duplicate).
  // Then scope to the selected channel — payments with no recorded source are
  // treated as web, which is where every pre-app order came from.
  const sourceOf = (p: RazorpayPayment): SourceTab =>
    (p.breakdown?.paymentSource || 'web').toLowerCase() === 'app' ? 'app' : 'web'

  const visiblePayments = payments
    .filter((p) => p.status !== 'created')
    .filter((p) => sourceTab === 'all' || sourceOf(p) === sourceTab)

  // Aggregate the 4 summary cards from the payments in the selected range.
  // Flamezo only earns a success share on app orders — web orders are the
  // outlet's own customers, so the merchant keeps the full amount there.
  const summary = visiblePayments.reduce(
    (acc, p) => {
      if (p.status === 'captured') {
        const gross = p.amount / 100
        acc.revenue += gross
        const isApp = sourceOf(p) === 'app'
        const flamezoCut = isApp ? p.breakdown?.flamezoGets || 0 : 0
        acc.flamezo += flamezoCut
        // Fall back to gross minus the cut when a payment has no stored split,
        // so "You Keep" still reconciles with Revenue.
        acc.youGet += isApp ? p.breakdown?.merchantGets || gross - flamezoCut : gross
      }
      return acc
    },
    { revenue: 0, youGet: 0, flamezo: 0 },
  )

  if (!activeRestaurantId) {
    return <div className="p-8 text-center text-muted-foreground">Please select a restaurant to view transactions.</div>
  }

  return (
    <div className="space-y-4 pb-10">
      {/* Header Area */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-0.5">
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            Transactions & History
            <History className="h-6 w-6 text-muted-foreground/50" />
          </h1>
          <p className="text-muted-foreground text-sm max-w-2xl">
            Monitor all incoming customer payments and manage refunds directly from your Razorpay account.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            className="rounded-full shadow-sm hover:bg-muted transition-all gap-2"
            onClick={() => loadPayments()}
            disabled={loading}
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
            Refresh
          </Button>
        </div>
      </div>

      {/* Channel tabs — scope every figure below to web, app, or both. */}
      <div className="inline-flex items-center gap-1 rounded-full bg-muted/60 p-1">
        {([
          { id: 'all', label: 'All' },
          { id: 'web', label: 'Web' },
          { id: 'app', label: 'App' },
        ] as { id: SourceTab; label: string }[]).map((t) => (
          <button
            key={t.id}
            onClick={() => setSourceTab(t.id)}
            className={`px-4 py-1.5 text-xs font-semibold rounded-full transition-all ${
              sourceTab === t.id
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Summary cards (merchant-only) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <SummaryCard title="Revenue" value={formatRs(summary.revenue)} subtext={sourceTab === 'all' ? 'Web + App in this range' : `${sourceTab === 'web' ? 'Web' : 'App'} orders in this range`} icon={IndianRupee} accent="orange" />
        <SummaryCard title="You Keep" value={formatRs(summary.youGet)} subtext={sourceTab === 'web' ? 'You keep 100% on web' : 'Your share of payments'} icon={Wallet} accent="emerald" />
        <SummaryCard title="Flamezo Share" value={formatRs(summary.flamezo)} subtext={sourceTab === 'web' ? 'No success share on web' : 'Success share on app orders'} icon={Sparkles} accent="muted" />
        <SummaryCard title="Transactions" value={visiblePayments.length} subtext="Payments in this range" icon={Receipt} accent="muted" />
      </div>

      {/* Filters Section */}
      <Card className="border-none bg-muted/30 shadow-none overflow-hidden">
        <CardContent className="p-3">
          <div className="flex flex-col space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/80 mr-1 ml-1">Filters:</span>
              {(['today', 'yesterday', '7d', '30d', 'custom'] as FilterPreset[]).map((preset) => (
                <Button
                  key={preset}
                  variant={activePreset === preset ? 'default' : 'outline'}
                  size="sm"
                  className={cn(
                    "rounded-full px-4 text-xs h-8 transition-all",
                    activePreset === preset ? "shadow-md shadow-primary/20" : "hover:border-primary/50"
                  )}
                  onClick={() => applyPreset(preset)}
                >
                  {preset === 'today' && 'Today'}
                  {preset === 'yesterday' && 'Yesterday'}
                  {preset === '7d' && 'Last 7 Days'}
                  {preset === '30d' && 'Last 30 Days'}
                  {preset === 'custom' && 'Custom Range'}
                </Button>
              ))}
            </div>

            {activePreset === 'custom' && (
              <div className="flex flex-col md:flex-row items-end gap-3 p-3 rounded-xl bg-background/50 border border-muted/50 animate-in fade-in slide-in-from-top-1 duration-200">
                <div className="flex-1 w-full space-y-1">
                  <DatePicker 
                    label="From" 
                    value={fromDate} 
                    onChange={setFromDate}
                  />
                </div>
                <div className="flex-1 w-full space-y-1">
                  <DatePicker 
                    label="To" 
                    value={toDate} 
                    onChange={setToDate}
                  />
                </div>
                <Button 
                  size="sm"
                  className="rounded-lg px-6 h-9"
                  onClick={() => loadPayments()}
                >
                  <Search className="h-4 w-4 mr-2" />
                  Search
                </Button>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Transactions Table */}
      <Card className="border-none shadow-sm overflow-hidden">
        <CardHeader className="flex flex-row items-center justify-between py-3">
          <div className="space-y-0.5">
            <CardTitle className="text-base font-bold flex items-center gap-2">
              <CalendarDays className="h-4 w-4 text-primary" />
              {activePreset === 'today' ? "Today's Transactions" : "Transaction List"}
            </CardTitle>
            <p className="text-[10px] text-muted-foreground font-medium flex items-center gap-1.5">
              <Clock className="h-3 w-3" />
              Showing results from {format(new Date(fromDate), 'do MMM')} to {format(new Date(toDate), 'do MMM, yyyy')}
            </p>
          </div>
          <Button variant="ghost" size="sm" className="text-[10px] text-muted-foreground h-7 hover:bg-muted rounded-full px-3 uppercase font-bold tracking-wider">
            <Download className="h-3 w-3 mr-1" />
            Export CSV
          </Button>
        </CardHeader>
        <CardContent className="px-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent border-muted/50">
                  <TableHead className="w-[180px] text-[10px] uppercase font-black tracking-widest pl-6 text-muted-foreground/70">Payment ID</TableHead>
                  <TableHead className="text-[10px] uppercase font-black tracking-widest text-muted-foreground/70">Date & Time</TableHead>
                  <TableHead className="text-[10px] uppercase font-black tracking-widest text-muted-foreground/70">Customer</TableHead>
                  <TableHead className="text-[10px] uppercase font-black tracking-widest text-muted-foreground/70">Method</TableHead>
                  <TableHead className="text-[10px] uppercase font-black tracking-widest text-muted-foreground/70">Amount</TableHead>
                  <TableHead className="text-[10px] uppercase font-black tracking-widest text-muted-foreground/70">Status</TableHead>
                  <TableHead className="text-right pr-6 text-[10px] uppercase font-black tracking-widest text-muted-foreground/70">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={i} className="animate-pulse">
                      <TableCell colSpan={7} className="h-16 pl-6">
                        <div className="h-4 bg-muted rounded w-3/4" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : visiblePayments.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="h-64 text-center text-muted-foreground">
                      <div className="flex flex-col items-center justify-center space-y-4">
                        <div className="h-16 w-16 bg-muted/50 rounded-full flex items-center justify-center">
                          <Search className="h-8 w-8 text-muted-foreground/20" />
                        </div>
                        <div className="space-y-1">
                          <p className="font-semibold text-foreground">No transactions found</p>
                          <p className="text-xs">Adjust your filters or try refreshing the list.</p>
                        </div>
                        <Button 
                          variant="outline" 
                          size="sm" 
                          className="rounded-full"
                          onClick={() => loadPayments()}
                        >
                          Refresh Page
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ) : (
                  visiblePayments.map((p, i) => (
                    <TableRow
                      key={p.id}
                      onClick={() => setDetailPayment(p)}
                      style={{ animationDelay: `${Math.min(i, 12) * 45}ms` }}
                      className="group hover:bg-muted/30 transition-colors border-muted/50 cursor-pointer animate-in fade-in slide-in-from-bottom-1 fill-mode-both duration-300"
                    >
                      <TableCell className="font-mono text-xs pl-6 text-primary group-hover:font-semibold transition-all">{p.id}</TableCell>
                      <TableCell className="text-sm">{formatDate(p.created_at)}</TableCell>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="text-sm font-semibold">{p.email || 'Guest Customer'}</span>
                          <span className="text-[10px] text-muted-foreground/70 font-mono">{p.contact || 'No contact'}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-xs capitalize">
                        <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted/50 w-fit">
                          <CreditCard className="h-3 w-3 text-muted-foreground" />
                          {p.method}
                        </div>
                      </TableCell>
                      <TableCell className="font-bold text-sm">
                        {formatCurrency(p.amount)}
                      </TableCell>
                      <TableCell>
                        {getStatusBadge(p.status)}
                      </TableCell>
                      <TableCell className="text-right pr-6">
                        <div className="flex items-center justify-end gap-2">
                        {p.status === 'captured' && (
                          <Dialog>
                            <DialogTrigger asChild>
                              <Button 
                                variant="outline" 
                                size="sm" 
                                className="h-8 rounded-lg hover:bg-red-50 hover:text-red-700 hover:border-red-200 transition-all gap-1.5"
                                onClick={(e) => { e.stopPropagation(); setSelectedPayment(p) }}
                              >
                                <Undo2 className="h-3 w-3" />
                                Refund
                              </Button>
                            </DialogTrigger>
                            <DialogContent className="sm:max-w-[425px] rounded-3xl">
                              <DialogHeader>
                                <DialogTitle className="text-xl">Process Refund</DialogTitle>
                                <DialogDescription className="text-xs">
                                  You are initiating a refund for payment <span className="font-mono font-bold text-primary">{p.id}</span>.
                                </DialogDescription>
                              </DialogHeader>
                              <div className="grid gap-6 py-4">
                                <div className="p-4 rounded-2xl bg-muted/30 border border-muted/50 space-y-3">
                                  <div className="flex justify-between items-center text-xs">
                                    <span className="text-muted-foreground text-xs uppercase font-bold tracking-wider">Customer</span>
                                    <span className="font-semibold">{p.email}</span>
                                  </div>
                                  <div className="flex justify-between items-center text-xs">
                                    <span className="text-muted-foreground text-xs uppercase font-bold tracking-wider">Method</span>
                                    <span className="font-semibold capitalize">{p.method}</span>
                                  </div>
                                  <div className="flex justify-between items-center">
                                    <span className="text-muted-foreground text-xs uppercase font-bold tracking-wider">Total Amount</span>
                                    <span className="text-lg font-bold text-foreground">{formatCurrency(p.amount)}</span>
                                  </div>
                                </div>

                                <div className="space-y-4">
                                  <div className="space-y-2">
                                    <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground ml-1">Refund Amount (Optional)</label>
                                    <div className="relative">
                                      <span className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground font-semibold">₹</span>
                                      <NumberInput 
                                        placeholder={`Full Amount: ${p.amount / 100}`} 
                                        className="pl-8 bg-muted/30 border-muted/50 focus:border-primary rounded-xl h-11"
                                        
                                        value={refundAmount}
                                        onChange={(e) => setRefundAmount(e.target.value)}
                                      />
                                    </div>
                                    <p className="text-[10px] text-muted-foreground ml-1 italic">Leave blank to refund the full amount.</p>
                                  </div>
                                  <div className="space-y-2">
                                    <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground ml-1">Reason for Refund</label>
                                    <select 
                                      className="w-full flex h-11 rounded-xl border border-muted/50 bg-muted/30 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 appearance-none bg-[url('data:image/svg+xml;charset=US-ASCII,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20width%3D%2224%22%20height%3D%2224%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23666%22%20stroke-width%3D%222%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpolyline%20points%3D%226%209%2012%2015%2018%209%22%3E%3C/polyline%3E%3C/svg%3E')] bg-[length:1.25em_1.25em] bg-[right_0.75em_center] bg-no-repeat cursor-pointer"
                                      value={refundReason}
                                      onChange={(e) => setRefundReason(e.target.value)}
                                    >
                                      <option value="requested_by_customer">Customer Requested</option>
                                      <option value="duplicate">Duplicate Payment</option>
                                      <option value="fraud">Fraudulent / Suspicious</option>
                                      <option value="other">Other Reason</option>
                                    </select>
                                  </div>
                                </div>
                              </div>
                              <DialogFooter className="pt-4 flex flex-col sm:flex-row gap-3">
                                <Button 
                                  variant="destructive" 
                                  onClick={handleRefund}
                                  disabled={isRefunding}
                                  className="w-full h-12 rounded-xl text-sm font-bold shadow-lg shadow-red-500/20"
                                >
                                  {isRefunding ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <ShieldAlert className="h-4 w-4 mr-2" />}
                                  Confirm & Process Refund
                                </Button>
                              </DialogFooter>
                            </DialogContent>
                          </Dialog>
                        )}
                          <div className="h-8 w-8 rounded-full flex items-center justify-center group-hover:bg-muted/50 transition-all shrink-0">
                            <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-all translate-x-[-2px] group-hover:translate-x-0" />
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Footer Info */}
      <div className="flex items-start gap-3 p-4 rounded-2xl bg-primary/5 border border-primary/10 max-w-2xl">
        <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
          <Info className="h-4 w-4 text-primary" />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-bold text-foreground">Refund Processing Notice</p>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            Transactions listed here are fetched directly from your <span className="font-bold">Razorpay Merchant Dashboard</span>. 
            Initiating a refund here will immediately trigger the process on Razorpay. 
            Refunds typically take <span className="font-bold">5-7 business days</span> to reflect in the customer's bank statement.
          </p>
        </div>
      </div>

      {/* Per-payment animated breakdown (merchant-only): bill → offer → split → bank */}
      <PaymentBreakdownModal
        open={!!detailPayment}
        onClose={() => setDetailPayment(null)}
        paymentId={detailPayment?.id}
        dateLabel={detailPayment ? formatDate(detailPayment.created_at) : ''}
        status={detailPayment?.status}
        method={detailPayment?.method}
        breakdown={detailPayment?.breakdown}
      />
    </div>
  )
}
