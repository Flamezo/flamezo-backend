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
  TrendingUp, AlertCircle, Zap, X, Bike, Sparkles, ArrowLeft,
  Clock, Star, ShoppingBag, Flame, RotateCcw
} from 'lucide-react'
import { EmptyState } from '@/components/EmptyState'
import { LockedFeature } from '@/components/FeatureGate/LockedFeature'
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
  required_items: '',
  valid_days_of_week: '',
  valid_time_start: '',
  valid_time_end: '',
  can_stack: false,
  free_item: '',
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
      description: 'Flat ₹50 off on orders above ₹299',
      category: 'best',
    },
  },
  {
    id: 'big_percent',
    label: 'Big % Off',
    tagline: 'High % with a rupee cap — drives big orders',
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
    id: 'free_delivery',
    label: 'Free Delivery',
    tagline: 'Zero delivery fee — huge conversion driver',
    icon: <Bike className="h-6 w-6" />,
    accent: 'bg-blue-500',
    badge: 'Popular',
    defaults: {
      offer_type: 'delivery',
      discount_type: 'delivery',
      discount_value: 0,
      min_order_amount: 149,
      code: 'FREEDEL',
      description: 'Free delivery on orders above ₹149',
      category: 'delivery',
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
      description: '15% off all orders between 11 AM – 3 PM',
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
      description: '25% off every weekend on orders above ₹249',
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
      description: '12% off on group orders above ₹999',
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
  const { selectedRestaurant, isDiamond } = useRestaurant()
  const { formatAmountNoDecimals } = useCurrency()
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [editingCoupon, setEditingCoupon] = useState<any>(null)
  const [filterType, setFilterType] = useState<string>('all')
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [couponToDelete, setCouponToDelete] = useState<{ name: string; code: string } | null>(null)
  const [selectedTemplate, setSelectedTemplate] = useState<CouponTemplate | null>(null)

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

  // ── Helpers ───────────────────────────────────────────────────────────────

  const getOfferTypeIcon = (type: string) => {
    switch (type) {
      case 'combo':    return <Gift className="h-4 w-4" />
      case 'auto':     return <TrendingUp className="h-4 w-4" />
      case 'delivery': return <Bike className="h-4 w-4" />
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

  if (!isDiamond) return <LockedFeature feature="coupons" requiredPlan={['DIAMOND']} />

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold">Manage Offers & Coupons</h1>
          <p className="text-muted-foreground mt-1">Create and manage discount coupons, auto-offers, and combo deals</p>
        </div>
        <Button onClick={() => setIsCreateDialogOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Create Coupon
        </Button>
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
                  <SelectItem value="delivery">Delivery Offers</SelectItem>
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
                  const isDelivery = coupon.discount_type === 'delivery' || coupon.offer_type === 'delivery'
                  const isPercent  = coupon.discount_type === 'percent'

                  const discountLabel = isDelivery
                    ? 'FREE DELIVERY'
                    : isPercent
                    ? `${coupon.discount_value}% OFF`
                    : `${formatAmountNoDecimals(coupon.discount_value)} OFF`

                  const discountColor = isDelivery ? 'text-blue-500' : 'text-green-600 dark:text-green-400'
                  const stripeColor   = isDelivery
                    ? 'bg-blue-500'
                    : coupon.offer_type === 'combo'
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
                          {isDelivery
                            ? <Bike className="h-4 w-4 shrink-0" />
                            : isPercent
                            ? <Percent className="h-4 w-4 shrink-0" />
                            : <Tag className="h-4 w-4 shrink-0" />
                          }
                          <span className="text-lg font-extrabold leading-none">{discountLabel}</span>
                          {coupon.max_discount_cap > 0 && !isDelivery && (
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

      {/* Template picker → shown when creating, not editing */}
      <TemplatePicker
        open={isCreateDialogOpen && !selectedTemplate}
        onClose={() => setIsCreateDialogOpen(false)}
        onSelect={(tpl) => setSelectedTemplate(tpl)}
      />

      {/* Coupon form dialog */}
      <CouponDialog
        open={(isCreateDialogOpen && !!selectedTemplate) || !!editingCoupon}
        onClose={() => {
          setIsCreateDialogOpen(false)
          setSelectedTemplate(null)
          setEditingCoupon(null)
        }}
        coupon={editingCoupon}
        templateDefaults={selectedTemplate?.defaults ?? null}
        onSave={handleSave}
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

function CouponDialog({ open, onClose, coupon, templateDefaults, onSave }: {
  open: boolean
  onClose: () => void
  coupon: any
  templateDefaults: Partial<typeof BLANK_FORM> | null
  onSave: (data: any) => Promise<void>
}) {
  const { formatAmountNoDecimals } = useCurrency()
  const { selectedRestaurant } = useRestaurant()
  const [saving, setSaving] = useState(false)
  const [selectedProducts, setSelectedProducts] = useState<string[]>([])

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
        required_items: coupon.required_items || null,
        valid_days_of_week: coupon.valid_days_of_week || '',
        valid_time_start: coupon.valid_time_start || '',
        valid_time_end: coupon.valid_time_end || '',
        can_stack: !!coupon.can_stack,
        free_item: coupon.free_item || '',
        category: coupon.category || 'best',
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
    } else {
      // New coupon — apply template defaults on top of blank form
      setFormData({ ...BLANK_FORM, ...(templateDefaults || {}) })
      setSelectedProducts([])
    }
  }, [open, coupon, templateDefaults])

  // Keep required_items in sync with the product multi-select
  useEffect(() => {
    if (formData.offer_type === 'combo') {
      setFormData((prev: any) => ({ ...prev, required_items: JSON.stringify(selectedProducts) }))
    }
  }, [selectedProducts, formData.offer_type])

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
      if (s.offer_type !== 'combo') { s.required_items = null; s.combo_price = null; s.free_item = null }
      else if (!s.required_items || s.required_items === '[]') s.required_items = null
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
                  if (v === 'delivery') { patch.category = 'delivery'; patch.discount_type = 'delivery' }
                  else if (v === 'combo') { patch.category = 'best'; patch.discount_type = 'flat' }
                  else { patch.category = 'best' }
                  set(patch)
                }}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="coupon">Coupon Code</SelectItem>
                  <SelectItem value="auto">Auto-Applied</SelectItem>
                  <SelectItem value="combo">Combo Deal</SelectItem>
                  <SelectItem value="delivery">Delivery Offer</SelectItem>
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
                formData.offer_type === 'combo'    ? 'Get 2 Pizzas + 1 Drink at a special combo price' :
                formData.offer_type === 'delivery' ? 'Free delivery on orders above ₹149' :
                formData.offer_type === 'auto'     ? 'Weekend special — 25% off all orders' :
                                                     'Get 20% off on orders above ₹299'
              }
            />
          </div>

          {/* ── Discount section — varies by offer type ── */}
          {formData.offer_type === 'combo' ? (
            <div className="space-y-4 rounded-xl border p-4">
              <p className="text-sm font-semibold flex items-center gap-2"><Gift className="h-4 w-4 text-purple-500" />Combo Settings</p>

              {/* Product picker */}
              <div className="space-y-2">
                <Label>Required Products *</Label>
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
                  <SelectTrigger><SelectValue placeholder="Add a product to the combo…" /></SelectTrigger>
                  <SelectContent>
                    {products.filter(p => !selectedProducts.includes(p.product_id)).map((p) => (
                      <SelectItem key={p.product_id} value={p.product_id}>{p.product_name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="combo_price">Combo Price ({currencySymbol}) *</Label>
                  <NumberInput id="combo_price" value={formData.combo_price}
                    onChange={(e: any) => set({ combo_price: parseFloat(e.target.value) || 0 })} min="0" required />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="free_item">Free Gift Item (BOGO)</Label>
                  <Select value={formData.free_item || '__none__'} onValueChange={(v) => set({ free_item: v === '__none__' ? '' : v })}>
                    <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">None</SelectItem>
                      {products.map((p) => <SelectItem key={p.product_id} value={p.product_id}>{p.product_name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>

          ) : formData.offer_type === 'delivery' ? (
            <div className="space-y-4 rounded-xl border border-blue-200 dark:border-blue-900 p-4">
              <p className="text-sm font-semibold flex items-center gap-2 text-blue-600 dark:text-blue-400">
                <Bike className="h-4 w-4" />Delivery Discount
              </p>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label>Delivery Benefit</Label>
                  <Select value={formData.discount_type} onValueChange={(v) => set({ discount_type: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="delivery">Free Delivery (waive full fee)</SelectItem>
                      <SelectItem value="flat">Flat {currencySymbol} off the fee</SelectItem>
                      <SelectItem value="percent">% off the fee</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {formData.discount_type !== 'delivery' && (
                  <div className="space-y-1.5">
                    <Label>Discount Value *</Label>
                    <NumberInput value={formData.discount_value}
                      onChange={(e: any) => set({ discount_value: parseFloat(e.target.value) || 0 })} min="0" required />
                  </div>
                )}
              </div>
            </div>

          ) : (
            <div className="space-y-4 rounded-xl border p-4">
              <p className="text-sm font-semibold flex items-center gap-2"><Tag className="h-4 w-4 text-green-600" />Discount</p>
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1.5">
                  <Label>Discount Type</Label>
                  <Select value={formData.discount_type} onValueChange={(v) => set({ discount_type: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="percent">Percentage (%)</SelectItem>
                      <SelectItem value="flat">Flat Amount ({currencySymbol})</SelectItem>
                      <SelectItem value="delivery">Free Delivery</SelectItem>
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
