import { useMemo, useState, useEffect } from 'react'
import { useFrappeGetDoc } from '@/lib/frappe'
import { usePrint } from '@/hooks/usePrint'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { 
  ChevronDown,
  Navigation,
  ShoppingBag,
  Bell,
  CheckCircle2,
  ChefHat,
  PackageCheck,
  Receipt,
  XCircle,
  Clock,
  User,
  CreditCard,
  Printer
} from 'lucide-react'
import { useFrappePostCall } from '@/lib/frappe'
import { toast } from 'sonner'
import { cn, getFrappeError } from '@/lib/utils'
import { useConfirm } from '@/hooks/useConfirm'
import { useCurrency } from '@/hooks/useCurrency'
import { Badge } from '@/components/ui/badge'

interface OrderItem {
  product_name?: string
  product?: string
  quantity: number
  unit_price: number
  total_price: number
  customizations?: string | any
}

interface Order {
  name: string
  order_number?: string
  status: string
  total: number
  creation: string
  table_number?: number
  order_type?: 'dine_in' | 'takeaway' | 'delivery' | string
  restaurant?: string
  customer_name?: string
  customer_phone?: string
  payment_method?: string
  payment_status?: string
  coupon?: string
  subtotal?: number
  discount?: number
  tax?: number
  delivery_fee?: number
  delivery_partner?: string
  delivery_status?: string
  order_items?: OrderItem[]
}

interface OrdersModernViewProps {
  orders: Order[]
  onCheckOrder: (orderId: string) => void
  onOrderUpdate?: () => void
  onShowCancelled?: () => void
}

const TABS = [
  { id: 'all', label: 'All Orders', icon: ShoppingBag, color: 'text-gray-500' },
  { id: 'new', label: 'New', icon: Bell, color: 'text-blue-500' },
  { id: 'confirmed', label: 'Confirmed', icon: CheckCircle2, color: 'text-orange-500' },
  { id: 'preparing', label: 'Preparing', icon: ChefHat, color: 'text-purple-500' },
  { id: 'ready', label: 'Ready', icon: PackageCheck, color: 'text-emerald-500' },
  { id: 'billed', label: 'Billed', icon: Receipt, color: 'text-gray-700' },
]

export function OrdersModernView({ orders, onCheckOrder, onOrderUpdate, onShowCancelled }: OrdersModernViewProps) {
  const { formatAmountNoDecimals } = useCurrency()
  const { call: updateStatus } = useFrappePostCall('flamezo_backend.flamezo.api.order_status.update_status')
  const { ConfirmDialogComponent } = useConfirm()
  const [activeTab, setActiveTab] = useState('new')

  // Live timer state
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60000) // Update every minute
    return () => clearInterval(timer)
  }, [])

  const getTimeElapsed = (creation: string) => {
    const start = new Date(creation)
    const diff = Math.floor((now.getTime() - start.getTime()) / 60000)
    if (diff < 1) return 'Just now'
    if (diff < 60) return `${diff} min ago`
    const hours = Math.floor(diff / 60)
    if (hours < 24) return `${hours}h ago`
    return start.toLocaleDateString()
  }

  const handleStatusChange = async (orderId: string, newStatus: string, label: string) => {
    try {
      await updateStatus({
        order_id: orderId,
        status: newStatus
      })
      toast.success(`Order marked as ${label}`)
      if (onOrderUpdate) onOrderUpdate()
    } catch (error: any) {
      toast.error(`Failed to update status to ${label}`, { description: getFrappeError(error) })
    }
  }

  const filteredOrders = useMemo(() => {
    if (activeTab === 'all') return orders
    return orders.filter(order => {
      const status = order.status?.toLowerCase()
      if (activeTab === 'new') return status === 'accepted' || status === 'auto accepted' || status === 'confirmed'
      if (activeTab === 'confirmed') return status === 'confirmed'
      if (activeTab === 'preparing') return status === 'preparing'
      if (activeTab === 'ready') return status === 'ready'
      if (activeTab === 'billed') return status === 'billed' || status === 'in billing' || status === 'delivered'
      return false
    })
  }, [orders, activeTab])

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: orders.length }
    orders.forEach(o => {
      const s = o.status?.toLowerCase()
      if (s === 'accepted' || s === 'auto accepted' || s === 'confirmed') c.new = (c.new || 0) + 1
      if (s === 'confirmed') c.confirmed = (c.confirmed || 0) + 1
      if (s === 'preparing') c.preparing = (c.preparing || 0) + 1
      if (s === 'ready') c.ready = (c.ready || 0) + 1
      if (s === 'billed' || s === 'in billing' || s === 'delivered') c.billed = (c.billed || 0) + 1
    })
    return c
  }, [orders])

  const [containerWidth, setContainerWidth] = useState(0)

  useEffect(() => {
    const observer = new ResizeObserver((entries) => {
      if (entries[0]) setContainerWidth(entries[0].contentRect.width)
    })
    const el = document.getElementById('modern-view-container')
    if (el) observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <div className="space-y-4" id="modern-view-container">
      <div className="w-full">
        <div className="flex justify-end -mt-3 mb-2">
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={onShowCancelled}
            className="text-red-600 hover:text-red-700 hover:bg-red-50 text-[11px] font-black uppercase h-8 px-3 gap-1.5 border border-red-100/50 shadow-sm transition-all active:scale-95"
          >
            <XCircle className="w-3.5 h-3.5" />
            Show Cancelled Order
          </Button>
        </div>

        <div className="flex bg-muted/50 p-1 rounded-lg w-full justify-start overflow-x-auto no-scrollbar gap-1 items-center">
          {TABS.map(tab => (
            <button 
              key={tab.id} 
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center px-4 py-2 rounded-md transition-all whitespace-nowrap text-sm font-medium",
                activeTab === tab.id 
                  ? "bg-background shadow-sm text-foreground" 
                  : "text-muted-foreground hover:bg-background/50 hover:text-foreground"
              )}
            >
              <tab.icon className={cn("w-4 h-4 mr-2", tab.color)} />
              <span>{tab.label}</span>
              <Badge variant="secondary" className="ml-2 bg-muted/80 text-[10px] px-1.5 h-4 border-none">
                {counts[tab.id] || 0}
              </Badge>
            </button>
          ))}
        </div>

        <div className="mt-6">
          {filteredOrders.length === 0 ? (
            <div className="text-center py-20 bg-muted/10 rounded-xl border-2 border-dashed border-muted">
              <div className="bg-muted p-4 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
                <ShoppingBag className="w-8 h-8 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-semibold text-foreground">No orders found</h3>
              <p className="text-sm text-muted-foreground">Orders for this status will appear here.</p>
            </div>
          ) : (
            <div className={cn(
              "grid gap-4 transition-all duration-300",
              containerWidth < 1100 ? "grid-cols-1 md:grid-cols-2 lg:grid-cols-3" : "grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
            )}>
              {filteredOrders.map(order => (
                <OrderCard 
                  key={order.name} 
                  order={order} 
                  onView={() => onCheckOrder(order.name)}
                  onStatusUpdate={handleStatusChange}
                  formatAmount={formatAmountNoDecimals}
                  timeElapsed={getTimeElapsed(order.creation)}
                />
              ))}
            </div>
          )}
        </div>
      </div>
      {ConfirmDialogComponent}
    </div>
  )
}

function OrderCard({ 
  order, 
  onView, 
  onStatusUpdate, 
  formatAmount,
  timeElapsed
}: { 
  order: Order
  onView: () => void
  onStatusUpdate: (id: string, status: string, label: string) => Promise<void>
  formatAmount: (val: number) => string
  timeElapsed: string
}) {
  const { print } = usePrint()
  const { restaurantConfig } = useRestaurant()
  const status = order.status?.toLowerCase()
  const isDineIn = order.order_type === 'dine_in'
  const isTakeaway = order.order_type === 'takeaway'
  const isDelivery = order.order_type === 'delivery'

  // Fetch full order doc (includes child table order_items) — same pattern as OrderDetailsDialog
  const { data: fullOrder } = useFrappeGetDoc('Order', order.name, {
    fields: ['order_items'],
    enabled: !!order.name
  })
  const orderItems: OrderItem[] = (fullOrder?.order_items as any) || []

  const ALL_STATUSES = [
    { value: 'confirmed', label: 'Confirmed' },
    { value: 'preparing', label: 'Preparing' },
    { value: 'ready', label: 'Ready' },
    { value: 'in_billing', label: 'In Billing' },
    { value: 'delivered', label: 'Delivered' },
    { value: 'billed', label: 'Billed' },
    { value: 'cancelled', label: 'Cancelled' },
  ]

  return (
    <Card className="group hover:shadow-xl transition-all duration-300 border-border/50 overflow-hidden bg-white dark:bg-zinc-900/50 hover:bg-[#fafafa] dark:hover:bg-zinc-900 relative border-l-4">
      <div className={cn(
        "absolute left-[-4px] top-0 bottom-0 w-1 rounded-l-full transition-all duration-300",
        status === 'confirmed' || status === 'accepted' || status === 'auto accepted' ? "bg-blue-500" :
        status === 'preparing' ? "bg-purple-500" :
        status === 'ready' ? "bg-emerald-500" :
        status === 'billed' || status === 'in billing' || status === 'delivered' ? "bg-gray-400" : "bg-muted"
      )} />
      
      <CardContent className="p-3 flex flex-col h-full">
        {/* Card Header */}
        <div className="flex justify-between items-center mb-3">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-black text-muted-foreground/60 uppercase tracking-widest">#</span>
            <span className="text-sm font-black text-foreground tracking-tight">
              {order.order_number || order.name}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3 text-muted-foreground/60" />
              <span className="text-[10px] font-bold text-muted-foreground/60 uppercase">{timeElapsed}</span>
            </div>
            {isDineIn && (
              <Badge variant="outline" className="bg-orange-500/10 text-orange-600 border-orange-200/50 font-black text-[10px] h-4.5 px-1.5 uppercase">
                DINE IN {(order.table_number !== undefined && order.table_number !== null) ? `· T-${order.table_number}` : ''}
              </Badge>
            )}
            {isTakeaway && (
               <Badge variant="outline" className="bg-blue-500/10 text-blue-600 border-blue-200/50 font-black text-[10px] h-4.5 px-1.5 uppercase">
                PICKUP
              </Badge>
            )}
            {isDelivery && (
               <div className="flex flex-col items-end gap-1">
                 <Badge variant="outline" className="bg-amber-500/10 text-amber-600 border-amber-200/50 font-black text-[10px] h-4.5 px-1.5 uppercase">
                  DELIVERY
                </Badge>
                {order.delivery_partner === 'borzo' && (
                  <span className="flex items-center gap-1 text-[8px] font-black text-amber-600 uppercase animate-pulse">
                    <Navigation className="w-2 h-2" />
                    {order.delivery_status || 'Finding...'}
                  </span>
                )}
               </div>
            )}
          </div>
        </div>

        {/* Content Area */}
        <div className="space-y-3 mb-4 flex-1">
          {/* Customer & Status - Vertical info with Inline Status */}
          <div className="flex items-center justify-between gap-3 bg-muted/20 p-2 rounded-lg border border-muted/30">
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-8 h-8 rounded-full bg-background flex items-center justify-center shrink-0 border border-muted/50 shadow-sm">
                <User className="w-4 h-4 text-muted-foreground" />
              </div>
              <div className="min-w-0 flex flex-col justify-center">
                <p className="text-[11px] font-black text-foreground truncate leading-tight italic">
                  {order.customer_name || 'Walk-in Guest'}
                </p>
                <p className="text-[9px] text-muted-foreground font-black tracking-tight leading-tight mt-0.5 opacity-70">
                  {order.customer_phone || 'No phone'}
                </p>
              </div>
            </div>
            <Badge 
              variant="secondary" 
              className={cn(
                "text-[9px] font-black uppercase px-2 py-0 h-4.5 border-none whitespace-nowrap shrink-0 ml-auto",
                status === 'confirmed' ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300" :
                status === 'preparing' ? "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300" :
                status === 'ready' ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300" :
                status === 'billed' || status === 'in billing' || status === 'delivered' ? "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300" :
                "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300"
              )}
            >
              {status?.replace('_', ' ')}
            </Badge>
          </div>

          <div className="bg-muted/30 p-2 rounded-lg border border-border/50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <ChefHat className="w-3 h-3 text-muted-foreground" />
                <span className="text-[10px] font-black uppercase text-muted-foreground">Kitchen Stack</span>
              </div>
              <span className="text-[10px] font-bold text-muted-foreground">Items: {orderItems.length}</span>
            </div>
          </div>
        </div>

        {/* Total & Payment */}
        <div className="flex items-end justify-between mb-4 pt-3 border-t border-dashed border-border">
          <div>
            <p className="text-[10px] font-black uppercase text-muted-foreground mb-0.5">Amount Due</p>
            <p className="text-lg font-black text-foreground">{formatAmount(order.total)}</p>
          </div>
          <div className="text-right">
             <div className="flex items-center gap-1.5 mb-0.5 justify-end">
                <CreditCard className="w-3 h-3 text-muted-foreground" />
                <span className="text-[10px] font-bold capitalize text-muted-foreground">
                  {(order.payment_method || 'Unpaid').replace('_', ' ')}
                </span>
             </div>
             <p className={cn(
               "text-[9px] font-black uppercase tracking-wider",
               order.payment_status === 'Paid' || order.payment_status === 'completed' ? "text-emerald-500" : "text-amber-500"
             )}>
               {order.payment_status === 'Paid' || order.payment_status === 'completed' ? 'Paid' : 'Pending'}
             </p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-1.5 container-actions">
          <Button 
            variant="outline" 
            size="sm" 
            onClick={(e) => {
              e.stopPropagation()
              print(order, { type: 'RECEIPT', restaurant: restaurantConfig?.restaurant })
            }}
            className="h-8 w-8 p-0 rounded-lg bg-background/50 hover:bg-zinc-100 dark:hover:bg-zinc-800 border border-border/80 shadow-sm shrink-0"
            title="Print Receipt"
          >
            <Printer className="w-3.5 h-3.5 text-muted-foreground" />
          </Button>

          <Button 
            variant="outline" 
            size="sm" 
            onClick={(e) => {
              e.stopPropagation()
              print(order, { type: 'KOT' })
            }}
            className="h-8 w-8 p-0 rounded-lg bg-background/50 hover:bg-zinc-100 dark:hover:bg-zinc-800 border border-border/80 shadow-sm shrink-0"
            title="Print KOT"
          >
            <ChefHat className="w-3.5 h-3.5 text-muted-foreground" />
          </Button>

          <Button 
            variant="outline" 
            size="sm" 
            onClick={onView}
            className="flex-1 h-8 rounded-lg bg-background/50 hover:bg-accent border border-border/80 shadow-sm text-[10px] font-bold uppercase gap-1.5"
          >
            Details
          </Button>

          {/* Contextual Status Action Dropdown */}
          <div className="flex-1 relative group/status">
            <select
              value={status === 'in billing' ? 'in_billing' : status}
              onChange={(e) => {
                const newStatus = e.target.value
                const label = ALL_STATUSES.find(s => s.value === newStatus)?.label || newStatus
                onStatusUpdate(order.name, newStatus, label)
              }}
              className={cn(
                "w-full h-8 px-2 pr-6 rounded-lg font-black text-[10px] uppercase shadow-sm cursor-pointer border-none outline-none appearance-none text-center transition-all duration-200",
                status === 'confirmed' ? "bg-blue-600 hover:bg-blue-700 text-white" :
                status === 'preparing' ? "bg-purple-600 hover:bg-purple-700 text-white" :
                status === 'ready' ? "bg-emerald-600 hover:bg-emerald-700 text-white" :
                status === 'in_billing' || status === 'in billing' ? "bg-orange-600 hover:bg-orange-700 text-white" :
                status === 'delivered' || status === 'billed' ? "bg-gray-900 hover:bg-black text-white" :
                "bg-blue-600 hover:bg-blue-700 text-white"
              )}
            >
              {ALL_STATUSES.map(s => (
                <option key={s.value} value={s.value} className="bg-white dark:bg-zinc-900 text-foreground">
                  {s.label}
                </option>
              ))}
            </select>
            <div className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-white/70 group-hover/status:text-white transition-colors">
              <ChevronDown className="w-3 h-3" />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
