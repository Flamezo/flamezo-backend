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
  ExternalLink,
  Save,
  Eye,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Info,
  RefreshCcw,
  Loader2,
  Store,
  Star,
  Sparkles,
} from 'lucide-react'
import { Switch } from '@/components/ui/switch'
import { useDataTable } from '@/hooks/useDataTable'
import { DataPagination } from '@/components/ui/DataPagination'
import { MerchantSelector } from '@/components/MerchantSelector'
import { BranchGroupTools } from '@/components/BranchGroupTools'
import { SearchableSelect } from '@/components/SearchableSelect'
import { BranchAccessDialog } from '@/components/BranchAccessDialog'
import { UpdateSuccessShareModal } from '@/components/UpdateSuccessShareModal'
import { UpdateLimelightModal } from '@/components/UpdateLimelightModal'

interface Merchant {
  name: string
  outlet_id: string
  outlet_name: string
  owner_email?: string
  owner_phone?: string
  outlet_type?: string
  is_active: number
  coins_balance: number
  platform_fee_percent: number
  is_signature?: number
  is_featured?: number
  limelight_start_date?: string | null
  limelight_end_date?: string | null
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

const OUTLET_TYPE_META: Record<string, { label: string; cls: string }> = {
  dining:        { label: 'Dine · Banquets',     cls: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-800' },
  cafe:          { label: 'Cafe · Bakeries',      cls: 'bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-400 dark:border-yellow-800' },
  wellness:      { label: 'Wellness · Beauty',    cls: 'bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-900/20 dark:text-teal-400 dark:border-teal-800' },
  fitness:       { label: 'Fitness · Yoga',       cls: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/20 dark:text-blue-400 dark:border-blue-800' },
  sports_court:  { label: 'Sports · Court',       cls: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800' },
  sports_venue:  { label: 'Play · Sports',        cls: 'bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-900/20 dark:text-cyan-400 dark:border-cyan-800' },
  fashion:       { label: 'Fashion · Accessories',cls: 'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-900/20 dark:text-purple-400 dark:border-purple-800' },
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

interface OnboardingDetail {
  name: string
  outlet_name: string
  linked_restaurant?: string
  status: string
  owner_name?: string
  owner_email?: string
  owner_phone?: string
  whatsapp_number?: string
  fssai_number?: string
  gst_number?: string
  tax_rate?: number
  pan_number?: string
  legal_name?: string
  business_type?: string
  bank_account_number?: string
  bank_ifsc?: string
  bank_holder_name?: string
  opening_time?: string
  closing_time?: string
  subtitle?: string
  description?: string
  default_theme?: string
  menu_layout?: string
  enable_table_booking?: number
  enable_banquet_booking?: number
  tables?: number
  address?: string
  city?: string
  state?: string
  zip_code?: string
  google_map_url?: string
  tagline?: string
  instagram_link?: string
  facebook_link?: string
  website_link?: string
  google_review_link?: string
  menu_link?: string
  logo?: string
  hero_image?: string
  menu_photos?: string[]
}

type WarningSeverity = 'error' | 'warning' | 'info'
interface FieldWarning { field: string; severity: WarningSeverity; message: string }

function validateOnboardingData(d: OnboardingDetail): FieldWarning[] {
  const warnings: FieldWarning[] = []
  const w = (field: string, severity: WarningSeverity, message: string) => warnings.push({ field, severity, message })

  // Contact
  if (!d.owner_name?.trim()) w('Owner Name', 'error', 'Missing')
  if (!d.owner_email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(d.owner_email)) w('Owner Email', 'error', 'Invalid email format')
  if (!d.owner_phone || !/^\d{10}$/.test(d.owner_phone.replace(/\D/g, ''))) w('Owner Phone', 'warning', 'Should be a 10-digit mobile number')
  if (d.whatsapp_number && !/^\d{10}$/.test(d.whatsapp_number.replace(/\D/g, ''))) w('WhatsApp Number', 'warning', 'Should be 10 digits')

  // Legal
  if (!d.fssai_number || !/^\d{14}$/.test(d.fssai_number.replace(/\s/g, ''))) w('FSSAI Number', 'error', 'Must be exactly 14 digits')
  if (!d.gst_number) w('GST Number', 'warning', 'Not provided')
  else if (!/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/.test(d.gst_number.toUpperCase())) w('GST Number', 'warning', "Doesn't match standard format (e.g. 27AAAAA0000A1Z5)")
  if (!d.pan_number) w('PAN Number', 'warning', 'Not provided')
  else if (!/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(d.pan_number.toUpperCase())) w('PAN Number', 'warning', 'Should be 10 chars, e.g. AAAAA1234A')
  if (!d.bank_account_number || !/^\d{9,18}$/.test(d.bank_account_number.replace(/\s/g, ''))) w('Bank Account', 'warning', 'Should be 9–18 digit account number')
  if (!d.bank_ifsc || !/^[A-Z]{4}0[A-Z0-9]{6}$/.test(d.bank_ifsc.toUpperCase())) w('IFSC Code', 'warning', 'Format: 4 letters + 0 + 6 alphanumeric, e.g. HDFC0001234')
  if (!d.legal_name?.trim()) w('Legal Name', 'warning', 'Business legal name not provided')
  if (d.tax_rate !== null && d.tax_rate !== undefined && ![0, 5, 12, 18, 28].includes(Number(d.tax_rate))) w('Tax Rate', 'warning', `${d.tax_rate}% is not a standard GST slab (0/5/12/18/28%)`)

  // Location
  if (!d.address?.trim()) w('Address', 'error', 'Missing')
  if (!d.city?.trim()) w('City', 'error', 'Missing')
  if (!d.state?.trim()) w('State', 'error', 'Missing')
  if (!d.zip_code || !/^\d{6}$/.test(d.zip_code)) w('PIN Code', 'warning', 'Should be a 6-digit Indian PIN code')
  if (!d.google_map_url) w('Google Maps Link', 'info', 'Not provided')
  else if (!/google\.com\/maps|maps\.app\.goo\.gl|goo\.gl\/maps/.test(d.google_map_url)) w('Google Maps Link', 'warning', "Doesn't look like a Google Maps URL")

  // Branding
  if (!d.logo) w('Logo', 'error', 'Not uploaded')
  if (!d.tagline?.trim()) w('Tagline', 'info', 'Not provided')
  if (!d.description?.trim()) w('Description', 'info', 'Not provided')
  else if (d.description.trim().length < 30) w('Description', 'info', 'Very short — add more detail for better discovery')

  // Operations
  if (!d.opening_time) w('Opening Time', 'warning', 'Not set')
  if (!d.closing_time) w('Closing Time', 'warning', 'Not set')

  return warnings
}

export default function AdminMerchantManagement() {
  const navigate = useNavigate()
  const { currentUser } = useFrappeAuth()
  const [updating, setUpdating] = useState<string | null>(null)
  const [isAdmin, setIsAdmin] = useState(false)
  const [isOnboardingModalOpen, setIsOnboardingModalOpen] = useState(false)
  const [selectedOnboarding, setSelectedOnboarding] = useState<string[]>([])
  const [showCompleted, setShowCompleted] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [selectedOnboardingResId, setSelectedOnboardingResId] = useState('')
  const [isLinkModalOpen, setIsLinkModalOpen] = useState(false)
  const [linkToCopy, setLinkToCopy] = useState('')

  // Opens the "Update Success Share?" prompt right after a Signature toggle
  // succeeds — set to the merchant just toggled, null when closed.
  const [shareUpdateTarget, setShareUpdateTarget] = useState<Merchant | null>(null)
  const [isSavingShareRate, setIsSavingShareRate] = useState(false)

  const [limelightUpdateTarget, setLimelightUpdateTarget] = useState<Merchant | null>(null)
  const [isSavingLimelight, setIsSavingLimelight] = useState(false)

  // Modals state
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
  const [merchantToDelete, setMerchantToDelete] = useState<{ id: string, name: string } | null>(null)
  const [verificationInput, setVerificationInput] = useState('')

  const [isCoinModalOpen, setIsCoinModalOpen] = useState(false)
  const [coinAmount, setCoinAmount] = useState('')
  const [coinReason, setCoinReason] = useState('Admin Grant')
  const [coinAction, setCoinAction] = useState<'grant' | 'deduct'>('grant')
  const [selectedMerchant, setSelectedMerchant] = useState<Merchant | null>(null)



  const [isSupervisorOnly, setIsSupervisorOnly] = useState(false)
  
  const [isPlatformSettingsModalOpen, setIsPlatformSettingsModalOpen] = useState(false)
  const [isBranchAccessOpen, setIsBranchAccessOpen] = useState(false)
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
    data: merchants,
    isLoading,
    mutate: loadMerchants,
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
    customEndpoint: 'flamezo_backend.flamezo.api.admin.get_all_outlets',
    paramNames: {
      page: 'page',
      pageSize: 'page_size',
      search: 'search',
      filters: 'filters'
    },
    initialPageSize: 20,
    debugId: 'admin-merchants'
  })

  // Merchant Groups (for the group filter + tools)
  const [groups, setGroups] = useState<Array<{ id: string; group_name: string; branch_count?: number }>>([])
  const [groupsReload, setGroupsReload] = useState(0)
  const { call: listGroups } = useFrappePostCall<{ success: boolean; groups?: any[] }>(
    'flamezo_backend.flamezo.api.branch_clone.list_groups'
  )
  useEffect(() => {
    listGroups({}).then((r: any) => { const d = r?.message ?? r; setGroups(d?.groups || []) }).catch(() => {})
  }, [groupsReload])

  // APIs
  const { call: toggleMerchantStatus } = useFrappePostCall<{ success: boolean, error?: string }>(
    'flamezo_backend.flamezo.api.admin.toggle_outlet_status'
  )
  const { call: deleteMerchant } = useFrappePostCall<{ success: boolean, message?: string, error?: string }>(
    'flamezo_backend.flamezo.api.admin.delete_outlet'
  )
  const { call: giveCoins } = useFrappePostCall<{ success: boolean, message?: string, error?: string }>(
    'flamezo_backend.flamezo.api.admin.admin_give_coins'
  )
  const { call: updateSettings } = useFrappePostCall<{ success: boolean, message?: string, error?: string }>(
    'flamezo_backend.flamezo.api.admin.admin_update_outlet_settings'
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
  const { call: fetchOnboardingDetail } = useFrappePostCall(
    'flamezo_backend.flamezo.api.onboarding.get_onboarding_by_name'
  )
  const { call: syncOnboarding } = useFrappePostCall(
    'flamezo_backend.flamezo.api.onboarding.sync_onboarding_to_outlet'
  )

  // Review modal state
  const [isReviewModalOpen, setIsReviewModalOpen] = useState(false)
  const [reviewDetail, setReviewDetail] = useState<OnboardingDetail | null>(null)
  const [reviewLoading, setReviewLoading] = useState(false)
  const [syncingName, setSyncingName] = useState<string | null>(null)
  const [optimisticTypes, setOptimisticTypes] = useState<Record<string, string>>({})

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
    'flamezo_backend.flamezo.api.admin.get_admin_outlets_stats',
    {},
    'admin-merchants-stats'
  )
  const adminStats: AdminStats | undefined = rawAdminStats?.message?.data

  useEffect(() => {
    if (rawPlatformSettings?.message?.data) {
      setPlatformSettings(rawPlatformSettings.message.data)
    }
  }, [rawPlatformSettings])

  const handleStatusToggle = async (outletName: string, currentStatus: number) => {
    try {
      setUpdating(outletName)
      const newStatus = currentStatus ? 0 : 1
      const result = await toggleMerchantStatus({ outlet_id: outletName, is_active: newStatus }) as any
      if (result?.message?.success) {
        toast.success(`Merchant ${newStatus ? 'activated' : 'deactivated'}`)
        loadMerchants()
      }
    } catch (error) {
      toast.error('Status synchronization failed')
    } finally {
      setUpdating(null)
    }
  }

  // Signature toggle — same effect as the Add Merchant modal's Signature
  // switch and the merchant details page's Signature toggle: flips
  // is_signature and its paired Success Share rate together (7% normal,
  // 11% signature) so the badge in the Success Share column and the ⭐ next
  // to the name both stay consistent with the table's own read of these
  // fields, with no separate optimistic-state plumbing needed.
  // Signature status and Success Share rate are separate decisions — this
  // toggle ONLY flips is_signature. Rate changes are never automatic; after
  // a successful toggle we open shareUpdateTarget so the admin can
  // explicitly choose to update the rate (or skip and leave it as-is).
  const handleSignatureToggle = async (merchant: Merchant, nextValue: boolean) => {
    try {
      setUpdating(merchant.name)
      const res = await updateSettings({
        outlet_id: merchant.outlet_id,
        updates: JSON.stringify({ is_signature: nextValue ? 1 : 0 }),
      }) as any
      if (res?.message?.success) {
        toast.success(nextValue ? 'Marked as Signature merchant' : 'Removed Signature status')
        await loadMerchants()
        setShareUpdateTarget(merchant)
      } else {
        toast.error(res?.message?.error || 'Failed to update Signature status')
      }
    } catch (error) {
      toast.error('Signature update failed')
    } finally {
      setUpdating(null)
    }
  }

  const handleUpdateShareRate = async (newRate: number) => {
    if (!shareUpdateTarget) return
    try {
      setIsSavingShareRate(true)
      const res = await updateSettings({
        outlet_id: shareUpdateTarget.outlet_id,
        updates: JSON.stringify({ platform_fee_percent: newRate }),
      }) as any
      if (res?.message?.success) {
        toast.success(`Success Share updated to ${newRate}%`)
        loadMerchants()
        setShareUpdateTarget(null)
      } else {
        toast.error(res?.message?.error || 'Failed to update Success Share')
      }
    } catch (error) {
      toast.error('Success Share update failed')
    } finally {
      setIsSavingShareRate(false)
    }
  }

  const handleLimelightToggle = async (merchant: Merchant, nextValue: boolean) => {
    if (nextValue) {
      setLimelightUpdateTarget(merchant)
    } else {
      try {
        setUpdating(merchant.name)
        const res = await updateSettings({
          outlet_id: merchant.outlet_id,
          updates: JSON.stringify({ is_featured: 0, limelight_start_date: null, limelight_end_date: null }),
        }) as any
        if (res?.message?.success) {
          toast.success('Removed from Limelight')
          await loadMerchants()
        } else {
          toast.error(res?.message?.error || 'Failed to remove from Limelight')
        }
      } catch (error) {
        toast.error('Limelight update failed')
      } finally {
        setUpdating(null)
      }
    }
  }

  const handleUpdateLimelight = async (startDate: string, endDate: string | null) => {
    if (!limelightUpdateTarget) return
    try {
      setIsSavingLimelight(true)
      const res = await updateSettings({
        outlet_id: limelightUpdateTarget.outlet_id,
        updates: JSON.stringify({ 
          is_featured: 1,
          limelight_start_date: startDate,
          limelight_end_date: endDate
        }),
      }) as any
      if (res?.message?.success) {
        toast.success(`Limelight schedule set`)
        loadMerchants()
        setLimelightUpdateTarget(null)
      } else {
        toast.error(res?.message?.error || 'Failed to update Limelight schedule')
      }
    } catch (error) {
      toast.error('Limelight schedule update failed')
    } finally {
      setIsSavingLimelight(false)
    }
  }

  const handleGiveCoins = async () => {
    if (!selectedMerchant || !coinAmount) return
    try {
      setUpdating(selectedMerchant.name)
      const amount = parseFloat(coinAmount)
      const finalAmount = coinAction === 'grant' ? amount : -Math.abs(amount)
      
      const result = await giveCoins({
        outlet_id: selectedMerchant.outlet_id,
        amount: finalAmount,
        reason: coinReason
      }) as any
      if (result?.message?.success) {
        toast.success(`${coinAction === 'grant' ? 'Granted' : 'Deducted'} ${coinAmount} coins`)
        setIsCoinModalOpen(false)
        loadMerchants()
      }
    } catch (error) {
      toast.error('Treasury update failed')
    } finally {
      setUpdating(null)
    }
  }



  const handleConfirmDelete = async () => {
    if (!merchantToDelete || verificationInput !== merchantToDelete.id) return
    try {
      setUpdating(merchantToDelete.id)
      const result = await deleteMerchant({ outlet_id: merchantToDelete.id }) as any
      if (result?.message?.success) {
        toast.success(`Merchant removed from system`)
        setIsDeleteDialogOpen(false)
        loadMerchants()
      } else {
        const msg = result?.message?.error || 'System purge failed'
        toast.error(msg)
      }
    } catch (error: any) {
      const msg = error?.message || 'System purge failed'
      toast.error(msg)
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
    const all = visibleOnboarding.map((r: any) => r.name)
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
      toast.error('Please select an outlet')
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

  const handleReviewOnboarding = async (name: string) => {
    setReviewLoading(true)
    setReviewDetail(null)
    setIsReviewModalOpen(true)
    try {
      const result = await fetchOnboardingDetail({ name }) as any
      if (result?.message?.success) {
        setReviewDetail(result.message.data)
      } else {
        toast.error(result?.message?.error || 'Failed to load details')
        setIsReviewModalOpen(false)
      }
    } catch {
      toast.error('Failed to load onboarding details')
      setIsReviewModalOpen(false)
    } finally {
      setReviewLoading(false)
    }
  }

  const handleSyncOnboarding = async (name: string) => {
    setSyncingName(name)
    try {
      const result = await syncOnboarding({ name }) as any
      if (result?.message?.success) {
        toast.success(result.message.message || 'Synced successfully')
        loadOnboarding()
        setIsReviewModalOpen(false)
        setReviewDetail(null)
      } else {
        toast.error(result?.message?.error || 'Sync failed')
      }
    } catch {
      toast.error('Sync failed')
    } finally {
      setSyncingName(null)
    }
  }

  const allOnboarding: any[] = onboardingData?.message?.data || []
  const pendingCount = allOnboarding.filter((r: any) => r.status === 'Client Submitted').length
  const completedCount = allOnboarding.filter((r: any) => r.status === 'Completed').length
  const visibleOnboarding = showCompleted ? allOnboarding : allOnboarding.filter((r: any) => r.status !== 'Completed')

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
              You lack the administrative clearance required to access the central merchant control hub.
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
    <div className="p-4 sm:p-6 space-y-3">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Merchant Management</h2>
          <p className="text-muted-foreground text-sm">
            Manage all merchants across all industries
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
            onClick={() => setIsBranchAccessOpen(true)}
            variant="outline"
            className="h-11 px-4 rounded-xl border-stone-200 hover:border-primary/30 hover:bg-primary/5 hover:-translate-y-1 hover:shadow-lg active:translate-y-0 transition-all duration-300 font-semibold group"
          >
            <Store className="h-4 w-4 mr-2 group-hover:scale-110 transition-transform" />
            Branch Access
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

      {/* Fleet-wide stats strip. Single read of get_admin_outlets_stats;
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
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
            <button
              type="button"
              className={cn(
                'text-left rounded-xl border bg-card p-2 hover:border-primary/40 hover:shadow-sm transition',
                isStatActive(null) ? 'ring-2 ring-primary/30 ring-offset-1' : ''
              )}
              onClick={() => applyStatFilter(null, null)}
              title="Show all merchants (clears stat-card filters)"
            >
              <div className="flex items-baseline justify-between gap-1.5">
                <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Total</p>
                <p className="text-base font-black tracking-tight leading-none">{adminStats.total}</p>
              </div>
              <p className="text-[10px] text-muted-foreground mt-0.5">{adminStats.active} online · {adminStats.inactive} offline</p>
            </button>
            <button
              type="button"
              className={cn(
                'text-left rounded-xl border bg-emerald-50/50 dark:bg-emerald-500/5 p-2 hover:border-emerald-300 hover:shadow-sm transition border-emerald-200/60 dark:border-emerald-500/20',
                'ring-emerald-300' + ring(isStatActive('is_active', 1))
              )}
              onClick={() => applyStatFilter('is_active', 1)}
              title="Show only active merchants"
            >
              <div className="flex items-baseline justify-between gap-1.5">
                <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-700 dark:text-emerald-400">Active</p>
                <p className="text-base font-black tracking-tight leading-none text-emerald-700 dark:text-emerald-300">{adminStats.active}</p>
              </div>
              <p className="text-[10px] text-emerald-700/70 dark:text-emerald-400/70 mt-0.5">Live</p>
            </button>
            <button
              type="button"
              className={cn(
                'text-left rounded-xl border bg-amber-50/50 dark:bg-amber-500/5 p-2 hover:border-amber-300 hover:shadow-sm transition border-amber-200/60 dark:border-amber-500/20',
                'ring-amber-300' + ring(isStatActive('has_outstanding', 'yes'))
              )}
              onClick={() => applyStatFilter('has_outstanding', 'yes')}
              title="Show only merchants with outstanding Success Share"
            >
              <div className="flex items-baseline justify-between gap-1.5">
                <p className="text-[10px] font-bold uppercase tracking-widest text-amber-700 dark:text-amber-400">Owing</p>
                <p className="text-base font-black tracking-tight leading-none text-amber-700 dark:text-amber-300">₹{adminStats.total_outstanding_rupees.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</p>
              </div>
              <p className="text-[10px] text-amber-700/70 dark:text-amber-400/70 mt-0.5">{adminStats.owing} merchants</p>
            </button>
            <button
              type="button"
              className={cn(
                'text-left rounded-xl border bg-rose-50/50 dark:bg-rose-500/5 p-2 hover:border-rose-300 hover:shadow-sm transition border-rose-200/60 dark:border-rose-500/20',
                'ring-rose-300' + ring(isStatActive('throttled', 'yes'))
              )}
              onClick={() => applyStatFilter('throttled', 'yes')}
              title="Show only merchants currently in cash-payment throttle"
            >
              <div className="flex items-baseline justify-between gap-1.5">
                <p className="text-[10px] font-bold uppercase tracking-widest text-rose-700 dark:text-rose-400">Throttled</p>
                <p className="text-base font-black tracking-tight leading-none text-rose-700 dark:text-rose-300">{adminStats.throttled}</p>
              </div>
              <p className="text-[10px] text-rose-700/70 dark:text-rose-400/70 mt-0.5">Cash paused (Tier 3)</p>
            </button>
            <button
              type="button"
              className={cn(
                'text-left rounded-xl border bg-blue-50/50 dark:bg-blue-500/5 p-2 hover:border-blue-300 hover:shadow-sm transition border-blue-200/60 dark:border-blue-500/20',
                'ring-blue-300' + ring(isStatActive('razorpay_kyc_status', 'under_review'))
              )}
              onClick={() => applyStatFilter('razorpay_kyc_status', 'under_review')}
              title="Show only merchants whose Route KYC is under review"
            >
              <div className="flex items-baseline justify-between gap-1.5">
                <p className="text-[10px] font-bold uppercase tracking-widest text-blue-700 dark:text-blue-400">KYC Pending</p>
                <p className="text-base font-black tracking-tight leading-none text-blue-700 dark:text-blue-300">{adminStats.kyc_pending}</p>
              </div>
              <p className="text-[10px] text-blue-700/70 dark:text-blue-400/70 mt-0.5">{adminStats.kyc_activated} activated · {adminStats.kyc_blocked} blocked</p>
            </button>
            <button
              type="button"
              className={cn(
                'text-left rounded-xl border bg-violet-50/50 dark:bg-violet-500/5 p-2 hover:border-violet-300 hover:shadow-sm transition border-violet-200/60 dark:border-violet-500/20',
                'ring-violet-300' + ring(isStatActive('mandate_status', 'active'))
              )}
              onClick={() => applyStatFilter('mandate_status', 'active')}
              title="Show only merchants with an active autopay mandate"
            >
              <div className="flex items-baseline justify-between gap-1.5">
                <p className="text-[10px] font-bold uppercase tracking-widest text-violet-700 dark:text-violet-400">Mandate Active</p>
                <p className="text-base font-black tracking-tight leading-none text-violet-700 dark:text-violet-300">{adminStats.mandate_active}</p>
              </div>
              <p className="text-[10px] text-violet-700/70 dark:text-violet-400/70 mt-0.5">{adminStats.mandate_missing} missing</p>
            </button>
          </div>
        )
      })()}

      {/* Group action buttons — outside the filter box, right-aligned. */}
      <div className="flex items-center justify-end">
        <BranchGroupTools onGroupsChanged={() => setGroupsReload(k => k + 1)} />
      </div>

      <Card>
        {/* Compact single-line filter bar. The dropdown trigger reads
            "<Field>: <selected>" so we don't need per-item prefixes. Smaller
            h-8 + tighter widths + reduced padding keeps everything on one
            row up to ~1280px and frees vertical space for the table. */}
        <CardHeader className="py-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[180px] max-w-[260px]">
              <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search merchants..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-7 h-8 text-xs"
              />
            </div>
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={() => { loadMerchants(); loadAdminStats() }}
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
                const f = filters.find((f: any) => f.fieldname === 'is_active')
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

            {/* Group filter — searchable (type-to-find) */}
            <SearchableSelect
              value={(filters.find((f: any) => f.fieldname === 'branch_group')?.value as string) || 'all'}
              triggerClassName="w-[120px]"
              placeholder="Group: All"
              options={[{ value: 'all', label: 'Group: All' }, ...groups.map((g) => ({ value: g.id, label: g.group_name }))]}
              onChange={(v) => {
                const next = filters.filter(f => f.fieldname !== 'branch_group')
                if (v !== 'all') next.push({ fieldname: 'branch_group', operator: '=', value: v })
                setFilters(next)
              }}
            />

            {/* Business Type */}
            <Select
              value={(filters.find((f: any) => f.fieldname === 'outlet_type')?.value as string) || 'all'}
              onValueChange={(v) => {
                const next = filters.filter((f: any) => f.fieldname !== 'outlet_type')
                if (v !== 'all') next.push({ fieldname: 'outlet_type', operator: '=', value: v })
                setFilters(next)
              }}
            >
              <SelectTrigger className="h-8 w-[140px] text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Type: All</SelectItem>
                <SelectItem value="dining">Dine · Banquets</SelectItem>
                <SelectItem value="cafe">Cafe · Bakeries</SelectItem>
                <SelectItem value="wellness">Wellness · Beauty</SelectItem>
                <SelectItem value="fitness">Fitness · Yoga</SelectItem>
                <SelectItem value="sports_court">Sports · Court</SelectItem>
                <SelectItem value="sports_venue">Play · Sports</SelectItem>
                <SelectItem value="fashion">Fashion · Accessories</SelectItem>
              </SelectContent>
            </Select>

            {/* Share & Mandate filters hidden per admin request — the stat
                cards above still drill into owing/mandate/throttle slices. */}

            {/* Route KYC */}
            <Select
              value={(filters.find((f: any) => f.fieldname === 'razorpay_kyc_status')?.value as string) || 'all'}
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

            {/* Throttle filter hidden per admin request — use the Throttled
                stat card to view throttled merchants. */}

            {/* Clear-all chip — right end of the first filter line. Counts and
                clears ONLY the dropdown filters; the All/Normal/Signature tab
                is a separate control with its own clear (below). */}
            {filters.filter((f: any) => f.fieldname !== 'is_signature').length > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs px-2.5 gap-1 text-muted-foreground hover:text-foreground ml-auto"
                onClick={() => setFilters(filters.filter((f: any) => f.fieldname === 'is_signature'))}
              >
                <XCircle className="h-3.5 w-3.5" />
                Clear ({filters.filter((f: any) => f.fieldname !== 'is_signature').length})
              </Button>
            )}

            {/* Second line: All / Normal / Signature segmented toggle,
                pinned right. Normal = not Signature; Signature = flag or 11%. */}
            <div className="basis-full flex items-center gap-2 pt-1">
              {(() => {
                // Three-way segmented toggle: All / Normal / Signature, with a
                // sliding indicator that animates between the three columns.
                const sigFilter = filters.find((f: any) => f.fieldname === 'is_signature')
                const mode = !sigFilter ? 'all' : (Number(sigFilter.value) === 1 ? 'signature' : 'normal')
                const setMode = (m: 'all' | 'normal' | 'signature') => {
                  const next = filters.filter(f => f.fieldname !== 'is_signature')
                  if (m === 'signature') next.push({ fieldname: 'is_signature', operator: '=', value: 1 })
                  else if (m === 'normal') next.push({ fieldname: 'is_signature', operator: '=', value: 0 })
                  setFilters(next)
                }
                const seg = [
                  { key: 'all' as const, label: 'All' },
                  { key: 'normal' as const, label: 'Normal' },
                  { key: 'signature' as const, label: 'Signature' },
                ]
                const activeIndex = seg.findIndex(s => s.key === mode)
                const isSig = mode === 'signature'
                // Column weights — Signature gets more room than All/Normal.
                const weights = [0.82, 0.82, 1.36]
                const total = weights.reduce((a, b) => a + b, 0)
                const cumStart = weights.reduce<number[]>((acc, w, i) => {
                  acc.push(i === 0 ? 0 : acc[i - 1] + weights[i - 1]); return acc
                }, [])
                const leftFrac = cumStart[activeIndex] / total
                const widthFrac = weights[activeIndex] / total
                return (
                  <div
                    className="ml-auto relative grid items-center rounded-lg border border-border bg-muted/30 p-0.5 w-[230px]"
                    style={{ gridTemplateColumns: `${weights[0]}fr ${weights[1]}fr ${weights[2]}fr` }}
                  >
                    {/* Sliding indicator — width & offset follow the active column. */}
                    <div
                      className={cn(
                        'absolute inset-y-0.5 rounded-md shadow-sm transition-all duration-300 ease-out',
                        isSig ? 'bg-amber-500' : 'bg-background'
                      )}
                      style={{
                        left: `calc(2px + ${leftFrac} * (100% - 4px))`,
                        width: `calc(${widthFrac} * (100% - 4px))`,
                      }}
                    />
                    {seg.map(s => {
                      const active = mode === s.key
                      const sig = s.key === 'signature'
                      return (
                        <button
                          key={s.key}
                          type="button"
                          onClick={() => setMode(s.key)}
                          className={cn(
                            'relative z-10 h-7 rounded-md text-xs font-semibold transition-colors flex items-center justify-center gap-1',
                            active
                              ? (sig ? 'text-white' : 'text-foreground')
                              : 'text-muted-foreground hover:text-foreground'
                          )}
                        >
                          {sig && <Star className={cn('h-3 w-3', active ? 'fill-white text-white' : 'text-amber-500')} />}
                          {s.label}
                        </button>
                      )
                    })}
                  </div>
                )
              })()}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading && !merchants.length ? (
            <div className="py-20 flex justify-center">
              <div className="animate-spin h-6 w-6 border-2 border-primary border-t-transparent rounded-full" />
            </div>
          ) : !merchants || merchants.length === 0 ? (
            <div className="py-20 text-center text-muted-foreground">No merchants found</div>
          ) : (
            <>
              <div className="rounded-md border overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="sticky left-0 z-20 bg-muted shadow-[inset_-1px_0_0_theme(colors.border)] min-w-[250px]">Merchant</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>ID</TableHead>
                      <TableHead>Success Share</TableHead>
                      <TableHead>Route KYC</TableHead>
                      <TableHead className="text-center">Active</TableHead>
                      <TableHead className="text-center">Signature</TableHead>
                      <TableHead className="text-center">Limelight</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {merchants.map((merchant: any) => (
                      <TableRow key={merchant.name} className="group">
                        <TableCell className="sticky left-0 z-10 bg-background group-hover:bg-muted shadow-[inset_-1px_0_0_theme(colors.border)] transition-colors">
                          <div className="flex items-center gap-2">
                            {/* Status dot — green = Online (is_active=1),
                                red = Offline. Pulses subtly on Online to
                                signal "live". */}
                            <span
                              className={cn(
                                "h-2 w-2 rounded-full shrink-0",
                                merchant.is_active
                                  ? "bg-emerald-500 ring-2 ring-emerald-500/20 animate-pulse"
                                  : "bg-rose-400 ring-2 ring-rose-400/20"
                              )}
                              title={merchant.is_active ? "Online — live" : "Offline"}
                              aria-label={merchant.is_active ? "Online" : "Offline"}
                            />
                            <div className="flex flex-col min-w-0">
                              <span className="font-bold truncate flex items-center gap-1.5">
                                {merchant.outlet_name}
                                {(!!merchant.is_signature || Math.abs(Number(merchant.platform_fee_percent ?? 0) - 11) < 0.001) && (
                                  <Star
                                    className="h-3.5 w-3.5 shrink-0 text-amber-500 fill-amber-500"
                                    aria-label="Signature merchant"
                                  />
                                )}
                              </span>
                              <span className="text-xs text-muted-foreground truncate">{merchant.owner_email}</span>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          {(() => {
                            const type = optimisticTypes[merchant.outlet_id] || merchant.outlet_type || 'dining'
                            const m = OUTLET_TYPE_META[type] || { label: type, cls: 'bg-stone-50 text-stone-600 border-stone-200' }
                            return (
                              <Select
                                value={type}
                                onValueChange={async (newType) => {
                                  setOptimisticTypes(prev => ({ ...prev, [merchant.outlet_id]: newType }))
                                  const res = await updateSettings({
                                    outlet_id: merchant.outlet_id,
                                    updates: JSON.stringify({ outlet_type: newType }),
                                  })
                                  if (res?.message?.success) {
                                    loadMerchants()
                                    toast.success(`Type updated to ${OUTLET_TYPE_META[newType]?.label ?? newType}`)
                                  } else {
                                    setOptimisticTypes(prev => ({ ...prev, [merchant.outlet_id]: merchant.outlet_type || 'dining' }))
                                    toast.error(res?.message?.error || 'Failed to update type')
                                  }
                                }}
                              >
                                <SelectTrigger className={`h-7 text-[10px] font-bold border px-2 py-0.5 rounded-full w-auto gap-1 ${m.cls}`}>
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {Object.entries(OUTLET_TYPE_META).map(([val, meta]) => (
                                    <SelectItem key={val} value={val} className="text-xs">
                                      {meta.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            )
                          })()}
                        </TableCell>
                        <TableCell>
                          <code className="text-[10px] bg-muted px-1 rounded">{merchant.outlet_id}</code>
                        </TableCell>
                        <TableCell>
                          {(() => {
                            // Success Share %. Legacy (grandfathered 1.5%) reads
                            // amber; everything else emerald. Signature status is
                            // shown by the ⭐ next to the name and edited in the
                            // merchant details page (same control as Add Merchant).
                            const rate = Number(merchant.platform_fee_percent ?? 0)
                            const isLegacy = Math.abs(rate - 1.5) < 0.001
                            return (
                              <Badge
                                variant="outline"
                                className={isLegacy
                                  ? 'bg-amber-50 text-amber-700 border-amber-200 font-mono'
                                  : 'bg-emerald-50 text-emerald-700 border-emerald-200 font-mono'}
                                title={isLegacy ? 'Grandfathered legacy rate' : 'Current rate'}
                              >
                                {rate}%
                              </Badge>
                            )
                          })()}
                        </TableCell>
                        <TableCell>
                          {(() => {
                            const k = merchant.razorpay_kyc_status || ''
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
                        {/* Active/inactive — ON (green) = live in the consumer
                            app; OFF = hidden from the app (outlet not ready).
                            Compact so it doesn't eat row space. */}
                        <TableCell className="text-center">
                          <Switch
                            checked={!!merchant.is_active}
                            disabled={updating === merchant.name}
                            onCheckedChange={() => handleStatusToggle(merchant.name, merchant.is_active)}
                            title={merchant.is_active ? 'Live in app — tap to take offline' : 'Hidden from app — tap to bring online'}
                            aria-label="Toggle merchant visibility in the app"
                            className="data-[state=checked]:bg-emerald-500"
                          />
                        </TableCell>
                        <TableCell className="text-center">
                          <Switch
                            checked={!!merchant.is_signature}
                            disabled={updating === merchant.name}
                            onCheckedChange={(checked) => handleSignatureToggle(merchant, checked)}
                            thumbIcon={
                              <Star
                                className={cn(
                                  "h-3 w-3",
                                  merchant.is_signature
                                    ? "fill-amber-500 text-amber-500"
                                    : "fill-muted-foreground text-muted-foreground"
                                )}
                              />
                            }
                          />
                        </TableCell>
                        <TableCell className="text-center">
                          {(() => {
                            let isLive = !!merchant.is_featured
                            if (isLive) {
                              const today = new Date().toISOString().split('T')[0]
                              if (merchant.limelight_end_date && merchant.limelight_end_date < today) isLive = false
                            }
                            return (
                              <Switch
                                checked={isLive}
                                disabled={updating === merchant.name}
                                onCheckedChange={(checked) => handleLimelightToggle(merchant, checked)}
                                thumbIcon={
                                  <Sparkles
                                    className={cn(
                                      "h-3 w-3",
                                      isLive
                                        ? "fill-indigo-500 text-indigo-500"
                                        : "fill-muted-foreground text-muted-foreground"
                                    )}
                                  />
                                }
                              />
                            )
                          })()}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button
                              variant="ghost" size="icon" className="h-8 w-8 text-amber-600"
                              onClick={() => {
                                setSelectedMerchant(merchant)
                                setCoinAmount('')
                                setIsCoinModalOpen(true)
                              }}
                            >
                              <Coins className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost" size="icon" className="h-8 w-8"
                              onClick={() => navigate(`/admin/merchants/${merchant.outlet_id}`)}
                            >
                              <Settings className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost" size="icon"
                              onClick={() => handleStatusToggle(merchant.name, merchant.is_active)}
                              disabled={updating === merchant.name}
                              className={cn("h-8 w-8", merchant.is_active ? "text-red-500" : "text-green-500")}
                            >
                              {merchant.is_active ? <PowerOff className="h-4 w-4" /> : <Power className="h-4 w-4" />}
                            </Button>
                            {!isSupervisorOnly && (
                              <Button
                                variant="ghost" size="icon"
                                className="h-8 w-8 text-red-600 hover:text-red-700 hover:bg-red-50"
                                onClick={() => {
                                  setMerchantToDelete({ id: merchant.outlet_id, name: merchant.outlet_name })
                                  setVerificationInput('')
                                  setIsDeleteDialogOpen(true)
                                }}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            )}
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
                {coinAction === 'grant' ? 'Manually add' : 'Manually remove'} digital coins {coinAction === 'grant' ? 'to' : 'from'} <span className="font-bold text-foreground">"{selectedMerchant?.outlet_name}"</span>.
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



      {/* Delete Confirmation Modal */}
      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent className="sm:max-w-[440px] p-0 overflow-hidden border-none shadow-2xl rounded-2xl">
          <div className="p-6 pt-8 text-center">
            <div className="mx-auto w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mb-4">
              <Trash2 className="h-6 w-6 text-red-600" />
            </div>
            <DialogHeader className="text-center">
              <DialogTitle className="text-xl font-bold text-center w-full">Delete Merchant</DialogTitle>
              <DialogDescription className="text-sm text-center pt-2">
                This action is irreversible. All configurations, balances, and data for <span className="font-bold text-foreground">"{merchantToDelete?.name}"</span> will be permanently removed.
              </DialogDescription>
            </DialogHeader>
          </div>
          <div className="px-8 pb-8 space-y-4">
            <div className="space-y-3">
              <Label className="text-xs font-semibold text-muted-foreground">
                To confirm, please type <span className="font-mono text-red-600 font-bold px-1 bg-red-50 rounded">{merchantToDelete?.id}</span> below.
              </Label>
              <Input
                value={verificationInput}
                onChange={(e) => setVerificationInput(e.target.value)}
                placeholder="Type merchant ID here"
                className="h-11 rounded-xl border-muted focus-visible:ring-red-500 font-medium"
                disabled={updating === merchantToDelete?.id}
              />
            </div>
          </div>
          <DialogFooter className="p-4 bg-muted/30 border-t flex flex-row gap-2 sm:justify-end">
            <Button
              variant="ghost"
              onClick={() => setIsDeleteDialogOpen(false)}
              disabled={updating === merchantToDelete?.id}
              className="rounded-xl flex-1 sm:flex-none"
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={verificationInput !== merchantToDelete?.id || updating === merchantToDelete?.id}
              onClick={handleConfirmDelete}
              className="rounded-xl px-6 flex-1 sm:flex-none bg-red-600 hover:bg-red-700 text-white shadow-sm"
            >
              {updating === merchantToDelete?.id ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Delete Merchant'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Onboarding Inbox Modal */}
      <BranchAccessDialog
        open={isBranchAccessOpen}
        onOpenChange={setIsBranchAccessOpen}
        onAssigned={() => loadMerchants()}
      />

      <UpdateSuccessShareModal
        open={!!shareUpdateTarget}
        onOpenChange={(open) => { if (!open) setShareUpdateTarget(null) }}
        merchantName={shareUpdateTarget?.outlet_name ?? ''}
        currentRate={Number(shareUpdateTarget?.platform_fee_percent ?? 0)}
        onConfirm={handleUpdateShareRate}
        isSaving={isSavingShareRate}
      />

      <UpdateLimelightModal
        open={!!limelightUpdateTarget}
        onOpenChange={(open) => { if (!open) setLimelightUpdateTarget(null) }}
        merchantName={limelightUpdateTarget?.outlet_name ?? ''}
        onConfirm={handleUpdateLimelight}
      />

      <Dialog open={isOnboardingModalOpen} onOpenChange={setIsOnboardingModalOpen}>
        <DialogContent className="sm:max-w-5xl w-[95vw] p-0 overflow-hidden border-none shadow-2xl rounded-2xl">
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
                      Review and finalize new outlet setups
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
                    Select Outlet
                  </Label>
                  <MerchantSelector
                    value={selectedOnboardingResId}
                    onSelect={setSelectedOnboardingResId}
                    options={(merchants || []).map((r: any) => ({
                      value: r.name,
                      label: r.outlet_name
                    }))}
                    placeholder="Search existing merchants..."
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
              <div className="flex items-center justify-between">
                <button
                  onClick={() => setShowCompleted(v => !v)}
                  className={cn(
                    'flex items-center gap-2 text-[11px] font-bold px-3 py-1.5 rounded-lg border transition-all',
                    showCompleted
                      ? 'bg-green-50 border-green-200 text-green-700 dark:bg-green-900/20 dark:border-green-800 dark:text-green-400'
                      : 'bg-muted/40 border-muted text-muted-foreground hover:text-foreground'
                  )}
                >
                  <div className={cn('h-1.5 w-1.5 rounded-full', showCompleted ? 'bg-green-500' : 'bg-muted-foreground')} />
                  {showCompleted ? 'Hiding completed' : `Show completed`}
                  {completedCount > 0 && (
                    <span className={cn('ml-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-black', showCompleted ? 'bg-green-100 text-green-700 dark:bg-green-900/40' : 'bg-muted text-muted-foreground')}>
                      {completedCount}
                    </span>
                  )}
                </button>
                <span className="text-[11px] text-muted-foreground">
                  {visibleOnboarding.length} {showCompleted ? 'total' : 'active'}
                </span>
              </div>
            </div>
          </div>

          <div className="p-0 max-h-[50vh] overflow-y-auto overflow-x-hidden">
            {!visibleOnboarding.length ? (
              <div className="py-20 text-center">
                <div className="mx-auto w-12 h-12 bg-muted/20 rounded-full flex items-center justify-center mb-4">
                  <Mail className="h-6 w-6 text-muted-foreground" />
                </div>
                <p className="text-muted-foreground font-medium">
                  {allOnboarding.length ? 'No active requests — toggle "Show completed" to see all.' : 'No onboarding requests found'}
                </p>
              </div>
            ) : (
              <table className="w-full table-fixed">
                <colgroup>
                  <col className="w-10" />
                  <col className="w-[28%]" />
                  <col className="w-[32%]" />
                  <col className="w-[14%]" />
                  <col className="w-[26%]" />
                </colgroup>
                <thead>
                  <tr className="bg-muted/5 border-b">
                    <th className="pl-4 py-3 w-10">
                      <Checkbox
                        checked={selectedOnboarding.length > 0 && selectedOnboarding.length === visibleOnboarding.length}
                        onCheckedChange={toggleSelectAll}
                        className="rounded-md border-muted-foreground/30 data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                      />
                    </th>
                    <th className="py-3 text-left text-xs font-bold uppercase tracking-wider text-muted-foreground">Outlet Name</th>
                    <th className="py-3 text-left text-xs font-bold uppercase tracking-wider text-muted-foreground">Owner / Status</th>
                    <th className="py-3 text-left text-xs font-bold uppercase tracking-wider text-muted-foreground">Created</th>
                    <th className="py-3 pr-4 text-right text-xs font-bold uppercase tracking-wider text-muted-foreground">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleOnboarding.map((req: any) => (
                    <tr key={req.name} className={cn(
                      "border-b hover:bg-muted/5 transition-colors",
                      selectedOnboarding.includes(req.name) && "bg-primary/5 hover:bg-primary/5",
                      req.status === 'Completed' && "opacity-50"
                    )}>
                      <td className="pl-4 py-3">
                        <Checkbox
                          checked={selectedOnboarding.includes(req.name)}
                          onCheckedChange={() => toggleSelectRow(req.name)}
                          className="rounded-md border-muted-foreground/30 data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                        />
                      </td>
                      <td className="py-3 pr-2 font-bold text-sm truncate max-w-0">
                        <span className="block truncate" title={req.outlet_name}>{req.outlet_name}</span>
                      </td>
                      <td className="py-3 pr-2 min-w-0">
                        <div className="flex flex-col min-w-0">
                          <span className="text-xs font-medium truncate" title={req.owner_email || 'No email provided'}>{req.owner_email || 'No email provided'}</span>
                          <div className="flex items-center mt-0.5">
                            <div className={cn(
                              "h-1.5 w-1.5 rounded-full mr-1.5 shrink-0",
                              req.status === 'Client Submitted' ? "bg-green-500" : req.status === 'Completed' ? "bg-blue-400" : "bg-amber-400"
                            )} />
                            <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground truncate">
                              {req.status}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 pr-2 text-xs text-muted-foreground whitespace-nowrap">
                        {formatDate(req.creation)}
                      </td>
                      <td className="py-3 pr-4">
                        <div className="flex justify-end items-center gap-1">
                          {req.status === 'Client Submitted' && (
                            <Button
                              variant="ghost"
                              size="icon"
                              title="Review"
                              className="h-8 w-8 hover:bg-violet-50 hover:text-violet-600 dark:hover:bg-violet-500/10 dark:hover:text-violet-400 rounded-lg"
                              onClick={() => handleReviewOnboarding(req.name)}
                            >
                              <Eye className="h-3.5 w-3.5" />
                            </Button>
                          )}
                          {req.status === 'Client Submitted' && req.linked_restaurant && (
                            <Button
                              variant="ghost"
                              size="icon"
                              title="Sync to merchant"
                              className="h-8 w-8 hover:bg-green-50 hover:text-green-600 dark:hover:bg-green-500/10 dark:hover:text-green-400 rounded-lg"
                              onClick={() => handleSyncOnboarding(req.name)}
                              disabled={syncingName === req.name}
                            >
                              {syncingName === req.name
                                ? <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                                : <RefreshCcw className="h-3.5 w-3.5" />}
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Open onboarding link"
                            className="h-8 w-8 hover:bg-primary/10 hover:text-primary rounded-lg"
                            onClick={() => window.open(req.onboarding_link, '_blank')}
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Copy link"
                            className="h-8 w-8 hover:bg-muted rounded-lg"
                            onClick={() => handleCopyOnboardingLink(req.onboarding_link)}
                          >
                            <ClipboardCopy className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Delete"
                            className="h-8 w-8 text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg"
                            onClick={() => handleDeleteOnboarding(req.name)}
                            disabled={updating === req.name}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
              Copy and share this link with the outlet owner.
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

      {/* Onboarding Review Dialog */}
      <Dialog open={isReviewModalOpen} onOpenChange={(open) => { setIsReviewModalOpen(open); if (!open) setReviewDetail(null) }}>
        <DialogContent className="sm:max-w-2xl p-0 overflow-hidden border-none shadow-2xl rounded-2xl">
          <div className="p-6 bg-gradient-to-br from-violet-50 via-background to-background dark:from-violet-950/20 border-b">
            <DialogHeader>
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-violet-100 dark:bg-violet-900/40 rounded-xl">
                  <Eye className="h-5 w-5 text-violet-600 dark:text-violet-400" />
                </div>
                <div>
                  <DialogTitle className="text-lg font-black">
                    {reviewDetail ? reviewDetail.outlet_name : 'Loading…'}
                  </DialogTitle>
                  <DialogDescription className="text-xs font-medium">
                    Submitted data review — verify before syncing
                  </DialogDescription>
                </div>
              </div>
              {reviewDetail && (() => {
                const warnings = validateOnboardingData(reviewDetail)
                const errors = warnings.filter(w => w.severity === 'error').length
                const warns = warnings.filter(w => w.severity === 'warning').length
                const infos = warnings.filter(w => w.severity === 'info').length
                return (
                  <div className="flex gap-2 mt-3 flex-wrap">
                    {errors > 0 && <Badge className="bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 gap-1"><XCircle className="h-3 w-3" />{errors} error{errors > 1 ? 's' : ''}</Badge>}
                    {warns > 0 && <Badge className="bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 gap-1"><AlertTriangle className="h-3 w-3" />{warns} warning{warns > 1 ? 's' : ''}</Badge>}
                    {infos > 0 && <Badge className="bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 gap-1"><Info className="h-3 w-3" />{infos} missing</Badge>}
                    {errors === 0 && warns === 0 && <Badge className="bg-green-100 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-400 gap-1"><CheckCircle2 className="h-3 w-3" />All checks passed</Badge>}
                  </div>
                )
              })()}
            </DialogHeader>
          </div>

          <div className="max-h-[55vh] overflow-y-auto p-6 space-y-5">
            {reviewLoading && (
              <div className="flex items-center justify-center py-16">
                <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            )}
            {reviewDetail && (() => {
              const warnings = validateOnboardingData(reviewDetail)
              const warnMap = Object.fromEntries(warnings.map(w => [w.field, w]))

              const renderField = (label: string, value: string | number | null | undefined, warnKey?: string) => {
                const warn = warnKey ? warnMap[warnKey] : undefined
                const hasValue = value !== null && value !== undefined && value !== ''
                return (
                  <div className="flex items-start gap-3 py-1.5">
                    <div className="mt-0.5 flex-shrink-0">
                      {warn ? (
                        warn.severity === 'error' ? <XCircle className="h-4 w-4 text-red-500" /> :
                        warn.severity === 'warning' ? <AlertTriangle className="h-4 w-4 text-amber-500" /> :
                        <Info className="h-4 w-4 text-blue-400" />
                      ) : hasValue ? (
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                      ) : (
                        <div className="h-4 w-4 rounded-full border border-muted-foreground/20" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{label}</span>
                        {warn && <span className={cn("text-[10px] font-bold rounded-full px-2 py-0.5",
                          warn.severity === 'error' ? "bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400" :
                          warn.severity === 'warning' ? "bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400" :
                          "bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400"
                        )}>{warn.message}</span>}
                      </div>
                      <p className={cn("text-sm mt-0.5 truncate", !hasValue && "text-muted-foreground/50 italic")}>{hasValue ? String(value) : '—'}</p>
                    </div>
                  </div>
                )
              }

              const sections: { title: string; fields: [string, string | number | null | undefined, string?][] }[] = [
                { title: 'Contact', fields: [
                  ['Owner Name', reviewDetail.owner_name, 'Owner Name'],
                  ['Owner Email', reviewDetail.owner_email, 'Owner Email'],
                  ['Owner Phone', reviewDetail.owner_phone, 'Owner Phone'],
                  ['WhatsApp', reviewDetail.whatsapp_number, 'WhatsApp Number'],
                ]},
                { title: 'Legal & Banking', fields: [
                  ['Legal Name', reviewDetail.legal_name, 'Legal Name'],
                  ['Business Type', reviewDetail.business_type],
                  ['FSSAI', reviewDetail.fssai_number, 'FSSAI Number'],
                  ['GST Number', reviewDetail.gst_number, 'GST Number'],
                  ['PAN Number', reviewDetail.pan_number, 'PAN Number'],
                  ['Tax Rate', reviewDetail.tax_rate !== undefined ? `${reviewDetail.tax_rate}%` : null, 'Tax Rate'],
                  ['Bank Account', reviewDetail.bank_account_number, 'Bank Account'],
                  ['IFSC Code', reviewDetail.bank_ifsc, 'IFSC Code'],
                  ['Account Holder', reviewDetail.bank_holder_name],
                ]},
                { title: 'Location', fields: [
                  ['Address', reviewDetail.address, 'Address'],
                  ['City', reviewDetail.city, 'City'],
                  ['State', reviewDetail.state, 'State'],
                  ['PIN Code', reviewDetail.zip_code, 'PIN Code'],
                  ['Google Maps', reviewDetail.google_map_url, 'Google Maps Link'],
                ]},
                { title: 'Branding & Social', fields: [
                  ['Logo', reviewDetail.logo ? '✓ Uploaded' : null, 'Logo'],
                  ['Tagline', reviewDetail.tagline, 'Tagline'],
                  ['Description', reviewDetail.description, 'Description'],
                  ['Instagram', reviewDetail.instagram_link],
                  ['Facebook', reviewDetail.facebook_link],
                  ['Website', reviewDetail.website_link],
                  ['Google Review', reviewDetail.google_review_link],
                ]},
                { title: 'Operations', fields: [
                  ['Opening Time', reviewDetail.opening_time, 'Opening Time'],
                  ['Closing Time', reviewDetail.closing_time, 'Closing Time'],
                  ['Tables', reviewDetail.tables],
                  ['Catalogue Layout', reviewDetail.menu_layout],
                  ['Default Theme', reviewDetail.default_theme],
                  ['Catalogue Photos', reviewDetail.menu_photos?.length ? `${reviewDetail.menu_photos.length} uploaded` : null],
                ]},
              ]

              return sections.map(section => (
                <div key={section.title}>
                  <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 mb-2 pb-1 border-b">{section.title}</p>
                  <div className="divide-y divide-border/40">
                    {section.fields.map(([label, value, warnKey]) => renderField(label, value as any, warnKey))}
                  </div>
                </div>
              ))
            })()}
          </div>

          <div className="p-4 bg-muted/30 border-t flex justify-between items-center gap-3">
            <Button variant="ghost" className="rounded-xl px-5 font-semibold text-sm" onClick={() => { setIsReviewModalOpen(false); setReviewDetail(null) }}>
              Close
            </Button>
            {reviewDetail && reviewDetail.linked_restaurant && (
              <Button
                className="rounded-xl px-6 font-bold bg-green-600 hover:bg-green-700 text-white shadow-lg shadow-green-500/20"
                onClick={() => handleSyncOnboarding(reviewDetail.name)}
                disabled={syncingName === reviewDetail.name}
              >
                {syncingName === reviewDetail.name
                  ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Syncing…</>
                  : <><RefreshCcw className="h-4 w-4 mr-2" />Sync to Outlet</>}
              </Button>
            )}
            {reviewDetail && !reviewDetail.linked_restaurant && (
              <p className="text-xs text-amber-600 dark:text-amber-400 font-medium">No linked outlet — cannot sync</p>
            )}
          </div>
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
