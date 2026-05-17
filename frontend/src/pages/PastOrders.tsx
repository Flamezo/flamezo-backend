import { useState } from 'react'
import { useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent } from '@/components/ui/card'
import { cn, getFrappeError } from '@/lib/utils'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DatePicker } from '@/components/ui/date-picker'
import { Eye, Filter, X, Search, Calendar, History, ReceiptText, ClipboardList } from 'lucide-react'
import { OrderDetailsDialog } from '@/components/OrderDetailsDialog'
import { LockedFeature } from '@/components/FeatureGate/LockedFeature'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { toast } from 'sonner'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useDataTable } from '@/hooks/useDataTable'
import { DataPagination } from '@/components/ui/DataPagination'

export default function PastOrders() {
  const { selectedRestaurant, isGold } = useRestaurant()
  
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null)
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [showBilledOnly, setShowBilledOnly] = useState(false)
  
  // Filter states
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const {
    data: orders,
    isLoading,
    mutate,
    page,
    setPage,
    pageSize,
    setPageSize,
    totalCount,
    searchQuery,
    setSearchQuery
  } = useDataTable({
    customEndpoint: 'flamezo_backend.flamezo.api.orders.get_orders',
    customParams: {
      restaurant_id: selectedRestaurant,
      status: showBilledOnly ? 'billed' : (statusFilter === 'all' ? undefined : statusFilter),
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      admin_mode: true
    },
    paramNames: {
      page: 'page',
      pageSize: 'limit',
      search: 'search_query'
    },
    initialPageSize: 20,
    debugId: `past-orders-${selectedRestaurant}-${showBilledOnly}`
  })

  // API calls
  const { call: updateOrderStatus } = useFrappePostCall('flamezo_backend.flamezo.api.order_status.update_status')

  // Normalize status value (handle legacy "in_billing" format)
  const normalizeStatus = (status: string): string => {
    if (status === 'in_billing') return 'In Billing'
    return status
  }

  const handleStatusChange = async (orderId: string, newStatus: string) => {
    try {
      const normalizedStatus = normalizeStatus(newStatus)
      await updateOrderStatus({
        order_id: orderId,
        status: normalizedStatus
      })
      
      const statusLabels: Record<string, string> = {
        'confirmed': 'Confirmed',
        'preparing': 'Preparing',
        'ready': 'Ready',
        'In Billing': 'In Billing',
        'delivered': 'Delivered',
        'billed': 'Billed',
        'cancelled': 'Cancelled'
      }
      
      toast.success(`Order status updated to ${statusLabels[normalizedStatus] || normalizedStatus}`)
      mutate()
    } catch (error: any) {
      console.error('Failed to update order status:', error)
      toast.error('Failed to update status', { description: getFrappeError(error) })
    }
  }

  const handleCheckOrder = (orderId: string) => {
    setSelectedOrderId(orderId)
    setIsDialogOpen(true)
  }

  const getStatusColor = (status: string) => {
    const s = status.toLowerCase()
    if (s === 'delivered' || s === 'billed') return 'bg-green-500/10 text-green-600 border-green-200'
    if (s === 'cancelled') return 'bg-red-500/10 text-red-600 border-red-200'
    if (s === 'confirmed') return 'bg-orange-500/10 text-orange-600 border-orange-200'
    if (s === 'preparing') return 'bg-purple-500/10 text-purple-600 border-purple-200'
    if (s === 'ready') return 'bg-blue-500/10 text-blue-600 border-blue-200'
    if (s === 'in billing' || s === 'in_billing') return 'bg-amber-500/10 text-amber-600 border-amber-200'
    return 'bg-muted text-muted-foreground border-border'
  }

  if (!isGold) {
    return <LockedFeature feature="ordering" requiredPlan={['GOLD']} />
  }

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4">
        <div className="space-y-1">
          <h2 className="text-2xl font-bold tracking-tight">Order Archives</h2>
          <p className="text-muted-foreground text-sm flex items-center gap-2">
            <History className="h-3.5 w-3.5" />
            {showBilledOnly 
              ? "Today's Settlement & Billed Activity" 
              : "Full transaction history across your restaurant network"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
           <div className="flex bg-muted/50 p-1 rounded-xl border border-border">
              <Button
                variant={!showBilledOnly ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setShowBilledOnly(false)}
                className={cn("rounded-lg text-xs font-semibold h-9", !showBilledOnly ? "shadow-sm" : "opacity-60")}
              >
                <ClipboardList className="h-3.5 w-3.5 mr-2" />
                All History
              </Button>
              <Button
                variant={showBilledOnly ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setShowBilledOnly(true)}
                className={cn("rounded-lg text-xs font-semibold h-9", showBilledOnly ? "shadow-sm" : "opacity-60")}
              >
                <ReceiptText className="h-3.5 w-3.5 mr-2" />
                Billed Only
              </Button>
           </div>
          <Button
            variant={showFilters ? 'default' : 'outline'}
            size="sm"
            onClick={() => setShowFilters(!showFilters)}
            className="h-11 px-4 rounded-xl shadow-none"
          >
            <Filter className={cn("h-4 w-4 mr-2", showFilters ? "fill-current" : "")} />
            Advanced
          </Button>
        </div>
      </div>

      {showFilters && (
        <Card className="border-none shadow-sm ring-1 ring-border bg-muted/10 animate-in fade-in slide-in-from-top-2 duration-300">
          <CardContent className="pt-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/50" />
                <Input
                  placeholder="Order ID / Mobile / Coupon..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9 h-10 rounded-xl bg-card shadow-none"
                />
              </div>

              {!showBilledOnly && (
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="h-10 rounded-xl bg-card shadow-none">
                    <SelectValue placeholder="All Statuses" />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl">
                    <SelectItem value="all">All Statuses</SelectItem>
                    <SelectItem value="confirmed">Confirmed</SelectItem>
                    <SelectItem value="preparing">Preparing</SelectItem>
                    <SelectItem value="ready">Ready</SelectItem>
                    <SelectItem value="In Billing">In Billing</SelectItem>
                    <SelectItem value="delivered">Delivered</SelectItem>
                    <SelectItem value="billed">Billed</SelectItem>
                    <SelectItem value="cancelled">Cancelled</SelectItem>
                  </SelectContent>
                </Select>
              )}

              <div className="flex gap-2 lg:col-span-2">
                <div className="relative flex-1">
                  <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/50 pointer-events-none" />
                  <DatePicker
                    value={dateFrom}
                    onChange={(v) => setDateFrom(v)}
                    placeholder="From Date"
                  />
                </div>
                <div className="relative flex-1">
                  <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/50 pointer-events-none" />
                  <DatePicker
                    value={dateTo}
                    onChange={(v) => setDateTo(v)}
                    placeholder="To Date"
                  />
                </div>
              </div>
            </div>

            {(searchQuery || statusFilter !== 'all' || dateFrom || dateTo) && (
              <div className="mt-4 flex justify-end">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setSearchQuery('')
                    setStatusFilter('all')
                    setDateFrom('')
                    setDateTo('')
                  }}
                  className="text-xs font-bold uppercase tracking-wider text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3 w-3 mr-2" />
                  Reset Filters
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          {!selectedRestaurant ? (
            <div className="py-20 text-center text-muted-foreground">
              Select a restaurant to view order archives
            </div>
          ) : isLoading && !orders.length ? (
            <div className="py-20 flex justify-center">
              <div className="animate-spin h-6 w-6 border-2 border-primary border-t-transparent rounded-full" />
            </div>
          ) : !orders || orders.length === 0 ? (
            <div className="py-20 text-center text-muted-foreground">
              No orders matched your criteria
            </div>
          ) : (
            <>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="pl-4">Order #</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Customer</TableHead>
                      <TableHead>Revenue</TableHead>
                      <TableHead>Timestamp</TableHead>
                      <TableHead className="text-right pr-4">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {orders.map((order: any) => (
                      <TableRow key={order.name}>
                        <TableCell className="pl-4 font-medium">
                          {order.order_number || order.name}
                        </TableCell>
                        <TableCell>
                          <Select
                            value={normalizeStatus(order.status || 'confirmed')}
                            onValueChange={(v) => handleStatusChange(order.name, v)}
                          >
                            <SelectTrigger className={cn("h-8 w-[120px] text-xs", getStatusColor(order.status))}>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="confirmed">Confirmed</SelectItem>
                              <SelectItem value="preparing">Preparing</SelectItem>
                              <SelectItem value="ready">Ready</SelectItem>
                              <SelectItem value="In Billing">In Billing</SelectItem>
                              <SelectItem value="delivered">Delivered</SelectItem>
                              <SelectItem value="billed">Billed</SelectItem>
                              <SelectItem value="cancelled">Cancelled</SelectItem>
                            </SelectContent>
                          </Select>
                        </TableCell>
                        <TableCell>
                          <div className="text-sm font-medium">{order.customer_name || 'Guest'}</div>
                          <div className="text-xs text-muted-foreground">{order.customer_phone || '—'}</div>
                        </TableCell>
                        <TableCell className="font-semibold">₹{order.total || 0}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {order.creation ? new Date(order.creation).toLocaleString('en-IN', {
                            day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
                          }) : '—'}
                        </TableCell>
                        <TableCell className="text-right pr-4">
                          <Button variant="ghost" size="icon" onClick={() => handleCheckOrder(order.name)}>
                            <Eye className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

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
            </>
          )}
        </CardContent>
      </Card>

      <OrderDetailsDialog
        orderId={selectedOrderId}
        open={isDialogOpen}
        onOpenChange={setIsDialogOpen}
      />
    </div>
  )
}
