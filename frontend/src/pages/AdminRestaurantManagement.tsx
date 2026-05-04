import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useFrappeAuth, useFrappePostCall, useFrappeGetCall } from '@/lib/frappe'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { toast } from 'sonner'
import { cn, copyToClipboard } from '@/lib/utils'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Label } from '@/components/ui/label'
import { 
  Shield, 
  RefreshCw, 
  Power, 
  PowerOff, 
  Trash2, 
  Coins, 
  Settings, 
  Zap, 
  Search,
  ArrowUpRight,
  Mail,
  Scale,
  Inbox,
  ClipboardCopy,
  Gem,
  Trophy,
  ExternalLink
} from 'lucide-react'
import { Switch } from '@/components/ui/switch'
import { useDataTable } from '@/hooks/useDataTable'
import { DataPagination } from '@/components/ui/DataPagination'
import { RestaurantSelector } from '@/components/RestaurantSelector'

interface Restaurant {
  name: string
  restaurant_id: string
  restaurant_name: string
  owner_email?: string
  is_active: number
  plan_type: 'SILVER' | 'GOLD' | 'DIAMOND'
  coins_balance: number
  platform_fee_percent: number
  monthly_minimum: number
  enable_floor_recovery: number
  creation: string
  modified: string
}

export default function AdminRestaurantManagement() {
  const navigate = useNavigate()
  const { currentUser } = useFrappeAuth()
  const [updating, setUpdating] = useState<string | null>(null)
  const [isAdmin, setIsAdmin] = useState(false)
  const [isOnboardingModalOpen, setIsOnboardingModalOpen] = useState(false)
  const [selectedOnboarding, setSelectedOnboarding] = useState<string[]>([])
  const [newRestaurantName, setNewRestaurantName] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [isNewLead, setIsNewLead] = useState(false)
  const [selectedOnboardingResId, setSelectedOnboardingResId] = useState('')
  const [isLinkModalOpen, setIsLinkModalOpen] = useState(false)
  const [linkToCopy, setLinkToCopy] = useState('')

  // Modals state
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
  const [restaurantToDelete, setRestaurantToDelete] = useState<{ id: string, name: string } | null>(null)
  const [verificationInput, setVerificationInput] = useState('')

  const [isCoinModalOpen, setIsCoinModalOpen] = useState(false)
  const [coinAmount, setCoinAmount] = useState('')
  const [coinReason, setCoinReason] = useState('Admin Grant')
  const [selectedRestaurant, setSelectedRestaurant] = useState<Restaurant | null>(null)

  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false)
  const [editPlatformFee, setEditPlatformFee] = useState('')
  const [editMonthlyMinimum, setEditMonthlyMinimum] = useState('')
  const [editName, setEditName] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [editFloorRecovery, setEditFloorRecovery] = useState(true)

  useEffect(() => {
    if (currentUser === 'Administrator') {
      setIsAdmin(true)
    } else {
      setIsAdmin(false)
    }
  }, [currentUser])

  const {
    data: restaurants,
    isLoading,
    mutate: loadRestaurants,
    page,
    setPage,
    pageSize,
    setPageSize,
    totalCount,
    searchQuery,
    setSearchQuery,
    filters,
    setFilters
  } = useDataTable({
    customEndpoint: 'dinematters.dinematters.api.admin.get_all_restaurants',
    paramNames: {
      page: 'page',
      pageSize: 'page_size',
      search: 'search',
      filters: 'filters'
    },
    initialPageSize: 20,
    debugId: 'admin-restaurants'
  })

  // APIs
  const { call: updateRestaurantPlan } = useFrappePostCall<{ success: boolean, error?: string }>(
    'dinematters.dinematters.api.admin.update_restaurant_plan'
  )
  const { call: toggleRestaurantStatus } = useFrappePostCall<{ success: boolean, error?: string }>(
    'dinematters.dinematters.api.admin.toggle_restaurant_status'
  )
  const { call: deleteRestaurant } = useFrappePostCall<{ success: boolean, message?: string, error?: string }>(
    'dinematters.dinematters.api.admin.delete_restaurant'
  )
  const { call: giveCoins } = useFrappePostCall<{ success: boolean, message?: string, error?: string }>(
    'dinematters.dinematters.api.admin.admin_give_coins'
  )
  const { call: updateSettings } = useFrappePostCall<{ success: boolean, message?: string, error?: string }>(
    'dinematters.dinematters.api.admin.admin_update_restaurant_settings'
  )

  const { call: generateOnboardingLink } = useFrappePostCall(
    'dinematters.dinematters.api.onboarding.generate_onboarding_link'
  )

  // Onboarding APIs
  const { data: onboardingData, mutate: loadOnboarding } = useFrappeGetCall(
    'dinematters.dinematters.api.onboarding.get_all_onboarding_requests'
  )
  const { call: deleteOnboarding } = useFrappePostCall(
    'dinematters.dinematters.api.onboarding.delete_onboarding_request'
  )
  const { call: bulkDeleteOnboarding } = useFrappePostCall(
    'dinematters.dinematters.api.onboarding.bulk_delete_onboarding_requests'
  )

  const handlePlanChange = async (restaurantName: string, newPlan: 'SILVER' | 'GOLD' | 'DIAMOND') => {
    try {
      setUpdating(restaurantName)
      const result = await updateRestaurantPlan({ restaurant_id: restaurantName, plan_type: newPlan }) as any
      if (result?.message?.success) {
        toast.success(`Plan upgraded to ${newPlan}`)
        if (selectedRestaurant) {
          setSelectedRestaurant({ ...selectedRestaurant, plan_type: newPlan })
        }
        loadRestaurants()
      }
    } catch (error) {
      toast.error('Strategic update failed')
    } finally {
      setUpdating(null)
    }
  }

  const handleStatusToggle = async (restaurantName: string, currentStatus: number) => {
    try {
      setUpdating(restaurantName)
      const newStatus = currentStatus ? 0 : 1
      const result = await toggleRestaurantStatus({ restaurant_id: restaurantName, is_active: newStatus }) as any
      if (result?.message?.success) {
        toast.success(`Restaurant ${newStatus ? 'activated' : 'deactivated'}`)
        loadRestaurants()
      }
    } catch (error) {
      toast.error('Status synchronization failed')
    } finally {
      setUpdating(null)
    }
  }

  const handleGiveCoins = async () => {
    if (!selectedRestaurant || !coinAmount) return
    try {
      setUpdating(selectedRestaurant.name)
      const result = await giveCoins({
        restaurant_id: selectedRestaurant.restaurant_id,
        amount: coinAmount,
        reason: coinReason
      }) as any
      if (result?.message?.success) {
        toast.success(`Granted ${coinAmount} coins to treasury`)
        setIsCoinModalOpen(false)
        loadRestaurants()
      }
    } catch (error) {
      toast.error('Treasury grant failed')
    } finally {
      setUpdating(null)
    }
  }

  const handleUpdateSettings = async () => {
    if (!selectedRestaurant) return
    try {
      setUpdating(selectedRestaurant.name)
      const result = await updateSettings({
        restaurant_id: selectedRestaurant.restaurant_id,
        updates: {
          platform_fee_percent: editPlatformFee,
          monthly_minimum: editMonthlyMinimum,
          restaurant_name: editName,
          owner_email: editEmail,
          enable_floor_recovery: editFloorRecovery ? 1 : 0
        }
      }) as any
      if (result?.message?.success) {
        toast.success('Core settings updated')
        if (selectedRestaurant) {
          setSelectedRestaurant({
            ...selectedRestaurant,
            restaurant_name: editName,
            owner_email: editEmail,
            platform_fee_percent: parseFloat(editPlatformFee),
            monthly_minimum: parseFloat(editMonthlyMinimum),
            enable_floor_recovery: editFloorRecovery ? 1 : 0
          })
        }
        setIsSettingsModalOpen(false)
        loadRestaurants()
      }
    } catch (error) {
      toast.error('Settings update failed')
    } finally {
      setUpdating(null)
    }
  }

  const handleConfirmDelete = async () => {
    if (!restaurantToDelete || verificationInput !== restaurantToDelete.id) return
    try {
      setUpdating(restaurantToDelete.id)
      const result = await deleteRestaurant({ restaurant_id: restaurantToDelete.id }) as any
      if (result?.message?.success) {
        toast.success(`Restaurant purged from system`)
        setIsDeleteDialogOpen(false)
        loadRestaurants()
      }
    } catch (error) {
      toast.error('System purge failed')
    } finally {
      setUpdating(null)
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
  }


  const handleDeleteOnboarding = async (name: string) => {
    try {
      setUpdating(name)
      const result = await deleteOnboarding({ name }) as any
      if (result?.message?.success) {
        toast.success('Request removed')
        loadOnboarding()
      }
    } finally {
      setUpdating(null)
    }
  }

  const handleCopyOnboardingLink = (link: string) => {
    setLinkToCopy(link)
    setIsLinkModalOpen(true)
  }

  const handleBulkDelete = async () => {
    if (!selectedOnboarding.length || !confirm(`Delete ${selectedOnboarding.length} onboarding requests?`)) return
    try {
      setUpdating('bulk-delete')
      const result = await bulkDeleteOnboarding({ names: selectedOnboarding }) as any
      if (result?.message?.success) {
        toast.success(`Successfully removed ${selectedOnboarding.length} requests`)
        setSelectedOnboarding([])
        loadOnboarding()
      }
    } finally {
      setUpdating(null)
    }
  }

  const toggleSelectAll = () => {
    const all = (onboardingData?.message?.data || []).map((r: any) => r.name)
    if (selectedOnboarding.length === all.length) {
      setSelectedOnboarding([])
    } else {
      setSelectedOnboarding(all)
    }
  }

  const toggleSelectRow = (name: string) => {
    setSelectedOnboarding(prev => 
      prev.includes(name) ? prev.filter(i => i !== name) : [...prev, name]
    )
  }

  const handleGenerateLink = async () => {
    if (!isNewLead && !selectedOnboardingResId) {
      toast.error('Please select a restaurant')
      return
    }
    if (isNewLead && !newRestaurantName.trim()) {
      toast.error('Please enter a restaurant name')
      return
    }

    try {
      setIsGenerating(true)
      const params = isNewLead 
        ? { restaurant_name: newRestaurantName }
        : { linked_restaurant: selectedOnboardingResId }

      const result = await generateOnboardingLink(params) as any
      if (result?.message?.success) {
        toast.success('Onboarding link generated!')
        setNewRestaurantName('')
        setSelectedOnboardingResId('')
        loadOnboarding()
      } else {
        toast.error(result?.message?.error || 'Generation failed')
      }
    } catch (error) {
      toast.error('API Error')
    } finally {
      setIsGenerating(false)
    }
  }

  const pendingCount = (onboardingData?.message?.data || []).filter((r: any) => r.status === 'Client Submitted').length

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center p-6">
        <Card className="w-full max-w-md border-none shadow-2xl rounded-3xl overflow-hidden">
          <div className="bg-red-600 h-2" />
          <CardContent className="p-10 text-center">
            <div className="mx-auto w-20 h-20 bg-red-100 rounded-2xl flex items-center justify-center mb-8">
              <Shield className="h-10 w-10 text-red-600" />
            </div>
            <h2 className="text-3xl font-black tracking-tight mb-4">RESTRICTED ZONE</h2>
            <p className="text-muted-foreground leading-relaxed font-medium">
              You lack the administrative clearance required to access the central restaurant control hub.
            </p>
            <Button onClick={() => navigate('/')} className="mt-8 rounded-xl px-10 h-12 font-bold uppercase tracking-widest text-xs">
              Return Home
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Restaurant Management</h2>
          <p className="text-muted-foreground text-sm">
            Manage all restaurants in the ecosystem
          </p>
        </div>
        <Button
          onClick={() => setIsOnboardingModalOpen(true)}
          variant="outline"
          className="relative h-11 px-6 rounded-xl border-primary/20 bg-primary/5 hover:bg-primary/10 transition-all font-semibold"
        >
          <Inbox className="h-4 w-4 mr-2 text-primary" />
          Onboarding Requests
          {pendingCount > 0 && (
            <Badge className="ml-2 bg-primary text-white border-none px-1.5 h-5 min-w-5 flex items-center justify-center animate-pulse">
              {pendingCount}
            </Badge>
          )}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="flex flex-col sm:flex-row items-center gap-3 w-full sm:w-auto">
              <div className="relative w-full sm:w-64">
                <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search restaurants..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 h-9"
                />
              </div>
              <Button
                variant="outline"
                size="icon"
                className="h-9 w-9 shrink-0"
                onClick={() => loadRestaurants()}
              >
                <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
              </Button>
            </div>
            <div className="flex flex-col sm:flex-row items-center gap-3 w-full sm:w-auto">
              <Select value={pageSize.toString()} onValueChange={(v) => setPageSize(parseInt(v))}>
                <SelectTrigger className="h-9 w-[120px]">
                  <SelectValue placeholder="Page Size" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="20">20 Rows</SelectItem>
                  <SelectItem value="50">50 Rows</SelectItem>
                  <SelectItem value="100">100 Rows</SelectItem>
                </SelectContent>
              </Select>

              <Select
                value={(() => {
                  const f = filters.find(f => f.fieldname === 'enable_floor_recovery')
                  if (!f) return 'all'
                  return f.value === 1 ? 'enabled' : 'disabled'
                })()}
                onValueChange={(v) => {
                  if (v === 'all') {
                    setFilters(filters.filter(f => f.fieldname !== 'enable_floor_recovery'))
                  } else {
                    const newFilters = filters.filter(f => f.fieldname !== 'enable_floor_recovery')
                    newFilters.push({ fieldname: 'enable_floor_recovery', operator: '=', value: v === 'enabled' ? 1 : 0 })
                    setFilters(newFilters)
                  }
                }}
              >
                <SelectTrigger className="h-9 w-[150px]">
                  <SelectValue placeholder="Floor Recovery" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Recovery: All</SelectItem>
                  <SelectItem value="enabled">Recovery: Enabled</SelectItem>
                  <SelectItem value="disabled">Recovery: Disabled</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading && !restaurants.length ? (
            <div className="py-20 flex justify-center">
              <div className="animate-spin h-6 w-6 border-2 border-primary border-t-transparent rounded-full" />
            </div>
          ) : !restaurants || restaurants.length === 0 ? (
            <div className="py-20 text-center text-muted-foreground">No restaurants found</div>
          ) : (
            <>
              <div className="rounded-md border overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Restaurant</TableHead>
                      <TableHead>ID</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Plan</TableHead>
                      <TableHead className="text-right">Coins</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {restaurants.map((restaurant: any) => (
                      <TableRow key={restaurant.name}>
                        <TableCell>
                          <div className="flex flex-col">
                            <span className="font-bold">{restaurant.restaurant_name}</span>
                            <span className="text-xs text-muted-foreground">{restaurant.owner_email}</span>
                          </div>
                        </TableCell>
                        <TableCell>
                          <code className="text-[10px] bg-muted px-1 rounded">{restaurant.restaurant_id}</code>
                        </TableCell>
                        <TableCell>
                          {restaurant.is_active ? (
                            <Badge variant="outline" className="bg-green-50 text-green-600 border-green-200">Online</Badge>
                          ) : (
                            <Badge variant="secondary">Offline</Badge>
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge variant={restaurant.plan_type === 'DIAMOND' ? 'default' : 'outline'}>
                            {restaurant.plan_type}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {restaurant.coins_balance.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button
                              variant="ghost" size="icon" className="h-8 w-8 text-amber-600"
                              onClick={() => {
                                setSelectedRestaurant(restaurant)
                                setCoinAmount('')
                                setIsCoinModalOpen(true)
                              }}
                            >
                              <Coins className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost" size="icon" className="h-8 w-8"
                              onClick={() => navigate(`/admin/restaurants/${restaurant.restaurant_id}`)}
                            >
                              <ArrowUpRight className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost" size="icon"
                              onClick={() => handleStatusToggle(restaurant.name, restaurant.is_active)}
                              disabled={updating === restaurant.name}
                              className={cn("h-8 w-8", restaurant.is_active ? "text-red-500" : "text-green-500")}
                            >
                              {restaurant.is_active ? <PowerOff className="h-4 w-4" /> : <Power className="h-4 w-4" />}
                            </Button>
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-8 w-8">
                                  <Settings className="h-4 w-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => {
                                  setSelectedRestaurant(restaurant)
                                  setEditName(restaurant.restaurant_name)
                                  setEditEmail(restaurant.owner_email || '')
                                  setEditPlatformFee(restaurant.platform_fee_percent.toString())
                                  setEditMonthlyMinimum(restaurant.monthly_minimum.toString())
                                  setEditFloorRecovery(!!restaurant.enable_floor_recovery)
                                  setIsSettingsModalOpen(true)
                                }}>
                                  <Settings className="h-4 w-4 mr-2" />
                                  <span>Configure</span>
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => {
                                  setRestaurantToDelete({ id: restaurant.restaurant_id, name: restaurant.restaurant_name })
                                  setVerificationInput('')
                                  setIsDeleteDialogOpen(true)
                                }} className="text-red-600">
                                  <Trash2 className="h-4 w-4 mr-2" />
                                  <span>Delete</span>
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
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


      {/* Grant Coins Modal */}
      <Dialog open={isCoinModalOpen} onOpenChange={setIsCoinModalOpen}>
        <DialogContent className="sm:max-w-[400px] p-0 overflow-hidden border-none shadow-2xl rounded-2xl">
          <div className="p-6 pt-8 text-center">
            <div className="mx-auto w-12 h-12 bg-amber-100 rounded-full flex items-center justify-center mb-4">
              <Coins className="h-6 w-6 text-amber-600" />
            </div>
            <DialogHeader className="text-center">
              <DialogTitle className="text-xl font-bold text-center w-full">Issue Credits</DialogTitle>
              <DialogDescription className="text-sm text-center pt-2">
                Manually add digital coins to <span className="font-bold text-foreground">"{selectedRestaurant?.restaurant_name}"</span>.
              </DialogDescription>
            </DialogHeader>
          </div>
          <div className="px-8 pb-8 space-y-5">
            <div className="space-y-2">
              <Label className="text-xs font-semibold text-muted-foreground">Magnitude (Amount)</Label>
              <NumberInput
                
                value={coinAmount}
                onChange={(e: any) => setCoinAmount(e.target.value)}
                placeholder="0.00"
                className="h-11 rounded-xl border-slate-300 focus-visible:ring-amber-500 font-bold text-lg bg-background text-foreground"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-semibold text-muted-foreground">Reason for Audit Trail</Label>
              <Input
                value={coinReason}
                onChange={(e: any) => setCoinReason(e.target.value)}
                placeholder="e.g., Marketing promotion"
                className="h-11 rounded-xl border-slate-300 bg-background text-foreground"
              />
            </div>
          </div>
          <DialogFooter className="p-4 bg-muted/30 border-t flex flex-row gap-2 sm:justify-end">
            <Button variant="ghost" onClick={() => setIsCoinModalOpen(false)} className="rounded-xl flex-1 sm:flex-none">Cancel</Button>
            <Button
              onClick={handleGiveCoins}
              className="rounded-xl px-6 flex-1 sm:flex-none bg-amber-600 hover:bg-amber-700 text-white shadow-sm"
            >
              Authorize Grant
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Advanced Settings Modal */}
      <Dialog open={isSettingsModalOpen} onOpenChange={setIsSettingsModalOpen}>
        <DialogContent className="sm:max-w-lg p-0 overflow-hidden border-none shadow-2xl rounded-2xl">
          <div className="p-6 pt-8 border-b bg-muted/10">
            <DialogHeader>
              <div className="flex items-center gap-3 mb-1">
                <div className="p-2 bg-primary/10 rounded-lg">
                  <Settings className="h-5 w-5 text-primary" />
                </div>
                <DialogTitle className="text-xl font-bold">Core Configuration</DialogTitle>
              </div>
              <DialogDescription className="text-sm font-medium pl-10 text-muted-foreground">
                Administrative parameters for <span className="text-foreground font-semibold">{selectedRestaurant?.restaurant_name}</span>
              </DialogDescription>
            </DialogHeader>
          </div>
          <div className="p-8 space-y-8 max-h-[60vh] overflow-y-auto">
            {/* Primary Details Section */}
            <div className="grid grid-cols-2 gap-6">
              <div className="space-y-2">
                <Label className="text-xs font-semibold text-muted-foreground ml-1">Trade Name</Label>
                <Input value={editName} onChange={(e: any) => setEditName(e.target.value)} className="h-11 rounded-xl border-slate-300 font-medium focus-visible:ring-primary/30 bg-background text-foreground" />
              </div>
              <div className="space-y-2">
                <Label className="text-xs font-semibold text-muted-foreground ml-1">Controller Email</Label>
                <Input value={editEmail} onChange={(e: any) => setEditEmail(e.target.value)} className="h-11 rounded-xl border-slate-300 font-medium focus-visible:ring-primary/30 bg-background text-foreground" />
              </div>
            </div>

            {/* Financial Parameters Section */}
            <div className="space-y-5 p-5 rounded-xl border bg-muted/5">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 bg-background rounded-md border shadow-sm">
                  <Coins className="h-3.5 w-3.5 text-primary" />
                </div>
                <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Financial Parameters</span>
              </div>

              <div className="grid grid-cols-2 gap-5">
                <div className="space-y-2">
                  <Label className="text-xs font-semibold text-muted-foreground ml-1">
                    Monthly Floor (₹)
                  </Label>
                  <NumberInput  value={editMonthlyMinimum} onChange={(e: any) => setEditMonthlyMinimum(e.target.value)} className="h-11 rounded-xl bg-background border-slate-300 font-bold text-foreground" />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs font-semibold text-muted-foreground ml-1">Network Fee (%)</Label>
                  <NumberInput  value={editPlatformFee} onChange={(e: any) => setEditPlatformFee(e.target.value)} className="h-11 rounded-xl bg-background border-slate-300 font-bold text-foreground" />
                </div>
              </div>
            </div>

            {/* Operational Controls Section */}
            <div className="space-y-4 p-5 rounded-xl border bg-primary/5 border-primary/10">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <Scale className="h-4 w-4 text-primary" />
                    <Label className="text-sm font-bold">
                      {selectedRestaurant?.plan_type === 'DIAMOND' ? 'Monthly Floor Guarantee' : 'Daily Floor Recovery'}
                    </Label>
                  </div>
                  <p className="text-[10px] text-muted-foreground font-medium">
                    {selectedRestaurant?.plan_type === 'DIAMOND' 
                      ? 'Control automatic monthly minimum fee deductions' 
                      : 'Control automatic nightly minimum fee deductions'}
                  </p>
                </div>
                <Switch
                  checked={editFloorRecovery}
                  onCheckedChange={setEditFloorRecovery}
                />
              </div>
              {!editFloorRecovery && (
                <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg flex items-start gap-2">
                  <Zap className="h-3 w-3 text-amber-600 mt-0.5" />
                  <p className="text-[9px] text-amber-700 font-bold leading-tight uppercase">
                    Billing Alert: {selectedRestaurant?.plan_type === 'DIAMOND' ? 'Monthly' : 'Nightly'} floor deduction is PAUSED for this restaurant.
                  </p>
                </div>
              )}
            </div>

            {/* Tier Evolution Section */}
            <div className="space-y-4">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 bg-background rounded-md border shadow-sm">
                  <Shield className="h-3.5 w-3.5 text-primary" />
                </div>
                <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Platform Access Tier</span>
              </div>
              
              <Select 
                value={selectedRestaurant?.plan_type} 
                onValueChange={(value) => handlePlanChange(selectedRestaurant!.restaurant_id, value as any)}
                disabled={updating === selectedRestaurant?.name}
              >
                <SelectTrigger className="h-14 rounded-2xl border-2 border-primary/20 bg-background hover:border-primary/40 transition-all">
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      "p-2 rounded-lg",
                      selectedRestaurant?.plan_type === 'DIAMOND' ? "bg-blue-500/10 text-blue-600" :
                      selectedRestaurant?.plan_type === 'GOLD' ? "bg-amber-500/10 text-amber-600" :
                      "bg-slate-500/10 text-slate-600"
                    )}>
                      {selectedRestaurant?.plan_type === 'DIAMOND' ? <Gem className="h-4 w-4" /> :
                       selectedRestaurant?.plan_type === 'GOLD' ? <Trophy className="h-4 w-4" /> :
                       <Shield className="h-4 w-4" />}
                    </div>
                    <div className="flex flex-col items-start">
                      <span className="text-sm font-black uppercase tracking-widest">{selectedRestaurant?.plan_type}</span>
                      <span className="text-[10px] font-bold text-muted-foreground uppercase opacity-70">Current Active Plan</span>
                    </div>
                  </div>
                </SelectTrigger>
                <SelectContent className="rounded-2xl p-1 shadow-2xl border-none">
                  {[
                    { id: 'SILVER', label: 'Silver Tier', icon: Shield, color: 'text-slate-500', desc: 'Basic Digital Menu' },
                    { id: 'GOLD', label: 'Gold Tier', icon: Trophy, color: 'text-amber-500', desc: '₹999/mo Minimum Floor' },
                    { id: 'DIAMOND', label: 'Diamond Tier', icon: Gem, color: 'text-blue-500', desc: '1.5% Success Share (₹399 Floor)' }
                  ].map((tier) => (
                    <SelectItem 
                      key={tier.id} 
                      value={tier.id}
                      className="rounded-xl py-3 focus:bg-primary/5 cursor-pointer"
                    >
                      <div className="flex items-center gap-3">
                        <div className={cn("p-1.5 rounded-md bg-muted/50", tier.color)}>
                          <tier.icon className="h-3.5 w-3.5" />
                        </div>
                        <div className="flex flex-col">
                          <span className="text-xs font-bold uppercase tracking-wider">{tier.label}</span>
                          <span className="text-[9px] text-muted-foreground font-medium">{tier.desc}</span>
                        </div>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              
              {updating === selectedRestaurant?.name && (
                <div className="flex items-center gap-2 px-1 text-[10px] font-bold text-primary animate-pulse">
                  <RefreshCw className="h-3 w-3 animate-spin" />
                  PROCESSING TIER TRANSITION...
                </div>
              )}
            </div>
          </div>
          <DialogFooter className="p-4 bg-muted/30 border-t flex flex-row gap-2 sm:justify-end">
            <Button variant="ghost" onClick={() => setIsSettingsModalOpen(false)} className="rounded-xl flex-1 sm:flex-none">Cancel</Button>
            <Button
              onClick={handleUpdateSettings}
              className="rounded-xl px-8 font-bold bg-primary text-white hover:bg-primary/90 shadow-sm flex-1 sm:flex-none"
            >
              Save Configuration
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Modal */}
      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent className="sm:max-w-[440px] p-0 overflow-hidden border-none shadow-2xl rounded-2xl">
          <div className="p-6 pt-8 text-center">
            <div className="mx-auto w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mb-4">
              <Trash2 className="h-6 w-6 text-red-600" />
            </div>
            <DialogHeader className="text-center">
              <DialogTitle className="text-xl font-bold text-center w-full">Delete Restaurant</DialogTitle>
              <DialogDescription className="text-sm text-center pt-2">
                This action is irreversible. All configurations, balances, and data for <span className="font-bold text-foreground">"{restaurantToDelete?.name}"</span> will be permanently removed.
              </DialogDescription>
            </DialogHeader>
          </div>
          <div className="px-8 pb-8 space-y-4">
            <div className="space-y-3">
              <Label className="text-xs font-semibold text-muted-foreground">
                To confirm, please type <span className="font-mono text-red-600 font-bold px-1 bg-red-50 rounded">{restaurantToDelete?.id}</span> below.
              </Label>
              <Input
                value={verificationInput}
                onChange={(e) => setVerificationInput(e.target.value)}
                placeholder="Type restaurant ID here"
                className="h-11 rounded-xl border-muted focus-visible:ring-red-500 font-medium"
              />
            </div>
          </div>
          <DialogFooter className="p-4 bg-muted/30 border-t flex flex-row gap-2 sm:justify-end">
            <Button variant="ghost" onClick={() => setIsDeleteDialogOpen(false)} className="rounded-xl flex-1 sm:flex-none">Cancel</Button>
            <Button
              variant="destructive"
              disabled={verificationInput !== restaurantToDelete?.id}
              onClick={handleConfirmDelete}
              className="rounded-xl px-6 flex-1 sm:flex-none bg-red-600 hover:bg-red-700 shadow-sm"
            >
              Delete Restaurant
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Onboarding Inbox Modal */}
      <Dialog open={isOnboardingModalOpen} onOpenChange={setIsOnboardingModalOpen}>
        <DialogContent className="sm:max-w-4xl p-0 overflow-hidden border-none shadow-2xl rounded-2xl">
          <div className="p-6 bg-muted/10 border-b">
            <DialogHeader>
              <div className="flex items-center gap-3">
                <div className="p-2 bg-primary/10 rounded-lg">
                  <Inbox className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <DialogTitle className="text-xl font-bold">Onboarding Inbox</DialogTitle>
                  <DialogDescription className="text-sm font-medium text-muted-foreground">
                    Review and finalize new restaurant setups
                  </DialogDescription>
                </div>
              </div>
              {selectedOnboarding.length > 0 && (
                <div className="flex items-center gap-3 animate-in fade-in slide-in-from-right-2">
                  <span className="text-xs font-bold text-primary bg-primary/10 px-2 py-1 rounded-md">
                    {selectedOnboarding.length} Selected
                  </span>
                  <Button 
                    variant="destructive" 
                    size="sm" 
                    className="h-8 rounded-lg font-bold shadow-sm"
                    onClick={handleBulkDelete}
                    disabled={updating === 'bulk-delete'}
                  >
                    <Trash2 className="h-3.5 w-3.5 mr-1.5" />
                    Delete Selected
                  </Button>
                </div>
              )}
            </DialogHeader>
          </div>

          <div className="px-6 py-5 bg-muted/5 border-b">
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label className="text-[10px] font-black uppercase tracking-widest text-primary">Onboarding Type</Label>
                  <p className="text-xs text-muted-foreground">Select an existing restaurant or create a new lead</p>
                </div>
                <div className="flex items-center gap-2 bg-muted/20 p-1 rounded-xl">
                  <button 
                    onClick={() => setIsNewLead(false)}
                    className={cn(
                      "px-3 py-1.5 rounded-lg text-xs font-bold transition-all",
                      !isNewLead ? "bg-white shadow-sm text-primary" : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    Existing
                  </button>
                  <button 
                    onClick={() => setIsNewLead(true)}
                    className={cn(
                      "px-3 py-1.5 rounded-lg text-xs font-bold transition-all",
                      isNewLead ? "bg-white shadow-sm text-primary" : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    New Lead
                  </button>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row gap-3 items-end animate-in fade-in slide-in-from-top-2 duration-300">
                <div className="flex-1 space-y-2 w-full">
                  <Label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground ml-1">
                    {isNewLead ? "Restaurant Name" : "Select Restaurant"}
                  </Label>
                  {isNewLead ? (
                    <Input 
                      placeholder="e.g. Flapjack Downtown" 
                      value={newRestaurantName}
                      onChange={(e) => setNewRestaurantName(e.target.value)}
                      className="h-10 rounded-xl bg-white"
                      onKeyDown={(e) => e.key === 'Enter' && handleGenerateLink()}
                    />
                  ) : (
                    <RestaurantSelector 
                      value={selectedOnboardingResId}
                      onSelect={setSelectedOnboardingResId}
                      options={(restaurants || []).map((r: any) => ({
                        value: r.name,
                        label: r.restaurant_name
                      }))}
                      placeholder="Search existing restaurants..."
                    />
                  )}
                </div>
                <Button 
                  onClick={handleGenerateLink}
                  disabled={isGenerating || (isNewLead ? !newRestaurantName.trim() : !selectedOnboardingResId)}
                  className="h-10 rounded-xl px-8 font-bold shadow-lg shadow-primary/20 whitespace-nowrap"
                >
                  {isGenerating ? <RefreshCw className="h-4 w-4 animate-spin mr-2" /> : <ExternalLink className="h-4 w-4 mr-2" />}
                  Generate Link
                </Button>
              </div>
            </div>
          </div>

          <div className="p-0 max-h-[45vh] overflow-y-auto">
            {!onboardingData?.message?.data?.length ? (
              <div className="py-20 text-center">
                <div className="mx-auto w-12 h-12 bg-muted/20 rounded-full flex items-center justify-center mb-4">
                  <Mail className="h-6 w-6 text-muted-foreground" />
                </div>
                <p className="text-muted-foreground font-medium">No pending onboarding requests found</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/5">
                    <TableHead className="w-12 pl-6">
                      <Checkbox 
                        checked={selectedOnboarding.length > 0 && selectedOnboarding.length === onboardingData?.message?.data?.length}
                        onCheckedChange={toggleSelectAll}
                        className="rounded-md border-muted-foreground/30 data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                      />
                    </TableHead>
                    <TableHead>Restaurant Name</TableHead>
                    <TableHead>Owner / Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="text-right pr-6">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(onboardingData?.message?.data || []).map((req: any) => (
                    <TableRow key={req.name} className={cn(
                      "hover:bg-muted/5 transition-colors",
                      selectedOnboarding.includes(req.name) && "bg-primary/5 hover:bg-primary/5"
                    )}>
                      <TableCell className="pl-6">
                        <Checkbox 
                          checked={selectedOnboarding.includes(req.name)}
                          onCheckedChange={() => toggleSelectRow(req.name)}
                          className="rounded-md border-muted-foreground/30 data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                        />
                      </TableCell>
                      <TableCell className="font-bold">{req.restaurant_name}</TableCell>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="text-xs font-medium">{req.owner_email || 'No email provided'}</span>
                          <div className="flex items-center mt-1">
                            <div className={cn(
                              "h-1.5 w-1.5 rounded-full mr-2",
                              req.status === 'Client Submitted' ? "bg-green-500" : "bg-amber-400"
                            )} />
                            <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                              {req.status}
                            </span>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDate(req.creation)}
                      </TableCell>
                      <TableCell className="text-right pr-6">
                        <div className="flex justify-end gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 px-2 text-xs font-semibold"
                            onClick={() => handleCopyOnboardingLink(req.onboarding_link)}
                          >
                            <ClipboardCopy className="h-3 w-3 mr-1" />
                            Copy Link
                          </Button>

                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 px-2 text-xs font-semibold text-red-500"
                            onClick={() => handleDeleteOnboarding(req.name)}
                            disabled={updating === req.name}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>

          <div className="p-4 bg-muted/30 border-t text-right">
            <Button variant="ghost" className="rounded-xl px-6 font-semibold" onClick={() => setIsOnboardingModalOpen(false)}>
              Close Inbox
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={isLinkModalOpen} onOpenChange={setIsLinkModalOpen}>
        <DialogContent className="sm:max-w-md p-6 rounded-2xl">
          <DialogHeader>
            <DialogTitle>Share Onboarding Link</DialogTitle>
            <DialogDescription>
              Copy and share this link with the restaurant owner.
            </DialogDescription>
          </DialogHeader>
          <div className="flex items-center space-x-2 mt-4">
            <div className="grid flex-1 gap-2">
              <Label htmlFor="link" className="sr-only">
                Link
              </Label>
              <Input
                id="link"
                readOnly
                value={linkToCopy}
                className="h-9 font-mono text-xs bg-muted/50"
              />
            </div>
            <Button 
              size="sm" 
              className="px-3"
              onClick={async () => {
                const success = await copyToClipboard(linkToCopy)
                if (success) {
                  toast.success('Copied!')
                  // Keep modal open for a moment so they see success, then maybe close or just let them close
                }
              }}
            >
              <span className="sr-only">Copy</span>
              <ClipboardCopy className="h-4 w-4" />
            </Button>
          </div>
          <DialogFooter className="sm:justify-start mt-6">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsLinkModalOpen(false)}
              className="rounded-xl"
            >
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
