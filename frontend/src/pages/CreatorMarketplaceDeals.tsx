import { useEffect, useState } from 'react'
import { useOutlet } from '@/contexts/OutletContext'
import { useFrappeGetCall, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { toast } from 'sonner'
import { getFrappeError } from '@/lib/utils'
import { Handshake, Wallet, CheckCircle2 } from 'lucide-react'

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

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'outline'> = {
  offered: 'outline',
  accepted: 'secondary',
  funded: 'secondary',
  delivered: 'default',
  released: 'default',
  cancelled: 'outline',
}

interface Deal {
  name: string
  status: string
  deal_type: 'cash' | 'barter'
  creator: string
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

  const handleAccept = async (deal: Deal) => {
    if (!selectedOutlet) return
    setBusyDeal(deal.name)
    try {
      await acceptApplication({ outlet_id: selectedOutlet, deal_id: deal.name })
      toast.success('Deal accepted')
      mutate()
    } catch (error: any) {
      toast.error('Could not accept deal', { description: getFrappeError(error) })
    } finally {
      setBusyDeal(null)
    }
  }

  const handleFund = async (deal: Deal) => {
    if (!selectedOutlet) return
    if (!razorpayLoaded) {
      toast.error('Payment system is still loading — try again in a moment.')
      return
    }
    setBusyDeal(deal.name)
    try {
      const res: any = await fundDeal({ outlet_id: selectedOutlet, deal_id: deal.name })
      const funding = res?.message?.data || res?.data
      const rzp = new window.Razorpay({
        key: funding.key_id,
        amount: Math.round(funding.amount_inr * 100),
        currency: 'INR',
        name: 'Flamezo Creator & Collab',
        description: `Escrow funding for collab ${deal.name}`,
        order_id: funding.razorpay_order_id,
        theme: { color: '#B7410E' },
        handler: async (paymentResponse: any) => {
          try {
            await verifyDealPayment({
              outlet_id: selectedOutlet,
              deal_id: deal.name,
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

  const handleApproveRelease = async (deal: Deal) => {
    if (!selectedOutlet) return
    setBusyDeal(deal.name)
    try {
      await approveRelease({ outlet_id: selectedOutlet, deal_id: deal.name })
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
    <div className="space-y-4">
      <div className="flex justify-end">
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((s) => (
              <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {deals.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <Handshake className="h-10 w-10 mx-auto mb-3 opacity-40" />
            No deals here yet.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Creator</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Value</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Deadline</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {deals.map((d) => (
                <TableRow key={d.name}>
                  <TableCell className="font-medium">{d.creator}</TableCell>
                  <TableCell className="capitalize">{d.deal_type}</TableCell>
                  <TableCell>
                    {d.deal_type === 'cash'
                      ? `₹${d.price_inr?.toLocaleString('en-IN')}`
                      : `₹${d.fair_value_inr?.toLocaleString('en-IN')} (barter)`}
                  </TableCell>
                  <TableCell>
                    <Badge variant={STATUS_VARIANT[d.status] || 'outline'}>{d.status}</Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{d.deadline || '—'}</TableCell>
                  <TableCell className="text-right">
                    {d.status === 'offered' && (
                      <Button size="sm" disabled={busyDeal === d.name} onClick={() => handleAccept(d)}>
                        {busyDeal === d.name ? 'Accepting…' : 'Accept'}
                      </Button>
                    )}
                    {d.status === 'accepted' && d.deal_type === 'cash' && (
                      <Button size="sm" disabled={busyDeal === d.name} onClick={() => handleFund(d)}>
                        <Wallet className="h-3.5 w-3.5 mr-1.5" />
                        {busyDeal === d.name ? 'Opening…' : 'Fund Escrow'}
                      </Button>
                    )}
                    {d.status === 'delivered' && (
                      <Button size="sm" disabled={busyDeal === d.name} onClick={() => handleApproveRelease(d)}>
                        <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" />
                        {busyDeal === d.name ? 'Releasing…' : 'Approve & Release'}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  )
}
