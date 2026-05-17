import { useMemo, useState } from 'react'
import { useFrappeGetDocList, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  closestCenter,
  PointerSensor,
  TouchSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { CSS } from '@dnd-kit/utilities'
import { useDraggable, useDroppable } from '@dnd-kit/core'
import { Eye, Clock, User, Phone, Banknote, CheckCircle2, Edit3 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useCurrency } from '@/hooks/useCurrency'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { OrderDetailsDialog } from '@/components/OrderDetailsDialog'
import { useConfirm } from '@/hooks/useConfirm'
import { toast } from 'sonner'
import { LockedFeature } from '@/components/FeatureGate/LockedFeature'

interface Order {
  name: string
  order_number?: string
  status: string
  total: number
  creation: string
  table_number?: number
  restaurant?: string
  customer_name?: string
  customer_phone?: string
  payment_method?: string
  payment_status?: string
}

// Pay-at-counter orders use status "pending" (works with all schema versions)
// Accept Orders filters by payment_method to show only pay-at-counter orders
const PENDING_STATUS = 'pending_verification'
const ACCEPTED_STATUS = 'confirmed' // Kitchen-ready status (sent to API)
const REJECTED_STATUS = 'cancelled'
const ACCEPTED_COLUMN_ID = 'accepted' // Droppable zone id for "Accepted" column (UI only)

function OrderCard({
  order,
  onViewDetails,
  onEdit,
  onAccept,
  onReject,
  isDragging = false,
  isOverlay = false,
}: {
  order: Order
  onViewDetails: (id: string) => void
  onEdit?: (id: string) => void
  onAccept?: (id: string) => void
  onReject?: (id: string) => void
  isDragging?: boolean
  isOverlay?: boolean
}) {
  const { formatAmountNoDecimals } = useCurrency()
  const { attributes, listeners, setNodeRef, transform } = useDraggable({
    id: order.name,
    data: { order },
  })

  const style = transform
    ? {
        transform: CSS.Translate.toString(transform),
        transition: isDragging ? 'none' : 'transform 200ms ease',
      }
    : undefined

  return (
    <Card
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      className={cn(
        'cursor-grab active:cursor-grabbing hover:shadow-md transition-all duration-200 bg-card border border-border',
        isDragging && 'opacity-50 scale-95 shadow-xl',
        isOverlay && 'cursor-grabbing shadow-2xl border-2 border-primary rotate-1 scale-105'
      )}
    >
      <CardContent className="px-4 py-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-semibold text-foreground">
            {order.order_number || order.name}
          </span>
          {typeof order.table_number === 'number' && order.table_number > 0 ? (
            <span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 border border-amber-200 dark:border-amber-800">
              Table {order.table_number}
            </span>
          ) : null}
        </div>
        {(order.customer_name || order.customer_phone) && (
          <div className="flex items-center gap-2 mb-2 text-xs text-muted-foreground">
            {order.customer_name && (
              <span className="flex items-center gap-1 truncate">
                <User className="h-3 w-3 flex-shrink-0" />
                {order.customer_name}
              </span>
            )}
            {order.customer_phone && (
              <span className="flex items-center gap-1 truncate flex-shrink-0">
                <Phone className="h-3 w-3" />
                {order.customer_phone}
              </span>
            )}
          </div>
        )}
        <div className="flex items-center justify-between mb-2">
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <Banknote className="h-3 w-3" />
            Pay at Counter
          </span>
          <span className="text-base font-bold text-foreground">
            {formatAmountNoDecimals(order.total)}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Clock className="h-3 w-3 flex-shrink-0" />
          <span>
            {order.creation
              ? new Date(order.creation).toLocaleString('en-IN', {
                  day: '2-digit',
                  month: 'short',
                  hour: '2-digit',
                  minute: '2-digit',
                })
              : 'N/A'}
          </span>
        </div>
        <div className="flex gap-2 mt-3">
          {onAccept && !isOverlay && (
            <Button
              size="sm"
              variant="default"
              className="flex-1 text-[10px] font-black uppercase h-8"
              onClick={e => {
                e.stopPropagation()
                onAccept(order.name)
              }}
            >
              Accept
            </Button>
          )}
          {onReject && !isOverlay && (
            <Button
              size="sm"
              variant="outline"
              className="flex-1 text-[10px] font-black uppercase h-8 border-2"
              onClick={e => {
                e.stopPropagation()
                onReject(order.name)
              }}
            >
              Cancel
            </Button>
          )}
          <div className="flex gap-1">
            {onEdit && !isOverlay && (
              <Button
                size="icon"
                variant="outline"
                className="w-8 h-8 rounded-lg border-2"
                onClick={e => {
                  e.stopPropagation()
                  onEdit(order.name)
                }}
                title="Edit Order"
              >
                <Edit3 className="w-3.5 h-3.5" />
              </Button>
            )}
            <Button
              size="icon"
              variant="outline"
              className="w-8 h-8 rounded-lg border-2"
              onClick={e => {
                e.stopPropagation()
                onViewDetails(order.name)
              }}
              title="View Details"
            >
              <Eye className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function DroppableColumn({
  id,
  title,
  orders,
  onViewDetails,
  onEdit,
  onAccept,
  onReject,
  activeId,
}: {
  id: string
  title: string
  orders: Order[]
  onViewDetails: (id: string) => void
  onEdit?: (id: string) => void
  onAccept?: (id: string) => void
  onReject?: (id: string) => void
  activeId: string | null
}) {
  const { setNodeRef, isOver } = useDroppable({ id })

  const isAccepted = id === ACCEPTED_COLUMN_ID

  return (
    <div className="flex flex-col flex-1 min-w-0">
      <div
        className={cn(
          'rounded-lg px-4 py-2 mb-3 inline-flex items-center justify-center border',
          isAccepted
            ? 'bg-[#dff6dd] dark:bg-[#1b5e20] text-[#107c10] dark:text-[#81c784] border-[#92c5f7] dark:border-[#4caf50]'
            : 'bg-[#fff4ce] dark:bg-[#ca5010]/20 text-[#b45309] dark:text-[#ffd89b] border-[#ffe69d] dark:border-[#ca5010]/40'
        )}
      >
        <h3 className="font-bold text-sm uppercase tracking-wide flex items-center gap-2">
          {isAccepted && <CheckCircle2 className="h-4 w-4" />}
          {title} ({orders.length})
        </h3>
      </div>
      <div
        ref={setNodeRef}
        className={cn(
          'rounded-lg px-3 py-3 space-y-3 flex-1 min-h-[320px] overflow-y-auto border-2 transition-all duration-200',
          isOver
            ? 'bg-primary/10 dark:bg-primary/20 border-primary border-dashed'
            : 'border-border bg-muted/30'
        )}
      >
        {orders.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full min-h-[280px] text-center text-muted-foreground">
            <p className="text-sm font-medium">
              {isAccepted ? 'Accepted orders appear here' : 'No pending orders'}
            </p>
            <p className="text-xs mt-1">
              {isAccepted
                ? 'Drag orders here to accept'
                : 'Pay-at-counter orders awaiting verification'}
            </p>
          </div>
        ) : (
          orders.map((order) => (
            <div
              key={order.name}
              className={cn(activeId === order.name && 'opacity-0')}
            >
              <OrderCard
                order={order}
                onViewDetails={onViewDetails}
                onEdit={onEdit}
                onAccept={onAccept}
                onReject={onReject}
              />
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default function AcceptOrders() {
  const { selectedRestaurant, isGold } = useRestaurant()
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [activeOrder, setActiveOrder] = useState<Order | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [startInEditMode, setStartInEditMode] = useState(false)
  const { confirm, ConfirmDialogComponent } = useConfirm()

  const { data: orders, isLoading, mutate } = useFrappeGetDocList(
    'Order',
    {
      fields: [
        'name',
        'order_number',
        'status',
        'total',
        'creation',
        'restaurant',
        'table_number',
        'customer_name',
        'customer_phone',
        'payment_method',
        'payment_status',
      ],
      // Note: Frappe React hooks expect filters as an array for strict typing.
      // We use a typed filter array here to keep TS happy and avoid shape errors.
      filters: [
        ['restaurant', '=', selectedRestaurant || ''],
        ['status', '=', PENDING_STATUS],
        ['payment_method', '=', 'pay_at_counter'],
      ] as any,
      limit: 200,
      orderBy: { field: 'creation', order: 'asc' },
    },
    selectedRestaurant ? `accept-orders-${selectedRestaurant}` : null
  )

  const { call: updateOrderStatus } = useFrappePostCall(
    'flamezo_backend.flamezo.api.order_status.update_status'
  )

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 5 } }),
    useSensor(KeyboardSensor)
  )

  const pendingOrders = useMemo(() => {
    if (!orders || !Array.isArray(orders)) return []
    return orders.filter(
      (o: Order) =>
        o.status === PENDING_STATUS &&
        (o.payment_method === 'pay_at_counter' || !o.payment_method)
    )
  }, [orders])

  const handleDragStart = (event: DragStartEvent) => {
    const order = event.active.data.current?.order as Order | undefined
    if (order) {
      setActiveOrder(order)
      setActiveId(event.active.id as string)
    }
  }

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event
    setActiveOrder(null)
    setActiveId(null)

    if (!over || active.id === over.id) return

    const targetId = over.id as string
    if (targetId !== ACCEPTED_COLUMN_ID) return

    const orderId = active.id as string

    try {
      const response: any = await updateOrderStatus({ order_id: orderId, status: ACCEPTED_STATUS })
      const body = response?.message ?? response
      if (body?.success) {
        toast.success('Order accepted — pushed to KOT')
        mutate()
      } else {
        throw new Error(body?.error?.message || 'Failed to accept order')
      }
    } catch (error: any) {
      const msg = error?.message || 'Failed to accept order'
      console.error('Failed to accept order:', error)
      toast.error(msg)
      mutate()
    }
  }

  const handleViewDetails = (id: string) => {
    setStartInEditMode(false)
    setSelectedOrderId(id)
    setDialogOpen(true)
  }

  const handleEditOrder = (id: string) => {
    setStartInEditMode(true)
    setSelectedOrderId(id)
    setDialogOpen(true)
  }

  const handleAccept = async (orderId: string) => {
    try {
      const response: any = await updateOrderStatus({ order_id: orderId, status: ACCEPTED_STATUS })
      const body = response?.message ?? response
      if (body?.success) {
        toast.success('Order accepted — pushed to KOT')
        mutate()
      } else {
        throw new Error(body?.error?.message || 'Failed to accept order')
      }
    } catch (error: any) {
      const msg = error?.message || 'Failed to accept order'
      console.error('Failed to accept order:', error)
      toast.error(msg)
      mutate()
    }
  }

  const handleReject = async (orderId: string) => {
    try {
      const ok = await confirm({
        title: 'Cancel Order',
        description: 'Are you sure you want to cancel this order? This action cannot be undone.',
        confirmText: 'Cancel Order',
        cancelText: 'Keep Order',
        variant: 'destructive',
      })
      if (!ok) return

      const response: any = await updateOrderStatus({ order_id: orderId, status: REJECTED_STATUS })
      const body = response?.message ?? response
      if (body?.success) {
        toast.success('Order cancelled')
        mutate()
      } else {
        throw new Error(body?.error?.message || 'Failed to cancel order')
      }
    } catch (error: any) {
      const msg = error?.message || 'Failed to cancel order'
      console.error('Failed to cancel order:', error)
      toast.error(msg)
      mutate()
    }
  }

  if (!selectedRestaurant) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-center">
        <p className="text-muted-foreground">Select a restaurant to view pending orders</p>
      </div>
    )
  }

  if (!isGold) {
    return <LockedFeature feature="ordering" requiredPlan={['GOLD']} />
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      <div>
        <h2 className="text-xl sm:text-2xl font-semibold text-foreground tracking-tight">
          Accept Orders
        </h2>
        <p className="text-muted-foreground text-sm mt-1">
          Verify pay-at-counter orders at the table, then drag to Accepted to push to KOT
        </p>
      </div>

      <Card>
        <CardContent className="pt-6">
          {isLoading ? (
            <div className="flex items-center justify-center py-16 text-muted-foreground">
              Loading pending orders...
            </div>
          ) : (
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragStart={handleDragStart}
              onDragEnd={handleDragEnd}
            >
              <div className="flex gap-6 overflow-x-auto pb-4" style={{ minHeight: '420px' }}>
                <DroppableColumn
                  id={PENDING_STATUS}
                  title="Pending Verification"
                  orders={pendingOrders}
                  onViewDetails={handleViewDetails}
                  onEdit={handleEditOrder}
                  onAccept={handleAccept}
                  onReject={handleReject}
                  activeId={activeId}
                />
                <DroppableColumn
                  id={ACCEPTED_COLUMN_ID}
                  title="Accepted (push to KOT)"
                  orders={[]}
                  onViewDetails={handleViewDetails}
                  onEdit={handleEditOrder}
                  activeId={activeId}
                />
              </div>

              <DragOverlay
                dropAnimation={{
                  duration: 300,
                  easing: 'cubic-bezier(0.18, 0.67, 0.6, 1)',
                }}
                style={{ opacity: 0.95 }}
              >
                {activeOrder ? (
                  <OrderCard
                    order={activeOrder}
                    onViewDetails={handleViewDetails}
                    isOverlay
                  />
                ) : null}
              </DragOverlay>
            </DndContext>
          )}
        </CardContent>
      </Card>

      <OrderDetailsDialog
        orderId={selectedOrderId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        startInEditMode={startInEditMode}
      />

      {ConfirmDialogComponent}
    </div>
  )
}
