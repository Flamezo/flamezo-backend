import { useState, useMemo, useEffect } from 'react'
import { useFrappeGetDoc, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Search,
  ChevronRight,
  Clock,
  ShoppingBag,
  RefreshCcw,
  XCircle,
  LayoutDashboard,
  FilterX,
  List,
  KanbanSquare,
  LayoutGrid
} from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useCurrency } from '@/hooks/useCurrency'
import { useDataTable } from '@/hooks/useDataTable'
import { DataPagination } from '@/components/ui/DataPagination'
import { OrderDetailsDialog } from '@/components/OrderDetailsDialog'
import { CancelledOrdersDialog } from '@/components/CancelledOrdersDialog'
import { OrdersKanban } from '@/components/OrdersKanban'
import { OrdersModernView } from '@/components/OrdersModernView'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from 'sonner'

export default function Orders() {
  const { selectedRestaurant } = useRestaurant()
  const { formatAmountNoDecimals } = useCurrency()

  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null)
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [isCancelledDialogOpen, setIsCancelledDialogOpen] = useState(false)
  const [view, setView] = useState<'table' | 'kanban' | 'modern'>('modern')

  // Filters
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [tableFilter, setTableFilter] = useState('all')

  // Restaurant details to get filter context
  const { data: restaurant } = useFrappeGetDoc('Restaurant', selectedRestaurant || '', {
    enabled: !!selectedRestaurant,
    fields: ['name']
  })
  const restaurantFilter = restaurant?.name

  const {
    data: orders,
    isLoading,
    mutate,
    page,
    setPage,
    pageSize,
    setPageSize,
    totalCount,
    setSearchQuery: setServerSearchQuery,
    setFilters: setDataTableFilters
  } = useDataTable({
    doctype: 'Order',
    initialFilters: restaurantFilter ? [
      { fieldname: 'restaurant', operator: '=', value: restaurantFilter },
      { fieldname: 'status', operator: '!=', value: 'pending_verification' },
      { fieldname: 'creation', operator: '>=', value: new Date().toISOString().split('T')[0] },
    ] : [],
    fields: ['name', 'order_number', 'status', 'total', 'creation', 'restaurant', 'table_number', 'order_type', 'coupon', 'customer_name', 'customer_phone', 'payment_method', 'payment_status', 'subtotal', 'discount', 'tax', 'delivery_fee', 'packaging_fee', 'order_items'],
    initialPageSize: 100,
    searchFields: ['order_number', 'customer_name', 'customer_phone', 'name'],
    debugId: `orders-${restaurantFilter}`
  })

  // Synchronize local UI filters with useDataTable
  useEffect(() => {
    const newFilters = [
      { fieldname: 'restaurant', operator: '=', value: restaurantFilter },
      { fieldname: 'status', operator: '!=', value: 'pending_verification' },
      { fieldname: 'creation', operator: '>=', value: new Date().toISOString().split('T')[0] },
    ]
    if (statusFilter !== 'all') {
      newFilters.push({ fieldname: 'status', operator: '=', value: statusFilter })
    }
    if (tableFilter !== 'all') {
      newFilters.push({ fieldname: 'table_number', operator: '=', value: tableFilter })
    }
    setDataTableFilters(newFilters)
  }, [statusFilter, tableFilter, restaurantFilter, setDataTableFilters])

  useEffect(() => {
    setServerSearchQuery(searchQuery)
  }, [searchQuery, setServerSearchQuery])

  // Table options from orders
  const uniqueTables = useMemo(() => {
    if (!orders) return []
    const tables = new Set(orders.map((o: any) => o.table_number).filter(Boolean))
    return Array.from(tables).sort((a: any, b: any) => String(a).localeCompare(String(b)))
  }, [orders])

  // We use orders directly from the hook which handles server-side filtering
  const filteredOrders = orders || []

  const clearFilters = () => {
    setSearchQuery('')
    setStatusFilter('all')
    setTableFilter('all')
  }

  const { call: updateStatusApi } = useFrappePostCall('flamezo_backend.flamezo.api.order_status.update_status')

  const handleUpdateStatus = async (orderId: string, status: string) => {
    try {
      await updateStatusApi({
        order_id: orderId,
        status: status
      })
      toast.success(`Order marked as ${status}`)
      mutate()
    } catch (e: any) {
      toast.error(e.message)
    }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6 pb-20">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-foreground flex items-center gap-2">
            <LayoutDashboard className="h-6 w-6 text-primary" />
            Live Orders
          </h1>
          <p className="text-sm text-muted-foreground">Monitor and manage incoming orders in real-time.</p>
        </div>
        <div className="flex items-center gap-2">
          {/* View Switcher */}
          <div className="flex bg-muted/50 p-1 rounded-lg border border-border/50 mr-2">
            <Button 
              variant={view === 'table' ? 'secondary' : 'ghost'} 
              size="sm" 
              className={cn("h-8 px-2.5 gap-2", view === 'table' ? "bg-background shadow-sm" : "text-muted-foreground")}
              onClick={() => setView('table')}
            >
              <List className="h-4 w-4" />
              <span className="text-xs font-bold hidden lg:inline">Table</span>
            </Button>
            <Button 
              variant={view === 'kanban' ? 'secondary' : 'ghost'} 
              size="sm" 
              className={cn("h-8 px-2.5 gap-2", view === 'kanban' ? "bg-background shadow-sm" : "text-muted-foreground")}
              onClick={() => setView('kanban')}
            >
              <KanbanSquare className="h-4 w-4" />
              <span className="text-xs font-bold hidden lg:inline">Kanban</span>
            </Button>
            <Button 
              variant={view === 'modern' ? 'secondary' : 'ghost'} 
              size="sm" 
              className={cn("h-8 px-2.5 gap-2", view === 'modern' ? "bg-background shadow-sm" : "text-muted-foreground")}
              onClick={() => setView('modern')}
            >
              <LayoutGrid className="h-4 w-4" />
              <span className="text-xs font-bold hidden lg:inline">Modern</span>
            </Button>
          </div>

          <Button variant="outline" size="sm" className="gap-2 h-10" onClick={() => mutate()} disabled={isLoading}>
            <RefreshCcw className={cn("h-4 w-4", isLoading && "animate-spin")} />
            Refresh
          </Button>
          <Button variant="outline" size="sm" className="gap-2 text-red-600 hover:text-red-700 hover:bg-red-50 h-10" onClick={() => setIsCancelledDialogOpen(true)}>
            <XCircle className="h-4 w-4" />
            Cancelled
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card className="border-none shadow-sm bg-card/50 backdrop-blur-sm">
        <CardContent className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Order #, Name, Phone..."
                className="pl-9 h-10"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="h-10">
                <SelectValue placeholder="All Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Live Status</SelectItem>
                <SelectItem value="confirmed">Confirmed</SelectItem>
                <SelectItem value="preparing">Preparing</SelectItem>
                <SelectItem value="prepared">Ready</SelectItem>
                <SelectItem value="delivered">Completed</SelectItem>
              </SelectContent>
            </Select>

            <Select value={tableFilter} onValueChange={setTableFilter}>
              <SelectTrigger className="h-10">
                <SelectValue placeholder="All Tables" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Tables</SelectItem>
                {uniqueTables.map((t: any) => (
                  <SelectItem key={t} value={t}>Table {t}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Button variant="ghost" className="h-10 gap-2 font-bold uppercase text-[10px] tracking-widest text-muted-foreground hover:text-destructive" onClick={clearFilters}>
              <FilterX className="h-4 w-4" />
              Reset Filters
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Orders View Content */}
      {view === 'table' ? (
        <Card className="shadow-xl border-none overflow-hidden bg-card/50 backdrop-blur-sm">
          <CardContent className="p-0">
            <Table>
              <TableHeader className="bg-muted/50">
                <TableRow>
                  <TableHead className="w-[100px] font-bold">Order #</TableHead>
                  <TableHead className="font-bold">Customer</TableHead>
                  <TableHead className="font-bold">Items</TableHead>
                  <TableHead className="font-bold">Total</TableHead>
                  <TableHead className="font-bold">Status</TableHead>
                  <TableHead className="font-bold text-center">Table</TableHead>
                  <TableHead className="text-right pr-6 font-bold">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading && orders?.length === 0 ? (
                  [1, 2, 3, 4, 5].map(i => (
                    <TableRow key={i}>
                      <TableCell colSpan={7}><Skeleton className="h-12 w-full" /></TableCell>
                    </TableRow>
                  ))
                ) : filteredOrders.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="h-64 text-center">
                      <div className="flex flex-col items-center gap-3 opacity-40">
                        <ShoppingBag className="h-12 w-12" />
                        <p className="text-sm font-bold uppercase tracking-widest">No active orders today</p>
                      </div>
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredOrders.map((order: any) => (
                    <TableRow key={order.name} className="group hover:bg-muted/30 transition-colors cursor-pointer" onClick={() => { setSelectedOrderId(order.name); setIsDialogOpen(true); }}>
                      <TableCell className="font-black text-primary">#{order.order_number}</TableCell>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="font-bold text-foreground">{order.customer_name || 'Guest'}</span>
                          <span className="text-[10px] text-muted-foreground">{order.customer_phone || '—'}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex -space-x-2 overflow-hidden">
                          {order.order_items?.slice(0, 3).map((item: any, i: number) => (
                            <div key={i} className="inline-block h-6 w-6 rounded-full ring-2 ring-background bg-muted flex items-center justify-center text-[8px] font-bold overflow-hidden" title={item.item_name}>
                              {item.item_name?.[0]}
                            </div>
                          ))}
                          {order.order_items?.length > 3 && (
                            <div className="inline-block h-6 w-6 rounded-full ring-2 ring-background bg-muted flex items-center justify-center text-[8px] font-bold">
                              +{order.order_items.length - 3}
                            </div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="font-black">₹{formatAmountNoDecimals(order.total)}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={cn(
                          "font-bold uppercase text-[9px] tracking-wider py-0.5",
                          order.status === 'confirmed' && "bg-blue-100 text-blue-700 border-blue-200",
                          order.status === 'preparing' && "bg-amber-100 text-amber-700 border-amber-200",
                          order.status === 'prepared' && "bg-emerald-100 text-emerald-700 border-emerald-200 animate-pulse",
                          order.status === 'delivered' && "bg-slate-100 text-slate-500",
                        )}>
                          {order.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-center">
                        {order.table_number ? (
                          <Badge variant="secondary" className="font-black">T-{order.table_number}</Badge>
                        ) : <span className="text-muted-foreground">—</span>}
                      </TableCell>
                      <TableCell className="text-right pr-6">
                        <Button variant="ghost" size="sm" className="opacity-0 group-hover:opacity-100 gap-2 transition-all">
                          Details
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>

            <div className="p-4 border-t">
              <DataPagination
                currentPage={page}
                totalCount={totalCount}
                pageSize={pageSize}
                onPageChange={setPage}
                onPageSizeChange={setPageSize}
                isLoading={isLoading}
              />
            </div>
          </CardContent>
        </Card>
      ) : view === 'kanban' ? (
        <OrdersKanban 
          orders={filteredOrders}
          onCheckOrder={(id) => { setSelectedOrderId(id); setIsDialogOpen(true); }}
          onOrderUpdate={() => mutate()}
          restaurantTables={restaurant?.total_tables || 0}
        />
      ) : (
        <OrdersModernView 
          orders={filteredOrders}
          onCheckOrder={(id) => { setSelectedOrderId(id); setIsDialogOpen(true); }}
          onOrderUpdate={() => mutate()}
          onShowCancelled={() => setIsCancelledDialogOpen(true)}
        />
      )}


      <OrderDetailsDialog
        orderId={selectedOrderId}
        open={isDialogOpen}
        onOpenChange={setIsDialogOpen}
      />

      <CancelledOrdersDialog
        isOpen={isCancelledDialogOpen}
        onClose={() => setIsCancelledDialogOpen(false)}
        orders={orders || []}
      />
    </div>
  )
}
