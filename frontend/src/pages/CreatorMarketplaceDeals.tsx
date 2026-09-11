import { useEffect, useState } from 'react'
import { useOutlet } from '@/contexts/OutletContext'
import { useFrappeGetCall, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent } from '@/components/ui/card'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import DealDetailSheet from '@/components/DealDetailSheet'
import CreatorProfileSheet from '@/components/CreatorProfileSheet'
import { toast } from 'sonner'
import { getFrappeError } from '@/lib/utils'
import { Handshake, Wallet, CheckCircle2, CalendarClock } from 'lucide-react'

function initials(name: string) {
  return name.split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('') || '?'
}

declare global {
  interface Window {
    Razorpay: any
  }
}

const STATUS_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'offered', label: 'Offered' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'funded', label: 'Funded' },
  { value: 'delivered', label: 'Delivered' },
  { value: 'released', label: 'Released' },
  { value: 'cancelled', label: 'Cancelled' },
]

const STATUS_COLORS: Record<string, string> = {
  offered: 'bg-muted text-muted-foreground border-border',
  accepted: 'bg-blue-50 text-blue-700 border-blue-200',
  funded: 'bg-blue-50 text-blue-700 border-blue-200',
  delivered: 'bg-amber-50 text-amber-700 border-amber-200',
  released: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  disputed: 'bg-red-50 text-red-700 border-red-200',
  refunded: 'bg-muted text-muted-foreground border-border',
  cancelled: 'bg-muted text-muted-foreground border-border',
}
const STATUS_LABELS: Record<string, string> = {
  offered: 'Offered',
  accepted: 'Accepted',
  funded: 'Funded',
  delivered: 'Delivered',
  released: 'Released',
  disputed: 'Disputed',
  refunded: 'Refunded',
  cancelled: 'Cancelled',
}

interface Deal {
  name: string
  status: string
  deal_type: 'cash' | 'barter'
  creator: string
  creator_name: string | null
  creator_profile_image: string | null
  price_inr: number
  fair_value_inr: number
  deadline: string
  creation: string
}

function useRazorpayScript() {
  const [loaded, setLoaded] = useState(!!window.Razorpay)
  useEffect(() => {
    if (window.Razorpay) { setLoaded(true); return }
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.onload = () => setLoaded(true)
    script.onerror = () => setLoaded(false)
    document.body.appendChild(script)
  }, [])
  return loaded
}

export default function CreatorMarketplaceDeals() {
  const { selectedOutlet } = useOutlet()
  const [status, setStatus] = useState('all')
  const [busyDeal, setBusyDeal] = useState<string | null>(null)
  const [viewingDealId, setViewingDealId] = useState<string | null>(null)
  const [viewingCreatorId, setViewingCreatorId] = useState<string | null>(null)
  const razorpayLoaded = useRazorpayScript()

  const { data, mutate, isLoading } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.collab_deals.list_outlet_deals',
    selectedOutlet ? { outlet_id: selectedOutlet, ...(status !== 'all' ? { status } : {}) } : undefined,
    selectedOutlet ? `outlet-deals-${selectedOutlet}-${status}` : undefined,
  )
  const { call: acceptApplication } = useFrappePostCall(
    'flamezo_backend.flamezo.api.collab_deals.accept_application',
  )
  const { call: fundDeal } = useFrappePostCall('flamezo_backend.flamezo.api.collab_deals.fund_deal')
  const { call: verifyDealPayment } = useFrappePostCall(
    'flamezo_backend.flamezo.api.collab_deals.verify_deal_payment',
  )
  const { call: approveRelease } = useFrappePostCall(
    'flamezo_backend.flamezo.api.collab_deals.approve_release',
  )

  const body: any = (data as any)?.message || data
  const deals: Deal[] = body?.data?.deals || []

  const handleAccept = async (dealId: string) => {
    if (!selectedOutlet) return
    setBusyDeal(dealId)
    try {
      await acceptApplication({ outlet_id: selectedOutlet, deal_id: dealId })
      toast.success('Deal accepted')
      mutate()
    } catch (error: any) {
      toast.error('Could not accept deal', { description: getFrappeError(error) })
    } finally {
      setBusyDeal(null)
    }
  }

  const handleFund = async (dealId: string) => {
    if (!selectedOutlet) return
    if (!razorpayLoaded) {
      toast.error('Payment system is still loading — try again in a moment.')
      return
    }
    setBusyDeal(dealId)
    try {
      const res: any = await fundDeal({ outlet_id: selectedOutlet, deal_id: dealId })
      const funding = res?.message?.data || res?.data
      const rzp = new window.Razorpay({
        key: funding.key_id,
        amount: Math.round(funding.amount_inr * 100),
        currency: 'INR',
        name: 'Flamezo Creator & Collab',
        description: `Escrow funding for collab ${dealId}`,
        order_id: funding.razorpay_order_id,
        theme: { color: '#B7410E' },
        handler: async (paymentResponse: any) => {
          try {
            await verifyDealPayment({
              outlet_id: selectedOutlet,
              deal_id: dealId,
              razorpay_order_id: funding.razorpay_order_id,
              razorpay_payment_id: paymentResponse.razorpay_payment_id,
              razorpay_signature: paymentResponse.razorpay_signature,
            })
            toast.success('Escrow funded')
            mutate()
          } catch (error: any) {
            toast.error('Payment verification failed', { description: getFrappeError(error) })
          } finally {
            setBusyDeal(null)
          }
        },
        modal: { ondismiss: () => setBusyDeal(null) },
      })
      rzp.on('payment.failed', (r: any) => {
        toast.error('Payment failed', { description: r.error?.description })
        setBusyDeal(null)
      })
      rzp.open()
    } catch (error: any) {
      toast.error('Could not start funding', { description: getFrappeError(error) })
      setBusyDeal(null)
    }
  }

  const handleApproveRelease = async (dealId: string) => {
    if (!selectedOutlet) return
    setBusyDeal(dealId)
    try {
      await approveRelease({ outlet_id: selectedOutlet, deal_id: dealId })
      toast.success('Deal released')
      mutate()
    } catch (error: any) {
      toast.error('Could not release deal', { description: getFrappeError(error) })
    } finally {
      setBusyDeal(null)
    }
  }

  if (isLoading && !data) return <GenericPageSkeleton />

  return (
    <div className="space-y-6 pb-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Deals</h1>
          <p className="text-muted-foreground text-sm mt-1">Fund escrow, track delivery & release payment</p>
        </div>
        <div className="shrink-0">
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="w-44 h-10 rounded-md shadow-sm bg-background border-border/60 focus:ring-1 focus:ring-primary/20 transition-all">
              <SelectValue placeholder="All Statuses" />
            </SelectTrigger>
            <SelectContent className="rounded-lg shadow-lg border-border/40">
              {STATUS_OPTIONS.map((s) => (
                <SelectItem key={s.value} value={s.value} className="rounded-md mx-1 my-0.5 cursor-pointer">
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {deals.length === 0 ? (
        <Card className="border-dashed bg-muted/30">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <div className="h-16 w-16 rounded-md bg-muted flex items-center justify-center mb-4">
              <Handshake className="h-8 w-8 text-muted-foreground/60" />
            </div>
            <h3 className="text-lg font-semibold mb-2">No deals here yet</h3>
            <p className="text-muted-foreground max-w-sm">
              When creators accept your collab invites, or when you accept their applications, deals will appear here.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {deals.map((d) => (
            <div key={d.name} className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-lg border border-border bg-card hover:border-foreground/20 transition-all">

              {/* Left Side: Avatar & Details. Avatar+name is its own
                  clickable target (opens the CREATOR's profile) nested
                  inside the row's own click target (opens the DEAL
                  detail) — same split Upwork uses: click the person, get
                  their profile; click anywhere else in the row, get the
                  contract. The outer wrapper is a div, not a button, so
                  it can legally contain the real nested button. */}
              <div
                role="button"
                tabIndex={0}
                onClick={() => setViewingDealId(d.name)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setViewingDealId(d.name) }}
                className="flex items-start gap-4 text-left cursor-pointer"
              >
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); setViewingCreatorId(d.creator) }}
                  className="shrink-0 cursor-pointer"
                >
                  <Avatar className="h-12 w-12 border shadow-sm mt-0.5 hover:ring-2 hover:ring-primary/30 transition-all">
                    {d.creator_profile_image && <AvatarImage src={d.creator_profile_image} alt={d.creator_name || d.creator} className="object-cover" />}
                    <AvatarFallback className="text-sm font-medium bg-muted text-muted-foreground">{initials(d.creator_name || d.creator)}</AvatarFallback>
                  </Avatar>
                </button>

                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); setViewingCreatorId(d.creator) }}
                      className="font-semibold text-base leading-tight text-left cursor-pointer hover:text-primary hover:underline transition-colors"
                    >
                      {d.creator_name || d.creator}
                    </button>
                    <Badge variant="secondary" className={`font-medium px-2 py-0.5 capitalize ${STATUS_COLORS[d.status] || ''}`}>
                      {STATUS_LABELS[d.status] || d.status}
                    </Badge>
                  </div>

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1.5 font-medium text-foreground">
                      {d.deal_type === 'cash' ? <Wallet className="h-3.5 w-3.5" /> : <Handshake className="h-3.5 w-3.5" />}
                      {d.deal_type === 'cash' ? `${d.price_inr?.toLocaleString('en-IN')} cash` : `${d.fair_value_inr?.toLocaleString('en-IN')} barter`}
                    </span>
                    {d.deadline && (
                      <span className="flex items-center gap-1.5 border-l pl-4 border-border/60">
                        <CalendarClock className="h-3.5 w-3.5" />
                        Due {d.deadline}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Right Side: Actions */}
              {(d.status === 'offered' || (d.status === 'accepted' && d.deal_type === 'cash') || d.status === 'delivered') && (
                <div className="shrink-0 sm:ml-auto">
                  {d.status === 'offered' && (
                    <Button className="rounded-md px-6 font-medium shadow-sm transition-all w-full sm:w-auto" disabled={busyDeal === d.name} onClick={() => handleAccept(d.name)}>
                      {busyDeal === d.name ? 'Accepting…' : 'Accept Deal'}
                    </Button>
                  )}
                  {d.status === 'accepted' && d.deal_type === 'cash' && (
                    <Button className="rounded-md px-6 font-medium shadow-sm transition-all w-full sm:w-auto" disabled={busyDeal === d.name} onClick={() => handleFund(d.name)}>
                      <Wallet className="h-4 w-4 mr-2" />
                      {busyDeal === d.name ? 'Opening…' : 'Fund Escrow'}
                    </Button>
                  )}
                  {d.status === 'delivered' && (
                    <Button className="rounded-md px-6 font-medium shadow-sm transition-all bg-emerald-600 hover:bg-emerald-700 text-white w-full sm:w-auto" disabled={busyDeal === d.name} onClick={() => handleApproveRelease(d.name)}>
                      <CheckCircle2 className="h-4 w-4 mr-2" />
                      {busyDeal === d.name ? 'Releasing…' : 'Approve & Release'}
                    </Button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <DealDetailSheet
        dealId={viewingDealId}
        outletId={selectedOutlet || undefined}
        onClose={() => setViewingDealId(null)}
        busy={!!viewingDealId && busyDeal === viewingDealId}
        onAccept={() => viewingDealId && handleAccept(viewingDealId)}
        onFund={() => viewingDealId && handleFund(viewingDealId)}
        onRelease={() => viewingDealId && handleApproveRelease(viewingDealId)}
      />

      <CreatorProfileSheet creatorId={viewingCreatorId} onClose={() => setViewingCreatorId(null)} />
    </div>
  )
}
