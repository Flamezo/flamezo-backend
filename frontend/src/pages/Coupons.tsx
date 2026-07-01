import { useState, useMemo, useEffect } from 'react'
import { useFrappeGetDocList, useFrappePostCall, useFrappeUpdateDoc, useFrappeDeleteDoc } from '@/lib/frappe'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Plus, Edit, Trash2, Tag, Percent, Gift, Calendar, Users,
  TrendingUp, AlertCircle, Zap, X, Sparkles, ArrowLeft,
  Clock, Star, ShoppingBag, Flame, RotateCcw, Download,
  BarChart3, CheckCircle2,
  XCircle, ChevronDown, ChevronUp, Phone, CreditCard, RefreshCw,
  ImagePlus, Loader2
} from 'lucide-react'
import { EmptyState } from '@/components/EmptyState'
import { LockedFeature } from '@/components/FeatureGate/LockedFeature'
import { AISuggestionsModal, type AISuggestion } from '@/components/coupons/AISuggestionsModal'
import { DatePicker } from '@/components/ui/date-picker'
import { TimePicker } from '@/components/ui/time-picker'
import { Checkbox } from '@/components/ui/checkbox'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useCurrency } from '@/hooks/useCurrency'
import { toast } from 'sonner'
import { getFrappeError } from '@/lib/utils'
import { useDataTable } from '@/hooks/useDataTable'
import { DataPagination } from '@/components/ui/DataPagination'

// ─── Constants ────────────────────────────────────────────────────────────────

const DAYS_OF_WEEK = [
  { label: 'Mon', value: 'monday' },
  { label: 'Tue', value: 'tuesday' },
  { label: 'Wed', value: 'wednesday' },
  { label: 'Thu', value: 'thursday' },
  { label: 'Fri', value: 'friday' },
  { label: 'Sat', value: 'saturday' },
  { label: 'Sun', value: 'sunday' },
]

// ─── Template definitions ─────────────────────────────────────────────────────
// Each template pre-fills the form so restaurant owners can start from a proven
// offer structure instead of a blank slate.

const BLANK_FORM = {
  code: '',
  description: '',
  discount_type: 'percent' as string,
  category: 'best',
  discount_value: 0,
  min_order_amount: 0,
  max_discount_cap: 0,
  is_active: true,
  offer_type: 'coupon' as string,
  priority: 1,
  max_uses: 0,
  max_uses_per_user: 0,
  valid_from: '',
  valid_until: '',
  combo_price: 0,
  bogo_free_item_value: 0,
  required_items: '',
  valid_days_of_week: '',
  valid_time_start: '',
  valid_time_end: '',
  can_stack: false,
  free_item: '',
  // New combo fields
  combo_type: 'fixed_bundle' as string,
  combo_name: '',
  item_pool: '',
  items_to_select: 2,
  display_on_menu: true,
  combo_image: '',
}

interface CouponTemplate {
  id: string
  label: string
  tagline: string
  icon: React.ReactNode
  accent: string        // tailwind bg class for the card accent
  badge?: string        // optional label like "Popular"
  defaults: Partial<typeof BLANK_FORM>
}

const TEMPLATES: CouponTemplate[] = [
  {
    id: 'blank',
    label: 'Custom / Blank',
    tagline: 'Start from scratch with full control',
    icon: <Sparkles className="h-6 w-6" />,
    accent: 'bg-slate-500',
    defaults: {},
  },
  {
    id: 'welcome',
    label: 'Welcome Offer',
    tagline: '20% off first order — great for new customer acquisition',
    icon: <Star className="h-6 w-6" />,
    accent: 'bg-orange-500',
    badge: 'Popular',
    defaults: {
      offer_type: 'coupon',
      discount_type: 'percent',
      discount_value: 20,
      max_discount_cap: 100,
      min_order_amount: 199,
      max_uses_per_user: 1,
      code: 'WELCOME20',
      description: 'Get 20% off on your first order',
      category: 'best',
    },
  },
  {
    id: 'flat_deal',
    label: 'Flat ₹ Deal',
    tagline: 'Fixed rupee off above a min order',
    icon: <Tag className="h-6 w-6" />,
    accent: 'bg-green-500',
    badge: 'Simple',
    defaults: {
      offer_type: 'coupon',
      discount_type: 'flat',
      discount_value: 50,
      min_order_amount: 299,
      code: 'FLAT50',
      description: 'Flat ₹50 off on bills above ₹299',
      category: 'best',
    },
  },
  {
    id: 'big_percent',
    label: 'Big % Off',
    tagline: 'High % with a rupee cap — drives big bills',
    icon: <Percent className="h-6 w-6" />,
    accent: 'bg-purple-500',
    defaults: {
      offer_type: 'coupon',
      discount_type: 'percent',
      discount_value: 40,
      max_discount_cap: 80,
      min_order_amount: 399,
      code: 'BIG40',
      description: 'Get 40% off up to ₹80 on your order',
      category: 'best',
    },
  },
  {
    id: 'lunch_special',
    label: 'Lunch Special',
    tagline: 'Auto-apply discount during lunch hours',
    icon: <Clock className="h-6 w-6" />,
    accent: 'bg-yellow-500',
    defaults: {
      offer_type: 'auto',
      discount_type: 'percent',
      discount_value: 15,
      max_discount_cap: 60,
      min_order_amount: 0,
      valid_time_start: '11:00:00',
      valid_time_end: '15:00:00',
      code: 'LUNCH15',
      description: '15% off all bills between 11 AM – 3 PM',
      category: 'best',
    },
  },
  {
    id: 'weekend_special',
    label: 'Weekend Blast',
    tagline: 'Bigger discount on Sat & Sun only',
    icon: <Flame className="h-6 w-6" />,
    accent: 'bg-rose-500',
    defaults: {
      offer_type: 'auto',
      discount_type: 'percent',
      discount_value: 25,
      max_discount_cap: 100,
      min_order_amount: 249,
      valid_days_of_week: JSON.stringify(['saturday', 'sunday']),
      code: 'WEEKEND25',
      description: '25% off every weekend on bills above ₹249',
      category: 'best',
    },
  },
  {
    id: 'loyalty',
    label: 'Loyalty / Repeat',
    tagline: 'Reward repeat customers with a recurring code',
    icon: <RotateCcw className="h-6 w-6" />,
    accent: 'bg-teal-500',
    defaults: {
      offer_type: 'coupon',
      discount_type: 'flat',
      discount_value: 75,
      min_order_amount: 399,
      can_stack: false,
      code: 'LOYAL75',
      description: 'Exclusive ₹75 off for our regular customers',
      category: 'best',
    },
  },
  {
    id: 'bulk_order',
    label: 'Bulk / Group Order',
    tagline: 'High min-order to incentivise large group bills',
    icon: <ShoppingBag className="h-6 w-6" />,
    accent: 'bg-indigo-500',
    defaults: {
      offer_type: 'coupon',
      discount_type: 'percent',
      discount_value: 12,
      max_discount_cap: 150,
      min_order_amount: 999,
      code: 'GROUP12',
      description: '12% off on group bills above ₹999',
      category: 'best',
    },
  },
  {
    id: 'combo',
    label: 'Combo Deal',
    tagline: 'Bundle specific dishes at a fixed price',
    icon: <Gift className="h-6 w-6" />,
    accent: 'bg-pink-500',
    defaults: {
      offer_type: 'combo',
      discount_type: 'flat',
      discount_value: 0,
      combo_price: 299,
      code: 'COMBO299',
      description: 'Get the combo for just ₹299',
      category: 'best',
    },
  },
]

// ─── Main page ────────────────────────────────────────────────────────────────

export default function Coupons() {
  const { selectedRestaurant, isGold, restaurant } = useRestaurant()
  const { formatAmountNoDecimals } = useCurrency()
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [editingCoupon, setEditingCoupon] = useState<any>(null)
  const [filterType, setFilterType] = useState<string>('all')
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [couponToDelete, setCouponToDelete] = useState<{ name: string; code: string } | null>(null)
  const [selectedTemplate, setSelectedTemplate] = useState<CouponTemplate | null>(null)
  const [isAIModalOpen, setIsAIModalOpen] = useState(false)
  const [aiPrefilledForm, setAiPrefilledForm] = useState<Partial<typeof BLANK_FORM> | null>(null)

  const initialFilters = useMemo(() => {
    if (!selectedRestaurant) return []
    const f: any[] = [{ fieldname: 'restaurant', operator: '=', value: selectedRestaurant }]
    if (filterType === 'active') {
      f.push({ fieldname: 'is_active', operator: '=', value: 1 })
    } else if (filterType === 'inactive') {
      f.push({ fieldname: 'is_active', operator: '=', value: 0 })
    } else if (filterType !== 'all') {
      f.push({ fieldname: 'offer_type', operator: '=', value: filterType })
    }
    return f
  }, [selectedRestaurant, filterType])

  const {
    data: coupons,
    isLoading,
    mutate,
    page, setPage,
    pageSize, setPageSize,
    totalCount,
    searchQuery, setSearchQuery,
  } = useDataTable({
    doctype: 'Coupon',
    fields: [
      'name', 'code', 'description', 'discount_type', 'discount_value',
      'min_order_amount', 'is_active', 'valid_from', 'valid_until',
      'max_uses', 'max_uses_per_user', 'usage_count', 'offer_type',
      'max_discount_cap', 'priority', 'restaurant', 'valid_days_of_week',
      'valid_time_start', 'valid_time_end', 'can_stack', 'free_item',
      'required_items', 'combo_price', 'category',
    ],
    initialFilters,
    orderBy: { field: 'creation', order: 'desc' },
    initialPageSize: 12,
    searchFields: ['name', 'code', 'description'],
    debugId: `coupons-${selectedRestaurant}`,
  })

  const { call: createCoupon } = useFrappePostCall('frappe.client.insert')
  const { updateDoc: updateCoupon } = useFrappeUpdateDoc()
  const { deleteDoc: deleteCoupon } = useFrappeDeleteDoc()
  const { call: checkFoodCostCoverage } = useFrappePostCall(
    'flamezo_backend.flamezo.api.costing.check_food_cost_coverage'
  )
  const [aiGateLoading, setAiGateLoading] = useState(false)

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleCreateCoupon = async (formData: any) => {
    await createCoupon({ doc: { doctype: 'Coupon', ...formData, restaurant: selectedRestaurant } })
    // Await mutate so the list is refreshed before the dialog closes
    await mutate()
    setIsCreateDialogOpen(false)
    setSelectedTemplate(null)
    toast.success('Coupon created successfully')
  }

  const handleUpdateCoupon = async (name: string, formData: any) => {
    await updateCoupon('Coupon', name, formData)
    await mutate()
    setEditingCoupon(null)
    toast.success('Coupon updated successfully')
  }

  const handleDeleteCoupon = async () => {
    if (!couponToDelete) return
    try {
      await deleteCoupon('Coupon', couponToDelete.name)
      await mutate()
      setDeleteDialogOpen(false)
      setCouponToDelete(null)
      toast.success('Coupon deleted successfully')
    } catch (error: any) {
      toast.error('Failed to delete coupon', { description: getFrappeError(error) })
    }
  }

  const openDeleteDialog = (name: string, code: string) => {
    setCouponToDelete({ name, code })
    setDeleteDialogOpen(true)
  }

  const handleToggleActive = async (name: string, currentValue: boolean) => {
    try {
      await updateCoupon('Coupon', name, { is_active: !currentValue ? 1 : 0 })
      await mutate()
    } catch (error: any) {
      toast.error('Failed to update coupon', { description: getFrappeError(error) })
    }
  }

  const handleSave = async (data: any) => {
    try {
      if (editingCoupon) {
        await handleUpdateCoupon(editingCoupon.name, data)
      } else {
        await handleCreateCoupon(data)
      }
    } catch (error: any) {
      toast.error(editingCoupon ? 'Failed to update coupon' : 'Failed to create coupon', {
        description: getFrappeError(error),
      })
    }
  }

  const aiSuggestionToFormData = (suggestion: AISuggestion) => ({
    code: suggestion.code,
    description: suggestion.description,
    offer_type: suggestion.offer_type,
    discount_type: suggestion.discount_type,
    discount_value: suggestion.discount_value,
    min_order_amount: suggestion.offer_type === 'combo' ? 0 : suggestion.min_order_amount,
    combo_price: suggestion.offer_type === 'combo' ? ((suggestion as any).combo_price ?? 0) : 0,
    max_discount_cap: suggestion.max_discount_cap ?? 0,
    category: suggestion.category,
    valid_days_of_week: suggestion.valid_days_of_week ? JSON.stringify(suggestion.valid_days_of_week) : '',
    valid_time_start: suggestion.valid_time_start ?? '',
    valid_time_end: suggestion.valid_time_end ?? '',
    max_uses: suggestion.max_uses,
    max_uses_per_user: suggestion.max_uses_per_user,
    can_stack: suggestion.can_stack,
    priority: suggestion.priority,
    is_active: true,
    // New combo-type fields from AI
    combo_type: (suggestion as any).combo_type ?? 'fixed_bundle',
    combo_name: (suggestion as any).combo_name ?? '',
    items_to_select: (suggestion as any).items_to_select ?? 2,
    display_on_menu: suggestion.offer_type === 'combo' ? ((suggestion as any).display_on_menu ?? true) : false,
  })

  const handleSaveAllAISuggestions = async (suggestions: AISuggestion[]) => {
    let saved = 0
    let failed = 0
    for (const suggestion of suggestions) {
      try {
        await createCoupon({
          doc: {
            doctype: 'Coupon',
            ...aiSuggestionToFormData(suggestion),
            restaurant: selectedRestaurant,
          },
        })
        saved++
      } catch {
        failed++
      }
    }
    await mutate()
    if (failed === 0) {
      toast.success(`${saved} coupon${saved > 1 ? 's' : ''} saved successfully`)
    } else {
      toast.warning(`${saved} saved, ${failed} failed (possibly duplicate codes)`)
    }
  }

  const handleUseAISuggestion = (suggestion: AISuggestion) => {
    const prefilled = {
      ...aiSuggestionToFormData(suggestion),
      ...(suggestion.combo_items_hint ? { _combo_items_hint: suggestion.combo_items_hint } : {}),
    }
    setAiPrefilledForm(prefilled)
    setEditingCoupon(null)
    setIsCreateDialogOpen(true)
  }

  const handleOpenAIModal = async () => {
    setAiGateLoading(true)
    try {
      const res = await checkFoodCostCoverage({ restaurant_id: selectedRestaurant })
      const payload = res?.message ?? res
      const data = payload?.data
      if (!payload?.success) {
        toast.error('Could not verify food cost data', { description: payload?.error?.message })
        return
      }
      if (!data?.all_covered) {
        const missing = data?.items_without_cost ?? 0
        const total = data?.total_items ?? 0
        toast.error('Food cost required for AI generation', {
          description: `${missing} of ${total} menu items are missing food cost. Go to Food Cost in the sidebar and set costs for all items — the AI needs this data to generate profit-safe offers.`,
          duration: 7000,
        })
        return
      }
    } catch (err: any) {
      toast.error('Could not verify food cost data', { description: err?.message })
      return
    } finally {
      setAiGateLoading(false)
    }
    setIsAIModalOpen(true)
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  const getOfferTypeIcon = (type: string) => {
    switch (type) {
      case 'combo':    return <Gift className="h-4 w-4" />
      case 'auto':     return <TrendingUp className="h-4 w-4" />
      default:         return <Tag className="h-4 w-4" />
    }
  }

  // ── Guards ────────────────────────────────────────────────────────────────

  if (!selectedRestaurant) {
    return (
      <div className="p-6">
        <EmptyState icon={AlertCircle} title="Select a Restaurant"
          description="Please select a restaurant from the sidebar to manage offers and coupons." />
      </div>
    )
  }

  if (!isGold) return <LockedFeature feature="coupons" requiredPlan={['GOLD']} />

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Manage Offers & Coupons</h1>
          <p className="text-muted-foreground mt-1">Create and manage discount coupons, auto-offers, and combo deals</p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            className="gap-2 border-primary/20 text-primary hover:bg-primary/5"
            onClick={() => {
              window.open('/api/method/flamezo_backend.flamezo.api.payments.download_guide?guide_name=Flamezo_Offers_Guide', '_blank')
            }}
          >
            <Download className="h-4 w-4" />
            Download Guide
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="gap-2 border-purple-400/40 text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-950/30"
            onClick={handleOpenAIModal}
            disabled={aiGateLoading}
          >
            {aiGateLoading
              ? <RefreshCw className="h-4 w-4 animate-spin" />
              : <Sparkles className="h-4 w-4" />
            }
            Generate with AI
          </Button>
          <Button onClick={() => { setAiPrefilledForm(null); setIsCreateDialogOpen(true) }}>
            <Plus className="h-4 w-4 mr-2" />
            Create Coupon
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Coupons', value: totalCount || 0, icon: <Tag className="h-5 w-5 text-muted-foreground" />, color: '' },
          { label: 'Active', value: coupons?.filter((c: any) => c.is_active).length || 0, icon: <TrendingUp className="h-5 w-5 text-green-600" />, color: 'text-green-600' },
          { label: 'Total Usage', value: coupons?.reduce((s: number, c: any) => s + (c.usage_count || 0), 0) || 0, icon: <Users className="h-5 w-5 text-muted-foreground" />, color: '' },
          { label: 'Combo Offers', value: coupons?.filter((c: any) => c.offer_type === 'combo').length || 0, icon: <Gift className="h-5 w-5 text-purple-600" />, color: 'text-purple-600' },
        ].map(({ label, value, icon, color }) => (
          <Card key={label}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground font-medium truncate">{label}</p>
                  <p className={`text-2xl font-bold mt-0.5 ${color}`}>{value}</p>
                </div>
                <div className="shrink-0 p-2 rounded-lg bg-muted/50">{icon}</div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Analytics */}
      <ClaimsAnalyticsCard restaurantId={selectedRestaurant} />

      {/* List */}
      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            <div>
              <CardTitle>All Coupons</CardTitle>
              <CardDescription>
                Manage your discount coupons and offers
                {totalCount > 0 && <span className="ml-2">(Showing {coupons?.length || 0} of {totalCount})</span>}
              </CardDescription>
            </div>
            <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
              <Input
                placeholder="Search coupons..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full sm:w-[200px]"
              />
              <Select value={filterType} onValueChange={setFilterType}>
                <SelectTrigger className="w-full sm:w-[200px]">
                  <SelectValue placeholder="Filter by type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Coupons</SelectItem>
                  <SelectItem value="active">Active Only</SelectItem>
                  <SelectItem value="inactive">Inactive Only</SelectItem>
                  <SelectItem value="coupon">Coupon Codes</SelectItem>
                  <SelectItem value="auto">Auto Offers</SelectItem>
                  <SelectItem value="combo">Combo Deals</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>

        <CardContent>
          {isLoading && !coupons?.length ? (
            <div className="text-center py-12 text-muted-foreground">Loading coupons…</div>
          ) : !coupons || coupons.length === 0 ? (
            <EmptyState
              icon={Tag}
              title="No Coupons Found"
              description={
                searchQuery || filterType !== 'all'
                  ? "No coupons match your search or filter criteria. Try adjusting your filters."
                  : "Create your first coupon to start offering discounts to your customers."
              }
              action={{ label: 'Create Coupon', onClick: () => setIsCreateDialogOpen(true) }}
            />
          ) : (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {coupons.map((coupon: any) => {
                  const isPercent = coupon.discount_type === 'percent'

                  let discountLabel = isPercent
                    ? `${coupon.discount_value}% OFF`
                    : `${formatAmountNoDecimals(coupon.discount_value)} OFF`

                  if (coupon.offer_type === 'combo') {
                    if (coupon.combo_type === 'bogo') {
                      discountLabel = 'BUY 1 GET 1'
                    } else if (coupon.combo_price > 0) {
                      discountLabel = `₹${formatAmountNoDecimals(coupon.combo_price)} COMBO`
                    } else {
                      discountLabel = 'COMBO DEAL'
                    }
                  }

                  const discountColor = 'text-green-600 dark:text-green-400'
                  const stripeColor   = coupon.offer_type === 'combo'
                    ? 'bg-purple-500'
                    : coupon.offer_type === 'auto'
                    ? 'bg-orange-500'
                    : 'bg-green-500'

                  return (
                    <div
                      key={coupon.name}
                      className={`relative flex flex-col rounded-xl border bg-card shadow-sm transition-opacity ${!coupon.is_active ? 'opacity-60' : ''}`}
                    >
                      <div className={`h-1 w-full rounded-t-xl ${stripeColor}`} />

                      <div className="flex flex-col flex-1 p-4 gap-3">
                        {/* Code + toggle */}
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            {getOfferTypeIcon(coupon.offer_type || 'coupon')}
                            <span className="font-bold text-sm tracking-widest uppercase truncate">{coupon.code}</span>
                          </div>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <span className={`text-[11px] font-medium ${coupon.is_active ? 'text-green-500 dark:text-green-400' : 'text-muted-foreground'}`}>
                              {coupon.is_active ? 'On' : 'Off'}
                            </span>
                            <Switch
                              checked={!!coupon.is_active}
                              onCheckedChange={() => handleToggleActive(coupon.name, !!coupon.is_active)}
                              className="data-[state=checked]:bg-green-500 h-5 w-9"
                            />
                          </div>
                        </div>

                        {/* Description */}
                        <p className="text-xs text-muted-foreground line-clamp-2 min-h-[32px] leading-relaxed">
                          {coupon.description || <span className="italic">No description</span>}
                        </p>

                        {/* Discount hero */}
                        <div className={`flex items-center gap-1.5 ${discountColor}`}>
                          {isPercent
                            ? <Percent className="h-4 w-4 shrink-0" />
                            : <Tag className="h-4 w-4 shrink-0" />
                          }
                          <span className="text-lg font-extrabold leading-none">{discountLabel}</span>
                          {coupon.max_discount_cap > 0 && (
                            <span className="text-[11px] font-normal text-muted-foreground ml-0.5">
                              up to {formatAmountNoDecimals(coupon.max_discount_cap)}
                            </span>
                          )}
                        </div>

                        {/* Meta grid */}
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
                          <div className="flex items-center justify-between">
                            <span className="text-muted-foreground">Min order</span>
                            <span className="font-medium text-foreground">
                              {coupon.min_order_amount > 0 ? formatAmountNoDecimals(coupon.min_order_amount) : '—'}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-muted-foreground">Usage</span>
                            <span className="font-medium text-foreground">
                              {coupon.usage_count || 0} / {coupon.max_uses || '∞'}
                            </span>
                          </div>
                          <div className="col-span-2 flex items-center justify-between">
                            <span className="flex items-center gap-1 text-muted-foreground">
                              {coupon.valid_until ? (
                                <>
                                  <Calendar className="h-3 w-3 shrink-0" />
                                  Until {new Date(coupon.valid_until).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
                                </>
                              ) : 'No expiry'}
                            </span>
                            {coupon.can_stack && (
                              <span className="flex items-center gap-0.5 text-blue-500 font-medium">
                                <Zap className="h-3 w-3" />Stackable
                              </span>
                            )}
                          </div>
                        </div>

                        <div className="border-t border-dashed border-border" />

                        {/* Actions */}
                        <div className="flex items-center gap-2">
                          <Button
                            variant="outline" size="sm"
                            className="flex-1 h-8 text-xs font-medium"
                            onClick={() => setEditingCoupon(coupon)}
                          >
                            <Edit className="h-3.5 w-3.5 mr-1.5" />Edit
                          </Button>
                          <Button
                            variant="outline" size="sm"
                            className="h-8 w-8 p-0 text-destructive hover:bg-destructive/10 hover:border-destructive/30"
                            onClick={() => openDeleteDialog(coupon.name, coupon.code)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>

              <DataPagination
                currentPage={page}
                totalCount={totalCount}
                pageSize={pageSize}
                onPageChange={setPage}
                onPageSizeChange={setPageSize}
                isLoading={isLoading}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Template picker → shown when creating, not editing, and no AI pre-fill */}
      <TemplatePicker
        open={isCreateDialogOpen && !selectedTemplate && !aiPrefilledForm}
        onClose={() => setIsCreateDialogOpen(false)}
        onSelect={(tpl) => setSelectedTemplate(tpl)}
      />

      {/* Coupon form dialog */}
      <CouponDialog
        open={(isCreateDialogOpen && (!!selectedTemplate || !!aiPrefilledForm)) || !!editingCoupon}
        onClose={() => {
          setIsCreateDialogOpen(false)
          setSelectedTemplate(null)
          setEditingCoupon(null)
          setAiPrefilledForm(null)
        }}
        coupon={editingCoupon}
        templateDefaults={selectedTemplate?.defaults ?? null}
        aiDefaults={aiPrefilledForm}
        onSave={handleSave}
      />

      {/* AI Suggestions Modal */}
      <AISuggestionsModal
        open={isAIModalOpen}
        onClose={() => setIsAIModalOpen(false)}
        restaurantId={selectedRestaurant!}
        onUseSuggestion={handleUseAISuggestion}
        onSaveAll={handleSaveAllAISuggestions}
        walletBalance={(restaurant as any)?.coins_balance ?? 0}
      />

      {/* Delete confirmation */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Coupon?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete <strong>"{couponToDelete?.code}"</strong>?
              This action cannot be undone and all usage history will be lost.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setCouponToDelete(null)}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteCoupon}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete Coupon
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

// ─── Template picker ──────────────────────────────────────────────────────────

function TemplatePicker({ open, onClose, onSelect }: {
  open: boolean
  onClose: () => void
  onSelect: (tpl: CouponTemplate) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl">Choose a Template</DialogTitle>
          <DialogDescription>
            Pick a pre-filled template to get started quickly, or start blank for full control.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
          {TEMPLATES.map((tpl) => (
            <button
              key={tpl.id}
              type="button"
              onClick={() => onSelect(tpl)}
              className="group relative flex items-start gap-4 rounded-xl border bg-card p-4 text-left
                         transition-all hover:border-primary hover:shadow-md focus-visible:outline-none
                         focus-visible:ring-2 focus-visible:ring-ring"
            >
              {/* Accent stripe */}
              <div className={`mt-0.5 shrink-0 flex items-center justify-center h-10 w-10 rounded-lg text-white ${tpl.accent}`}>
                {tpl.icon}
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-sm">{tpl.label}</span>
                  {tpl.badge && (
                    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400">
                      {tpl.badge}
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{tpl.tagline}</p>
                {tpl.defaults.code && (
                  <p className="mt-1.5 text-[11px] font-mono font-bold tracking-widest text-primary/70">
                    {tpl.defaults.code}
                  </p>
                )}
              </div>

              {/* Hover arrow */}
              <Plus className="h-4 w-4 text-muted-foreground/40 group-hover:text-primary transition-colors shrink-0 mt-1" />
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ─── Coupon form dialog ───────────────────────────────────────────────────────

function CouponDialog({ open, onClose, coupon, templateDefaults, aiDefaults, onSave }: {
  open: boolean
  onClose: () => void
  coupon: any
  templateDefaults: Partial<typeof BLANK_FORM> | null
  aiDefaults?: Partial<typeof BLANK_FORM> | null
  onSave: (data: any) => Promise<void>
}) {
  const { formatAmountNoDecimals } = useCurrency()
  const { selectedRestaurant } = useRestaurant()
  const [saving, setSaving] = useState(false)
  const [selectedProducts, setSelectedProducts] = useState<string[]>([])
  const [selectedPoolProducts, setSelectedPoolProducts] = useState<string[]>([])
  const [generatingImage, setGeneratingImage] = useState(false)
  const { call: enqueueEnhancement } = useFrappePostCall('flamezo_backend.flamezo.api.ai_media.enqueue_enhancement')
  const { call: getEnhancementStatus } = useFrappePostCall('flamezo_backend.flamezo.api.ai_media.get_enhancement_status')

  const { data: productsData } = useFrappeGetDocList('Menu Product', {
    fields: ['product_id', 'product_name', 'category_name', 'main_category'],
    filters: selectedRestaurant ? ({ restaurant: selectedRestaurant, is_active: 1 } as any) : undefined,
    limit: 500,
    orderBy: { field: 'product_name', order: 'asc' } as any,
  })

  const products: { product_id: string; product_name: string }[] = (productsData as any) || []

  const [formData, setFormData] = useState<any>({ ...BLANK_FORM })

  // Populate form whenever the dialog opens
  useEffect(() => {
    if (!open) return
    if (coupon) {
      setFormData({
        ...BLANK_FORM,
        code: coupon.code || '',
        description: coupon.description || '',
        discount_type: coupon.discount_type || 'percent',
        discount_value: coupon.discount_value || 0,
        min_order_amount: coupon.min_order_amount || 0,
        max_discount_cap: coupon.max_discount_cap || 0,
        is_active: coupon.is_active ?? true,
        offer_type: coupon.offer_type || 'coupon',
        priority: coupon.priority || 1,
        max_uses: coupon.max_uses || 0,
        max_uses_per_user: coupon.max_uses_per_user || 0,
        valid_from: coupon.valid_from || '',
        valid_until: coupon.valid_until || '',
        combo_price: coupon.combo_price || 0,
        bogo_free_item_value: coupon.bogo_free_item_value || 0,
        required_items: coupon.required_items || null,
        valid_days_of_week: coupon.valid_days_of_week || '',
        valid_time_start: coupon.valid_time_start || '',
        valid_time_end: coupon.valid_time_end || '',
        can_stack: !!coupon.can_stack,
        free_item: coupon.free_item || '',
        category: coupon.category || 'best',
        combo_type: coupon.combo_type || 'fixed_bundle',
        combo_name: coupon.combo_name || '',
        item_pool: coupon.item_pool || '',
        items_to_select: coupon.items_to_select || 2,
        display_on_menu: coupon.display_on_menu ?? true,
        combo_image: coupon.combo_image || '',
      })
      if (coupon.required_items) {
        try {
          const parsed = typeof coupon.required_items === 'string'
            ? JSON.parse(coupon.required_items)
            : coupon.required_items
          setSelectedProducts(Array.isArray(parsed) ? parsed : [])
        } catch { setSelectedProducts([]) }
      } else {
        setSelectedProducts([])
      }
      if (coupon.item_pool) {
        try {
          const parsed = typeof coupon.item_pool === 'string'
            ? JSON.parse(coupon.item_pool)
            : coupon.item_pool
          setSelectedPoolProducts(Array.isArray(parsed) ? parsed : [])
        } catch { setSelectedPoolProducts([]) }
      } else {
        setSelectedPoolProducts([])
      }
    } else {
      // New coupon — AI defaults take priority over template defaults
      setFormData({ ...BLANK_FORM, ...(templateDefaults || {}), ...(aiDefaults || {}) })
      // Resolve combo_items_hint names → product IDs
      const hint = (aiDefaults as any)?._combo_items_hint as string | undefined
      if (hint && products.length > 0) {
        const names = hint.split(',').map((n: string) => n.trim().toLowerCase())
        const matched = products
          .filter(p => names.some(n => p.product_name.toLowerCase().includes(n) || n.includes(p.product_name.toLowerCase())))
          .map(p => p.product_id)
        setSelectedProducts(matched)
      } else {
        setSelectedProducts([])
      }
      setSelectedPoolProducts([])
    }
  }, [open, coupon, templateDefaults, aiDefaults])

  // Keep required_items in sync with the product multi-select
  useEffect(() => {
    if (formData.offer_type === 'combo') {
      setFormData((prev: any) => ({ ...prev, required_items: JSON.stringify(selectedProducts) }))
    }
  }, [selectedProducts, formData.offer_type])

  // Keep item_pool in sync with pool product multi-select
  useEffect(() => {
    if (formData.offer_type === 'combo') {
      setFormData((prev: any) => ({ ...prev, item_pool: JSON.stringify(selectedPoolProducts) }))
    }
  }, [selectedPoolProducts, formData.offer_type])

  const set = (patch: Partial<typeof BLANK_FORM>) =>
    setFormData((prev: any) => ({ ...prev, ...patch }))

  const toggleDay = (day: string) => {
    let days: string[] = []
    try { days = formData.valid_days_of_week ? JSON.parse(formData.valid_days_of_week) : [] } catch { days = [] }
    days = days.includes(day) ? days.filter(d => d !== day) : [...days, day]
    set({ valid_days_of_week: days.length ? JSON.stringify(days) : '' })
  }

  const isDaySelected = (day: string) => {
    try { return (formData.valid_days_of_week ? JSON.parse(formData.valid_days_of_week) : []).includes(day) }
    catch { return false }
  }

  const handleGenerateImage = async () => {
    if (!selectedRestaurant || !coupon?.name) return
    setGeneratingImage(true)
    try {
      const res = await enqueueEnhancement({
        restaurant: selectedRestaurant,
        owner_doctype: 'Coupon',
        owner_name: coupon.name,
        mode: 'generate',
      }) as any
      const generationId = res?.message?.generation_id
      if (!generationId) throw new Error('No generation ID returned')
      // Poll until done
      let attempts = 0
      while (attempts < 40) {
        await new Promise(r => setTimeout(r, 3000))
        const status = await getEnhancementStatus({ generation_id: generationId }) as any
        const s = status?.message
        if (s?.status === 'Completed' && s?.enhanced_image_url) {
          set({ combo_image: s.enhanced_image_url })
          break
        }
        if (s?.status === 'Failed') throw new Error(s?.error_message || 'Generation failed')
        attempts++
      }
    } catch (err: any) {
      alert(err?.message || 'Image generation failed')
    } finally {
      setGeneratingImage(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const s = { ...formData }
      if (!s.free_item) s.free_item = null
      if (!s.valid_from) s.valid_from = null
      if (!s.valid_until) s.valid_until = null
      if (!s.valid_time_start) s.valid_time_start = null
      if (!s.valid_time_end) s.valid_time_end = null
      if (!s.valid_days_of_week) s.valid_days_of_week = null
      if (s.offer_type !== 'combo') {
        s.required_items = null; s.combo_price = null; s.free_item = null
        s.combo_type = null; s.combo_name = null; s.item_pool = null
        s.items_to_select = null; s.display_on_menu = 0
      } else {
        if (!s.required_items || s.required_items === '[]') s.required_items = null
        if (!s.item_pool || s.item_pool === '[]') s.item_pool = null
        if (!s.combo_name) s.combo_name = null
        s.display_on_menu = s.display_on_menu ? 1 : 0
      }
      if (!s.max_uses || s.max_uses === 0) s.max_uses = null
      if (!s.max_uses_per_user || s.max_uses_per_user === 0) s.max_uses_per_user = null
      if (!s.max_discount_cap || s.max_discount_cap === 0) s.max_discount_cap = null
      if (!s.min_order_amount || s.min_order_amount === 0) s.min_order_amount = null
      await onSave(s)
    } finally {
      setSaving(false)
    }
  }

  const currencySymbol = formatAmountNoDecimals(0).replace(/\d/g, '').trim() || '₹'

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{coupon ? 'Edit Coupon' : 'Create New Coupon'}</DialogTitle>
          <DialogDescription>
            {coupon ? 'Update coupon details' : 'Fill in the details for your new offer'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-5">

          {/* ── Row 1: Code + Offer Type ── */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="code">Coupon Code *</Label>
              <Input
                id="code"
                value={formData.code}
                onChange={(e) => set({ code: e.target.value.toUpperCase() })}
                placeholder="SAVE20"
                required
                className="font-mono font-bold tracking-widest"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="offer_type">Offer Type</Label>
              <Select
                value={formData.offer_type}
                onValueChange={(v) => {
                  const patch: any = { offer_type: v }
                  if (v === 'combo') { patch.category = 'best'; patch.discount_type = 'flat' }
                  else { patch.category = 'best' }
                  set(patch)
                }}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="coupon">Coupon Code</SelectItem>
                  <SelectItem value="auto">Auto-Applied</SelectItem>
                  <SelectItem value="combo">Combo Deal</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* ── Description ── */}
          <div className="space-y-1.5">
            <Label htmlFor="description">Description <span className="text-muted-foreground font-normal">(shown to customers)</span></Label>
            <Input
              id="description"
              value={formData.description}
              onChange={(e) => set({ description: e.target.value })}
              placeholder={
                formData.offer_type === 'combo' ? 'Get 2 Pizzas + 1 Drink at a special combo price' :
                formData.offer_type === 'auto'  ? 'Weekend special — 25% off all bills' :
                                                  'Get 20% off on bills above ₹299'
              }
            />
          </div>

          {/* ── Discount section — varies by offer type ── */}
          {formData.offer_type === 'combo' ? (
            <div className="space-y-4 rounded-xl border p-4">
              <p className="text-sm font-semibold flex items-center gap-2"><Gift className="h-4 w-4 text-purple-500" />Combo Settings</p>

              {/* Row: Combo Type + Display Name */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label>Combo Type *</Label>
                  <Select value={formData.combo_type} onValueChange={(v) => set({ combo_type: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="fixed_bundle">Fixed Bundle</SelectItem>
                      <SelectItem value="bogo">BOGO — cheapest item free</SelectItem>
                      <SelectItem value="build_your_own">Build Your Own</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="combo_name">Display Name <span className="text-muted-foreground font-normal text-xs">(on menu card)</span></Label>
                  <Input
                    id="combo_name"
                    value={formData.combo_name}
                    onChange={(e: any) => set({ combo_name: e.target.value })}
                    placeholder={
                      formData.combo_type === 'bogo' ? 'Buy 2 Get 1 Free' :
                      formData.combo_type === 'build_your_own' ? 'Build Your Meal' :
                      'Weekend Bundle'
                    }
                  />
                </div>
              </div>

              {/* fixed_bundle: all required products must be in cart */}
              {formData.combo_type === 'fixed_bundle' && (
                <div className="space-y-2">
                  <Label>Required Products <span className="text-muted-foreground font-normal text-xs">(all must be in cart)</span></Label>
                  {selectedProducts.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {selectedProducts.map((pid) => {
                        const prod = products.find(p => p.product_id === pid)
                        return (
                          <Badge key={pid} variant="secondary" className="gap-1 text-xs">
                            {prod?.product_name || pid}
                            <button type="button" onClick={() => setSelectedProducts(prev => prev.filter(p => p !== pid))}>
                              <X className="h-3 w-3" />
                            </button>
                          </Badge>
                        )
                      })}
                    </div>
                  )}
                  <Select value="" onValueChange={(pid) => pid && !selectedProducts.includes(pid) && setSelectedProducts(prev => [...prev, pid])}>
                    <SelectTrigger><SelectValue placeholder="Add a product to the bundle…" /></SelectTrigger>
                    <SelectContent>
                      {products.filter(p => !selectedProducts.includes(p.product_id)).map((p) => (
                        <SelectItem key={p.product_id} value={p.product_id}>{p.product_name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* bogo / build_your_own: item pool + how many to pick */}
              {(formData.combo_type === 'bogo' || formData.combo_type === 'build_your_own') && (
                <div className="space-y-3">
                  <div className="space-y-2">
                    <Label>Item Pool <span className="text-muted-foreground font-normal text-xs">
                      {formData.combo_type === 'bogo'
                        ? '— customer picks from these; cheapest one goes free'
                        : '— customer picks from these at the combo price'}
                    </span></Label>
                    {selectedPoolProducts.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mb-2">
                        {selectedPoolProducts.map((pid) => {
                          const prod = products.find(p => p.product_id === pid)
                          return (
                            <Badge key={pid} variant="secondary" className="gap-1 text-xs">
                              {prod?.product_name || pid}
                              <button type="button" onClick={() => setSelectedPoolProducts(prev => prev.filter(p => p !== pid))}>
                                <X className="h-3 w-3" />
                              </button>
                            </Badge>
                          )
                        })}
                      </div>
                    )}
                    <Select value="" onValueChange={(pid) => pid && !selectedPoolProducts.includes(pid) && setSelectedPoolProducts(prev => [...prev, pid])}>
                      <SelectTrigger><SelectValue placeholder="Add product to pool…" /></SelectTrigger>
                      <SelectContent>
                        {products.filter(p => !selectedPoolProducts.includes(p.product_id)).map((p) => (
                          <SelectItem key={p.product_id} value={p.product_id}>{p.product_name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5 w-1/2">
                    <Label htmlFor="items_to_select">
                      {formData.combo_type === 'bogo' ? 'Items to Buy (N in BOGO)' : 'Items to Select'}
                    </Label>
                    <NumberInput
                      id="items_to_select"
                      value={formData.items_to_select}
                      onChange={(e: any) => set({ items_to_select: parseInt(e.target.value) || 2 })}
                      min="1"
                    />
                  </div>
                </div>
              )}

              {/* Price — BOGO uses fixed free-item value; others use combo_price */}
              {formData.combo_type === 'bogo' ? (
                <div className="space-y-1.5">
                  <Label htmlFor="bogo_free_item_value">
                    Free Item Value ({currencySymbol}) *
                    <span className="text-muted-foreground font-normal text-xs ml-1">— the rupee value of the item the customer gets free</span>
                  </Label>
                  <NumberInput
                    id="bogo_free_item_value"
                    value={formData.bogo_free_item_value}
                    onChange={(e: any) => set({ bogo_free_item_value: parseFloat(e.target.value) || 0 })}
                    min="0"
                    required
                  />
                  <p className="text-xs text-muted-foreground">
                    Both you and the customer see this as a fixed discount. E.g. if cheapest qualifying item is ₹199, set ₹199.
                  </p>
                </div>
              ) : (
                <div className="space-y-1.5">
                  <Label htmlFor="combo_price">
                    Combo Price ({currencySymbol}) *
                    {formData.combo_type === 'build_your_own' && (
                      <span className="text-muted-foreground font-normal text-xs ml-1">— what the customer pays for their picks</span>
                    )}
                  </Label>
                  <NumberInput id="combo_price" value={formData.combo_price}
                    onChange={(e: any) => set({ combo_price: parseFloat(e.target.value) || 0 })} min="0" required />
                </div>
              )}

              {/* Combo card image — mandatory to show on menu */}
              <div className="space-y-2 rounded-lg border p-3">
                <Label className="flex items-center gap-1.5">
                  <ImagePlus className="h-4 w-4 text-purple-500" />
                  Combo Card Image <span className="text-red-500">*</span>
                  <span className="text-muted-foreground font-normal text-xs">(required to show on menu)</span>
                </Label>
                {formData.combo_image ? (
                  <div className="relative w-32 h-40 rounded-xl overflow-hidden border">
                    <img src={formData.combo_image} alt="Combo" className="w-full h-full object-cover" />
                    <button
                      type="button"
                      onClick={() => set({ combo_image: '' })}
                      className="absolute top-1 right-1 bg-black/60 rounded-full p-0.5 text-white hover:bg-black/80"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ) : (
                  <div className="w-32 h-40 rounded-xl border-2 border-dashed border-muted-foreground/30 flex items-center justify-center text-muted-foreground/50">
                    <ImagePlus className="h-8 w-8" />
                  </div>
                )}
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    disabled={generatingImage || !coupon?.name}
                    onClick={handleGenerateImage}
                  >
                    {generatingImage ? (
                      <><Loader2 className="h-3.5 w-3.5 animate-spin" />Generating…</>
                    ) : (
                      <><Sparkles className="h-3.5 w-3.5 text-purple-500" />Generate with AI</>
                    )}
                  </Button>
                  <label className="cursor-pointer">
                    <Button type="button" variant="outline" size="sm" className="gap-1.5 pointer-events-none">
                      <ImagePlus className="h-3.5 w-3.5" />Upload
                    </Button>
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={async (e) => {
                        const file = e.target.files?.[0]
                        if (!file) return
                        const reader = new FileReader()
                        reader.onload = () => set({ combo_image: reader.result as string })
                        reader.readAsDataURL(file)
                      }}
                    />
                  </label>
                </div>
                {!coupon?.name && (
                  <p className="text-xs text-muted-foreground">Save the coupon first to enable AI generation.</p>
                )}
              </div>

              {/* Show on menu card toggle */}
              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="display_on_menu"
                  checked={!!formData.display_on_menu}
                  onChange={(e) => set({ display_on_menu: e.target.checked } as any)}
                  className="h-4 w-4 rounded border-border"
                />
                <label htmlFor="display_on_menu" className="text-sm cursor-pointer">
                  Show as a combo card on the menu page
                  {!formData.combo_image && formData.display_on_menu && (
                    <span className="ml-2 text-xs text-amber-600">(add an image above first)</span>
                  )}
                  {formData.combo_image && formData.display_on_menu && formData.combo_type !== 'bogo' && !formData.combo_price && (
                    <span className="ml-2 text-xs text-red-600">(set a combo price — ₹0 combos won't appear on menu)</span>
                  )}
                  {formData.combo_image && formData.display_on_menu && formData.combo_type === 'bogo' && !formData.bogo_free_item_value && (
                    <span className="ml-2 text-xs text-red-600">(set the free item value — ₹0 BOGO won't appear on menu)</span>
                  )}
                </label>
              </div>
            </div>

          ) : (
            <div className="space-y-4 rounded-xl border p-4">
              <p className="text-sm font-semibold flex items-center gap-2"><Tag className="h-4 w-4 text-green-600" />Discount</p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="space-y-1.5">
                  <Label>Discount Type</Label>
                  <Select value={formData.discount_type} onValueChange={(v) => set({ discount_type: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="percent">Percentage (%)</SelectItem>
                      <SelectItem value="flat">Flat Amount ({currencySymbol})</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>
                    {formData.discount_type === 'percent' ? 'Discount %' : `Discount (${currencySymbol})`} *
                  </Label>
                  <NumberInput value={formData.discount_value}
                    onChange={(e: any) => set({ discount_value: parseFloat(e.target.value) || 0 })} min="0" required />
                </div>
                <div className="space-y-1.5">
                  <Label>Max Cap ({currencySymbol}) <span className="text-muted-foreground font-normal text-xs">optional</span></Label>
                  <NumberInput value={formData.max_discount_cap}
                    onChange={(e: any) => set({ max_discount_cap: parseFloat(e.target.value) || 0 })} min="0" />
                </div>
              </div>
            </div>
          )}

          {/* ── Conditions ── */}
          <div className="space-y-4 rounded-xl border p-4">
            <p className="text-sm font-semibold">Conditions</p>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label>Min Order Amount ({currencySymbol})</Label>
                <NumberInput value={formData.min_order_amount}
                  onChange={(e: any) => set({ min_order_amount: parseFloat(e.target.value) || 0 })} min="0" />
              </div>
              <div className="space-y-1.5">
                <Label>Priority <span className="text-muted-foreground font-normal text-xs">(higher = applied first)</span></Label>
                <NumberInput value={formData.priority}
                  onChange={(e: any) => set({ priority: parseInt(e.target.value) || 1 })} min="1" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label>Total Usage Limit <span className="text-muted-foreground font-normal text-xs">0 = unlimited</span></Label>
                <NumberInput value={formData.max_uses}
                  onChange={(e: any) => set({ max_uses: parseInt(e.target.value) || 0 })} min="0" />
              </div>
              <div className="space-y-1.5">
                <Label>Per-Customer Limit <span className="text-muted-foreground font-normal text-xs">0 = unlimited</span></Label>
                <NumberInput value={formData.max_uses_per_user}
                  onChange={(e: any) => set({ max_uses_per_user: parseInt(e.target.value) || 0 })} min="0" />
              </div>
            </div>
          </div>

          {/* ── Validity ── */}
          <div className="space-y-4 rounded-xl border p-4">
            <p className="text-sm font-semibold">Validity Window</p>
            <div className="grid grid-cols-2 gap-4">
              <DatePicker label="Valid From" value={formData.valid_from}
                onChange={(v) => set({ valid_from: v })} />
              <DatePicker label="Valid Until" value={formData.valid_until}
                onChange={(v) => set({ valid_until: v })} />
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Active Days</Label>
              <div className="flex flex-wrap gap-2">
                {DAYS_OF_WEEK.map((day) => (
                  <button
                    key={day.value}
                    type="button"
                    onClick={() => toggleDay(day.value)}
                    className={`px-3 py-1 rounded-full text-xs font-semibold border transition-colors
                      ${isDaySelected(day.value)
                        ? 'bg-primary text-primary-foreground border-primary'
                        : 'bg-transparent text-muted-foreground border-border hover:border-primary/50'}`}
                  >
                    {day.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <TimePicker label="Time Start" value={formData.valid_time_start}
                onChange={(e) => set({ valid_time_start: e.target.value })} />
              <TimePicker label="Time End" value={formData.valid_time_end}
                onChange={(e) => set({ valid_time_end: e.target.value })} />
            </div>
          </div>

          {/* ── Flags ── */}
          <div className="flex items-center gap-6">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <Checkbox id="is_active" checked={formData.is_active}
                onCheckedChange={(c) => set({ is_active: !!c })} />
              <span className="text-sm font-medium">Active</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <Checkbox id="can_stack" checked={formData.can_stack}
                onCheckedChange={(c) => set({ can_stack: !!c })} />
              <span className="text-sm font-medium">Stackable</span>
              <span className="text-xs text-muted-foreground">(combine with other offers)</span>
            </label>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
              <ArrowLeft className="h-4 w-4 mr-1.5" />Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? 'Saving…' : coupon ? 'Update Coupon' : 'Create Coupon'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ─── Claims Analytics Card ────────────────────────────────────────────────────

function ClaimsAnalyticsCard({ restaurantId }: { restaurantId: string }) {
  const [period, setPeriod] = useState('30d')
  const [showDetails, setShowDetails] = useState(false)
  const [loading, setLoading] = useState(false)
  const [analytics, setAnalytics] = useState<any>(null)

  const { call: fetchAnalytics } = useFrappePostCall(
    'flamezo_backend.flamezo.api.coupons.get_offer_claims_analytics'
  )

  const load = async (p = period) => {
    if (!restaurantId) return
    setLoading(true)
    try {
      const res = await fetchAnalytics({ restaurant_id: restaurantId, period: p })
      const payload = (res as any)?.message ?? res
      if (payload?.success) setAnalytics(payload.data)
    } catch { /* silent */ } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [restaurantId, period])

  const summary = analytics?.summary
  const byCoupon: any[] = analytics?.byCoupon || []
  const recentClaims: any[] = analytics?.recentClaims || []

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30">
              <BarChart3 className="h-4 w-4 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <CardTitle className="text-base">Offer Claims</CardTitle>
              <CardDescription className="text-xs mt-0.5">How many claims converted to Flamezo payments</CardDescription>
            </div>
          </div>
          <Select value={period} onValueChange={(v) => { setPeriod(v); load(v) }}>
            <SelectTrigger className="w-[90px] h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7d">7 days</SelectItem>
              <SelectItem value="30d">30 days</SelectItem>
              <SelectItem value="90d">90 days</SelectItem>
              <SelectItem value="all">All time</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading && !analytics ? (
          <div className="flex items-center justify-center py-6">
            <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : !summary ? (
          <p className="text-sm text-muted-foreground text-center py-4">No claims data yet</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: 'Total Claims', value: summary.totalClaims, color: '' },
                { label: 'Paid via Flamezo', value: `${summary.conversionRate}%`, color: 'text-green-600 dark:text-green-400' },
                { label: 'Paid', value: summary.paidCount, color: 'text-green-600' },
                { label: 'Drop-off', value: summary.notPaidCount, color: 'text-red-500' },
              ].map(({ label, value, color }) => (
                <div key={label} className="rounded-xl bg-muted/50 p-3 text-center">
                  <p className={`text-2xl font-bold ${color}`}>{value}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
                </div>
              ))}
            </div>

            {summary.totalPaidAmount > 0 && (
              <div className="rounded-xl border border-green-200 dark:border-green-800 bg-green-50/50 dark:bg-green-900/10 px-4 py-3 flex items-center justify-between">
                <span className="text-sm font-medium text-green-700 dark:text-green-400">Revenue via Flamezo</span>
                <span className="text-lg font-bold text-green-700 dark:text-green-400">
                  ₹{summary.totalPaidAmount.toLocaleString('en-IN')}
                </span>
              </div>
            )}

            <button
              onClick={() => setShowDetails(v => !v)}
              className="w-full flex items-center justify-between text-xs text-muted-foreground hover:text-foreground transition-colors py-1"
            >
              <span className="font-medium">{showDetails ? 'Hide details' : 'Per-coupon breakdown & recent claims'}</span>
              {showDetails ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </button>

            {showDetails && (
              <div className="space-y-4 border-t pt-4">
                {byCoupon.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-2">By Coupon</p>
                    <div className="space-y-2">
                      {byCoupon.map((row) => (
                        <div key={row.coupon_id} className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5">
                          <div className="min-w-0">
                            <p className="font-mono font-bold text-sm truncate">{row.coupon_code}</p>
                            <p className="text-[11px] text-muted-foreground mt-0.5">
                              {row.total_claims} claims · {row.paid_count} paid · {row.not_paid_count} drop-off
                            </p>
                          </div>
                          <Badge
                            variant="secondary"
                            className={row.conversion_rate >= 50
                              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 shrink-0'
                              : 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400 shrink-0'}
                          >
                            {row.conversion_rate}%
                          </Badge>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {recentClaims.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-2">Recent Claims</p>
                    <div className="rounded-lg border overflow-hidden">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-muted/50">
                            <th className="text-left px-3 py-2 font-semibold text-muted-foreground">Coupon</th>
                            <th className="text-left px-3 py-2 font-semibold text-muted-foreground">Customer</th>
                            <th className="text-left px-3 py-2 font-semibold text-muted-foreground">Claimed</th>
                            <th className="text-right px-3 py-2 font-semibold text-muted-foreground">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                          {recentClaims.slice(0, 20).map((c) => (
                            <tr key={c.id} className="hover:bg-muted/30 transition-colors">
                              <td className="px-3 py-2 font-mono font-bold">{c.couponCode}</td>
                              <td className="px-3 py-2 text-muted-foreground">
                                <span className="flex items-center gap-1">
                                  <Phone className="h-3 w-3 shrink-0" />{c.customerPhone}
                                </span>
                              </td>
                              <td className="px-3 py-2 text-muted-foreground">
                                {c.claimedAt ? new Date(c.claimedAt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'}
                              </td>
                              <td className="px-3 py-2 text-right">
                                {c.isPaid ? (
                                  <span className="inline-flex items-center gap-1 text-green-600 font-medium">
                                    <CheckCircle2 className="h-3.5 w-3.5" />Paid
                                    {c.paidAmount > 0 && <span className="text-muted-foreground font-normal ml-1">₹{c.paidAmount}</span>}
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 text-red-500">
                                    <XCircle className="h-3.5 w-3.5" />Not paid
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
