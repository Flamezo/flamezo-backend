import { Fragment, useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useFrappePostCall } from '@/lib/frappe'
import { useOutlet } from '@/contexts/OutletContext'
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
import { Users, Loader2, CheckCircle, ChevronDown, ChevronRight, Eye, Search, UserCheck, Upload, Import, Lock, Unlock } from 'lucide-react'
import { toast } from 'sonner'
import { useDataTable } from '@/hooks/useDataTable'
import { DataPagination } from '@/components/ui/DataPagination'
import { CustomersSkeleton } from '@/components/PageSkeletons'

interface OutletCustomer {
  id: string
  phone: string | null
  customerName: string
  verifiedAt: string | null
  birthday: string | null
  lastVisited: string | null
  tableBookings: unknown[]
  banquetBookings: unknown[]
  is_unlocked?: boolean
}

interface OutletData {
  outlet_id: string
  outlet_name: string
  tableBookings: unknown[]
  banquetBookings: unknown[]
}

interface CustomerProfileData {
  success: boolean
  data?: {
    customer: { id: string; phone: string; customerName: string; email?: string; birthday?: string; verifiedAt?: string }
    restaurants: OutletData[]
  }
  error?: string
}

export default function Customers() {
  const { selectedOutlet } = useOutlet()
  const { formatAmountNoDecimals } = useCurrency()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [profileCustomerId, setProfileCustomerId] = useState<string | null>(null)
  const [profileData, setProfileData] = useState<CustomerProfileData | null>(null)
  const [profileLoading, setProfileLoading] = useState(false)
  const [isUpdatingVerify, setIsUpdatingVerify] = useState(false)

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
      <OutletCustomer>({
        customEndpoint: 'flamezo_backend.flamezo.api.customers.get_outlet_customers',
        customParams: { outlet_id: selectedOutlet },
        paramNames: {
          page: 'page',
          pageSize: 'page_size',
          search: 'search'
        },
        initialPageSize: 20,
        debugId: `outlet-customers-${selectedOutlet}`
      })

  // Customer data extractor
  const customers = useMemo(() => {
    return fetchedCustomers || []
  }, [fetchedCustomers])

  const { outletConfig, refreshConfig } = useOutlet()
  const isVerifyEnabled = outletConfig?.settings?.verifyMyUser ?? false

  const { call: setValue } = useFrappePostCall('frappe.client.set_value')

  const handleToggleVerify = async (checked: boolean) => {
    if (!selectedOutlet) return
    setIsUpdatingVerify(true)
    try {
      await setValue({
        doctype: 'Outlet Config',
        name: selectedOutlet,
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
      const res = await getCustomerProfile({ customer_id: customerId, outlet_id: selectedOutlet })
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

  if (!selectedOutlet) {
    return (
      <div className="p-6">
        <Card className="border-none shadow-sm ring-1 ring-border">
          <CardContent className="pt-12 pb-12">
            <div className="flex flex-col items-center justify-center text-center space-y-3">
              <div className="h-12 w-12 bg-muted rounded-full flex items-center justify-center">
                <UserCheck className="h-6 w-6 text-muted-foreground/50" />
              </div>
              <p className="text-muted-foreground font-medium">
                Select an outlet from the dropdown to view customers.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (isLoading && !customers?.length) return <CustomersSkeleton />

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Customers</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Build and manage your loyal customer base
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <CardTitle>Customer Directory</CardTitle>
              <CardDescription>
                {totalCount} total customers have interacted with your outlet
              </CardDescription>
            </div>
            <div className="flex flex-col sm:flex-row items-center gap-4">
              <div className="flex items-center gap-2 bg-green-500/10 px-3 py-1.5 rounded-xl border border-green-500/30">
                <div className="w-2 h-2 rounded-full bg-green-500" />
                <span className="text-[10px] font-black uppercase tracking-widest text-green-600">OTP Verified</span>
              </div>
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
          {customers.length === 0 ? (
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
                      return (
                        <Fragment key={c.id}>
                          <TableRow>
                            <TableCell className="text-center">
                              
                            </TableCell>
                            <TableCell className="font-medium">
                              <div className="flex items-center gap-2">
                                <div>
                                  {c.customerName || '—'}
                                </div>
                                
                              </div>
                            </TableCell>
                            <TableCell>
                              <div>{c.phone || '—'}</div>
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
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleViewFullProfile(c.id)}
                                  className="h-8"
                                >
                                  <Eye className="h-4 w-4 mr-2" />
                                  Profile
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                          
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
                    <div key={rest.outlet_id} className="space-y-4">
                      
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
                      {(!rest.tableBookings || rest.tableBookings.length === 0) &&
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
