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
  ExternalLink, Save
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
  owner_phone?: string
  is_active: number
  coins_balance: number
  platform_fee_percent: number
  monthly_minimum: number
  enable_floor_recovery: number
  creation: string
  modified: string
  // Razorpay Route hybrid state (May 2026)
  mandate_status?: '' | 'inactive' | 'active' | 'failed'
  outstanding_commission_paise?: number
  cash_payments_disabled_until?: string | null
  cash_sweep_failure_count?: number
  razorpay_kyc_status?: '' | 'under_review' | 'needs_clarification' | 'activated' | 'suspended' | 'rejected'
  route_mode?: '' | 'flamezo_hold' | 'direct_split' | 'disabled'
}

interface AdminStats {
  total: number
  active: number
  inactive: number
  mandate_active: number
  mandate_missing: number
  kyc_activated: number
  kyc_pending: number
  kyc_blocked: number
  throttled: number
  owing: number
  total_outstanding_paise: number
  total_outstanding_rupees: number
  total_coins: number
}

export default function AdminRestaurantManagement() {
  const navigate = useNavigate()
  const { currentUser } = useFrappeAuth()
  const [updating, setUpdating] = useState<string | null>(null)
  const [isAdmin, setIsAdmin] = useState(false)
  const [isOnboardingModalOpen, setIsOnboardingModalOpen] = useState(false)
  const [selectedOnboarding, setSelectedOnboarding] = useState<string[]>([])
  const [isGenerating, setIsGenerating] = useState(false)
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
  const [coinAction, setCoinAction] = useState<'grant' | 'deduct'>('grant')
  const [selectedRestaurant, setSelectedRestaurant] = useState<Restaurant | null>(null)

  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false)
  const [editPlatformFee, setEditPlatformFee] = useState('')
  const [editName, setEditName] = useState('')
  const [editEmail, setEditEmail] = useState('')

  const [isSupervisorOnly, setIsSupervisorOnly] = useState(false)
  
  const [isPlatformSettingsModalOpen, setIsPlatformSettingsModalOpen] = useState(false)
  const [platformSettings, setPlatformSettings] = useState({
    charge_gst: false,
    gst_percent: 18,
    gold_monthly_fee: 0,
    gold_commission_percent: 3.0
  })

  useEffect(() => {
    // Wait for currentUser
    if (!currentUser) return

    const win = window as any
    const userRoles: string[] = win.frappe?.boot?.user_roles || win.frappe?.boot?.user?.roles || win.frappe?.user_roles || []
    
    const isSupervisor = userRoles.includes('Flamezo Supervisor')
    const isSystemManager = userRoles.includes('System Manager')
    const isRootAdmin = currentUser === 'Administrator'

    if (isRootAdmin || isSupervisor || isSystemManager) {
      setIsAdmin(true)
      setIsSupervisorOnly(isSupervisor && !isRootAdmin && !isSystemManager)
    } else {
      setIsAdmin(false)
      setIsSupervisorOnly(false)
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
    customEndpoint: 'flamezo_backend.flamezo.api.admin.get_all_restaurants',
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
  const { call: toggleRestaurantStatus } = useFrappePostCall<{ success: boolean, error?: string }>(
    'flamezo_backend.flamezo.api.admin.toggle_restaurant_status'
  )
  const { call: deleteRestaurant } = useFrappePostCall<{ success: boolean, message?: string, error?: string }>(
    'flamezo_backend.flamezo.api.admin.delete_restaurant'
  )
  const { call: giveCoins } = useFrappePostCall<{ success: boolean, message?: string, error?: string }>(
    'flamezo_backend.flamezo.api.admin.admin_give_coins'
  )
  const { call: updateSettings } = useFrappePostCall<{ success: boolean, message?: string, error?: string }>(
    'flamezo_backend.flamezo.api.admin.admin_update_restaurant_settings'
  )

  const { call: generateOnboardingLink } = useFrappePostCall(
    'flamezo_backend.flamezo.api.onboarding.generate_onboarding_link'
  )

  // Onboarding APIs
  const { data: onboardingData, mutate: loadOnboarding } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.onboarding.get_all_onboarding_requests'
  )
  const { call: deleteOnboarding } = useFrappePostCall(
    'flamezo_backend.flamezo.api.onboarding.delete_onboarding_request'
  )
  const { call: bulkDeleteOnboarding } = useFrappePostCall(
    'flamezo_backend.flamezo.api.onboarding.bulk_delete_onboarding_requests'
  )

  const { data: rawPlatformSettings, mutate: loadPlatformSettings } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.admin.get_platform_settings',
    {},
    'platform-settings'
  )

  const { call: updatePlatformSettings } = useFrappePostCall(
    'flamezo_backend.flamezo.api.admin.update_platform_settings'
  )

  // Fleet-wide stats for the strip at the top. Refetches every time the
  // table mutates so KPIs reflect the freshest state after coin grants,
  // status toggles, etc.
  const { data: rawAdminStats, mutate: loadAdminStats } = useFrappeGetCall<{ message?: { success: boolean; data?: AdminStats } }>(
    'flamezo_backend.flamezo.api.admin.get_admin_restaurants_stats',
    {},
    'admin-restaurants-stats'
  )
  const adminStats: AdminStats | undefined = rawAdminStats?.message?.data

  useEffect(() => {
    if (rawPlatformSettings?.message?.data) {
      setPlatformSettings(rawPlatformSettings.message.data)
    }
  }, [rawPlatformSettings])

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
      const amount = parseFloat(coinAmount)
      const finalAmount = coinAction === 'grant' ? amount : -Math.abs(amount)
      
      const result = await giveCoins({
        restaurant_id: selectedRestaurant.restaurant_id,
        amount: finalAmount,
        reason: coinReason
      }) as any
      if (result?.message?.success) {
        toast.success(`${coinAction === 'grant' ? 'Granted' : 'Deducted'} ${coinAmount} coins`)
        setIsCoinModalOpen(false)
        loadRestaurants()
      }
    } catch (error) {
      toast.error('Treasury update failed')
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
          restaurant_name: editName,
          owner_email: editEmail,
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
    if (!selectedOnboardingResId) {
      toast.error('Please select a restaurant')
      return
    }

    try {
      setIsGenerating(true)
      const params = { linked_restaurant: selectedOnboardingResId }

      const result = await generateOnboardingLink(params) as any
      if (result?.message?.success) {
        toast.success('Onboarding link generated!')
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

  const handleUpdatePlatformSettings = async () => {
    try {
      setUpdating('platform-settings')
      const result = await updatePlatformSettings({ settings: platformSettings }) as any
      if (result?.message?.success) {
        toast.success('Platform settings synchronized')
        loadPlatformSettings()
        setIsPlatformSettingsModalOpen(false)
      }
    } catch (error) {
      toast.error('Failed to sync platform settings')
    } finally {
      setUpdating(null)
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
        <div className="flex items-center gap-3">
          <Button
            onClick={() => setIsPlatformSettingsModalOpen(true)}
            variant="outline"
            className="h-11 px-4 rounded-xl border-stone-200 hover:border-primary/30 hover:bg-primary/5 hover:-translate-y-1 hover:shadow-lg active:translate-y-0 transition-all duration-300 font-semibold group"
          >
            <Settings className="h-4 w-4 mr-2 group-hover:rotate-90 transition-transform duration-500" />
            Platform Settings
          </Button>

          <Button
            onClick={() => setIsOnboardingModalOpen(true)}
            variant="outline"
            className="relative h-11 px-6 rounded-xl border-primary/20 bg-primary/5 hover:bg-primary/10 hover:-translate-y-1 hover:shadow-lg active:translate-y-0 transition-all duration-300 font-semibold group"
          >
            <Inbox className="h-4 w-4 mr-2 text-primary group-hover:scale-110 transition-transform" />
            Onboarding Requests
            {pendingCount > 0 && (
              <Badge className="ml-2 bg-primary text-white border-none px-1.5 h-5 min-w-5 flex items-center justify-center animate-pulse">
                {pendingCount}
              </Badge>
            )}
          </Button>
        </div>
      </div>

      {/* Fleet-wide stats strip. Single read of get_admin_restaurants_stats;
          refreshes alongside the table. Each card is clickable to apply the
          matching filter so the admin can drill from KPI → row set in one
          click. */}
      {adminStats && (() => {
        // Fields a stat-card can own. Clicking a card sets ITS filter and
        // clears any OTHER stat-card filters that might be sticky from a
        // prior click — that way "Total" actually resets the slice and you
        // can switch between cards cleanly. Non-card filters (Search,
        // Recovery, Floor Recovery select, Success Share tier select) are
        // preserved across stat-card clicks.
        const STAT_FILTER_FIELDS = ['is_active', 'has_outstanding', 'throttled', 'razorpay_kyc_status', 'mandate_status']
        const applyStatFilter = (fieldname: string | null, value: any) => {
          const next = filters.filter((f: any) => !STAT_FILTER_FIELDS.includes(f.fieldname))
          if (fieldname !== null) next.push({ fieldname, operator: '=', value })
          setFilters(next)
        }
        // True if the given (fieldname, value) is the currently active stat
        // filter — used to highlight the selected card.
        const isStatActive = (fieldname: string | null, value?: any) => {
          if (fieldname === null) return !filters.some((f: any) => STAT_FILTER_FIELDS.includes(f.fieldname))
          return filters.some((f: any) => f.fieldname === fieldname && f.value === value)
        }
        const ring = (on: boolean) => on ? ' ring-2 ring-offset-1' : ''
        return (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 mb-3">
            <button
              type="button"
              className={cn(
                'text-left rounded-xl border bg-card p-3 hover:border-primary/40 hover:shadow-sm transition',
                isStatActive(null) ? 'ring-2 ring-primary/30 ring-offset-1' : ''
              )}
              onClick={() => applyStatFilter(null, null)}
              title="Show all restaurants (clears stat-card filters)"
            >
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Total</p>
              <p className="text-2xl font-black tracking-tight">{adminStats.total}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">{adminStats.active} online · {adminStats.inactive} offline</p>
            </button>
            <button
              type="button"
              className={cn(
                'text-left rounded-xl border bg-emerald-50/50 dark:bg-emerald-500/5 p-3 hover:border-emerald-300 hover:shadow-sm transition border-emerald-200/60 dark:border-emerald-500/20',
                'ring-emerald-300' + ring(isStatActive('is_active', 1))
              )}
              onClick={() => applyStatFilter('is_active', 1)}
              title="Show only active restaurants"
            >
              <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-700 dark:text-emerald-400">Active</p>
              <p className="text-2xl font-black tracking-tight text-emerald-700 dark:text-emerald-300">{adminStats.active}</p>
              <p className="text-[10px] text-emerald-700/70 dark:text-emerald-400/70 mt-0.5">Live + receiving orders</p>
            </button>
            <button
              type="button"
              className={cn(
                'text-left rounded-xl border bg-amber-50/50 dark:bg-amber-500/5 p-3 hover:border-amber-300 hover:shadow-sm transition border-amber-200/60 dark:border-amber-500/20',
                'ring-amber-300' + ring(isStatActive('has_outstanding', 'yes'))
              )}
              onClick={() => applyStatFilter('has_outstanding', 'yes')}
              title="Show only restaurants with outstanding Success Share"
            >
              <p className="text-[10px] font-bold uppercase tracking-widest text-amber-700 dark:text-amber-400">Owing</p>
              <p className="text-2xl font-black tracking-tight text-amber-700 dark:text-amber-300">₹{adminStats.total_outstanding_rupees.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</p>
              <p className="text-[10px] text-amber-700/70 dark:text-amber-400/70 mt-0.5">{adminStats.owing} restaurants</p>
            </button>
            <button
              type="button"
              className={cn(
                'text-left rounded-xl border bg-rose-50/50 dark:bg-rose-500/5 p-3 hover:border-rose-300 hover:shadow-sm transition border-rose-200/60 dark:border-rose-500/20',
                'ring-rose-300' + ring(isStatActive('throttled', 'yes'))
              )}
              onClick={() => applyStatFilter('throttled', 'yes')}
              title="Show only restaurants currently in cash-payment throttle"
            >
              <p className="text-[10px] font-bold uppercase tracking-widest text-rose-700 dark:text-rose-400">Throttled</p>
              <p className="text-2xl font-black tracking-tight text-rose-700 dark:text-rose-300">{adminStats.throttled}</p>
              <p className="text-[10px] text-rose-700/70 dark:text-rose-400/70 mt-0.5">Cash paused (Tier 3)</p>
            </button>
            <button
              type="button"
              className={cn(
                'text-left rounded-xl border bg-blue-50/50 dark:bg-blue-500/5 p-3 hover:border-blue-300 hover:shadow-sm transition border-blue-200/60 dark:border-blue-500/20',
                'ring-blue-300' + ring(isStatActive('razorpay_kyc_status', 'under_review'))
              )}
              onClick={() => applyStatFilter('razorpay_kyc_status', 'under_review')}
              title="Show only restaurants whose Route KYC is under review"
            >
              <p className="text-[10px] font-bold uppercase tracking-widest text-blue-700 dark:text-blue-400">KYC Pending</p>
              <p className="text-2xl font-black tracking-tight text-blue-700 dark:text-blue-300">{adminStats.kyc_pending}</p>
              <p className="text-[10px] text-blue-700/70 dark:text-blue-400/70 mt-0.5">{adminStats.kyc_activated} activated · {adminStats.kyc_blocked} blocked</p>
            </button>
            <button
              type="button"
              className={cn(
                'text-left rounded-xl border bg-violet-50/50 dark:bg-violet-500/5 p-3 hover:border-violet-300 hover:shadow-sm transition border-violet-200/60 dark:border-violet-500/20',
                'ring-violet-300' + ring(isStatActive('mandate_status', 'active'))
              )}
              onClick={() => applyStatFilter('mandate_status', 'active')}
              title="Show only restaurants with an active autopay mandate"
            >
              <p className="text-[10px] font-bold uppercase tracking-widest text-violet-700 dark:text-violet-400">Mandate Active</p>
              <p className="text-2xl font-black tracking-tight text-violet-700 dark:text-violet-300">{adminStats.mandate_active}</p>
              <p className="text-[10px] text-violet-700/70 dark:text-violet-400/70 mt-0.5">{adminStats.mandate_missing} missing</p>
            </button>
          </div>
        )
      })()}

      <Card>
        {/* Compact single-line filter bar. The dropdown trigger reads
            "<Field>: <selected>" so we don't need per-item prefixes. Smaller
            h-8 + tighter widths + reduced padding keeps everything on one
            row up to ~1280px and frees vertical space for the table. */}
        <CardHeader className="py-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[180px] max-w-[260px]">
              <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search restaurants..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-7 h-8 text-xs"
              />
            </div>
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={() => { loadRestaurants(); loadAdminStats() }}
              title="Refresh"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isLoading && "animate-spin")} />
            </Button>

            <div className="h-5 w-px bg-border mx-1" />

            {/* Page size */}
            <Select value={pageSize.toString()} onValueChange={(v) => setPageSize(parseInt(v))}>
              <SelectTrigger className="h-8 w-[78px] text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="20">20</SelectItem>
                <SelectItem value="50">50</SelectItem>
                <SelectItem value="100">100</SelectItem>
              </SelectContent>
            </Select>

            {/* Status */}
            <Select
              value={(() => {
                const f = filters.find(f => f.fieldname === 'is_active')
                if (!f) return 'all'
                return f.value === 1 ? 'active' : 'inactive'
              })()}
              onValueChange={(v) => {
                const next = filters.filter(f => f.fieldname !== 'is_active')
                if (v !== 'all') next.push({ fieldname: 'is_active', operator: '=', value: v === 'active' ? 1 : 0 })
                setFilters(next)
              }}
            >
              <SelectTrigger className="h-8 w-[112px] text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Status: All</SelectItem>
                <SelectItem value="active">Status: Online</SelectItem>
                <SelectItem value="inactive">Status: Offline</SelectItem>
              </SelectContent>
            </Select>

            {/* Success Share Tier */}
            <Select
              value={(filters.find(f => f.fieldname === 'success_share_tier')?.value as string) || 'all'}
              onValueChange={(v) => {
                const next = filters.filter(f => f.fieldname !== 'success_share_tier')
                if (v !== 'all') next.push({ fieldname: 'success_share_tier', operator: '=', value: v })
                setFilters(next)
              }}
            >
              <SelectTrigger className="h-8 w-[124px] text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Share: All</SelectItem>
                <SelectItem value="new">Share: New</SelectItem>
                <SelectItem value="legacy">Share: Legacy 1.5%</SelectItem>
                <SelectItem value="custom">Share: Custom</SelectItem>
              </SelectContent>
            </Select>

            {/* Mandate */}
            <Select
              value={(filters.find(f => f.fieldname === 'mandate_status')?.value as string) || 'all'}
              onValueChange={(v) => {
                const next = filters.filter(f => f.fieldname !== 'mandate_status')
                if (v !== 'all') next.push({ fieldname: 'mandate_status', operator: '=', value: v })
                setFilters(next)
              }}
            >
              <SelectTrigger className="h-8 w-[128px] text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Mandate: All</SelectItem>
                <SelectItem value="active">Mandate: Active</SelectItem>
                <SelectItem value="inactive">Mandate: Inactive</SelectItem>
                <SelectItem value="failed">Mandate: Failed</SelectItem>
              </SelectContent>
            </Select>

            {/* Route KYC */}
            <Select
              value={(filters.find(f => f.fieldname === 'razorpay_kyc_status')?.value as string) || 'all'}
              onValueChange={(v) => {
                const next = filters.filter(f => f.fieldname !== 'razorpay_kyc_status')
                if (v !== 'all') next.push({ fieldname: 'razorpay_kyc_status', operator: '=', value: v })
                setFilters(next)
              }}
            >
              <SelectTrigger className="h-8 w-[120px] text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">KYC: All</SelectItem>
                <SelectItem value="activated">KYC: Activated</SelectItem>
                <SelectItem value="under_review">KYC: Review</SelectItem>
                <SelectItem value="needs_clarification">KYC: Needs Info</SelectItem>
                <SelectItem value="rejected">KYC: Rejected</SelectItem>
                <SelectItem value="suspended">KYC: Suspended</SelectItem>
              </SelectContent>
            </Select>

            {/* Throttle */}
            <Select
              value={(filters.find(f => f.fieldname === 'throttled')?.value as string) || 'all'}
              onValueChange={(v) => {
                const next = filters.filter(f => f.fieldname !== 'throttled')
                if (v !== 'all') next.push({ fieldname: 'throttled', operator: '=', value: v })
                setFilters(next)
              }}
            >
              <SelectTrigger className="h-8 w-[112px] text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Throttle: All</SelectItem>
                <SelectItem value="yes">Throttle: On</SelectItem>
                <SelectItem value="no">Throttle: Off</SelectItem>
              </SelectContent>
            </Select>

            {/* Clear-all chip — only when any filter is applied. */}
            {filters.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 text-xs px-2 text-rose-600 hover:text-rose-700 hover:bg-rose-50 ml-auto"
                onClick={() => setFilters([])}
              >
                Clear ({filters.length})
              </Button>
            )}
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
                      <TableHead>Success Share</TableHead>
                      <TableHead className="text-right">Outstanding</TableHead>
                      <TableHead>Mandate</TableHead>
                      <TableHead>Route KYC</TableHead>
                      <TableHead className="text-right">Coins</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {restaurants.map((restaurant: any) => (
                      <TableRow key={restaurant.name}>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            {/* Status dot — green = Online (is_active=1),
                                red = Offline. Pulses subtly on Online to
                                signal "live + receiving orders". */}
                            <span
                              className={cn(
                                "h-2 w-2 rounded-full shrink-0",
                                restaurant.is_active
                                  ? "bg-emerald-500 ring-2 ring-emerald-500/20 animate-pulse"
                                  : "bg-rose-400 ring-2 ring-rose-400/20"
                              )}
                              title={restaurant.is_active ? "Online — live + receiving orders" : "Offline"}
                              aria-label={restaurant.is_active ? "Online" : "Offline"}
                            />
                            <div className="flex flex-col min-w-0">
                              <span className="font-bold truncate">{restaurant.restaurant_name}</span>
                              <span className="text-xs text-muted-foreground truncate">{restaurant.owner_email}</span>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <code className="text-[10px] bg-muted px-1 rounded">{restaurant.restaurant_id}</code>
                        </TableCell>
                        <TableCell>
                          {(() => {
                            // Show the restaurant's actual Success Share %. Most
                            // are 3% (new default); legacy ones grandfathered at
                            // 1.5% appear distinct so ops can spot them.
                            const rate = Number(restaurant.platform_fee_percent ?? 0)
                            const isLegacy = Math.abs(rate - 1.5) < 0.001
                            return (
                              <Badge
                                variant="outline"
                                className={isLegacy
                                  ? 'bg-amber-50 text-amber-700 border-amber-200 font-mono'
                                  : 'bg-emerald-50 text-emerald-700 border-emerald-200 font-mono'}
                                title={isLegacy ? 'Grandfathered legacy rate' : 'Current default rate'}
                              >
                                {rate}%
                              </Badge>
                            )
                          })()}
                        </TableCell>
                        {/* Outstanding cash Success Share (paise → rupees).
                            Show in red when in cash-payment throttle window. */}
                        <TableCell className="text-right font-mono">
                          {(() => {
                            const paise = Number(restaurant.outstanding_commission_paise || 0)
                            const isThrottled = restaurant.cash_payments_disabled_until
                              ? new Date(restaurant.cash_payments_disabled_until) >= new Date(new Date().toDateString())
                              : false
                            if (paise === 0) {
                              return <span className="text-muted-foreground">₹0</span>
                            }
                            return (
                              <span
                                className={isThrottled ? 'text-rose-600 font-bold' : 'text-amber-600 font-semibold'}
                                title={isThrottled
                                  ? `Throttled — cash disabled until ${restaurant.cash_payments_disabled_until}`
                                  : 'Outstanding cash Success Share'}
                              >
                                ₹{(paise / 100).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                              </span>
                            )
                          })()}
                        </TableCell>
                        <TableCell>
                          {(() => {
                            const s = restaurant.mandate_status || ''
                            const map: Record<string, { label: string; cls: string }> = {
                              active:   { label: 'Active',   cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
                              inactive: { label: 'Inactive', cls: 'bg-stone-50 text-stone-600 border-stone-200' },
                              failed:   { label: 'Failed',   cls: 'bg-rose-50 text-rose-700 border-rose-200' },
                            }
                            const m = map[s] || { label: s || '—', cls: 'bg-stone-50 text-stone-500 border-stone-200' }
                            return <Badge variant="outline" className={m.cls}>{m.label}</Badge>
                          })()}
                        </TableCell>
                        <TableCell>
                          {(() => {
                            const k = restaurant.razorpay_kyc_status || ''
                            const map: Record<string, { label: string; cls: string }> = {
                              activated:           { label: 'Activated',     cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
                              under_review:        { label: 'Under Review',  cls: 'bg-blue-50 text-blue-700 border-blue-200' },
                              needs_clarification: { label: 'Needs Info',    cls: 'bg-amber-50 text-amber-700 border-amber-200' },
                              rejected:            { label: 'Rejected',      cls: 'bg-rose-50 text-rose-700 border-rose-200' },
                              suspended:           { label: 'Suspended',     cls: 'bg-rose-50 text-rose-700 border-rose-200' },
                            }
                            const m = map[k] || { label: k || 'Not started', cls: 'bg-stone-50 text-stone-500 border-stone-200' }
                            return <Badge variant="outline" className={m.cls}>{m.label}</Badge>
                          })()}
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
                                  setIsSettingsModalOpen(true)
                                }}>
                                  <Settings className="h-4 w-4 mr-2" />
                                  <span>Configure</span>
                                </DropdownMenuItem>
                                {!isSupervisorOnly && (
                                  <DropdownMenuItem onClick={() => {
                                    setRestaurantToDelete({ id: restaurant.restaurant_id, name: restaurant.restaurant_name })
                                    setVerificationInput('')
                                    setIsDeleteDialogOpen(true)
                                  }} className="text-red-600">
                                    <Trash2 className="h-4 w-4 mr-2" />
                                    <span>Delete</span>
                                  </DropdownMenuItem>
                                )}
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
                {coinAction === 'grant' ? 'Manually add' : 'Manually remove'} digital coins {coinAction === 'grant' ? 'to' : 'from'} <span className="font-bold text-foreground">"{selectedRestaurant?.restaurant_name}"</span>.
              </DialogDescription>
            </DialogHeader>
          </div>
          <div className="px-8 pb-8 space-y-5">
            <div className="flex items-center justify-center gap-2 bg-muted/20 p-1 rounded-xl mb-2">
              <button
                onClick={() => {
                  setCoinAction('grant')
                  setCoinReason('Admin Grant')
                }}
                className={cn(
                  "flex-1 py-2 rounded-lg text-xs font-bold transition-all",
                  coinAction === 'grant' ? "bg-white shadow-sm text-amber-600" : "text-muted-foreground hover:text-foreground"
                )}
              >
                Grant Credits
              </button>
              <button
                onClick={() => {
                  setCoinAction('deduct')
                  setCoinReason('Admin Deduction')
                }}
                className={cn(
                  "flex-1 py-2 rounded-lg text-xs font-bold transition-all",
                  coinAction === 'deduct' ? "bg-white shadow-sm text-red-600" : "text-muted-foreground hover:text-foreground"
                )}
              >
                Deduct Coins
              </button>
            </div>

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
              className={cn(
                "rounded-xl px-6 flex-1 sm:flex-none text-white shadow-sm",
                coinAction === 'grant' ? "bg-amber-600 hover:bg-amber-700" : "bg-red-600 hover:bg-red-700"
              )}
            >
              {coinAction === 'grant' ? 'Authorize Grant' : 'Authorize Deduction'}
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

              <div className="space-y-2">
                <Label className="text-xs font-semibold text-muted-foreground ml-1">Success Share (%)</Label>
                <NumberInput value={editPlatformFee} onChange={(e: any) => setEditPlatformFee(e.target.value)} className="h-11 rounded-xl bg-background border-slate-300 font-bold text-foreground" />
              </div>
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
          <div className="p-8 bg-gradient-to-br from-primary/10 via-background to-background border-b relative overflow-hidden">
            <div className="absolute -top-10 -right-10 opacity-[0.03] rotate-12">
              <Inbox className="h-40 w-40" />
            </div>
            <DialogHeader className="relative z-10">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-center gap-4">
                  <div className="p-3 bg-primary/10 rounded-2xl backdrop-blur-sm border border-primary/20 shadow-inner">
                    <Inbox className="h-6 w-6 text-primary" />
                  </div>
                  <div>
                    <DialogTitle className="text-2xl font-black tracking-tight">Onboarding Inbox</DialogTitle>
                    <DialogDescription className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                      <div className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                      Review and finalize new restaurant setups
                    </DialogDescription>
                  </div>
                </div>
                {selectedOnboarding.length > 0 && (
                  <div className="flex items-center gap-3 animate-in fade-in slide-in-from-right-4 duration-300">
                    <Badge className="bg-primary/10 text-primary border-primary/20 px-3 py-1 text-xs font-bold rounded-full">
                      {selectedOnboarding.length} Selected
                    </Badge>
                    <Button
                      variant="destructive"
                      size="sm"
                      className="h-9 rounded-xl font-bold shadow-lg shadow-red-500/10 hover:scale-105 transition-all"
                      onClick={handleBulkDelete}
                      disabled={updating === 'bulk-delete'}
                    >
                      <Trash2 className="h-3.5 w-3.5 mr-2" />
                      Delete
                    </Button>
                  </div>
                )}
              </div>
            </DialogHeader>
          </div>

          <div className="px-6 py-5 bg-muted/5 border-b">
            <div className="flex flex-col gap-4">
              <div className="flex flex-col sm:flex-row gap-3 items-end animate-in fade-in slide-in-from-top-2 duration-300">
                <div className="flex-1 space-y-2 w-full">
                  <Label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground ml-1">
                    Select Restaurant
                  </Label>
                  <RestaurantSelector
                    value={selectedOnboardingResId}
                    onSelect={setSelectedOnboardingResId}
                    options={(restaurants || []).map((r: any) => ({
                      value: r.name,
                      label: r.restaurant_name
                    }))}
                    placeholder="Search existing restaurants..."
                  />
                </div>
                <Button
                  onClick={handleGenerateLink}
                  disabled={isGenerating || !selectedOnboardingResId}
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
                            className="h-9 px-3 text-xs font-bold hover:bg-primary/10 hover:text-primary transition-all rounded-lg"
                            onClick={() => window.open(req.onboarding_link, '_blank')}
                          >
                            <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                            Launch
                          </Button>

                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-9 px-3 text-xs font-bold hover:bg-muted transition-all rounded-lg"
                            onClick={() => handleCopyOnboardingLink(req.onboarding_link)}
                          >
                            <ClipboardCopy className="h-3.5 w-3.5 mr-1.5" />
                            Copy
                          </Button>

                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-9 w-9 text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-all rounded-lg"
                            onClick={() => handleDeleteOnboarding(req.name)}
                            disabled={updating === req.name}
                          >
                            <Trash2 className="h-4 w-4" />
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
      {/* Platform Settings Modal */}
      <Dialog open={isPlatformSettingsModalOpen} onOpenChange={setIsPlatformSettingsModalOpen}>
        <DialogContent className="sm:max-w-[500px] rounded-3xl p-0 overflow-hidden border-none shadow-2xl">
          <div className="bg-gradient-to-br from-stone-900 to-stone-800 dark:from-stone-950 dark:to-stone-900 p-8 text-white relative overflow-hidden">
            <div className="absolute -top-6 -right-6 p-8 opacity-10 rotate-12 group-hover:rotate-45 transition-transform duration-1000">
              <Settings className="h-32 w-32" />
            </div>
            <div className="absolute top-0 left-0 w-full h-full bg-[radial-gradient(circle_at_30%_30%,rgba(255,255,255,0.05),transparent)] pointer-events-none" />
            <DialogHeader className="relative z-10">
              <div className="flex items-center gap-3 mb-2">
                <div className="p-2 bg-white/10 rounded-xl backdrop-blur-md border border-white/10">
                  <Settings className="h-5 w-5 text-amber-400" />
                </div>
                <DialogTitle className="text-2xl font-black tracking-tight text-white">Platform Settings</DialogTitle>
              </div>
              <DialogDescription className="text-stone-400 font-medium pl-1">
                Universal configuration for Flamezo ecosystem
              </DialogDescription>
            </DialogHeader>
          </div>

          <div className="p-8 space-y-8 bg-background">
            <div className="space-y-6">
              <div className="flex items-center justify-between p-5 bg-muted/30 dark:bg-muted/10 rounded-2xl border border-border/50 hover:border-primary/20 transition-all shadow-sm">
                <div className="space-y-1">
                  <Label className="text-base font-bold flex items-center gap-2">
                    Charge GST 
                    {platformSettings.charge_gst && <Badge className="bg-green-500/20 text-green-600 border-none text-[9px] h-4">ACTIVE</Badge>}
                  </Label>
                  <p className="text-xs text-muted-foreground font-medium">Add tax to all platform transactions</p>
                </div>
                <Switch 
                  checked={platformSettings.charge_gst}
                  onCheckedChange={(v) => setPlatformSettings(prev => ({ ...prev, charge_gst: v }))}
                />
              </div>

              {platformSettings.charge_gst && (
                <div className="space-y-2 animate-in fade-in slide-in-from-top-2 duration-300">
                  <Label className="text-sm font-bold ml-1 text-muted-foreground">GST Percentage (%)</Label>
                  <NumberInput
                    value={platformSettings.gst_percent}
                    onChange={(e) => setPlatformSettings(prev => ({ ...prev, gst_percent: parseFloat(e.target.value || '0') }))}
                    placeholder="18.0"
                    className="h-12 rounded-xl bg-muted/30 border-border focus-visible:ring-primary/20"
                  />
                </div>
              )}

              <div className="h-px bg-stone-100" />

              <div className="space-y-2">
                <Label className="text-sm font-bold ml-1 text-muted-foreground">Platform Success Share (%)</Label>
                <NumberInput
                  value={platformSettings.gold_commission_percent}
                  onChange={(e) => setPlatformSettings(prev => ({ ...prev, gold_commission_percent: parseFloat(e.target.value || '0') }))}
                  className="h-12 rounded-xl"
                />
              </div>
            </div>
          </div>

          <DialogFooter className="p-6 bg-muted/30 dark:bg-muted/10 border-t border-border/50 flex flex-row gap-3">
            <Button 
              variant="ghost" 
              onClick={() => setIsPlatformSettingsModalOpen(false)}
              className="rounded-xl h-12 font-bold flex-1"
            >
              Cancel
            </Button>
            <Button 
              onClick={handleUpdatePlatformSettings}
              disabled={updating === 'platform-settings'}
              className="rounded-xl h-12 px-10 font-bold bg-stone-900 dark:bg-primary text-white hover:bg-stone-800 dark:hover:bg-primary/90 shadow-xl shadow-stone-900/10 transition-all flex-1"
            >
              {updating === 'platform-settings' ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  )
}
