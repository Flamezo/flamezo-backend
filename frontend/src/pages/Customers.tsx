import { Fragment, useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useFrappePostCall } from '@/lib/frappe'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useCurrency } from '@/hooks/useCurrency'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Users, Loader2, CheckCircle, ChevronDown, ChevronRight, Eye, Star, Search, UserCheck, Upload, Import, Lock, Unlock, Coins } from 'lucide-react'
import CustomerImportModal from '@/components/CustomerImportModal'
import { toast } from 'sonner'
import { useDataTable } from '@/hooks/useDataTable'
import { DataPagination } from '@/components/ui/DataPagination'

interface OrderItem {
  name: string
  order_number: string
  total: number
  status: string
  creation: string
  customer_rating?: number
  customer_feedback?: string
  food_rating?: number
  service_rating?: number
}

interface RestaurantCustomer {
  id: string
  phone: string | null
  customerName: string
  verifiedAt: string | null
  birthday: string | null
  lastVisited: string | null
  isImported?: boolean
  orders: OrderItem[]
  tableBookings: unknown[]
  banquetBookings: unknown[]
  is_unlocked?: boolean
}

interface RestaurantData {
  restaurant_id: string
  restaurant_name: string
  orders: OrderItem[]
  tableBookings: unknown[]
  banquetBookings: unknown[]
}

interface CustomerProfileData {
  success: boolean
  data?: {
    customer: { id: string; phone: string; customerName: string; email?: string; birthday?: string; verifiedAt?: string }
    restaurants: RestaurantData[]
  }
  error?: string
}

export default function Customers() {
  const { selectedRestaurant } = useRestaurant()
  const { formatAmountNoDecimals } = useCurrency()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [profileCustomerId, setProfileCustomerId] = useState<string | null>(null)
  const [profileData, setProfileData] = useState<CustomerProfileData | null>(null)
  const [profileLoading, setProfileLoading] = useState(false)
  const [isUpdatingVerify, setIsUpdatingVerify] = useState(false)
  const [importOpen, setImportOpen] = useState(false)

  const {
    data: fetchedCustomers,
    isLoading,
    page,
    setPage,
    pageSize,
    setPageSize,
    totalCount,
    searchQuery,
    setSearchQuery,
    mutate: refreshCustomers
  } = useDataTable
      <RestaurantCustomer>({
        customEndpoint: 'flamezo_backend.flamezo.api.customers.get_restaurant_customers',
        customParams: { restaurant_id: selectedRestaurant },
        paramNames: {
          page: 'page',
          pageSize: 'page_size',
          search: 'search'
        },
        initialPageSize: 20,
        debugId: `restaurant-customers-${selectedRestaurant}`
      })

  // Customer data extractor
  const customers = useMemo(() => {
    return fetchedCustomers || []
  }, [fetchedCustomers])

  const { restaurantConfig, refreshConfig, isSilver, planType } = useRestaurant()
  const isVerifyEnabled = restaurantConfig?.settings?.verifyMyUser ?? false

  const { call: setValue } = useFrappePostCall('frappe.client.set_value')
  const { call: unlockCustomerApi } = useFrappePostCall('flamezo_backend.flamezo.api.customers.unlock_customer_data')

  const handleUnlockCustomer = async (customerId: string) => {
    try {
      const res = await unlockCustomerApi({
        restaurant_id: selectedRestaurant,
        customer_id: customerId
      })
      const body = (res as any)?.message || res
      if (body.success) {
        toast.success(body.message || 'Profile unlocked!')
        refreshCustomers()
      } else {
        toast.error(body.error || 'Failed to unlock profile')
      }
    } catch (err) {
      toast.error('Internal error occurred')
    }
  }

  const handleToggleVerify = async (checked: boolean) => {
    if (!selectedRestaurant) return
    setIsUpdatingVerify(true)
    try {
      await setValue({
        doctype: 'Restaurant Config',
        name: selectedRestaurant,
        fieldname: 'verify_my_user',
        value: checked ? 1 : 0
      })
      toast.success(checked ? 'User verification enabled' : 'User verification disabled')
      await refreshConfig()
    } catch (err) {
      toast.error('Failed to update verification setting')
    } finally {
      setIsUpdatingVerify(false)
    }
  }

  const { call: getCustomerProfile } = useFrappePostCall(
    'flamezo_backend.flamezo.api.customers.get_customer_profile'
  )

  const handleViewFullProfile = async (customerId: string) => {
    setProfileCustomerId(customerId)
    setProfileLoading(true)
    setProfileData(null)
    try {
      const res = await getCustomerProfile({ customer_id: customerId, restaurant_id: selectedRestaurant })
      const body = (res as { message?: CustomerProfileData })?.message ?? (res as CustomerProfileData)
      setProfileData(body)
    } catch {
      toast.error('Failed to load customer profile')
    } finally {
      setProfileLoading(false)
    }
  }

  const formatDate = (d: string) => {
    try {
      return new Date(d).toLocaleDateString('en-IN', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    } catch {
      return d
    }
  }

  if (!selectedRestaurant) {
    return (
      <div className="p-6">
        <Card className="border-none shadow-sm ring-1 ring-border">
          <CardContent className="pt-12 pb-12">
            <div className="flex flex-col items-center justify-center text-center space-y-3">
              <div className="h-12 w-12 bg-muted rounded-full flex items-center justify-center">
                <UserCheck className="h-6 w-6 text-muted-foreground/50" />
              </div>
              <p className="text-muted-foreground font-medium">
                Select a restaurant from the dropdown to view customers.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Customers</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Build and manage your loyal customer base
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-2 h-9 rounded-xl border-dashed self-start sm:self-auto"
          onClick={() => setImportOpen(true)}
        >
          <Upload className="h-4 w-4" />
          Import Customers
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <CardTitle>Customer Directory</CardTitle>
              <CardDescription>
                {totalCount} total customers have interacted with your restaurant
              </CardDescription>
            </div>
            <div className="flex flex-col sm:flex-row items-center gap-4">
              {!isSilver && (
                <div className="flex items-center gap-2 bg-muted/30 px-3 py-1.5 rounded-xl border border-border/50">
                  <Switch
                    id="verify-user-card"
                    checked={isVerifyEnabled}
                    onCheckedChange={handleToggleVerify}
                    disabled={isUpdatingVerify}
                    className="scale-90"
                  />
                  <Label htmlFor="verify-user-card" className="text-[10px] font-black uppercase tracking-widest text-muted-foreground mr-1 cursor-pointer">Verify Users</Label>
                </div>
              )}
              <div className="relative w-full sm:w-64">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/60" />
                <Input
                  placeholder="Search name or phone..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9 h-10 rounded-xl bg-card border-border shadow-none"
                />
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading && !customers.length ? (
            <div className="py-20 flex justify-center">
              <div className="animate-spin h-6 w-6 border-2 border-primary border-t-transparent rounded-full" />
            </div>
          ) : customers.length === 0 ? (
            <div className="py-20 text-center text-muted-foreground">No customers found</div>
          ) : (
            <>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[50px]"></TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Phone</TableHead>
                      <TableHead>Last Visited</TableHead>
                      <TableHead className="text-center">Verified</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {customers.map((c) => {
                      const isExpanded = expandedId === c.id
                      const hasOrders = c.orders && c.orders.length > 0
                      return (
                        <Fragment key={c.id}>
                          <TableRow>
                            <TableCell className="text-center">
                              {hasOrders && (
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => setExpandedId(isExpanded ? null : c.id)}
                                  className="h-8 w-8"
                                >
                                  {isExpanded ? (
                                    <ChevronDown className="h-4 w-4" />
                                  ) : (
                                    <ChevronRight className="h-4 w-4" />
                                  )}
                                </Button>
                              )}
                            </TableCell>
                            <TableCell className="font-medium">
                              <div className="flex items-center gap-2">
                                <div className={!c.is_unlocked && isSilver ? "select-none opacity-40 brightness-50" : ""}>
                                  {c.customerName || '—'}
                                </div>
                                {c.isImported && (
                                  <div className="relative group inline-flex items-center">
                                    <Import className="h-3 w-3 text-blue-500 cursor-default" />
                                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-[100]">
                                      <div className="bg-slate-900 text-white text-[10px] px-2 py-1 rounded shadow-xl whitespace-nowrap font-medium ring-1 ring-white/10">
                                        Imported by restaurant
                                        <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-900" />
                                      </div>
                                    </div>
                                  </div>
                                )}
                              </div>
                            </TableCell>
                            <TableCell>
                              <div className={!c.is_unlocked && isSilver ? "select-none opacity-40 brightness-50" : ""}>
                                {c.phone || '—'}
                              </div>
                            </TableCell>
                            <TableCell className="text-muted-foreground">
                              {c.lastVisited ? formatDate(c.lastVisited) : '—'}
                            </TableCell>
                            <TableCell className="text-center">
                              {c.verifiedAt ? (
                                <Badge variant="outline" className="text-green-600 border-green-200 bg-green-50">Verified</Badge>
                              ) : (
                                <Badge variant="secondary">Unverified</Badge>
                              )}
                            </TableCell>
                            <TableCell className="text-right">
                              <div className="flex items-center justify-end gap-2">
                                {!c.is_unlocked && isSilver && (
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleUnlockCustomer(c.id)}
                                    className="h-8 rounded-lg bg-primary/5 hover:bg-primary/10 border-primary/20 text-primary font-bold transition-all hover:scale-[1.02] active:scale-[0.98] group"
                                  >
                                    <Coins className="h-3.5 w-3.5 mr-1.5 group-hover:rotate-12 transition-transform" />
                                    5 Credits
                                  </Button>
                                )}
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleViewFullProfile(c.id)}
                                  className="h-8"
                                  disabled={!c.is_unlocked && isSilver}
                                >
                                  <Eye className="h-4 w-4 mr-2" />
                                  Profile
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                          {isExpanded && hasOrders && (
                            <TableRow>
                              <TableCell colSpan={6} className="bg-muted/30 p-4">
                                <div className="rounded-md border bg-card">
                                  <Table>
                                    <TableHeader>
                                      <TableRow>
                                        <TableHead className="pl-4">Order #</TableHead>
                                        <TableHead>Date</TableHead>
                                        <TableHead>Amount</TableHead>
                                        <TableHead className="text-center">Status</TableHead>
                                        <TableHead>Rating</TableHead>
                                        <TableHead className="text-right pr-4">Actions</TableHead>
                                      </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                      {c.orders.map((o) => (
                                        <TableRow key={o.name}>
                                          <TableCell className="pl-4 font-medium text-primary">
                                            <Link to={`/orders/${o.name}`} className="hover:underline">
                                              {o.order_number}
                                            </Link>
                                          </TableCell>
                                          <TableCell className="text-muted-foreground">{formatDate(o.creation)}</TableCell>
                                          <TableCell className="font-semibold">{formatAmountNoDecimals(o.total ?? 0)}</TableCell>
                                          <TableCell className="text-center">
                                            <Badge variant="outline" className="capitalize">{o.status}</Badge>
                                          </TableCell>
                                          <TableCell>
                                            {(o.food_rating ?? o.customer_rating) != null ? (
                                              <div className="flex items-center gap-1">
                                                <Star className="h-3 w-3 fill-amber-500 text-amber-500" />
                                                <span className="text-xs font-medium">{o.food_rating ?? o.customer_rating}.0</span>
                                              </div>
                                            ) : '—'}
                                          </TableCell>
                                          <TableCell className="text-right pr-4">
                                            <Link to={`/orders/${o.name}`}>
                                              <Button variant="outline" size="sm" className="h-7 text-xs">Details</Button>
                                            </Link>
                                          </TableCell>
                                        </TableRow>
                                      ))}
                                    </TableBody>
                                  </Table>
                                </div>
                              </TableCell>
                            </TableRow>
                          )}
                        </Fragment>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>

              <DataPagination
                currentPage={page}
                totalCount={totalCount}
                pageSize={pageSize}
                onPageChange={setPage}
                onPageSizeChange={setPageSize}
                isLoading={isLoading}
              />
            </>
          )}
        </CardContent>
      </Card>

      <CustomerImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        restaurantId={selectedRestaurant}
        onImportComplete={() => {
          setImportOpen(false)
          refreshCustomers()
        }}
      />

      {/* Admin: Full Customer Profile Dialog */}
      <Dialog open={!!profileCustomerId} onOpenChange={(open) => !open && setProfileCustomerId(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto rounded-2xl border-none shadow-2xl p-0">
          <div className="bg-muted/30 p-6 rounded-t-2xl border-b border-border/50">
            <DialogHeader className="flex flex-row items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className="h-12 w-12 bg-primary/10 rounded-full flex items-center justify-center">
                  <Users className="h-6 w-6 text-primary" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <DialogTitle className="text-xl font-bold tracking-tight">
                      {profileData?.data?.customer?.customerName || "Customer Profile"}
                    </DialogTitle>
                    {profileData?.data?.customer?.verifiedAt && (
                      <Badge variant="secondary" className="gap-1 bg-emerald-500/10 text-emerald-600 border-none shadow-none px-2 py-0 h-5 text-[10px]">
                        <CheckCircle className="h-3 w-3" />
                        Verified
                      </Badge>
                    )}
                  </div>
                  {profileData?.data?.customer ? (
                    <DialogDescription className="text-sm font-medium mt-1 text-muted-foreground flex items-center gap-2">
                      <span>{profileData.data.customer.phone}</span>
                      {profileData.data.customer.email && <span>•</span>}
                      {profileData.data.customer.email && <span>{profileData.data.customer.email}</span>}
                      {profileData.data.customer.birthday && <span>•</span>}
                      {profileData.data.customer.birthday && (
                        <span className="flex items-center gap-1">
                          <span className="text-primary/70">🎂</span> {formatDate(profileData.data.customer.birthday)}
                        </span>
                      )}
                    </DialogDescription>
                  ) : (
                    <DialogDescription className="text-xs">
                      Insights and order history for this customer
                    </DialogDescription>
                  )}
                </div>
              </div>
            </DialogHeader>
          </div>
          <div className="p-6 pt-4">
            {profileLoading ? (
              <div className="flex flex-col items-center justify-center py-20 space-y-4">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Building Profile...</p>
              </div>
            ) : profileData?.data ? (
              <div className="space-y-6">
                <div>
                  {profileData.data.restaurants.map((rest) => (
                    <div key={rest.restaurant_id} className="space-y-4">
                      {rest.orders && rest.orders.length > 0 && (
                        <div className="text-sm">
                          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Order History</p>
                          <div className="rounded-md border bg-card/50">
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead className="pl-4 h-9 text-xs">Order #</TableHead>
                                  <TableHead className="h-9 text-xs">Date</TableHead>
                                  <TableHead className="h-9 text-xs">Amount</TableHead>
                                  <TableHead className="text-center h-9 text-xs">Status</TableHead>
                                  <TableHead className="h-9 text-xs">Rating</TableHead>
                                  <TableHead className="text-right pr-4 h-9 text-xs">Actions</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {rest.orders.map((o: OrderItem) => (
                                  <TableRow key={o.name} className="hover:bg-muted/50 border-border/50">
                                    <TableCell className="pl-4 font-bold text-primary py-2 text-xs">
                                      <Link to={`/orders/${o.name}`} className="hover:underline">
                                        {o.order_number}
                                      </Link>
                                    </TableCell>
                                    <TableCell className="text-muted-foreground py-2 text-xs">{formatDate(o.creation)}</TableCell>
                                    <TableCell className="font-bold py-2 text-xs">{formatAmountNoDecimals(o.total ?? 0)}</TableCell>
                                    <TableCell className="text-center py-2 text-xs">
                                      <Badge variant="outline" className="capitalize text-[10px] h-5 py-0 px-1.5">{o.status}</Badge>
                                    </TableCell>
                                    <TableCell className="py-2 text-xs">
                                      {(o.food_rating ?? o.customer_rating) != null ? (
                                        <Badge variant="outline" className="border-amber-200 text-amber-600 bg-amber-50 h-5 px-1.5 py-0 text-[10px] font-bold">
                                          <Star className="h-2.5 w-2.5 fill-amber-500 mr-1" />
                                          {o.food_rating ?? o.customer_rating}.0
                                        </Badge>
                                      ) : <span className="text-muted-foreground/50">—</span>}
                                    </TableCell>
                                    <TableCell className="text-right pr-4 py-2">
                                      <Link to={`/orders/${o.name}`}>
                                        <Button variant="ghost" size="sm" className="h-6 text-[10px] font-semibold px-2">View</Button>
                                      </Link>
                                    </TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </div>
                        </div>
                      )}
                      <div className="flex gap-4">
                        {rest.tableBookings && rest.tableBookings.length > 0 && (
                          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                            Bookings: <span className="text-foreground">{rest.tableBookings.length}</span>
                          </p>
                        )}
                        {rest.banquetBookings && rest.banquetBookings.length > 0 && (
                          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                            Banquets: <span className="text-foreground">{rest.banquetBookings.length}</span>
                          </p>
                        )}
                      </div>
                      {(!rest.orders || rest.orders.length === 0) &&
                        (!rest.tableBookings || rest.tableBookings.length === 0) &&
                        (!rest.banquetBookings || rest.banquetBookings.length === 0) && (
                          <div className="py-12 flex flex-col items-center justify-center border rounded-md border-dashed border-border/60 bg-muted/10">
                            <p className="text-sm font-medium text-muted-foreground">No transaction history found</p>
                          </div>
                        )}
                    </div>
                  ))}
                </div>
              </div>
            ) : profileData && !profileData.data && (
              <div className="py-20 text-center">
                <p className="text-muted-foreground text-sm font-medium">
                  {profileData.error || 'Profile retrieval failed. Please try again.'}
                </p>
              </div>
            )}
          </div>
          <div className="p-4 bg-muted/20 border-t border-border/50 rounded-b-2xl flex justify-end">
            <Button variant="ghost" onClick={() => setProfileCustomerId(null)} className="h-9 px-6 font-semibold">Close</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
