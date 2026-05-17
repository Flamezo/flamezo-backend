import { useMemo, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Eye, Clock, User, Phone, CreditCard, Tag } from 'lucide-react'
import { DndContext, DragEndEvent, DragOverlay, DragStartEvent, DragMoveEvent, closestCorners, PointerSensor, TouchSensor, KeyboardSensor, useSensor, useSensors } from '@dnd-kit/core'
import { CSS } from '@dnd-kit/utilities'
import { useDraggable, useDroppable } from '@dnd-kit/core'
import { useFrappePostCall } from '@/lib/frappe'
import { toast } from 'sonner'
import { cn, getFrappeError } from '@/lib/utils'
import { useConfirm } from '@/hooks/useConfirm'
import { useCurrency } from '@/hooks/useCurrency'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

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
}

interface OrdersKanbanProps {
  orders: Order[]
  onCheckOrder: (orderId: string) => void
  onOrderUpdate?: () => void
  onCancelOrder?: (orderId: string) => void
  onBilledOrder?: (orderId: string) => void
  restaurantTables?: number
}

const STATUSES = [
  { value: 'confirmed', label: 'Confirmed', color: 'bg-orange-50 dark:bg-[#ea580c]/20 text-[#ea580c] dark:text-[#ff8c42] border-orange-200 dark:border-[#ea580c]/40' },
  { value: 'preparing', label: 'Preparing', color: 'bg-[#e8d5ff] dark:bg-[#4a148c] text-[#8764b8] dark:text-[#ba68c8] border-[#d4b9e8] dark:border-[#6a1b9a]' },
  { value: 'delivered', label: 'Delivered', color: 'bg-[#dff6dd] dark:bg-[#1b5e20] text-[#107c10] dark:text-[#81c784] border-[#92c5f7] dark:border-[#4caf50]' },
  { value: 'In Billing', label: 'In Billing', color: 'bg-[#fff3e0] dark:bg-[#e65100]/20 text-[#e65100] dark:text-[#ff9800] border-[#ffe0b2] dark:border-[#e65100]/40' },
]

// Map new workflow statuses to Kanban columns for display
const STATUS_TO_COLUMN: Record<string, string> = {
  'Auto Accepted': 'confirmed',
  'Accepted': 'confirmed',
}

// Draggable Order Card Component
function DraggableOrderCard({ 
  order, 
  onCheckOrder, 
  onCancelOrder,
  onBilledOrder,
  onTableNumberChange,
  tableOptions = []
}: { 
  order: Order
  onCheckOrder: (orderId: string) => void
  onCancelOrder?: (orderId: string) => void
  onBilledOrder?: (orderId: string) => void
  onTableNumberChange?: (orderId: string, tableNumber: number) => void
  tableOptions?: number[]
}) {
  const { confirm, ConfirmDialogComponent } = useConfirm()
  const { formatAmountNoDecimals } = useCurrency()
  const safeTableOptions = Array.isArray(tableOptions) ? tableOptions : []
  const { attributes, listeners, setNodeRef, isDragging, transform } = useDraggable({
    id: order.name,
    data: {
      order,
    },
  })

  const style = transform ? {
    transform: CSS.Translate.toString(transform),
    transition: isDragging ? 'none' : 'transform 200ms ease',
  } : {
    transition: 'transform 200ms ease',
  }

  // Normalize status for comparison
  const normalizedStatus = order.status === 'in_billing' ? 'In Billing' : order.status
  
  // Don't show cancel button for cancelled, delivered, billed, or In Billing orders
  const showCancelButton = normalizedStatus !== 'cancelled' && normalizedStatus !== 'delivered' && normalizedStatus !== 'billed' && normalizedStatus !== 'In Billing'
  
  // Show billed button only for orders in In Billing status
  const showBilledButton = normalizedStatus === 'In Billing'
  const orderTypeLabel = (order.order_type || 'dine_in').replace('_', ' ')
  const orderTypeBadgeClass =
    order.order_type === 'delivery'
      ? 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/30 dark:text-blue-300 dark:border-blue-800'
      : order.order_type === 'takeaway'
      ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-800'
      : 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:border-emerald-800'

  return (
    <Card
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      className={cn(
        "cursor-grab active:cursor-grabbing hover:shadow-md transition-all duration-200 bg-card border border-border py-0",
        isDragging && "opacity-50 scale-95 shadow-xl"
      )}
    >
      <CardContent className="px-3 py-3">
        {/* Header: Order ID and Table */}
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-1.5 min-w-0 flex-1">
            <span className="text-xs font-semibold text-foreground uppercase truncate">
              {order.order_number || order.name}
            </span>
          </div>
          {safeTableOptions.length > 0 && onTableNumberChange && typeof order.table_number === 'number' && order.table_number > 0 ? (
            <Select
              value={order.table_number.toString()}
              onValueChange={(value) => {
                const parsed = parseInt(value, 10)
                const tableNum = Number.isNaN(parsed) ? 1 : parsed
                onTableNumberChange?.(order.name, tableNum)
              }}
            >
              <SelectTrigger
                className="h-5 px-1.5 text-[10px] font-medium bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 border border-gray-700 dark:border-gray-300 flex-shrink-0 w-auto min-w-[60px]"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => e.stopPropagation()}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {safeTableOptions.map((tableNum) => (
                  <SelectItem key={tableNum} value={tableNum.toString()}>
                    Table {tableNum}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : typeof order.table_number === 'number' && order.table_number > 0 ? (
            <span className="inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 border border-gray-700 dark:border-gray-300 flex-shrink-0">
              Table {order.table_number}
            </span>
          ) : null}
        </div>

        <div className="mb-2">
          <span className={cn(
            'inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-semibold capitalize',
            orderTypeBadgeClass
          )}>
            {orderTypeLabel}
          </span>
        </div>
        
        {/* Customer Info - Single Row */}
        {(order.customer_name || order.customer_phone) && (
          <div className="flex items-center gap-2 mb-2.5 text-xs text-muted-foreground">
            {order.customer_name && (
              <div className="flex items-center gap-1 min-w-0 flex-1">
                <User className="h-3 w-3 text-muted-foreground/70 flex-shrink-0" />
                <span className="truncate">{order.customer_name}</span>
              </div>
            )}
            {order.customer_phone && (
              <div className="flex items-center gap-1 flex-shrink-0">
                <Phone className="h-3 w-3 text-muted-foreground/70" />
                <span className="truncate">{order.customer_phone}</span>
              </div>
            )}
          </div>
        )}
        
        {/* Order Total - TO PAY */}
        <div className="mb-2.5 pb-2.5 border-b border-border">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-xs text-muted-foreground font-medium">TO PAY</span>
            <span className="text-base font-bold text-foreground">
              {formatAmountNoDecimals(order.total)}
            </span>
          </div>
        </div>
        
        {/* Payment & Coupon Info */}
        <div className="space-y-1 mb-2.5">
          {order.payment_method && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <CreditCard className="h-3 w-3 text-muted-foreground/70 flex-shrink-0" />
              <span className="capitalize truncate">{order.payment_method.replace('_', ' ')}</span>
              {order.payment_status && order.payment_method !== 'pay_at_counter' && (
                <span className={cn(
                  "ml-1 px-1 py-0.5 rounded-md text-[10px] font-semibold",
                  order.payment_status === 'completed' 
                    ? "bg-[#dff6dd] dark:bg-[#1b5e20] text-[#0d5d0d] dark:text-[#a5d6a7]"
                    : order.payment_status === 'failed'
                    ? "bg-[#fde7e9] dark:bg-[#b71c1c] text-[#b91c1c] dark:text-[#ffcdd2]"
                    : "bg-[#fff4ce] dark:bg-[#ca5010]/20 text-[#b45309] dark:text-[#ffd89b]"
                )}>
                  {order.payment_status === 'completed'
                    ? 'Paid'
                    : order.payment_status === 'failed'
                    ? 'Payment Failed'
                    : 'Payment Pending'}
                </span>
              )}
            </div>
          )}
          {order.coupon && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Tag className="h-3 w-3 text-muted-foreground/70 flex-shrink-0" />
              <span className="truncate">{order.coupon}</span>
            </div>
          )}
        </div>
        
        {/* Timestamp */}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-2.5">
          <Clock className="h-3 w-3 text-muted-foreground/70 flex-shrink-0" />
          <span>
            {order.creation ? new Date(order.creation).toLocaleString('en-IN', {
              day: '2-digit',
              month: 'short',
              hour: '2-digit',
              minute: '2-digit'
            }) : 'N/A'}
          </span>
        </div>
        
        {/* Footer Actions */}
        <div className="flex items-center gap-2 pt-2 border-t border-border">
          {showCancelButton && onCancelOrder && (
            <Button
              variant="outline"
              size="sm"
              onClick={async (e) => {
                e.stopPropagation()
                const confirmed = await confirm({
                  title: 'Cancel Order',
                  description: 'Are you sure you want to cancel this order? This action cannot be undone.',
                  variant: 'destructive',
                  confirmText: 'Cancel Order',
                  cancelText: 'Keep Order'
                })
                if (confirmed) {
                  onCancelOrder(order.name)
                }
              }}
              onPointerDown={(e) => e.stopPropagation()}
              className="h-7 px-2 text-xs text-destructive hover:text-destructive/80 hover:bg-destructive/10 border-destructive/20 flex-1"
            >
              Cancel
            </Button>
          )}
          {showBilledButton && onBilledOrder && (
            <Button
              variant="outline"
              size="sm"
              onClick={async (e) => {
                e.stopPropagation()
                const confirmed = await confirm({
                  title: 'Mark as Billed',
                  description: 'Are you sure you want to mark this order as billed?',
                  variant: 'default',
                  confirmText: 'Mark as Billed',
                  cancelText: 'Cancel'
                })
                if (confirmed) {
                  onBilledOrder(order.name)
                }
              }}
              onPointerDown={(e) => e.stopPropagation()}
              className="h-7 px-2 text-xs text-[#107c10] dark:text-[#81c784] hover:text-[#107c10]/80 dark:hover:text-[#81c784]/80 hover:bg-[#dff6dd]/50 dark:hover:bg-[#1b5e20]/30 border-[#107c10]/20 dark:border-[#81c784]/20 flex-1"
            >
              Billed
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation()
              onCheckOrder(order.name)
            }}
            onPointerDown={(e) => e.stopPropagation()}
            className="h-7 px-2 text-xs text-foreground hover:text-foreground hover:bg-accent flex-1"
          >
            <Eye className="h-3.5 w-3.5 mr-1" />
            View
          </Button>
          {ConfirmDialogComponent}
        </div>
      </CardContent>
    </Card>
  )
}

// Droppable Status Column Component
function DroppableStatusColumn({ 
  status, 
  orders, 
  onCheckOrder,
  onCancelOrder,
  onBilledOrder,
  activeId,
  handleTableNumberChange,
  tableOptions = []
}: { 
  status: typeof STATUSES[0]
  orders: Order[]
  onCheckOrder: (orderId: string) => void
  onCancelOrder?: (orderId: string) => void
  onBilledOrder?: (orderId: string) => void
  activeId?: string | null
  handleTableNumberChange: (orderId: string, tableNumber: number) => void
  tableOptions?: number[]
}) {
  const safeTableOptions = Array.isArray(tableOptions) ? tableOptions : []
  const { setNodeRef, isOver } = useDroppable({
    id: status.value,
  })

  return (
    <div className="flex-shrink-0 flex-1 min-w-0 flex flex-col">
      <div className={`rounded-md px-3 py-2 ${status.color} mb-3 inline-flex items-center justify-center border`}>
        <h3 className="font-bold text-xs uppercase tracking-wide">
          {status.label} ({orders.length})
        </h3>
      </div>
      
      <div
        ref={setNodeRef}
        className={cn(
          "space-y-1.5 rounded-md px-2 py-1 bg-muted flex-1 overflow-y-auto transition-all duration-200 border",
          isOver 
            ? 'bg-primary/10 dark:bg-primary/20 border-2 border-primary border-dashed shadow-inner' 
            : 'border-border hover:border-border/80'
        )}
        style={{ maxHeight: 'calc(100vh - 320px)', minHeight: '300px' }}
      >
        {orders.length === 0 ? (
          <div className="text-center text-muted-foreground text-sm py-8">
            No orders
          </div>
        ) : (
          orders.map(order => (
            <div
              key={order.name}
              className={cn(
                "transition-all duration-200",
                activeId === order.name && "opacity-0"
              )}
            >
              <DraggableOrderCard
                order={order}
                onCheckOrder={onCheckOrder}
                onCancelOrder={onCancelOrder}
                onBilledOrder={onBilledOrder}
                onTableNumberChange={handleTableNumberChange}
                tableOptions={safeTableOptions}
              />
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export function OrdersKanban({ orders, onCheckOrder, onOrderUpdate, onCancelOrder, onBilledOrder, restaurantTables }: OrdersKanbanProps) {
  const { formatAmountNoDecimals } = useCurrency()
  const { call } = useFrappePostCall('flamezo_backend.flamezo.api.order_status.update_status')
  const { call: updateTableNumber } = useFrappePostCall('flamezo_backend.flamezo.api.order_status.update_table_number')
  const [activeOrder, setActiveOrder] = useState<Order | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  
  // Generate table options based on restaurant tables count
  const tableOptions = useMemo(() => {
    const maxTables = Number(restaurantTables ?? 0)
    const options: number[] = []
    if (maxTables > 0) {
      for (let i = 1; i <= maxTables; i++) {
        options.push(i)
      }
    }
    return options
  }, [restaurantTables])
  
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 5,
      },
    }),
    useSensor(TouchSensor, {
      activationConstraint: {
        delay: 150,
        tolerance: 5,
      },
    }),
    useSensor(KeyboardSensor)
  )

  // Normalize status value (handle legacy "in_billing" format)
  const normalizeStatus = (status: string): string => {
    if (status === 'in_billing') {
      return 'In Billing'
    }
    return status
  }

  const ordersByStatus = useMemo(() => {
    const grouped: Record<string, Order[]> = {}
    STATUSES.forEach(status => {
      grouped[status.value] = []
    })
    orders.forEach(order => {
      const raw = normalizeStatus(order.status || 'confirmed')
      const status = STATUS_TO_COLUMN[raw] ?? raw
      if (!grouped[status]) {
        grouped[status] = []
      }
      grouped[status].push(order)
    })
    return grouped
  }, [orders])

  const handleDragStart = (event: DragStartEvent) => {
    const order = event.active.data.current?.order as Order | undefined
    if (order) {
      setActiveOrder(order)
      setActiveId(event.active.id as string)
    }
  }

  const handleDragMove = (_event: DragMoveEvent) => {
    // optional: add visual feedback
  }

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event

    setActiveOrder(null)
    setActiveId(null)

    if (!over || active.id === over.id) {
      return
    }

    const orderId = active.id as string
    const newStatus = normalizeStatus(over.id as string)

    try {
      await call({
        order_id: orderId,
        status: newStatus,
      })

      toast.success(`Order moved to ${STATUSES.find(s => s.value === newStatus)?.label || newStatus}`)
    } catch (error: any) {
      console.error('Failed to update order status:', error)
      toast.error('Failed to update order status', { description: getFrappeError(error) })
    } finally {
      if (onOrderUpdate) {
        onOrderUpdate()
      }
    }
  }

  const handleCancelOrder = async (orderId: string) => {
    try {
      await call({
        order_id: orderId,
        status: 'cancelled'
      })
      
      toast.success('Order cancelled successfully')
      
      if (onOrderUpdate) {
        onOrderUpdate()
      }
    } catch (error: any) {
      console.error('Failed to cancel order:', error)
      toast.error('Failed to cancel order', { description: getFrappeError(error) })
      
      if (onOrderUpdate) {
        onOrderUpdate()
      }
    }
  }

  const handleBilledOrder = async (orderId: string) => {
    try {
      await call({
        order_id: orderId,
        status: 'billed'
      })
      
      toast.success('Order marked as billed successfully')
      
      if (onOrderUpdate) {
        onOrderUpdate()
      }
    } catch (error: any) {
      console.error('Failed to mark order as billed:', error)
      toast.error('Failed to mark order as billed', { description: getFrappeError(error) })
      
      if (onOrderUpdate) {
        onOrderUpdate()
      }
    }
  }

  const handleTableNumberChange = async (orderId: string, tableNumber: number) => {
    try {
      await updateTableNumber({
        order_id: orderId,
        table_number: tableNumber
      })
      
      toast.success(`Table updated to Table ${tableNumber}`)
      
      if (onOrderUpdate) {
        onOrderUpdate()
      }
    } catch (error: any) {
      console.error('Failed to update table number:', error)
      toast.error('Failed to update table number', { description: getFrappeError(error) })
      
      if (onOrderUpdate) {
        onOrderUpdate()
      }
    }
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragMove={handleDragMove}
      onDragEnd={handleDragEnd}
    >
      <div className="flex gap-4 overflow-x-hidden pb-4" style={{ height: 'calc(100vh - 280px)' }}>
        {STATUSES.map((status) => {
          const statusOrders = ordersByStatus[status.value] || []
          
          return (
            <DroppableStatusColumn
              key={status.value}
              status={status}
              orders={statusOrders}
              onCheckOrder={onCheckOrder}
              onCancelOrder={onCancelOrder || handleCancelOrder}
              onBilledOrder={onBilledOrder || handleBilledOrder}
              activeId={activeId}
              handleTableNumberChange={handleTableNumberChange}
              tableOptions={tableOptions}
            />
          )
        })}
      </div>
      
      <DragOverlay
        dropAnimation={{
          duration: 300,
          easing: 'cubic-bezier(0.18, 0.67, 0.6, 1)',
        }}
        style={{
          opacity: 0.95,
        }}
      >
        {activeOrder ? (
          <Card className="shadow-2xl border-2 border-primary rotate-1 scale-105 bg-card">
            <CardContent className="px-3 py-3">
              <div className="flex items-center justify-between mb-2.5">
                <span className="text-xs font-semibold text-foreground uppercase truncate">
                  {activeOrder.order_number || activeOrder.name}
                </span>
                {typeof activeOrder.table_number === 'number' && activeOrder.table_number > 0 ? (
                  <span className="inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 border border-gray-700 dark:border-gray-300 flex-shrink-0">
                    Table {activeOrder.table_number}
                  </span>
                ) : null}
              </div>

              {(activeOrder.customer_name || activeOrder.customer_phone) && (
                <div className="flex items-center gap-2 mb-2.5 text-xs text-muted-foreground">
                  {activeOrder.customer_name && (
                    <div className="flex items-center gap-1 min-w-0 flex-1">
                      <User className="h-3 w-3 text-muted-foreground/70 flex-shrink-0" />
                      <span className="truncate">{activeOrder.customer_name}</span>
                    </div>
                  )}
                  {activeOrder.customer_phone && (
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <Phone className="h-3 w-3 text-muted-foreground/70" />
                      <span className="truncate">{activeOrder.customer_phone}</span>
                    </div>
                  )}
                </div>
              )}

              <div className="mb-2.5 pb-2.5 border-b border-border">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-xs text-muted-foreground font-medium">TO PAY</span>
                  <span className="text-base font-bold text-foreground">
                    {formatAmountNoDecimals(activeOrder.total)}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Clock className="h-3 w-3 text-muted-foreground/70 flex-shrink-0" />
                <span>
                  {activeOrder.creation ? new Date(activeOrder.creation).toLocaleString('en-IN', {
                    day: '2-digit',
                    month: 'short',
                    hour: '2-digit',
                    minute: '2-digit'
                  }) : 'N/A'}
                </span>
              </div>
            </CardContent>
          </Card>
        ) : null}
      </DragOverlay>
    </DndContext>
  )
}
