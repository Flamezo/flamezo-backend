import { useFrappeGetDoc, useFrappePostCall, useFrappeEventListener } from '@/lib/frappe'
import { usePrint } from '@/hooks/usePrint'
import { useRestaurant } from '@/contexts/RestaurantContext'
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { useCurrency } from '@/hooks/useCurrency'
import {
  ShoppingBag,
  Clock,
  User,
  CreditCard,
  MapPin,
  Truck,
  HelpCircle,
  Copy,
  CheckCircle2,
  AlertCircle,
  Calendar,
  Hash,
  ArrowRight,
  Loader2,
  Plus,
  Minus,
  Trash2,
  Edit3,
  Search,
  X,
  Save,
  ChevronDown,
  ChevronUp,
  Zap
} from 'lucide-react'
import { useState, useMemo, useEffect } from 'react'
import { toast } from 'sonner'
import { getFrappeError, cn, copyToClipboard } from '@/lib/utils'
import DeliveryMap from './DeliveryMap'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { useFrappeGetDocList } from '@/lib/frappe'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'

interface OrderDetailsDialogProps {
  orderId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  startInEditMode?: boolean
}

export function OrderDetailsDialog({ orderId, open, onOpenChange, startInEditMode }: OrderDetailsDialogProps) {
  const { formatAmount, formatAmountNoDecimals } = useCurrency()
  const [copied, setCopied] = useState(false)
  const { print } = usePrint()
  const { restaurantConfig } = useRestaurant()
  const selectedRestaurant = restaurantConfig?.restaurant?.name

  // Editing State
  const [isEditing, setIsEditing] = useState(false)
  const [editItems, setEditItems] = useState<any[]>([])
  const [isSaving, setIsSaving] = useState(false)
  const [showProductSearch, setShowProductSearch] = useState(false)
  const [productSearchTerm, setProductSearchTerm] = useState('')
  const [selectedProductForCustomization, setSelectedProductForCustomization] = useState<any>(null)
  const [tempCustomizations, setTempCustomizations] = useState<Record<string, any>>({})

  const { data: order, isLoading, mutate } = useFrappeGetDoc('Order', orderId || '', {
    fields: ['*'],
    enabled: open && !!orderId
  })

  // Listen for real-time order updates
  useFrappeEventListener('order_update', (data: any) => {
    if (data.order_id === orderId) {
      mutate()
    }
  })

  const [assigningDelivery, setAssigningDelivery] = useState(false)
  const [cancellingDelivery, setCancellingDelivery] = useState(false)
  const [progressingDelivery, setProgressingDelivery] = useState(false)
  const [deliveryMode, setDeliveryMode] = useState<'auto' | 'manual'>('manual')
  const [manualForm, setManualForm] = useState({ rider_name: '', rider_phone: '', eta: '' })
  const [deliveryPanelOpen, setDeliveryPanelOpen] = useState(true)
  const [isEditingRiderInfo, setIsEditingRiderInfo] = useState(false)
  const [editRiderForm, setEditRiderForm] = useState({ rider_name: '', rider_phone: '', eta: '' })

  // Fetch restaurant logistics config
  const { data: restaurantDoc } = useFrappeGetDoc(
    'Restaurant',
    restaurantConfig?.restaurant?.name || '',
    restaurantConfig?.restaurant?.name
      ? `DeliveryDialog-Restaurant-${restaurantConfig.restaurant.name}`
      : null
  )
  const logisticsProvider: 'Borzo' | 'Flash' | 'Self' =
    (restaurantDoc?.preferred_logistics_provider || 'Flash') as any
  const isSelfDelivery = logisticsProvider === 'Self'

  useEffect(() => {
    if (restaurantDoc) {
      setDeliveryMode(isSelfDelivery ? 'manual' : 'auto')
    }
  }, [restaurantDoc, isSelfDelivery])

  const providerBadge = {
    Borzo: { color: 'bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-950/30 dark:text-orange-400 dark:border-orange-900', icon: <Truck className="w-3 h-3" /> },
    Flash: { color: 'bg-indigo-100 text-indigo-700 border-indigo-200 dark:bg-indigo-950/30 dark:text-indigo-400 dark:border-indigo-900', icon: <Zap className="w-3 h-3" /> },
    Self: { color: 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-900', icon: <User className="w-3 h-3" /> },
  }[logisticsProvider]

  const { call: assignDeliveryAPI } = useFrappePostCall('flamezo_backend.flamezo.api.delivery.assign_delivery')
  const { call: cancelDeliveryAPI } = useFrappePostCall('flamezo_backend.flamezo.api.delivery.cancel_delivery')
  const { call: updateOrderItemsAPI } = useFrappePostCall('flamezo_backend.flamezo.api.orders.update_order_items')
  const { call: updateDeliveryInfoAPI } = useFrappePostCall('flamezo_backend.flamezo.api.delivery.update_delivery_info')
  const { call: markSelfDeliveryStatusAPI } = useFrappePostCall('flamezo_backend.flamezo.api.delivery.mark_self_delivery_status')

  // Product List for Search
  const { data: allProductsData } = useFrappeGetDocList(
    'Menu Product',
    {
      fields: ['product_id', 'product_name', 'category_name', 'price', 'main_category', 'customization_questions'],
      filters: selectedRestaurant ? ({ restaurant: selectedRestaurant, is_active: 1 } as any) : undefined,
      limit: 500,
      orderBy: { field: 'product_name', order: 'asc' } as any
    },
    (open && isEditing) ? `edit-order-products-${selectedRestaurant}` : null
  )

  const allProducts = (allProductsData as any[]) || []

  const filteredSearchProducts = useMemo(() => {
    if (!productSearchTerm.trim()) return allProducts.slice(0, 10)
    const term = productSearchTerm.toLowerCase()
    return allProducts.filter(p =>
      p.product_name.toLowerCase().includes(term) ||
      p.product_id.toLowerCase().includes(term) ||
      (p.category_name || '').toLowerCase().includes(term)
    ).slice(0, 50)
  }, [allProducts, productSearchTerm])

  const handleStartEdit = () => {
    if (!order) return
    setIsEditing(true)
    const items = (order.order_items || []).map((i: any) => ({
      ...i,
      dishId: i.product,
      product_name: i.product_name,
      customizations: parseCustomizations(i.customizations)
    }))
    setEditItems(items)
  }

  useEffect(() => {
    if (open && startInEditMode && order) {
      handleStartEdit()
    }
  }, [open, startInEditMode, !!order])

  const handleCancelEdit = () => {
    setIsEditing(false)
    setEditItems([])
    setShowProductSearch(false)
    setSelectedProductForCustomization(null)
  }

  const handleQuantityChange = (index: number, delta: number) => {
    setEditItems(prev => {
      const updated = [...prev]
      const newQty = Math.max(1, (updated[index].quantity || 1) + delta)
      updated[index] = { ...updated[index], quantity: newQty }
      return updated
    })
  }

  const handleRemoveItem = (index: number) => {
    setEditItems(prev => prev.filter((_, i) => i !== index))
  }

  const handleAddProduct = (product: any) => {
    // If product has customizations, show customization selection
    if (product.customization_questions && JSON.parse(product.customization_questions || '[]').length > 0) {
      setSelectedProductForCustomization(product)
      // Initialize default customizations
      const defaultCusts: Record<string, any> = {}
      const questions = JSON.parse(product.customization_questions || '[]')
      questions.forEach((q: any) => {
        const defaultOps = q.options?.filter((o: any) => o.is_default).map((o: any) => o.option_id) || []
        if (defaultOps.length > 0) {
          defaultCusts[q.question_id] = q.question_type === 'single' ? defaultOps[0] : defaultOps
        }
      })
      setTempCustomizations(defaultCusts)
    } else {
      // Add directly
      setEditItems(prev => [
        ...prev,
        {
          dishId: product.product_id,
          product_name: product.product_name,
          quantity: 1,
          unitPrice: product.price,
          customizations: {}
        }
      ])
      setShowProductSearch(false)
      setProductSearchTerm('')
      toast.success(`${product.product_name} added to order`)
    }
  }

  const handleConfirmCustomization = () => {
    if (!selectedProductForCustomization) return

    setEditItems(prev => [
      ...prev,
      {
        dishId: selectedProductForCustomization.product_id,
        product_name: selectedProductForCustomization.product_name,
        quantity: 1,
        unitPrice: selectedProductForCustomization.price,
        customizations: tempCustomizations
      }
    ])

    setSelectedProductForCustomization(null)
    setTempCustomizations({})
    setShowProductSearch(false)
    setProductSearchTerm('')
    toast.success(`${selectedProductForCustomization.product_name} added with customizations`)
  }

  const handleSaveOrder = async () => {
    if (!orderId || !selectedRestaurant) return
    if (editItems.length === 0) {
      toast.error('Order must have at least one item')
      return
    }

    setIsSaving(true)
    try {
      const res = await updateOrderItemsAPI({
        order_id: orderId,
        items: JSON.stringify(editItems),
        restaurant_id: selectedRestaurant
      })

      const result = (res as any)?.message || res
      if (!result?.success) throw new Error(result?.error || 'Failed to update order items')

      toast.success('Order updated successfully')
      mutate()
      setIsEditing(false)
    } catch (e: any) {
      toast.error('Failed to update order', { description: getFrappeError(e) })
    } finally {
      setIsSaving(false)
    }
  }

  const handleAssignDelivery = async () => {
    if (!order?.name) return
    setAssigningDelivery(true)
    try {
      const payload: any = {
        order_id: order.name,
        delivery_mode: deliveryMode,
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
      mutate()
    } catch (e: any) {
      toast.error('Failed to assign delivery', { description: getFrappeError(e) })
    } finally {
      setAssigningDelivery(false)
    }
  }

  const handleCancelDelivery = async () => {
    if (!order?.delivery_id && !order?.delivery_partner) return
    if (!confirm("Are you sure you want to cancel the delivery assignment?")) return;
    setCancellingDelivery(true)
    try {
      const res = await cancelDeliveryAPI({
        order_id: order.name,
        delivery_id: order.delivery_id
      })
      const result = (res as any)?.message || res
      if (!result?.success) throw new Error(result?.error || 'Failed to cancel delivery')

      toast.success('Delivery cancelled successfully')
      mutate()
    } catch (e: any) {
      toast.error('Failed to cancel delivery', { description: getFrappeError(e) })
    } finally {
      setCancellingDelivery(false)
    }
  }

  const handleSelfDeliveryProgress = async (newStatus: 'DISPATCHED' | 'DELIVERED') => {
    if (!order?.name) return
    const label = newStatus === 'DISPATCHED' ? 'Mark as Picked Up' : 'Mark as Delivered'
    if (!confirm(`${label}? This will update the customer tracking status.`)) return
    setProgressingDelivery(true)
    try {
      const res = await markSelfDeliveryStatusAPI({ order_id: order.name, new_status: newStatus })
      const result = (res as any)?.message || res
      if (!result?.success) throw new Error(result?.error || 'Failed to update status')
      toast.success(newStatus === 'DELIVERED' ? '✅ Order marked as Delivered!' : '🛵 Marked as Picked Up')
      mutate()
    } catch (e: any) {
      toast.error('Failed to update delivery status', { description: getFrappeError(e) })
    } finally {
      setProgressingDelivery(false)
    }
  }

  const handleUpdateRiderInfo = async () => {
    if (!order?.name) return
    try {
      const res = await updateDeliveryInfoAPI({
        order_id: order.name,
        rider_name: editRiderForm.rider_name || undefined,
        rider_phone: editRiderForm.rider_phone || undefined,
        eta: editRiderForm.eta || undefined,
      })
      const result = (res as any)?.message || res
      if (!result?.success) throw new Error(result?.error || 'Failed to update rider info')
      toast.success('Rider info updated')
      setIsEditingRiderInfo(false)
      mutate()
    } catch (e: any) {
      toast.error('Failed to update rider info', { description: getFrappeError(e) })
    }
  }

  // Fetch coupon details if coupon is applied
  const { data: coupon } = useFrappeGetDoc('Coupon', order?.coupon || '', {
    fields: ['code', 'discount_type', 'discount_value', 'description', 'detailed_description'],
    enabled: open && !!order?.coupon
  })

  const restaurantInfo = restaurantConfig?.restaurant || {}

  if (!orderId) return null

  const handleCopyId = async () => {
    if (orderId) {
      const success = await copyToClipboard(orderId)
      if (success) {
        setCopied(true)
        toast.success('Order ID copied to clipboard')
        setTimeout(() => setCopied(false), 2000)
      } else {
        toast.error('Failed to copy ID')
      }
    }
  }

  const getStatusConfig = (status: string, deliveryStatus?: string, orderType?: string) => {
    // Prioritize delivery status if it's a delivery order and we have a granular status
    if (orderType === 'delivery' && deliveryStatus) {
      const dStatus = deliveryStatus.toLowerCase()
      if (dStatus === 'cancelled') {
        return { color: 'text-red-600 bg-red-50 border-red-200 dark:bg-red-900/30 dark:border-red-800 dark:text-red-400', icon: AlertCircle, label: 'Delivery Cancelled' }
      }
      if (dStatus === 'delivered' || dStatus === 'completed') {
        return { color: 'text-green-600 bg-green-50 border-green-200 dark:bg-green-900/30 dark:border-green-800 dark:text-green-400', icon: CheckCircle2, label: 'Delivered' }
      }
      // For active delivery statuses (assigned, departed, etc.)
      return {
        color: 'text-primary bg-primary/5 border-primary/20 dark:bg-primary/10 dark:border-primary/30',
        icon: Truck,
        label: deliveryStatus
      }
    }

    const s = status?.toLowerCase()
    switch (s) {
      case 'delivered':
      case 'billed':
        return { color: 'text-green-600 bg-green-50 border-green-200 dark:bg-green-900/30 dark:border-green-800 dark:text-green-400', icon: CheckCircle2, label: 'Completed' }
      case 'cancelled':
        return { color: 'text-red-600 bg-red-50 border-red-200 dark:bg-red-900/30 dark:border-red-800 dark:text-red-400', icon: AlertCircle, label: 'Cancelled' }
      case 'pending verification':
      case 'pending_verification':
        return { color: 'text-amber-600 bg-amber-50 border-amber-200 dark:bg-amber-900/30 dark:border-amber-800 dark:text-amber-400', icon: Clock, label: 'Verifying' }
      case 'preparing':
        return { color: 'text-purple-600 bg-purple-50 border-purple-200 dark:bg-purple-900/30 dark:border-purple-800 dark:text-purple-400', icon: Loader2, label: 'Preparing' }
      case 'ready':
        return { color: 'text-blue-600 bg-blue-50 border-blue-200 dark:bg-blue-900/30 dark:border-blue-800 dark:text-blue-400', icon: ArrowRight, label: 'Ready for Pickup' }
      default:
        return { color: 'text-gray-600 bg-gray-50 border-gray-200 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-400', icon: HelpCircle, label: status }
    }
  }

  const parseCustomizations = (customizations: string | object | null) => {
    if (!customizations) return {}
    if (typeof customizations === 'string') {
      try {
        return JSON.parse(customizations)
      } catch {
        return {}
      }
    }
    return customizations
  }

  const statusConfig = getStatusConfig(order?.status || '', order?.delivery_status, order?.order_type)
  const StatusIcon = statusConfig.icon

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto p-0 border-none bg-slate-50 dark:bg-zinc-950 gap-0">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 space-y-4">
            <DialogTitle className="sr-only">Order Information Fetching</DialogTitle>
            <DialogDescription className="sr-only">We are retrieving the latest order status and items.</DialogDescription>
            <div className="w-10 h-10 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
            <p className="text-sm font-medium text-muted-foreground italic">Fetching order details...</p>
          </div>
        ) : order ? (
          <div className="flex flex-col h-full bg-white dark:bg-zinc-900 shadow-xl overflow-hidden">
            <DialogTitle className="sr-only">{order?.order_number || order?.name} Details</DialogTitle>
            <DialogDescription className="sr-only">Comprehensive view of order summary, items, and delivery status.</DialogDescription>
            {/* Enterprise Header */}
            <div className="px-6 py-6 border-b bg-white dark:bg-zinc-900 sticky top-0 z-10">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60 flex items-center gap-1">
                      <Hash className="w-3 h-3" />
                      Order Identification
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-2xl font-display font-black tracking-tight text-foreground">
                      {order?.order_number || order?.name}
                    </h2>
                    <button
                      onClick={handleCopyId}
                      className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors text-muted-foreground"
                      title="Copy Order ID"
                    >
                      {copied ? <CheckCircle2 className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <div className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border-2 font-bold text-xs uppercase tracking-wider shadow-sm ${statusConfig.color}`}>
                    <StatusIcon className="w-4 h-4" />
                    {statusConfig.label}
                  </div>

                  {!isEditing && order?.status !== 'cancelled' && order?.status !== 'billed' && order?.status !== 'delivered' && (
                    <Button
                      variant="outline"
                      onClick={handleStartEdit}
                      className="rounded-xl border-2 font-black text-[10px] uppercase h-8 px-3"
                    >
                      <Edit3 className="w-3.5 h-3.5 mr-1" />
                      Edit Order
                    </Button>
                  )}
                </div>
              </div>
            </div>

            <div className="p-6 space-y-8 overflow-y-auto bg-slate-50/50 dark:bg-zinc-950/20">
              {/* Info Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-white dark:bg-zinc-900 p-4 rounded-2xl border border-gray-100 dark:border-zinc-800 shadow-sm transition-all hover:shadow-md">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="p-1.5 rounded-lg bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400">
                      <ShoppingBag className="w-4 h-4" />
                    </div>
                    <span className="text-[10px] font-black uppercase tracking-tighter text-muted-foreground">Order Type</span>
                  </div>
                  <p className="text-sm font-bold capitalize">{(order.order_type || 'dine_in').replace('_', ' ')}</p>
                  {order.order_type === 'dine_in' && (order.table_number !== undefined && order.table_number !== null) && (
                    <p className="text-xs text-muted-foreground mt-1 font-mono bg-gray-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded inline-block">Table No. {order.table_number}</p>
                  )}
                  {order.order_type === 'takeaway' && (
                    <p className="text-[10px] text-muted-foreground mt-1 font-bold uppercase tracking-tighter bg-blue-50 dark:bg-blue-900/20 text-blue-600 px-1.5 py-0.5 rounded inline-block">Self Pickup</p>
                  )}
                  {order.order_type === 'delivery' && (
                    <p className="text-[10px] text-muted-foreground mt-1 font-bold uppercase tracking-tighter bg-orange-50 dark:bg-orange-900/20 text-orange-600 px-1.5 py-0.5 rounded inline-block">Doorstep Delivery</p>
                  )}
                </div>

                <div className="bg-white dark:bg-zinc-900 p-4 rounded-2xl border border-gray-100 dark:border-zinc-800 shadow-sm transition-all hover:shadow-md">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="p-1.5 rounded-lg bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
                      <Calendar className="w-4 h-4" />
                    </div>
                    <span className="text-[10px] font-black uppercase tracking-tighter text-muted-foreground">Timing</span>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs flex items-center justify-between">
                      <span className="text-muted-foreground">Placed:</span>
                      <span className="font-bold">{new Date(order.creation).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    </p>
                    {order.pickup_time && (
                      <p className="text-xs flex items-center justify-between">
                        <span className="text-muted-foreground">Pickup:</span>
                        <span className="font-bold">{new Date(order.pickup_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      </p>
                    )}
                  </div>
                </div>

                <div className="bg-white dark:bg-zinc-900 p-4 rounded-2xl border border-gray-100 dark:border-zinc-800 shadow-sm transition-all hover:shadow-md">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="p-1.5 rounded-lg bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400">
                      <User className="w-4 h-4" />
                    </div>
                    <span className="text-[10px] font-black uppercase tracking-tighter text-muted-foreground">Customer</span>
                  </div>
                  <p className="text-sm font-bold truncate">{order.customer_name || 'Guest User'}</p>
                  <p className="text-xs text-muted-foreground mt-1 font-mono tracking-tighter">{order.customer_phone || 'No phone'}</p>
                </div>
              </div>

              {/* Delivery Details Section (If applicable) */}
              {order.order_type === 'delivery' && (
                <div className="bg-white dark:bg-zinc-900 rounded-2xl border border-gray-100 dark:border-zinc-800 overflow-hidden shadow-sm">
                  {/* Collapsible Header */}
                  <div
                    className="px-4 py-3 border-b bg-gray-50/50 dark:bg-zinc-800/30 flex items-center justify-between cursor-pointer select-none"
                    onClick={() => setDeliveryPanelOpen(prev => !prev)}
                  >
                    <div className="flex items-center gap-2">
                      <Truck className="w-4 h-4 text-primary" />
                      <h3 className="text-xs font-black uppercase tracking-widest">Delivery Management</h3>
                      {/* Provider badge */}
                      <span className={cn(
                        'ml-1 inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[9px] font-bold border uppercase tracking-wide',
                        providerBadge.color
                      )}>
                        {providerBadge.icon}
                        {logisticsProvider}
                      </span>
                    </div>
                    <button className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors">
                      {deliveryPanelOpen
                        ? <ChevronUp className="w-4 h-4" />
                        : <ChevronDown className="w-4 h-4" />}
                    </button>
                  </div>

                  {deliveryPanelOpen && (
                    <div className="p-4 space-y-4">
                      {!order.delivery_id && order.status !== 'cancelled' && (
                        <div className="p-4 bg-slate-50 dark:bg-zinc-800/50 rounded-xl border-2 border-dashed border-zinc-200 dark:border-zinc-700 space-y-4">
                          {/* Provider info row */}
                          <div className="flex items-center gap-2 pb-2 border-b border-zinc-200 dark:border-zinc-700">
                            <span className="text-[10px] text-muted-foreground font-medium">Config:</span>
                            <span className={cn(
                              'inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[9px] font-bold border uppercase tracking-wide',
                              providerBadge.color
                            )}>
                              {providerBadge.icon}
                              {isSelfDelivery ? 'Self / Own Riders' : `${logisticsProvider} — Managed`}
                            </span>
                          </div>

                          {/* ── SELF / MANUAL UI ── */}
                          {isSelfDelivery && (
                            <div className="space-y-3">
                              <p className="text-[10px] text-muted-foreground">Assign your own rider. No API dispatch. No wallet balance deducted.</p>
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                <div className="space-y-1">
                                  <label className="text-[10px] font-black uppercase text-muted-foreground">Rider Name</label>
                                  <input className="flex h-8 w-full rounded-lg border border-input bg-transparent px-3 py-1 text-xs shadow-sm focus:outline-none focus:ring-1 focus:ring-primary" value={manualForm.rider_name} onChange={e => setManualForm({ ...manualForm, rider_name: e.target.value })} placeholder="Rider Name" />
                                </div>
                                <div className="space-y-1">
                                  <label className="text-[10px] font-black uppercase text-muted-foreground">Rider Phone</label>
                                  <input className="flex h-8 w-full rounded-lg border border-input bg-transparent px-3 py-1 text-xs shadow-sm focus:outline-none focus:ring-1 focus:ring-primary" value={manualForm.rider_phone} onChange={e => setManualForm({ ...manualForm, rider_phone: e.target.value })} placeholder="Rider Phone" />
                                </div>
                                <div className="space-y-1">
                                  <label className="text-[10px] font-black uppercase text-muted-foreground">ETA (mins)</label>
                                  <input className="flex h-8 w-full rounded-lg border border-input bg-transparent px-3 py-1 text-xs shadow-sm focus:outline-none focus:ring-1 focus:ring-primary" value={manualForm.eta} onChange={e => setManualForm({ ...manualForm, eta: e.target.value })} placeholder="e.g. 30" />
                                </div>
                              </div>
                              <div className="flex justify-end">
                                <Button size="sm" onClick={handleAssignDelivery} disabled={assigningDelivery} className="h-8 text-xs font-bold uppercase tracking-wider bg-blue-600 hover:bg-blue-700">
                                  <User className="w-3.5 h-3.5 mr-1.5" />
                                  {assigningDelivery ? 'Assigning...' : 'Assign Delivery'}
                                </Button>
                              </div>
                            </div>
                          )}

                          {/* ── BORZO / FLASH INTEGRATED UI ── */}
                          {!isSelfDelivery && (
                            <div className="space-y-3">
                              <div className="flex justify-end">
                                <Button
                                  size="sm"
                                  onClick={handleAssignDelivery}
                                  disabled={assigningDelivery}
                                  className="h-8 text-xs font-bold uppercase tracking-wider bg-indigo-600 hover:bg-indigo-700"
                                >
                                  <Zap className="w-3.5 h-3.5 mr-1.5" />
                                  {assigningDelivery ? 'Booking...' : `Book via ${logisticsProvider}`}
                                </Button>
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {(order.delivery_id || order.delivery_partner) && (
                        <div className="flex flex-col gap-4 p-4 bg-slate-50 dark:bg-zinc-800/50 rounded-xl border border-zinc-100 dark:border-zinc-800">
                          <div className="flex items-start justify-between">
                            <div>
                              <p className="text-xs font-black uppercase tracking-tighter text-muted-foreground mb-1">Assigned Partner</p>
                              <p className="text-sm font-bold flex items-center gap-1.5">
                                {order.delivery_partner === 'borzo' ? <><Truck className="w-3.5 h-3.5" /> Borzo Delivery</> :
                                  order.delivery_partner === 'flash' ? <><Zap className="w-3.5 h-3.5 text-indigo-600" /> Flash Delivery</> :
                                    order.delivery_partner === 'manual' || order.delivery_mode === 'manual' ? <><User className="w-3.5 h-3.5 text-blue-600" /> Manual Delivery</> :
                                      'Unassigned'}
                              </p>

                              {order.delivery_id && order.delivery_partner !== 'manual' && order.delivery_mode !== 'manual' && (
                                <p className="text-[10px] font-mono mt-1 bg-gray-100 dark:bg-zinc-700 px-1.5 py-0.5 rounded inline-block">
                                  ID: {order.delivery_id} | Status: <span className="font-bold text-primary">{order.delivery_status}</span>
                                </p>
                              )}
                              {(order.delivery_partner === 'manual' || order.delivery_mode === 'manual') && (
                                <p className="text-[10px] font-bold mt-1 bg-gray-100 dark:bg-zinc-700 px-1.5 py-0.5 rounded inline-block">
                                  Status: <span className="text-primary">{order.delivery_status || 'Assigned'}</span>
                                </p>
                              )}
                              {order.delivery_eta && (
                                <p className="text-[10px] font-bold text-muted-foreground mt-1">ETA: {order.delivery_eta} mins</p>
                              )}
                            </div>

                            <div className="flex flex-col gap-2 items-end">
                              {order.delivery_status !== 'cancelled' && order.delivery_status !== 'DELIVERED' && order.delivery_status !== 'delivered' && (
                                <Button size="sm" variant="destructive" onClick={handleCancelDelivery} disabled={cancellingDelivery} className="h-7 text-[10px] font-bold uppercase">
                                  {cancellingDelivery ? 'Cancelling...' : 'Cancel'}
                                </Button>
                              )}
                              {/* Self delivery: edit rider info toggle */}
                              {(order.delivery_partner === 'manual') && order.delivery_status !== 'DELIVERED' && order.delivery_status !== 'delivered' && order.delivery_status !== 'cancelled' && (
                                <Button
                                  size="sm" variant="outline"
                                  onClick={() => {
                                    setEditRiderForm({
                                      rider_name: order.delivery_rider_name || '',
                                      rider_phone: order.delivery_rider_phone || '',
                                      eta: order.delivery_eta || '',
                                    })
                                    setIsEditingRiderInfo((v: boolean) => !v)
                                  }}
                                  className="h-7 text-[10px] font-bold uppercase border-blue-300 text-blue-700 dark:text-blue-400"
                                >
                                  {isEditingRiderInfo ? 'Cancel Edit' : 'Edit Rider'}
                                </Button>
                              )}
                            </div>
                          </div>

                          {/* ── Inline edit rider form (self-delivery only) ── */}
                          {isEditingRiderInfo && (order.delivery_partner === 'manual') && (
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3 bg-blue-50 dark:bg-blue-900/10 rounded-xl border border-blue-100 dark:border-blue-800/50">
                              <div className="space-y-1">
                                <label className="text-[10px] font-black uppercase text-muted-foreground">Rider Name</label>
                                <input className="flex h-8 w-full rounded-lg border border-input bg-transparent px-3 py-1 text-xs shadow-sm focus:outline-none focus:ring-1 focus:ring-primary"
                                  value={editRiderForm.rider_name} onChange={e => setEditRiderForm((f: any) => ({ ...f, rider_name: e.target.value }))} placeholder="Rider Name" />
                              </div>
                              <div className="space-y-1">
                                <label className="text-[10px] font-black uppercase text-muted-foreground">Rider Phone</label>
                                <input className="flex h-8 w-full rounded-lg border border-input bg-transparent px-3 py-1 text-xs shadow-sm focus:outline-none focus:ring-1 focus:ring-primary"
                                  value={editRiderForm.rider_phone} onChange={e => setEditRiderForm((f: any) => ({ ...f, rider_phone: e.target.value }))} placeholder="Rider Phone" />
                              </div>
                              <div className="space-y-1">
                                <label className="text-[10px] font-black uppercase text-muted-foreground">ETA (mins)</label>
                                <input className="flex h-8 w-full rounded-lg border border-input bg-transparent px-3 py-1 text-xs shadow-sm focus:outline-none focus:ring-1 focus:ring-primary"
                                  value={editRiderForm.eta} onChange={e => setEditRiderForm((f: any) => ({ ...f, eta: e.target.value }))} placeholder="e.g. 25" />
                              </div>
                              <div className="sm:col-span-3 flex justify-end">
                                <Button size="sm" onClick={handleUpdateRiderInfo} className="h-8 text-xs font-bold uppercase tracking-wider bg-blue-600 hover:bg-blue-700">
                                  <Save className="w-3.5 h-3.5 mr-1.5" /> Update Rider Info
                                </Button>
                              </div>
                            </div>
                          )}

                          {/* ── Self delivery status progression ── */}
                          {(order.delivery_partner === 'manual') && order.delivery_status !== 'DELIVERED' && order.delivery_status !== 'delivered' && order.delivery_status !== 'cancelled' && (
                            <div className="flex gap-2 pt-1">
                              {(order.delivery_status === 'assigned' || order.delivery_status === 'ACCEPTED') && (
                                <Button
                                  size="sm" variant="outline"
                                  onClick={() => handleSelfDeliveryProgress('DISPATCHED')}
                                  disabled={progressingDelivery}
                                  className="flex-1 h-8 text-xs font-bold uppercase tracking-wider border-orange-300 text-orange-700 hover:bg-orange-50 dark:text-orange-400"
                                >
                                  <Truck className="w-3.5 h-3.5 mr-1.5" />
                                  {progressingDelivery ? 'Updating...' : 'Mark Picked Up 🛵'}
                                </Button>
                              )}
                              <Button
                                size="sm"
                                onClick={() => handleSelfDeliveryProgress('DELIVERED')}
                                disabled={progressingDelivery}
                                className="flex-1 h-8 text-xs font-bold uppercase tracking-wider bg-green-600 hover:bg-green-700 text-white"
                              >
                                <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />
                                {progressingDelivery ? 'Updating...' : 'Mark Delivered ✅'}
                              </Button>
                            </div>
                          )}

                          {order.delivery_rider_name && (
                            <div className="flex items-center gap-3 p-3 bg-blue-50 dark:bg-blue-900/10 rounded-xl border border-blue-100 dark:border-blue-800/50">
                              <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-black">
                                {order.delivery_rider_name.charAt(0).toUpperCase()}
                              </div>
                              <div>
                                <p className="text-[10px] font-black uppercase text-blue-600">Active Rider</p>
                                <p className="text-xs font-bold leading-none">{order.delivery_rider_name}</p>
                                <p className="text-[10px] font-mono text-muted-foreground mt-0.5">{order.delivery_rider_phone}</p>
                              </div>
                            </div>
                          )}

                          {order.delivery_tracking_url && order.delivery_status !== 'cancelled' && (
                            <Button variant="outline" size="sm" asChild className="h-8 text-xs font-bold uppercase w-full">
                              <a href={order.delivery_tracking_url} target="_blank" rel="noopener noreferrer">Track Rider</a>
                            </Button>
                          )}
                        </div>
                      )}

                      {/* Integrated Live Map — always show for delivery orders when restaurant co-ords exist */}
                      {restaurantInfo.latitude && restaurantInfo.longitude && (
                        <div className="mt-2">
                          <DeliveryMap
                            restaurantName={restaurantInfo.name}
                            pickupLocation={restaurantInfo.latitude && restaurantInfo.longitude ? {
                              lat: parseFloat(restaurantInfo.latitude),
                              lng: parseFloat(restaurantInfo.longitude)
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
                        </div>
                      )}

                      <div className="flex gap-4 pt-2 border-t border-zinc-100 dark:border-zinc-800">
                        <div className="mt-1">
                          <MapPin className="w-4 h-4 text-muted-foreground" />
                        </div>
                        <div className="flex-1 space-y-1">
                          <p className="text-xs font-bold uppercase tracking-tighter text-muted-foreground">Drop Location</p>
                          <p className="text-xs font-medium leading-relaxed">{[order.delivery_house_number ? `#${order.delivery_house_number}` : '', order.delivery_address, order.delivery_landmark, order.delivery_city, order.delivery_zip_code].filter(Boolean).join(', ')}</p>
                          {order.delivery_instructions && (
                            <div className="mt-2 p-2 bg-amber-50 dark:bg-amber-900/10 rounded-lg border border-amber-100 dark:border-amber-800/50">
                              <p className="text-[10px] font-black uppercase text-amber-600 mb-0.5">Instructions</p>
                              <p className="text-xs font-medium italic">"{order.delivery_instructions}"</p>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Items Table Section */}
              <div className="bg-white dark:bg-zinc-900 rounded-2xl border border-gray-100 dark:border-zinc-800 overflow-hidden shadow-sm">
                <div className="px-4 py-4 border-b bg-gray-50/50 dark:bg-zinc-800/30 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
                      <Hash className="w-3.5 h-3.5 text-primary" />
                    </div>
                    <h3 className="text-xs font-black uppercase tracking-widest">Order Items</h3>
                  </div>
                  <div className="flex items-center gap-2">
                    {isEditing && (
                      <Button
                        size="sm"
                        variant="default"
                        onClick={() => setShowProductSearch(true)}
                        className="h-8 text-[10px] font-black uppercase tracking-wider rounded-lg"
                      >
                        <Plus className="w-3.5 h-3.5 mr-1" />
                        Add Product
                      </Button>
                    )}
                    <span className="text-[10px] font-bold bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 rounded-full text-muted-foreground">
                      {(isEditing ? editItems : order.order_items)?.length || 0} Products
                    </span>
                  </div>
                </div>

                <div className="divide-y divide-gray-100 dark:divide-zinc-800">
                  {isEditing ? (
                    editItems.map((item: any, index: number) => {
                      const hasCustomizations = item.customizations && Object.keys(item.customizations).length > 0

                      return (
                        <div key={index} className="p-4 hover:bg-slate-50/50 dark:hover:bg-white/[0.02] transition-colors">
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-3">
                                <div className="flex items-center gap-1.5 bg-zinc-100 dark:bg-zinc-800 rounded-lg p-1">
                                  <button
                                    onClick={() => handleQuantityChange(index, -1)}
                                    className="w-6 h-6 flex items-center justify-center hover:bg-zinc-200 dark:hover:bg-zinc-700 rounded transition-colors"
                                  >
                                    <Minus className="w-3.5 h-3.5" />
                                  </button>
                                  <span className="w-8 text-center font-black text-sm">{item.quantity || 1}</span>
                                  <button
                                    onClick={() => handleQuantityChange(index, 1)}
                                    className="w-6 h-6 flex items-center justify-center hover:bg-zinc-200 dark:hover:bg-zinc-700 rounded transition-colors"
                                  >
                                    <Plus className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                                <span className="text-base font-bold text-foreground truncate">{item.product_name || item.dishId}</span>
                              </div>

                              {hasCustomizations && (
                                <div className="mt-2 ml-16 space-y-1">
                                  {Object.entries(item.customizations).map(([question, options]: [string, any]) => {
                                    const opts = Array.isArray(options) ? options : [options]
                                    return (
                                      <div key={question} className="flex items-start gap-1.5">
                                        <span className="text-[10px] uppercase font-bold text-muted-foreground/60 mt-0.5">{question}:</span>
                                        <span className="text-xs font-medium text-muted-foreground leading-tight">{opts.join(', ')}</span>
                                      </div>
                                    )
                                  })}
                                </div>
                              )}
                            </div>
                            <div className="text-right flex flex-col items-end gap-2">
                              {/* Remove Button */}
                              <button
                                onClick={() => handleRemoveItem(index)}
                                className="p-1.5 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                                title="Remove Item"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                              <p className="text-sm font-black text-foreground">{formatAmount((item.totalPrice || item.unitPrice) * item.quantity)}</p>
                            </div>
                          </div>
                        </div>
                      )
                    })
                  ) : (
                    order.order_items?.map((item: any, index: number) => {
                      const customizations = parseCustomizations(item.customizations)
                      const hasCustomizations = customizations && Object.keys(customizations).length > 0

                      return (
                        <div key={index} className="p-4 hover:bg-slate-50/50 dark:hover:bg-white/[0.02] transition-colors">
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <div className="flex items-center justify-center font-mono font-black text-xs min-w-[24px] h-[24px] bg-zinc-900 text-white rounded-md shadow-inner">
                                  {item.quantity || 1}
                                </div>
                                <span className="text-base font-bold text-foreground truncate">{item.product_name || item.product || 'Unnamed Item'}</span>
                              </div>

                              {hasCustomizations && (
                                <div className="mt-2 ml-8 space-y-1">
                                  {Object.entries(customizations).map(([question, options]: [string, any]) => {
                                    const opts = Array.isArray(options) ? options : [options]
                                    return (
                                      <div key={question} className="flex items-start gap-1.5">
                                        <span className="text-[10px] uppercase font-bold text-muted-foreground/60 mt-0.5">{question}:</span>
                                        <span className="text-xs font-medium text-muted-foreground leading-tight">{opts.join(', ')}</span>
                                      </div>
                                    )
                                  })}
                                </div>
                              )}
                            </div>
                            <div className="text-right">
                              <p className="text-sm font-black text-foreground">{formatAmount(item.total_price || item.unit_price)}</p>
                              <p className="text-[10px] text-muted-foreground font-mono mt-0.5 opacity-60">
                                @{formatAmount(item.unit_price)}
                              </p>
                            </div>
                          </div>
                        </div>
                      )
                    })
                  )}
                </div>

                {/* Product Search Overlay (Internal) */}
                {isEditing && showProductSearch && (
                  <div className="p-4 border-t bg-slate-100/50 dark:bg-zinc-800/50 space-y-4">
                    <div className="flex items-center gap-3">
                      <div className="relative flex-1">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                        <Input
                          placeholder="Search menu products..."
                          value={productSearchTerm}
                          onChange={e => setProductSearchTerm(e.target.value)}
                          className="pl-9 h-9 text-sm"
                          autoFocus
                        />
                      </div>
                      <Button variant="ghost" size="icon" onClick={() => setShowProductSearch(false)} className="h-9 w-9">
                        <X className="w-4 h-4" />
                      </Button>
                    </div>

                    <div className="max-h-[300px] overflow-y-auto space-y-2 pr-1">
                      {filteredSearchProducts.map(p => (
                        <div
                          key={p.product_id}
                          onClick={() => handleAddProduct(p)}
                          className="flex items-center justify-between p-3 bg-white dark:bg-zinc-900 rounded-xl border border-zinc-100 dark:border-zinc-800 cursor-pointer hover:border-primary transition-all group shadow-sm"
                        >
                          <div>
                            <p className="font-bold text-sm group-hover:text-primary transition-colors">{p.product_name}</p>
                            <p className="text-[10px] text-muted-foreground">{p.category_name} · {p.main_category}</p>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className="text-xs font-black">{formatAmount(p.price)}</span>
                            <div className="p-1 rounded-md bg-zinc-100 dark:bg-zinc-800 group-hover:bg-primary group-hover:text-white transition-colors">
                              <Plus className="w-3.5 h-3.5" />
                            </div>
                          </div>
                        </div>
                      ))}
                      {filteredSearchProducts.length === 0 && (
                        <p className="text-center py-8 text-xs text-muted-foreground italic">No products found matching "{productSearchTerm}"</p>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Customization Sub-modal (Inline for dashboard) */}
              {selectedProductForCustomization && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
                  <div className="bg-white dark:bg-zinc-900 w-full max-w-md rounded-3xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
                    <div className="p-6 border-b flex items-center justify-between">
                      <div>
                        <h3 className="text-lg font-black">{selectedProductForCustomization.product_name}</h3>
                        <p className="text-xs text-muted-foreground uppercase tracking-widest font-bold">Customize Item</p>
                      </div>
                      <Button variant="ghost" size="icon" onClick={() => setSelectedProductForCustomization(null)} className="rounded-full">
                        <X className="w-5 h-5" />
                      </Button>
                    </div>

                    <div className="p-6 max-h-[60vh] overflow-y-auto space-y-6">
                      {JSON.parse(selectedProductForCustomization.customization_questions || '[]').map((q: any) => (
                        <div key={q.question_id} className="space-y-3">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-black">{q.title}</p>
                            {q.is_required && <Badge variant="destructive" className="text-[8px] h-4">Required</Badge>}
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            {q.options?.map((opt: any) => {
                              const isSelected = q.question_type === 'single'
                                ? tempCustomizations[q.question_id] === opt.option_id
                                : (tempCustomizations[q.question_id] || []).includes(opt.option_id)

                              return (
                                <button
                                  key={opt.option_id}
                                  onClick={() => {
                                    if (q.question_type === 'single') {
                                      setTempCustomizations(prev => ({ ...prev, [q.question_id]: opt.option_id }))
                                    } else {
                                      const current = tempCustomizations[q.question_id] || []
                                      const updated = current.includes(opt.option_id)
                                        ? current.filter((id: string) => id !== opt.option_id)
                                        : [...current, opt.option_id]
                                      setTempCustomizations(prev => ({ ...prev, [q.question_id]: updated }))
                                    }
                                  }}
                                  className={cn(
                                    "flex flex-col items-start p-3 rounded-xl border-2 text-left transition-all",
                                    isSelected
                                      ? "border-primary bg-primary/5 dark:bg-primary/10"
                                      : "border-zinc-100 dark:border-zinc-800 hover:border-zinc-200"
                                  )}
                                >
                                  <span className={cn("text-xs font-bold", isSelected ? "text-primary" : "text-foreground")}>{opt.label}</span>
                                  {opt.price > 0 && <span className="text-[10px] text-muted-foreground mt-0.5">+{formatAmount(opt.price)}</span>}
                                </button>
                              )
                            })}
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="p-6 bg-zinc-50 dark:bg-zinc-800/50 flex gap-3">
                      <Button variant="outline" onClick={() => setSelectedProductForCustomization(null)} className="flex-1 rounded-xl font-bold">Cancel</Button>
                      <Button onClick={handleConfirmCustomization} className="flex-1 rounded-xl font-black uppercase tracking-wider">Confirm</Button>
                    </div>
                  </div>
                </div>
              )}

              {/* Payment & Summary */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-start pb-4">
                {/* Method Info */}
                <div className="space-y-4">
                  <div className="bg-zinc-50 dark:bg-zinc-800/40 p-5 rounded-2xl border-2 border-dashed border-zinc-200 dark:border-zinc-700">
                    <div className="flex items-center gap-2 mb-3">
                      <CreditCard className="w-5 h-5 text-muted-foreground" />
                      <span className="text-xs font-black uppercase tracking-wider text-muted-foreground">Payment Method</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-full bg-white dark:bg-zinc-700 shadow-sm flex items-center justify-center">
                        <CreditCard className="w-5 h-5 text-primary" />
                      </div>
                      <div>
                        <p className="text-sm font-black capitalize">{(order.payment_method || 'Unspecified').replace('_', ' ')}</p>
                        <p className={`text-[10px] font-bold uppercase mt-0.5 ${order.payment_status === 'Paid' ? 'text-green-500' : 'text-orange-500'}`}>
                          {order.payment_status || 'Pending Payment'}
                        </p>
                      </div>
                    </div>
                  </div>

                  {order.coupon && (
                    <div className="bg-green-50 dark:bg-green-900/20 p-4 rounded-2xl border border-green-100 dark:border-green-800/50">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] font-black uppercase text-green-700 dark:text-green-400 tracking-widest">Promotion Applied</span>
                        <div className="px-2 py-0.5 bg-green-600 text-white text-[9px] font-black rounded-full shadow-sm">
                          -{coupon?.discount_type === 'percent' ? `${coupon.discount_value}%` : formatAmount(coupon?.discount_value || 0)}
                        </div>
                      </div>
                      <p className="text-sm font-black text-green-800 dark:text-green-300">{order.coupon}</p>
                      {coupon?.description && <p className="text-xs text-green-600/80 dark:text-green-400/60 mt-1 italic leading-tight">{coupon.description}</p>}
                    </div>
                  )}
                </div>

                {/* Final Breakdown */}
                <div className="space-y-3">
                  <div className="flex justify-between items-center text-sm px-1">
                    <span className="text-muted-foreground font-medium">Sub Total</span>
                    <span className="font-bold text-foreground">{formatAmount(order.subtotal)}</span>
                  </div>

                  {order.loyalty_discount > 0 && (
                    <div className="flex justify-between items-center text-sm px-1 italic">
                      <div className="flex items-center gap-1.5">
                        <div className="w-1 h-3 bg-green-500 rounded-full" />
                        <span className="text-green-600 font-bold">Loyalty Discount ({order.loyalty_coins_redeemed} Coins)</span>
                      </div>
                      <span className="font-black text-green-600">-{formatAmount(order.loyalty_discount)}</span>
                    </div>
                  )}

                  {(order.discount - (order.loyalty_discount || 0)) > 0 && (
                    <div className="flex justify-between items-center text-sm px-1 italic">
                      <div className="flex items-center gap-1.5">
                        <div className="w-1 h-3 bg-green-500 rounded-full" />
                        <span className="text-green-600 font-bold">Coupon Savings</span>
                      </div>
                      <span className="font-black text-green-600">-{formatAmount(order.discount - (order.loyalty_discount || 0))}</span>
                    </div>
                  )}

                  <div className="border-t border-slate-100 dark:border-zinc-800/50 my-2" />

                  {order.packaging_fee > 0 && (
                    <div className="flex justify-between items-center text-sm px-1">
                      <span className="text-muted-foreground font-medium">Packaging Charge</span>
                      <span className="font-bold text-foreground">{formatAmount(order.packaging_fee)}</span>
                    </div>
                  )}

                  {order.delivery_fee > 0 && (
                    <div className="flex justify-between items-center text-sm px-1">
                      <span className="text-muted-foreground font-medium">Delivery Charge</span>
                      <span className="font-bold text-foreground">{formatAmount(order.delivery_fee)}</span>
                    </div>
                  )}

                  {order.tax > 0 && (
                    <div className="flex justify-between items-center text-sm px-1">
                      <span className="text-muted-foreground font-medium">Taxes</span>
                      <span className="font-bold text-foreground">{formatAmount(order.tax)}</span>
                    </div>
                  )}

                  <div className="mt-4 pt-4 border-t-2 border-slate-100 dark:border-zinc-800 flex justify-between items-end px-1">
                    <div>
                      <p className="text-[10px] font-black uppercase text-muted-foreground tracking-widest mb-1">Total Amount Payable</p>
                      <span className="text-[10px] text-muted-foreground font-medium italic">Incl. all taxes and fees</span>
                    </div>
                    <div className="text-right">
                      <h4 className="text-3xl font-display font-black text-foreground tracking-tighter leading-none">
                        {formatAmountNoDecimals(order.total)}
                      </h4>
                    </div>
                  </div>

                  {order.coins_earned > 0 && (
                    <div className="mt-6 pt-4 border-t border-dashed border-slate-200 dark:border-zinc-800 flex justify-between items-center px-1">
                      <div>
                        <p className="text-[10px] font-black uppercase text-orange-600 tracking-widest mb-0.5">Loyalty Points Earning</p>
                        <p className="text-[10px] text-muted-foreground font-bold italic">Order Earning</p>
                      </div>
                      <div className="text-right">
                        <span className="text-lg font-black text-orange-600">+{order.coins_earned}</span>
                        <span className="text-[10px] font-bold text-orange-600/70 ml-1 uppercase">Coins</span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Action Bar */}
            <div className="p-4 border-t bg-white dark:bg-zinc-900 flex justify-end gap-3 sticky bottom-0">
              {isEditing ? (
                <>
                  <button
                    onClick={handleCancelEdit}
                    disabled={isSaving}
                    className="px-6 py-2.5 rounded-xl font-bold text-sm bg-gray-100 dark:bg-zinc-800 text-foreground hover:bg-gray-200 dark:hover:bg-zinc-700 transition-all border-b-4 border-gray-200 dark:border-zinc-700 active:border-b-0 active:translate-y-1"
                  >
                    Discard Changes
                  </button>
                  <button
                    onClick={handleSaveOrder}
                    disabled={isSaving}
                    className="px-6 py-2.5 rounded-xl font-black text-[10px] uppercase bg-primary text-white hover:bg-primary/90 border-b-4 border-primary/20 active:border-b-0 active:translate-y-1 flex items-center gap-2"
                  >
                    {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                    {isSaving ? 'Updating...' : 'Save Order Changes'}
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={() => onOpenChange(false)}
                    className="px-6 py-2.5 rounded-xl font-bold text-sm bg-gray-100 dark:bg-zinc-800 text-foreground hover:bg-gray-200 dark:hover:bg-zinc-700 transition-all border-b-4 border-gray-200 dark:border-zinc-700 active:border-b-0 active:translate-y-1"
                  >
                    Close Window
                  </button>
                  <button
                    onClick={() => print(order, { type: 'KOT' })}
                    className="px-6 py-2.5 rounded-xl font-black text-[10px] uppercase bg-purple-100 text-purple-700 hover:bg-purple-200 border-b-4 border-purple-200 active:border-b-0 active:translate-y-1"
                  >
                    Print KOT
                  </button>
                  <button
                    onClick={() => print(order, { type: 'RECEIPT', restaurant: restaurantConfig?.restaurant })}
                    className="px-6 py-2.5 rounded-xl font-black text-[10px] uppercase bg-zinc-900 text-white hover:bg-black border-b-4 border-zinc-950 active:border-b-0 active:translate-y-1"
                  >
                    Print Receipt
                  </button>
                </>
              )}
            </div>
          </div>
        ) : (
          <div className="text-center py-20 px-6 space-y-4">
            <div className="w-16 h-16 bg-red-50 dark:bg-red-900/20 rounded-full flex items-center justify-center mx-auto">
              <AlertCircle className="w-8 h-8 text-red-500" />
            </div>
            <div>
              <h3 className="text-xl font-black text-foreground">Order Not Found</h3>
              <p className="text-sm text-muted-foreground mt-2 max-w-sm mx-auto">We couldn't retrieve the details for this order. It may have been deleted or the ID is incorrect.</p>
            </div>
            <button
              onClick={() => onOpenChange(false)}
              className="px-8 py-3 bg-primary text-white font-black rounded-xl"
            >
              Go Back
            </button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

