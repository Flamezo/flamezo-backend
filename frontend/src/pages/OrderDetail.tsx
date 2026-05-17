import { useParams, Link } from 'react-router-dom'
import { useFrappeGetDoc, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ArrowLeft, Star, Truck, Calculator, Wallet, Clock, ChevronDown, ChevronUp, User, Zap } from 'lucide-react'
import { toast } from 'sonner'
import { useState, useEffect } from 'react'
import DeliveryMap from '@/components/DeliveryMap'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useCurrency } from '@/hooks/useCurrency'
import { cn } from '@/lib/utils'

type LogisticsProvider = 'Borzo' | 'Flash' | 'Self'

export default function OrderDetail() {
  const { formatAmount, formatAmountNoDecimals } = useCurrency()
  const { orderId } = useParams<{ orderId: string }>()
  const { data: order, isLoading } = useFrappeGetDoc('Order', orderId || '', {
    fields: ['*']
  })

  // Delivery Management collapse state
  const [deliveryPanelOpen, setDeliveryPanelOpen] = useState(true)

  // Restaurant doc — fetch logistics provider config
  const { data: restaurantDoc } = useFrappeGetDoc('Restaurant', order?.restaurant || '', {
    enabled: !!order?.restaurant,
    fields: ['name', 'tables', 'latitude', 'longitude', 'restaurant_name', 'preferred_logistics_provider']
  })

  const logisticsProvider: LogisticsProvider = (restaurantDoc?.preferred_logistics_provider || 'Flash') as LogisticsProvider
  const isSelfDelivery = logisticsProvider === 'Self'

  // Pre-set delivery mode based on restaurant logistics config
  const [deliveryMode, setDeliveryMode] = useState<'auto' | 'manual'>('manual')

  // Sync deliveryMode when restaurantDoc loads
  useEffect(() => {
    if (restaurantDoc) {
      setDeliveryMode(isSelfDelivery ? 'manual' : 'auto')
    }
  }, [restaurantDoc, isSelfDelivery])

  // Table update API call
  const { call: updateTableNumber } = useFrappePostCall('flamezo_backend.flamezo.api.order_status.update_table_number')

  const [assigningDelivery, setAssigningDelivery] = useState(false)
  const [cancellingDelivery, setCancellingDelivery] = useState(false)

  // Delivery API calls
  const { call: assignDeliveryAPI } = useFrappePostCall('flamezo_backend.flamezo.api.delivery.assign_delivery')
  const { call: cancelDeliveryAPI } = useFrappePostCall('flamezo_backend.flamezo.api.delivery.cancel_delivery')
  const [manualForm, setManualForm] = useState({ rider_name: '', rider_phone: '', eta: '' })
  const [quote, setQuote] = useState<any>(null)
  const [isQuoting, setIsQuoting] = useState(false)

  const { call: getQuoteAPI } = useFrappePostCall('flamezo_backend.flamezo.api.delivery.get_delivery_quote')

  const handleGetQuote = async () => {
    if (!order?.name) return
    setIsQuoting(true)
    try {
      const res: any = await getQuoteAPI({ order_id: order.name })
      const result = res?.message || res
      if (result?.success) {
        setQuote(result)
        toast.success('Delivery estimate fetched')
      } else {
        throw new Error(result?.error || 'Failed to fetch quote')
      }
    } catch (e: any) {
      toast.error(e.message || 'Error fetching quote')
    } finally {
      setIsQuoting(false)
    }
  }

  const handleAssignDelivery = async () => {
    if (!order?.name) return
    setAssigningDelivery(true)
    try {
      const payload: any = {
        order_id: order.name,
        delivery_mode: deliveryMode,
        // Always pass the restaurant's configured provider
        partner_name: isSelfDelivery ? 'manual' : (logisticsProvider?.toLowerCase() || 'flash'),
      }
      if (deliveryMode === 'manual') {
        payload.rider_name = manualForm.rider_name
        payload.rider_phone = manualForm.rider_phone
        payload.eta = manualForm.eta
      }

      const res = await assignDeliveryAPI(payload)
      const result = (res as any)?.message || res
      if (!result?.success) throw new Error(result?.error || 'Failed to assign delivery')

      toast.success(isSelfDelivery ? 'Rider assigned manually' : `Delivery booked via ${logisticsProvider}`)
      window.location.reload()
    } catch (e: any) {
      toast.error(e.message || 'Error occurred')
    } finally {
      setAssigningDelivery(false)
    }
  }

  const handleCancelDelivery = async () => {
    if (!order?.delivery_id && !order?.delivery_partner) return
    if (!confirm("Are you sure you want to cancel the delivery assignment?")) return
    setCancellingDelivery(true)
    try {
      const res = await cancelDeliveryAPI({
        order_id: order.name,
        delivery_id: order.delivery_id
      })
      const result = (res as any)?.message || res
      if (!result?.success) throw new Error(result?.error || 'Failed to cancel delivery')

      toast.success('Delivery cancelled successfully')
      window.location.reload()
    } catch (e: any) {
      toast.error(e.message || 'Error occurred')
    } finally {
      setCancellingDelivery(false)
    }
  }

  // Generate table options based on restaurant tables count
  const tableOptions = [0, ...(restaurantDoc?.tables ? Array.from({ length: restaurantDoc.tables }, (_, i) => i + 1) : [])]

  const handleTableNumberChange = async (newTableNumber: number) => {
    if (!order?.name) return
    try {
      await updateTableNumber({ order_id: order.name, table_number: newTableNumber })
      toast.success(`Table updated to Table ${newTableNumber}`)
      window.location.reload()
    } catch (error: any) {
      toast.error(error?.message || 'Failed to update table number')
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="text-center py-8 text-muted-foreground">Loading order details...</div>
      </div>
    )
  }

  if (!order) {
    return (
      <div className="space-y-6">
        <div className="text-center py-8">
          <p className="text-muted-foreground mb-4">Order not found</p>
          <Link to="/orders"><Button>Back to Orders</Button></Link>
        </div>
      </div>
    )
  }

  const isDeliveryAssigned = !!(order.delivery_id || order.delivery_partner)
  const isDeliveryActive = isDeliveryAssigned && order.delivery_status !== 'cancelled' && order.delivery_status !== 'delivered'
  const isManualMode = order.delivery_partner === 'manual' || order.delivery_mode === 'manual' || isSelfDelivery

  // Provider badge config
  const providerBadge = {
    Borzo: { color: 'bg-orange-100 text-orange-700 border-orange-200', icon: <Truck className="w-3.5 h-3.5" /> },
    Flash: { color: 'bg-indigo-100 text-indigo-700 border-indigo-200', icon: <Zap className="w-3.5 h-3.5" /> },
    Self:  { color: 'bg-blue-100 text-blue-700 border-blue-200',   icon: <User className="w-3.5 h-3.5" /> },
  }[logisticsProvider]

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/orders">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
        </Link>
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Order Details</h2>
          <p className="text-muted-foreground">{order.order_number || order.name}</p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Order Information</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-sm text-muted-foreground">Order ID</p>
              <p className="font-mono text-sm">{order.order_id || order.name}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Status</p>
              <span className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
                order.status === 'delivered' ? 'bg-green-100 text-green-800' :
                order.status === 'cancelled' ? 'bg-red-100 text-red-800' :
                order.status === 'pending' ? 'bg-yellow-100 text-yellow-800' :
                'bg-blue-100 text-blue-800'
              }`}>
                {order.status || 'N/A'}
              </span>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Restaurant</p>
              <p className="font-medium">{order.restaurant || 'N/A'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Order Type</p>
              <p className="font-medium capitalize">{((order.order_type || 'dine_in') as string).replace('_', ' ')}</p>
            </div>
            {tableOptions.length > 0 ? (
              <div>
                <p className="text-sm text-muted-foreground">Table Number</p>
                <Select
                  value={(order.table_number ?? 0).toString()}
                  onValueChange={(value) => {
                    const parsed = parseInt(value, 10)
                    handleTableNumberChange(Number.isNaN(parsed) ? 0 : parsed)
                  }}
                >
                  <SelectTrigger className="w-full max-w-[150px]"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {tableOptions.map((tableNum) => (
                      <SelectItem key={tableNum} value={tableNum.toString()}>Table {tableNum}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : order.table_number ? (
              <div>
                <p className="text-sm text-muted-foreground">Table Number</p>
                <span className="inline-flex items-center rounded-full px-2 py-1 text-xs font-medium bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 border border-gray-700 dark:border-gray-300">
                  Table {order.table_number}
                </span>
              </div>
            ) : null}
            <div>
              <p className="text-sm text-muted-foreground">Created</p>
              <p>{order.creation ? new Date(order.creation).toLocaleString() : 'N/A'}</p>
            </div>
            {(order.pickup_time || order.estimated_delivery) && (
              <div>
                <p className="text-sm text-muted-foreground">Timing</p>
                <p>
                  {order.pickup_time
                    ? `Pickup: ${new Date(order.pickup_time).toLocaleString()}`
                    : `ETA: ${new Date(order.estimated_delivery).toLocaleString()}`}
                </p>
              </div>
            )}
            {(order.delivery_address || order.delivery_city || order.delivery_instructions) && (
              <div>
                <p className="text-sm text-muted-foreground">Delivery Details</p>
                {order.delivery_address ? <p>{order.delivery_address}</p> : null}
                {order.delivery_landmark ? <p className="text-sm text-muted-foreground">Landmark: {order.delivery_landmark}</p> : null}
                {order.delivery_city ? <p className="text-sm text-muted-foreground">City: {order.delivery_city}</p> : null}
                {order.delivery_instructions ? <p className="text-sm text-muted-foreground">Instructions: {order.delivery_instructions}</p> : null}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Payment Summary</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between">
              <p className="text-muted-foreground">Subtotal</p>
              <p className="font-medium">{formatAmount(order.subtotal)}</p>
            </div>
            {order.discount && order.discount > 0 && (
              <div className="flex justify-between">
                <p className="text-muted-foreground">Discount</p>
                <p className="font-medium text-green-600">-{formatAmount(order.discount)}</p>
              </div>
            )}
            {order.tax && order.tax > 0 && (
              <div className="flex justify-between">
                <p className="text-muted-foreground">Tax</p>
                <p className="font-medium">{formatAmount(order.tax)}</p>
              </div>
            )}
            {order.delivery_fee && order.delivery_fee > 0 && (
              <div className="flex justify-between">
                <p className="text-muted-foreground">Delivery Fee (Customer Price)</p>
                <p className="font-medium">{formatAmount(order.delivery_fee)}</p>
              </div>
            )}
            {order.logistics_platform_fee && order.logistics_platform_fee > 0 && (
              <div className="flex justify-between">
                <p className="text-muted-foreground">Logistics Platform Fee</p>
                <p className="font-medium">{formatAmount(order.logistics_platform_fee)}</p>
              </div>
            )}
            {order.packaging_fee && order.packaging_fee > 0 && (
              <div className="flex justify-between">
                <p className="text-muted-foreground">Packaging Fee + Operation Overhead</p>
                <p className="font-medium">{formatAmount(order.packaging_fee)}</p>
              </div>
            )}
            <div className="flex justify-between border-t pt-4">
              <p className="font-semibold">Total</p>
              <p className="font-bold text-lg">{formatAmountNoDecimals(order.total)}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Delivery Management ─────────────────────────────────────────────── */}
      {order.order_type === 'delivery' && (
        <Card>
          {/* Collapsible Header */}
          <CardHeader
            className="cursor-pointer select-none"
            onClick={() => setDeliveryPanelOpen(prev => !prev)}
          >
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Truck className="h-5 w-5 text-primary" />
                Delivery Management
                {/* Provider badge from restaurant config */}
                {restaurantDoc && (
                  <span className={cn(
                    'ml-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold border uppercase tracking-wide',
                    providerBadge.color
                  )}>
                    {providerBadge.icon}
                    {logisticsProvider}
                  </span>
                )}
              </CardTitle>
              <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0">
                {deliveryPanelOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </Button>
            </div>
          </CardHeader>

          {deliveryPanelOpen && (
            <CardContent className="space-y-4">

              {/* ── Not yet assigned ─────────────────────────────────────── */}
              {!order.delivery_id && order.status !== 'cancelled' && (
                <div className="p-4 bg-muted/50 rounded-lg border space-y-4">

                  {/* Provider info row */}
                  <div className="flex items-center gap-3 pb-2 border-b">
                    <span className="text-sm text-muted-foreground">Active Logistics Config:</span>
                    <span className={cn(
                      'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold border',
                      providerBadge.color
                    )}>
                      {providerBadge.icon}
                      {isSelfDelivery ? 'Self / Own Riders (Manual)' : `${logisticsProvider} — Flamezo Managed`}
                    </span>
                  </div>

                  {/* ── SELF / MANUAL DELIVERY UI ──────────────────────── */}
                  {isSelfDelivery && (
                    <div className="space-y-4">
                      <p className="text-sm text-muted-foreground">
                        Assign your own rider's details below. No API dispatch. No coins deducted.
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Rider Name</label>
                          <input
                            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-primary"
                            value={manualForm.rider_name}
                            onChange={e => setManualForm({ ...manualForm, rider_name: e.target.value })}
                            placeholder="e.g. Rahul Kumar"
                          />
                        </div>
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Rider Phone</label>
                          <input
                            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-primary"
                            value={manualForm.rider_phone}
                            onChange={e => setManualForm({ ...manualForm, rider_phone: e.target.value })}
                            placeholder="e.g. 9987654321"
                          />
                        </div>
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">ETA (mins)</label>
                          <input
                            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-primary"
                            value={manualForm.eta}
                            onChange={e => setManualForm({ ...manualForm, eta: e.target.value })}
                            placeholder="e.g. 30"
                          />
                        </div>
                      </div>
                      <div className="flex justify-end">
                        <Button
                          onClick={handleAssignDelivery}
                          disabled={assigningDelivery}
                          className="font-black uppercase text-xs tracking-widest bg-blue-600 hover:bg-blue-700"
                        >
                          <User className="h-4 w-4 mr-2" />
                          {assigningDelivery ? 'Assigning...' : 'Assign Delivery'}
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* ── INTEGRATED (Borzo / Flash) DELIVERY UI ─────────── */}
                  {!isSelfDelivery && (
                    <div className="space-y-4">
                      {!quote ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          className="w-full bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200/50 dark:bg-emerald-950/20 dark:text-emerald-400 dark:hover:bg-emerald-900/30"
                          onClick={handleGetQuote}
                          disabled={isQuoting}
                        >
                          <Calculator className="h-4 w-4 mr-2" />
                          {isQuoting ? 'Fetching Estimate...' : `Get ${logisticsProvider} Delivery Estimate`}
                        </Button>
                      ) : (
                        <div className="bg-gradient-to-br from-indigo-50 to-blue-50 dark:from-indigo-950/20 dark:to-blue-950/20 border border-indigo-100 dark:border-indigo-900/50 rounded-xl p-4 shadow-sm">
                          <div className="flex justify-between items-start mb-4">
                            <div className="flex items-center gap-2">
                              <Wallet className="h-4 w-4 text-indigo-600" />
                              <span className="text-xs font-black uppercase text-indigo-600 tracking-wider">
                                {quote.provider || logisticsProvider} Estimate
                              </span>
                            </div>
                            <Button variant="ghost" size="sm" className="h-6 text-[10px]" onClick={() => setQuote(null)}>Reset</Button>
                          </div>

                          <div className="grid grid-cols-2 gap-4 mb-4">
                            <div className="p-3 bg-white/50 dark:bg-black/20 rounded-lg border border-indigo-100/50">
                              <p className="text-[10px] font-bold text-indigo-600/70 uppercase mb-1">Base Courier</p>
                              <p className="text-lg font-black">{formatAmount(quote.courier_fee)}</p>
                            </div>
                            <div className="p-3 bg-white/50 dark:bg-black/20 rounded-lg border border-indigo-100/50">
                              <p className="text-[10px] font-bold text-indigo-600/70 uppercase mb-1">Merchant Markup</p>
                              <p className="text-lg font-black text-emerald-600">+{formatAmount(quote.markup)}</p>
                            </div>
                          </div>

                          <div className="flex justify-between items-end border-t border-indigo-100 pt-3 mt-3">
                            <div>
                              <p className="text-3xl font-black tracking-tighter text-indigo-900 dark:text-indigo-100">
                                {formatAmountNoDecimals(quote.delivery_fee)}
                              </p>
                              <p className="text-[10px] font-bold text-indigo-600/70 mt-1 uppercase tracking-widest leading-none">Total Customer Price</p>
                            </div>
                            <div className="text-right">
                              <p className="text-xs font-bold text-indigo-800 dark:text-indigo-200 mb-1">Incl. Platform Fee</p>
                              <div className="flex items-center gap-1 justify-end text-emerald-600">
                                <Clock className="h-3 w-3" />
                                <span className="text-[10px] font-black uppercase tracking-tight">{quote.eta_mins || 30} Mins ETA</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      <div className="flex justify-end">
                        <Button
                          onClick={handleAssignDelivery}
                          disabled={assigningDelivery || !quote}
                          className="font-black uppercase text-xs tracking-widest bg-indigo-600 hover:bg-indigo-700"
                        >
                          <Zap className="h-4 w-4 mr-2" />
                          {assigningDelivery
                            ? 'Booking...'
                            : `Confirm & Book ${quote?.provider || logisticsProvider}`}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ── Already assigned ─────────────────────────────────────── */}
              {isDeliveryAssigned && (
                <div className="space-y-4">
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 bg-muted/50 rounded-lg border">
                    <div>
                      <p className="font-semibold capitalize flex items-center gap-2">
                        {isManualMode
                          ? <><User className="w-4 h-4 text-blue-600" /> Self / Manual Delivery</>
                          : <><Zap className="w-4 h-4 text-indigo-600" /> {order.delivery_partner} Delivery</>
                        }
                      </p>

                      {!isManualMode && order.delivery_id && (
                        <p className="text-sm text-muted-foreground font-mono mt-1">
                          ID: {order.delivery_id} | Status:{' '}
                          <span className="font-semibold text-primary">{order.delivery_status}</span>
                        </p>
                      )}
                      {isManualMode && (
                        <p className="text-sm text-muted-foreground mt-1">
                          Status:{' '}
                          <span className="font-semibold text-primary">{order.delivery_status || 'Assigned'}</span>
                        </p>
                      )}
                      {order.delivery_eta && (
                        <p className="text-sm text-muted-foreground mt-1">ETA: {order.delivery_eta}</p>
                      )}
                      {order.delivery_rider_name && (
                        <div className="mt-2 text-sm bg-blue-50 dark:bg-blue-900/20 p-2 rounded border border-blue-100 dark:border-blue-900/50">
                          🛵 Rider: <span className="font-semibold">{order.delivery_rider_name}</span>{' '}
                          {order.delivery_rider_phone && `(${order.delivery_rider_phone})`}
                        </div>
                      )}
                    </div>

                    <div className="flex flex-col gap-2 w-full sm:w-auto">
                      {!isManualMode && order.delivery_tracking_url && isDeliveryActive && (
                        <Button variant="outline" asChild className="w-full sm:w-auto">
                          <a href={order.delivery_tracking_url} target="_blank" rel="noopener noreferrer">
                            Track Rider
                          </a>
                        </Button>
                      )}
                      {isDeliveryActive && (
                        <Button
                          variant="destructive"
                          onClick={handleCancelDelivery}
                          disabled={cancellingDelivery}
                          className="w-full sm:w-auto"
                        >
                          {cancellingDelivery ? 'Cancelling...' : 'Cancel Assignment'}
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* Live Map — only for integrated providers */}
                  {!isManualMode && (order.delivery_latitude || order.delivery_location_pin || order.rider_latitude) && (
                    <DeliveryMap
                      restaurantName={restaurantDoc?.restaurant_name || restaurantDoc?.name}
                      pickupLocation={restaurantDoc?.latitude && restaurantDoc?.longitude ? {
                        lat: parseFloat(restaurantDoc.latitude),
                        lng: parseFloat(restaurantDoc.longitude)
                      } : undefined}
                      dropLocation={order.delivery_latitude && order.delivery_longitude ? {
                        lat: parseFloat(order.delivery_latitude),
                        lng: parseFloat(order.delivery_longitude)
                      } : order.delivery_location_pin && String(order.delivery_location_pin).includes(',') ? {
                        lat: parseFloat(String(order.delivery_location_pin).split(',')[0]),
                        lng: parseFloat(String(order.delivery_location_pin).split(',')[1])
                      } : undefined}
                      riderLocation={order.rider_latitude && order.rider_longitude ? {
                        lat: parseFloat(order.rider_latitude),
                        lng: parseFloat(order.rider_longitude)
                      } : undefined}
                      riderLastUpdated={order.rider_last_updated}
                    />
                  )}
                </div>
              )}
            </CardContent>
          )}
        </Card>
      )}

      {/* ── Customer Feedback ─────────────────────────────────────────────── */}
      {((order as any).customer_rating != null || (order as any).food_rating != null || (order as any).service_rating != null || !!((order as any).customer_feedback && String((order as any).customer_feedback).trim())) && (
        <Card>
          <CardHeader><CardTitle>Customer Feedback</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-6">
              {((order as any).food_rating ?? (order as any).customer_rating) != null && (
                <div>
                  <p className="text-sm text-muted-foreground">Food Rating</p>
                  <span className="flex items-center gap-1">
                    <Star className="h-5 w-5 fill-amber-400 text-amber-400" />
                    {(order as any).food_rating ?? (order as any).customer_rating}/5
                  </span>
                </div>
              )}
              {(order as any).service_rating != null && (
                <div>
                  <p className="text-sm text-muted-foreground">Service Rating</p>
                  <span className="flex items-center gap-1">
                    <Star className="h-5 w-5 fill-amber-400 text-amber-400" />
                    {(order as any).service_rating}/5
                  </span>
                </div>
              )}
            </div>
            {(order as any).customer_feedback && (
              <div>
                <p className="text-sm text-muted-foreground">Feedback</p>
                <p className="text-sm">{(order as any).customer_feedback}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Order Items ───────────────────────────────────────────────────── */}
      {order.order_items && order.order_items.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Order Items</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-4">
              {order.order_items.map((item: any, index: number) => (
                <div key={index} className="flex justify-between items-center border-b pb-4 last:border-0">
                  <div>
                    <p className="font-medium">{item.product_name || item.product || 'N/A'}</p>
                    <p className="text-sm text-muted-foreground">Quantity: {item.quantity || 1}</p>
                    {item.unit_price && (
                      <p className="text-sm text-muted-foreground">Unit Price: {formatAmount(item.unit_price)}</p>
                    )}
                  </div>
                  <p className="font-medium">{formatAmount(item.total_price || item.unit_price)}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
