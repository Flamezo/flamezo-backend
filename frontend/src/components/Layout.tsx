import { Link, useLocation, useNavigate, Outlet } from 'react-router-dom'
import { Home, ShoppingCart, Package, Truck, FolderTree, Grid3x3, Sparkles, Star, Store, X, Lock, LockOpen, ChevronDown, ChevronRight, TrendingUp, TrendingDown, DollarSign, AlertCircle, Activity, Moon, Sun, ExternalLink, Eye, Plus, Loader2, QrCode, Clock, User, Users, LogOut, LayoutDashboard, CheckCircle2, Calendar, Tag, Shield, ShieldAlert, Wallet, Crown, CreditCard, Settings, MessageSquare, Megaphone, Send, Zap, BarChart3, Menu, Search, Globe, Mail, Smartphone, ClipboardCopy, PartyPopper } from 'lucide-react'
import { cn, copyToClipboard } from '@/lib/utils'
import { useFrappeGetDocList, useFrappeGetDoc, useFrappePostCall, useFrappeAuth } from '@/lib/frappe'
import { AiRechargeModal } from '@/components/AiRechargeModal'
import { useState, useEffect, useMemo } from 'react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useTheme } from '@/contexts/ThemeContext'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useCurrency } from '@/hooks/useCurrency'
import Breadcrumb from './Breadcrumb'
import { BillingNotificationBar } from './BillingNotificationBar'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { RadioGroup, RadioGroupItem } from './ui/radio-group'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'
import { SuspendedOverlay } from './SuspendedOverlay'
import { normalizePhone } from '@/utils/otpStorage'
import { getFeatureAccessStatus, GOLD_ONLY_FEATURES } from '@/utils/featureAccess'

interface LayoutProps {
  children?: React.ReactNode
}

function UserProfileDropdown() {
  const { logout, currentUser } = useFrappeAuth()
  const bootUserRaw = (window as any)?.frappe?.boot?.user
  // Frappe boot.user can be string (username) or object { name, email, ... }
  const bootUser = typeof bootUserRaw === 'string'
    ? bootUserRaw
    : (bootUserRaw?.name ?? bootUserRaw?.email ?? 'Guest')
  const userDisplay = bootUser !== 'Guest' ? String(bootUser) : 'User'
  const userInitial = (userDisplay?.charAt?.(0) ?? 'U').toUpperCase()

  const handleLogout = async () => {
    try {
      await logout()
      // Full page reload clears cache and ensures session is gone
      window.location.replace('/dinematters/login')
    } catch {
      // Still redirect on error so user can retry
      window.location.replace('/dinematters/login')
    }
  }

  // Redirect to ERPNext/Frappe site (e.g. http://localhost:8000/)
  const siteOrigin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000'
  const deskUrl = `${siteOrigin}/app`

  // Check if main admin (or you could check boot.user.roles if desired)
  const isMainAdmin = currentUser === 'Administrator'

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100 transition-all border shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-200 focus:ring-offset-2"
          aria-label="User menu"
        >
          <span className="text-xs font-bold">{userInitial}</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuItem asChild>
          <Link to="/account" className="flex items-center gap-2 cursor-pointer">
            <User className="h-4 w-4" />
            My Account
          </Link>
        </DropdownMenuItem>

        {isMainAdmin && (
          <DropdownMenuItem asChild>
            <a href={deskUrl} className="flex items-center gap-2 cursor-pointer">
              <LayoutDashboard className="h-4 w-4" />
              Switch To Desk
            </a>
          </DropdownMenuItem>
        )}

        <DropdownMenuItem
          onClick={handleLogout}
          className="flex items-center gap-2 cursor-pointer text-destructive focus:text-destructive"
        >
          <LogOut className="h-4 w-4" />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

const SIDEBAR_GROUPS_KEY = 'dinematters_sidebar_groups_open'

type NavLink = { type: 'link'; name: string; href: string; icon: React.ComponentType<{ className?: string }>; badgeHref?: string; feature?: string; adminOnly?: boolean }
type NavGroup = {
  type: 'group'
  id: string
  name: string
  icon: React.ComponentType<{ className?: string }>
  children: { name: string; href: string; icon?: React.ComponentType<{ className?: string }>; badgeHref?: string; feature?: string; adminOnly?: boolean }[]
  feature?: string
  adminOnly?: boolean
}
type NavItem = NavLink | NavGroup

// GOLD-only: full ordering system, CRM, marketing, POS

const navigation: NavItem[] = [
  { type: 'link', name: 'Dashboard', href: '/dashboard', icon: Home },
  {
    type: 'group',
    id: 'setup-config',
    name: 'Setup & Config',
    icon: Store,
    children: [
      { name: 'Setup Wizard', href: '/setup', icon: Sparkles },
      { name: 'Team Management', href: '/team', icon: Users, adminOnly: true },
      { name: 'POS Integration', href: '/pos-integration', icon: Settings, feature: 'pos_integration' },
      { name: 'Manage Offer and Coupons', href: '/coupons', icon: Tag, feature: 'coupons' },
      { name: 'Manage QR Code', href: '/qr-codes', icon: QrCode },
      { name: 'Home Features', href: '/home-features', icon: Grid3x3 },
      { name: 'Order settings', href: '/frontend-ordering', icon: Package, feature: 'order_settings' },
      { name: 'Logistics Hub', href: '/logistics-hub', icon: Truck, feature: 'ordering' },
      { name: 'AI Menu Background', href: '/ai-menu-theme-background', icon: Sparkles },
      { name: 'Gallery Management', href: '/gallery-management', icon: Star },
    ],
  },
  { type: 'link', name: 'Customer pay & Usage', href: '/billing', icon: CreditCard, feature: 'customer_pay_and_usage' },
  {
    type: 'group',
    id: 'manage-orders',
    name: 'Manage Orders',
    icon: ShoppingCart,
    feature: 'ordering',
    children: [
      { name: 'Real Time Orders', href: '/orders', icon: ShoppingCart, badgeHref: '/orders', feature: 'ordering' },
      { name: 'Accept Orders', href: '/accept-orders', icon: CheckCircle2, badgeHref: '/accept-orders', feature: 'ordering' },
      { name: 'Past and Billed Orders', href: '/past-orders', icon: Clock, feature: 'ordering' },
    ],
  },
  { type: 'link', name: 'WhatsApp Orders', href: '/whatsapp-orders', icon: MessageSquare, badgeHref: '/whatsapp-orders', feature: 'whatsapp_orders' },
  { type: 'link', name: 'Table Bookings', href: '/bookings', icon: Calendar, feature: 'table_booking' },
  { type: 'link', name: 'Events', href: '/events', icon: PartyPopper, feature: 'events' },
  { type: 'link', name: 'Customers', href: '/customers', icon: Users, feature: 'customer' },
  {
    type: 'group',
    id: 'loyalty-growth',
    name: 'Loyalty & Growth',
    icon: Wallet,
    feature: 'loyalty',
    children: [
      { name: 'Loyalty Settings', href: '/loyalty-settings', icon: Settings, feature: 'loyalty' },
      { name: 'Customer Insights', href: '/loyalty-insights', icon: Users, feature: 'loyalty_insights' },
    ],
  },
  {
    type: 'group',
    id: 'manage-product',
    name: 'Manage Product',
    icon: Package,
    children: [
      { name: 'Menu Management', href: '/menu', icon: Package },
      { name: 'AI Image Gallery', href: '/ai-enhancements', icon: Sparkles },
      { name: 'Recommendations Engine', href: '/recommendations-engine', icon: FolderTree, feature: 'ai_recommendations' },
    ],

  },
  {
    type: 'group',
    id: 'marketing-studio',
    name: 'Marketing Studio',
    icon: Megaphone,
    feature: 'marketing_studio',
    children: [
      { name: 'Overview', href: '/marketing', icon: BarChart3, feature: 'marketing_studio' },
      { name: 'Campaigns', href: '/marketing/campaigns', icon: Send, feature: 'marketing_studio' },
      { name: 'Automation', href: '/marketing/automation', icon: Zap, feature: 'marketing_studio' },
      { name: 'Segments', href: '/marketing/segments', icon: Users, feature: 'marketing_studio' },
      { name: 'Analytics', href: '/marketing/analytics', icon: TrendingUp, feature: 'marketing_studio' },
    ],
  },
  {
    type: 'group',
    id: 'google-growth',
    name: 'Google Growth',
    icon: Globe,
    feature: 'google_growth',
    children: [
      { name: 'Discovery Loop', href: '/google-growth', icon: Sparkles, feature: 'google_growth' },
      { name: 'Menu & Product Sync', href: '/google-growth/sync', icon: Package, feature: 'google_growth_sync' },
      { name: 'Reviews & AI Reply', href: '/google-growth/reviews', icon: Star, feature: 'google_growth_ai' },
    ],
  },
  // Admin-only link - will be filtered by admin check in render
  { type: 'link', name: 'Restaurant Management', href: '/admin/restaurants', icon: Shield, adminOnly: true },
]

export default function Layout({ children }: LayoutProps) {
  const { currentUser } = useFrappeAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const { theme, toggleTheme } = useTheme()
  const { selectedRestaurant, setSelectedRestaurant, restaurants, isGold, isSilver, planType, coinsBalance, billingStatus, isActive, refreshConfig, billingInfo, isAdmin: isRestaurantAdmin } = useRestaurant()
  const { formatAmountNoDecimals } = useCurrency()
  const [sidebarOpen, setSidebarOpen] = useState(false) // Mobile sidebar
  const [sidebarExpanded, setSidebarExpanded] = useState(true) // Desktop sidebar expanded/collapsed
  const [sidebarHovered, setSidebarHovered] = useState(false) // Hover state for temporary expansion
  const [hoverDisabled, setHoverDisabled] = useState(false) // Temporarily disable hover after toggle
  const [selectOpen, setSelectOpen] = useState(false) // Track if restaurant select is open
  const [lockAnimating, setLockAnimating] = useState(false) // Track lock animation state
  const [isLinkModalOpen, setIsLinkModalOpen] = useState(false)
  const [linkToCopy, setLinkToCopy] = useState('')

  // Wallet Balance in top bar
  const [showTopBarRecharge, setShowTopBarRecharge] = useState(false)

  // Admin access state - system admin (Administrator) for Restaurant Management nav
  const [isSystemAdmin, setIsSystemAdmin] = useState(false)
  // Combined isAdmin: true if system admin OR Restaurant Admin via plan context
  const isAdmin = isSystemAdmin || isRestaurantAdmin

  // Sync balance when updated from other components (like Recharge Modal)
  useEffect(() => {
    const handleBalanceUpdate = (e: any) => {
      if (e.detail?.refresh) {
        // Immediate refresh when explicitly requested via event
        refreshConfig()
      }
    }
    window.addEventListener('coins-updated', handleBalanceUpdate)
    return () => window.removeEventListener('coins-updated', handleBalanceUpdate)
  }, [selectedRestaurant, refreshConfig])

  // Expanded nav groups (persisted in localStorage)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => {
    if (typeof window === 'undefined') return new Set()
    try {
      const saved = localStorage.getItem(SIDEBAR_GROUPS_KEY)
      return new Set(saved ? JSON.parse(saved) : [])
    } catch {
      return new Set()
    }
  })
  const toggleGroup = (groupId: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(groupId)) next.delete(groupId)
      else next.add(groupId)
      try {
        localStorage.setItem(SIDEBAR_GROUPS_KEY, JSON.stringify([...next]))
      } catch { }
      return next
    })
  }

  // Auto-expand group when current path is under one of its children; persist so it stays open after refresh
  useEffect(() => {
    const path = location.pathname
    navigation.forEach((item) => {
      if (item.type === 'group') {
        const hasActiveChild = item.children.some(
          (c) => path === c.href || (c.href !== '/dashboard' && path.startsWith(c.href))
        )
        if (hasActiveChild) {
          setExpandedGroups((prev) => {
            if (prev.has(item.id)) return prev
            const next = new Set(prev).add(item.id)
            try {
              localStorage.setItem(SIDEBAR_GROUPS_KEY, JSON.stringify([...next]))
            } catch { }
            return next
          })
        }
      }
    })
  }, [location.pathname])

  // Helper to determine feature locking and required plan
  const getFeatureStatus = (feature?: string) => {
    return getFeatureAccessStatus(planType, feature)
  }

  const handleLockedClick = (e: React.MouseEvent, name: string, status: { isLocked: boolean; requiredTier: string | null }) => {
    if (status.isLocked) {
      e.preventDefault()
      e.stopPropagation()
      toast.error(`${name} requires ${status.requiredTier} plan`, {
        description: `Upgrade to ${status.requiredTier} to unlock this feature`
      })
      return true
    }
    return false
  }

  const [showRestaurantSearch, setShowRestaurantSearch] = useState(false)
  const [restaurantSearchQuery, setRestaurantSearchQuery] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newRestaurantData, setNewRestaurantData] = useState({
    restaurant_name: '',
    owner_email: '',
    owner_phone: '',
    referral_code: ''
  })
  const [isCreating, setIsCreating] = useState(false)
  const [sendOnboarding, setSendOnboarding] = useState(false)
  const [sendPaymentInfo, setSendPaymentInfo] = useState(false)
  const [paymentTier, setPaymentTier] = useState<'SILVER' | 'GOLD'>('SILVER')

  // API calls
  const { call: createRestaurant } = useFrappePostCall('frappe.client.insert')
  const { call: onboardOwner } = useFrappePostCall<{ success: boolean; message?: string; data?: { email_sent: boolean; onboard_link?: string } }>('dinematters.dinematters.api.admin.admin_onboard_restaurant_owner')
  const { call: createPaymentLink } = useFrappePostCall<{ success: boolean; payment_link_url?: string; amount?: number; owner_phone?: string; error?: string }>('dinematters.dinematters.api.admin.admin_create_wallet_payment_link')


  useEffect(() => {
    // Wait for currentUser to be loaded
    if (!currentUser) return;

    // Check for Administrator or DineMatters Supervisor role
    const userRoles = (window as any)?.frappe?.boot?.user_roles || []
    const isSupervisor = userRoles.includes('DineMatters Supervisor')

    if (currentUser === 'Administrator' || isSupervisor) {
      setIsSystemAdmin(true)
    } else {
      setIsSystemAdmin(false)
    }
  }, [currentUser])

  // Handle restaurant change
  const handleRestaurantChange = (restaurantId: string) => {
    if (restaurantId === '__create_new__') {
      // Open create restaurant modal
      setShowCreateModal(true)
      setNewRestaurantData({
        restaurant_name: '',
        owner_email: '',
        owner_phone: '',
        referral_code: ''
      })
      return
    }

    if (restaurantId === '__search__') {
      setShowRestaurantSearch(true)
      setRestaurantSearchQuery('')
      return
    }

    setSelectedRestaurant(restaurantId)
    // Dispatch custom event to notify other components
    window.dispatchEvent(new CustomEvent('restaurant-selected'))
  }

  // Handle create restaurant submission
  const handleCreateRestaurant = async () => {
    if (!newRestaurantData.restaurant_name.trim()) {
      toast.error('Restaurant name is required')
      return
    }
    if (!newRestaurantData.owner_email.trim()) {
      toast.error('Owner email is required')
      return
    }

    setIsCreating(true)
    try {
      // Create restaurant document (no tables field)
      const result = await createRestaurant({
        doc: {
          doctype: 'Restaurant',
          restaurant_name: newRestaurantData.restaurant_name.trim(),
          owner_email: newRestaurantData.owner_email.trim(),
          owner_phone: newRestaurantData.owner_phone.trim() || undefined,
          referred_by_restaurant_code: newRestaurantData.referral_code.trim() || undefined,
          is_active: 1
        }
      })

      if (result?.message) {
        const createdRestaurant = result.message
        const restaurantName = createdRestaurant.restaurant_name || createdRestaurant.name
        const restaurantDocName = createdRestaurant.name || createdRestaurant.restaurant_id
        const restaurantId = createdRestaurant.restaurant_id || restaurantDocName

        toast.success('Restaurant created successfully!')

        // ── Post-creation: Send Onboarding Details ──────────────────────
        if (sendOnboarding && newRestaurantData.owner_email.trim()) {
          try {
            const onboardRes = await onboardOwner({
              restaurant_id: restaurantId,
              owner_name: '',
              owner_email: newRestaurantData.owner_email.trim()
            }) as any
            if (onboardRes?.message?.success) {
              const emailSent = onboardRes.message.data?.email_sent
              if (emailSent) {
                toast.success('Onboarding email sent!', {
                  description: `Password setup link dispatched to ${newRestaurantData.owner_email}`
                })
              } else {
                toast.warning('Onboarding link generated', {
                  description: 'Email delivery failed. Copy the link from the restaurant details page.'
                })
              }
            }
          } catch (err) {
            console.error('Onboarding error:', err)
            toast.error('Could not send onboarding email', {
              description: 'Restaurant was created. Retry from Restaurant Details page.'
            })
          }
        }

        // ── Post-creation: Send Payment Info via WhatsApp ───────────────
        if (sendPaymentInfo && paymentTier !== 'SILVER') {
          try {
            const plinkRes = await createPaymentLink({
              restaurant_id: restaurantId,
              tier: paymentTier
            }) as any

            if (plinkRes?.message?.success) {
              const { payment_link_url, amount, owner_phone, whatsapp_sent, whatsapp_error } = plinkRes.message
              const phone = normalizePhone(owner_phone || newRestaurantData.owner_phone || '')

              const waText = encodeURIComponent(
                `Hi! 👋 Welcome to DineMatters.\n\n` +
                `To activate your *${paymentTier}* plan, please complete your wallet top-up of *₹${amount.toLocaleString()}* (Incl. 18% GST) using the secure payment link below:\n\n` +
                `💳 ${payment_link_url}\n\n` +
                `Once paid, your wallet will be automatically credited and you're good to go! 🚀`
              )

              if (whatsapp_sent) {
                toast.success(`WhatsApp sent!`, {
                  description: `Payment link for ₹${amount.toLocaleString()} sent automatically via Evolution API.`
                })
              } else if (phone) {
                // Fallback to manual wa.me if auto-send failed or wasn't attempted
                window.open(`https://wa.me/${phone}?text=${waText}`, '_blank', 'noopener,noreferrer')
                toast.success(`WhatsApp opened!`, {
                  description: whatsapp_error
                    ? `Auto-send failed (${whatsapp_error}). Manual link ready.`
                    : `Payment link for ₹${amount.toLocaleString()} (${paymentTier}) ready to send.`
                })
              } else {
                // No phone — show link modal as fallback
                setLinkToCopy(payment_link_url || '')
                setIsLinkModalOpen(true)
              }
            } else {
              toast.error('Could not create payment link', {
                description: plinkRes?.message?.error || 'Please create it from the restaurant details page.'
              })
            }
          } catch (err) {
            console.error('Payment link error:', err)
            toast.error('Payment link creation failed')
          }
        }

        // ── Close & Navigate ────────────────────────────────────────────
        setShowCreateModal(false)
        setNewRestaurantData({ restaurant_name: '', owner_email: '', owner_phone: '', referral_code: '' })
        setSendOnboarding(false)
        setSendPaymentInfo(false)
        setPaymentTier('SILVER')

        setSelectedRestaurant(restaurantDocName)
        window.dispatchEvent(new CustomEvent('restaurant-selected'))

        const urlFriendlyName = restaurantName.toLowerCase().replace(/\s+/g, '-')
        setTimeout(() => {
          navigate(`/setup/${encodeURIComponent(urlFriendlyName)}`, { replace: true })
        }, 100)
      } else {
        throw new Error('Failed to create restaurant')
      }
    } catch (error: any) {
      console.error('Error creating restaurant:', error)
      toast.error('Failed to create restaurant', {
        description: error?.message || 'An error occurred while creating the restaurant'
      })
    } finally {
      setIsCreating(false)
    }
  }

  // Get current restaurant details (from list) and fetch the selected restaurant doc directly
  const currentRestaurant = restaurants.find(r => r.name === selectedRestaurant || r.restaurant_id === selectedRestaurant)

  // Fetch restaurant document to get slug and authoritative restaurant_name
  const { data: restaurantDoc } = useFrappeGetDoc('Restaurant', selectedRestaurant || '', {
    enabled: !!selectedRestaurant
  })

  // Preview URL path: slug preferred, fallback to restaurant_id for all pages
  const previewPath = restaurantDoc?.slug || restaurantDoc?.restaurant_id || currentRestaurant?.restaurant_id || selectedRestaurant || ''

  // Fetch orders for analytics - filter by selected restaurant and TODAY ONLY for performance
  const todayStart = useMemo(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    // Format for Frappe: YYYY-MM-DD HH:mm:ss
    return d.toISOString().split('T')[0] + ' 00:00:00'
  }, [])

  const { data: orders } = useFrappeGetDocList('Order', {
    fields: ['name', 'status', 'total', 'creation', 'restaurant', 'is_tokenization', 'is_whatsapp_order', 'payment_method'],
    filters: selectedRestaurant ? {
      restaurant: selectedRestaurant,
      "is_tokenization": ["!=", 1],
      "creation": [">=", todayStart]
    } as any : undefined,
    limit: 500, // Increased limit for today's orders but restricted by time
    orderBy: { field: 'creation', order: 'desc' }
  }, selectedRestaurant ? `orders-badges-${selectedRestaurant}` : null)

  // Calculate analytics metrics
  const analytics = useMemo(() => {
    if (!orders || orders.length === 0) {
      return {
        todayRevenue: 0,
        todayOrders: 0,
        pendingOrders: 0,
        totalRevenue: 0,
        totalOrders: 0,
        avgOrderValue: 0,
        yesterdayRevenue: 0,
        yesterdayOrders: 0,
        revenueChange: 0,
        ordersChange: 0,
      }
    }

    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)

    // Today's metrics
    const todayOrders = orders.filter((order: any) => {
      const orderDate = new Date(order.creation)
      return orderDate >= today
    })
    const todayRevenue = todayOrders.reduce((sum: number, order: any) => sum + (order.total || 0), 0)
    const todayOrdersCount = todayOrders.length

    // Yesterday's metrics
    const yesterdayOrders = orders.filter((order: any) => {
      const orderDate = new Date(order.creation)
      return orderDate >= yesterday && orderDate < today
    })
    const yesterdayRevenue = yesterdayOrders.reduce((sum: number, order: any) => sum + (order.total || 0), 0)
    const yesterdayOrdersCount = yesterdayOrders.length

    // Overall metrics
    const totalRevenue = orders.reduce((sum: number, order: any) => sum + (order.total || 0), 0)
    const totalOrders = orders.length
    const avgOrderValue = totalOrders > 0 ? totalRevenue / totalOrders : 0
    const pendingOrders = orders.filter((order: any) => {
      // Match Real Time Orders behaviour: count only today's orders
      if (!order?.creation) return false
      const createdAt = new Date(order.creation)
      if (Number.isNaN(createdAt.getTime())) return false
      if (createdAt < today) return false

      const raw = String(order.status || '')
      const s = raw.trim().toLowerCase()
      return (
        s === 'auto accepted' ||
        s === 'accepted' ||
        s === 'confirmed' ||
        s === 'preparing' ||
        s === 'ready' ||
        s === 'in billing'
      )
    }).length

    // Calculate changes
    const revenueChange = yesterdayRevenue > 0
      ? ((todayRevenue - yesterdayRevenue) / yesterdayRevenue) * 100
      : (todayRevenue > 0 ? 100 : 0)
    const ordersChange = yesterdayOrdersCount > 0
      ? ((todayOrdersCount - yesterdayOrdersCount) / yesterdayOrdersCount) * 100
      : (todayOrdersCount > 0 ? 100 : 0)

    return {
      todayRevenue,
      todayOrders: todayOrdersCount,
      pendingOrders,
      totalRevenue,
      totalOrders,
      avgOrderValue,
      yesterdayRevenue,
      yesterdayOrders: yesterdayOrdersCount,
      revenueChange,
      ordersChange,
    }
  }, [orders])

  // Get pending orders count for badge
  const pendingOrders = analytics.pendingOrders
  const acceptPendingOrders = useMemo(() => {
    if (!orders || orders.length === 0) return 0

    const today = new Date()
    today.setHours(0, 0, 0, 0)

    return orders.filter((order: any) => {
      if (!order?.creation) return false
      const createdAt = new Date(order.creation)
      if (Number.isNaN(createdAt.getTime()) || createdAt < today) return false

      const status = String(order.status || '').trim().toLowerCase()
      const paymentMethod = String(order.payment_method || '').trim().toLowerCase()

      return status === 'pending_verification' && paymentMethod === 'pay_at_counter'
    }).length
  }, [orders])

  const whatsappPendingOrders = useMemo(() => {
    if (!orders || orders.length === 0) return 0

    const today = new Date()
    today.setHours(0, 0, 0, 0)

    return orders.filter((order: any) => {
      if (!order?.creation) return false
      const createdAt = new Date(order.creation)
      if (Number.isNaN(createdAt.getTime()) || createdAt < today) return false

      const status = String(order.status || '').trim().toLowerCase()
      const isWhatsApp = Boolean(order.is_whatsapp_order)

      // Only count 'pending_verification' (Awaiting Msg) as actionable badge alerts
      return status === 'pending_verification' && isWhatsApp
    }).length
  }, [orders])

  // Determine if sidebar should show expanded content (either expanded state or hovered, but not if hover is disabled)
  const showExpanded = sidebarExpanded || (sidebarHovered && !hoverDisabled)

  // Handle toggle button click
  const handleToggle = () => {
    // Trigger animation
    setLockAnimating(true)
    setTimeout(() => {
      setLockAnimating(false)
    }, 300)

    setSidebarExpanded(!sidebarExpanded)
    // Disable hover temporarily to prevent immediate re-expansion
    setHoverDisabled(true)
    setSidebarHovered(false)
    // Re-enable hover after a short delay
    setTimeout(() => {
      setHoverDisabled(false)
    }, 300)
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Sidebar - Toggleable with Hover */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 bg-sidebar border-r border-sidebar-border transform transition-all duration-200 ease-in-out shadow-sm",
          // Mobile: slide in/out
          sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
          // Desktop: width based on expanded state or hover
          showExpanded ? "lg:w-64" : "lg:w-16"
        )}
        onMouseEnter={() => !sidebarExpanded && !hoverDisabled && setSidebarHovered(true)}
        onMouseLeave={(e) => {
          // Don't collapse if select dropdown is open or if mouse is moving to dropdown
          const relatedTarget = e.relatedTarget as HTMLElement
          if (!selectOpen && relatedTarget && typeof relatedTarget.closest === 'function' && !relatedTarget.closest('[role="listbox"]')) {
            setSidebarHovered(false)
          }
        }}
      >
        <div className="flex flex-col h-full">
          {/* Logo with Toggle Button - Unified with Top Navbar */}
          <div className={cn(
            "flex items-center bg-card border-r border-sidebar-border transition-all",
            showExpanded ? "px-4 justify-between py-2.5 h-[3.5rem]" : "px-2 justify-center h-[3.5rem]"
          )}>
            {showExpanded ? (
              <>
                <div className="flex-1 flex flex-col gap-0.5 min-w-0 max-w-full">
                  {/* Restaurant Dropdown */}
                  {restaurants.length > 0 ? (
                    <Select
                      value={selectedRestaurant || restaurants[0]?.name || ''}
                      onValueChange={handleRestaurantChange}
                      onOpenChange={(open) => {
                        setSelectOpen(open)
                        // Keep sidebar expanded while dropdown is open
                        if (open && !sidebarExpanded) {
                          setSidebarHovered(true)
                        }
                      }}
                    >
                      <SelectTrigger className="h-auto py-1.5 px-2 border-0 bg-transparent hover:bg-sidebar-accent shadow-none focus:ring-0 focus:ring-offset-0 w-full data-[state=open]:bg-sidebar-accent">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="text-sm font-semibold text-sidebar-foreground truncate whitespace-nowrap overflow-hidden max-w-[100px]">
                            {restaurantDoc?.restaurant_name || currentRestaurant?.restaurant_name || restaurants[0]?.restaurant_name || 'Select Restaurant'}
                          </span>
                          {isGold ? (
                            <span className="inline-flex items-center gap-0.5 px-2 py-0.5 text-[10px] font-black rounded-full flex-shrink-0 border"
                              style={{
                                background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 40%, #B45309 100%)',
                                borderColor: '#FCD34D',
                                color: '#FFF8E7',
                                boxShadow: '0 0 0 1px rgba(253,211,77,0.3), 0 2px 6px rgba(180,83,9,0.4)',
                                letterSpacing: '0.05em'
                              }}
                            >
                              <Crown className="h-2.5 w-2.5" style={{ color: '#FEF3C7', fill: '#FEF3C7', opacity: 0.9 }} />
                              GOLD
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-1.5 py-0.5 text-[9px] font-bold bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400 rounded-full flex-shrink-0 border border-slate-200 dark:border-slate-700">
                              SILVER
                            </span>
                          )}
                        </div>
                      </SelectTrigger>
                      <SelectContent
                        className="min-w-[220px] max-h-[450px] z-[60]"
                        onCloseAutoFocus={() => {
                          // When dropdown closes, allow sidebar to collapse if needed
                          setSelectOpen(false)
                        }}
                      >
                        {isAdmin && (
                          <>
                            <SelectItem value="__create_new__" className="text-primary font-bold focus:bg-primary/5 focus:text-primary mb-1">
                              <div className="flex items-center gap-2 w-full py-0">
                                <Plus className="h-4 w-4 text-primary flex-shrink-0" />
                                <span className="text-sm">New Restaurant</span>
                              </div>
                            </SelectItem>
                            <div className="border-t border-border/50 mx-1 mb-1" />
                          </>
                        )}

                        <SelectItem value="__search__" className="text-muted-foreground italic focus:bg-muted/5 transition-colors">
                          <div className="flex items-center gap-2 w-full py-0">
                            <Search className="h-4 w-4 flex-shrink-0" />
                            <span className="text-sm">Search / View All</span>
                          </div>
                        </SelectItem>

                        <div className="border-t border-border/40 my-1" />

                        <div className="max-h-[300px] overflow-y-auto custom-scrollbar">
                          {restaurants.map((restaurant) => (
                            <SelectItem key={restaurant.name} value={restaurant.name} className="py-1.5 focus:bg-sidebar-accent">
                              <div className="flex items-center gap-2 w-full">
                                <Store className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                                <div className="flex flex-col min-w-0 flex-1">
                                  <span className="text-sm font-medium text-foreground truncate">{restaurant.restaurant_name}</span>
                                  {!restaurant.is_active && (
                                    <span className="text-[9px] font-bold text-red-500/60 uppercase">Inactive</span>
                                  )}
                                </div>
                              </div>
                            </SelectItem>
                          ))}
                        </div>
                      </SelectContent>
                    </Select>
                  ) : (
                    <div className="flex items-center gap-2 py-1.5 px-2">
                      <Store className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                      <span className="text-sm text-muted-foreground">No restaurants</span>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {/* Lock/Unlock Button - Desktop Only */}
                  <button
                    onClick={handleToggle}
                    className={cn(
                      "hidden lg:flex items-center justify-center p-1.5 rounded-md transition-all duration-300",
                      "hover:bg-sidebar-accent active:scale-90",
                      "relative overflow-visible",
                      sidebarExpanded
                        ? "text-primary hover:text-primary/80"
                        : "text-muted-foreground hover:text-sidebar-foreground"
                    )}
                    title={sidebarExpanded ? "Unlock sidebar (allow auto-collapse)" : "Lock sidebar (keep expanded)"}
                  >
                    <div className={cn(
                      "relative transition-all duration-300",
                      lockAnimating && "lock-toggle-animate"
                    )}>
                      {sidebarExpanded ? (
                        <Lock className="h-4 w-4 transition-all duration-300" />
                      ) : (
                        <LockOpen className="h-4 w-4 transition-all duration-300" />
                      )}
                    </div>
                  </button>
                  {/* Close Button - Mobile Only */}
                  <button
                    onClick={() => setSidebarOpen(false)}
                    className="lg:hidden p-2.5 -mr-1 rounded-md hover:bg-sidebar-accent transition-colors active:scale-95"
                    aria-label="Close menu"
                  >
                    <X className="h-5 w-5 text-muted-foreground" />
                  </button>
                </div>
              </>
            ) : (
              <>
                <Link to="/dashboard" className="flex items-center justify-center hover:opacity-80 transition-opacity flex-1">
                  <Store className="h-5 w-5 text-primary" />
                </Link>
                {/* Lock/Unlock Button when collapsed - Desktop Only */}
                <button
                  onClick={handleToggle}
                  className={cn(
                    "hidden lg:flex items-center justify-center p-1.5 rounded transition-all duration-300",
                    "hover:bg-sidebar-accent active:scale-90",
                    "relative overflow-visible",
                    sidebarExpanded
                      ? "text-primary hover:text-primary/80"
                      : "text-muted-foreground hover:text-sidebar-foreground"
                  )}
                  title={sidebarExpanded ? "Unlock sidebar" : "Lock sidebar"}
                >
                  <div className={cn(
                    "relative transition-all duration-300",
                    lockAnimating && "lock-toggle-animate"
                  )}>
                    {sidebarExpanded ? (
                      <Lock className="h-4 w-4 transition-all duration-300" />
                    ) : (
                      <LockOpen className="h-4 w-4 transition-all duration-300" />
                    )}
                  </div>
                </button>
              </>
            )}
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-2 py-2 space-y-0.5 overflow-y-auto">
            {isActive && navigation
              .filter((item) => {
                if (item.adminOnly && !isAdmin) {
                  return false
                }
                // WhatsApp Orders visibility: only GOLD and SILVER
                if (item.feature === 'whatsapp_orders' && !isGold && !isSilver) {
                  return false
                }
                if (item.type === 'group') {
                  const filteredChildren = item.children.filter((child) => !child.adminOnly || isAdmin)
                  return filteredChildren.length > 0
                }
                return true
              })
              .map((item) => {
                if (item.type === 'link') {
                  const Icon = item.icon
                  const isActive = location.pathname === item.href ||
                    (item.href !== '/dashboard' && location.pathname.startsWith(item.href))
                  const badgeCount = item.badgeHref === '/orders'
                    ? pendingOrders
                    : item.badgeHref === '/accept-orders'
                      ? acceptPendingOrders
                      : item.badgeHref === '/whatsapp-orders'
                        ? whatsappPendingOrders
                        : 0
                  const showBadge = badgeCount > 0
                  // Unified locking logic
                  const featureStatus = getFeatureStatus(item.feature)
                  const isLocked = featureStatus.isLocked

                  const LockIcon = (item.feature && GOLD_ONLY_FEATURES.includes(item.feature))
                    ? (
                      <div className="flex items-center gap-0.5 flex-shrink-0">
                        <Lock className="h-3 w-3 text-muted-foreground/60" />
                        <Star className="h-2.5 w-2.5 text-amber-500 fill-amber-500" />
                      </div>
                    )
                    : <Lock className="h-3.5 w-3.5 text-muted-foreground/60 flex-shrink-0" />

                  return (
                    <Link
                      key={item.name}
                      to={item.href}
                      onClick={(e) => {
                        if (handleLockedClick(e, item.name, featureStatus)) return
                        setSidebarOpen(false)
                      }}
                      className={cn(
                        "relative flex items-center rounded-md text-sm font-normal transition-all group",
                        showExpanded ? "gap-3 px-3 py-2" : "justify-center px-2 py-2",
                        "hover:bg-sidebar-accent active:bg-sidebar-accent/80",
                        isActive
                          ? "bg-primary/10 text-primary font-medium dark:bg-primary/20"
                          : "text-sidebar-foreground hover:text-sidebar-foreground",
                        isLocked && "opacity-60"
                      )}
                      title={!showExpanded ? item.name : undefined}
                    >
                      {isActive && (
                        <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary rounded-r" />
                      )}
                      <Icon className={cn(
                        "h-4 w-4 flex-shrink-0",
                        isActive ? "text-primary" : "text-muted-foreground"
                      )} />
                      {showExpanded && (
                        <>
                          <span className="flex-1">{item.name}</span>
                          {isLocked && (
                            LockIcon
                          )}
                          {!isLocked && showBadge && (
                            <span className="h-5 min-w-[20px] px-1.5 rounded-full bg-destructive text-white text-xs flex items-center justify-center font-semibold">
                              {badgeCount > 9 ? '9+' : badgeCount}
                            </span>
                          )}
                        </>
                      )}
                      {!showExpanded && (
                        <span className="absolute left-full ml-2 px-2 py-1 rounded-md bg-foreground text-background text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none z-50 shadow-lg">
                          {item.name}
                          {isLocked && ' 🔒'}
                          {showBadge && ` (${badgeCount} pending)`}
                        </span>
                      )}
                    </Link>
                  )
                }

                // Group (dropdown)
                const group = item
                const Icon = group.icon
                const isExpanded = expandedGroups.has(group.id)
                const filteredChildren = group.children.filter(child => !child.adminOnly || isAdmin)
                const hasActiveChild = filteredChildren.some(
                  (c) => location.pathname === c.href || (c.href !== '/dashboard' && location.pathname.startsWith(c.href))
                )
                const groupBadgeCount = filteredChildren.reduce((sum, child) => {
                  if (child.badgeHref === '/orders') return sum + pendingOrders
                  if (child.badgeHref === '/accept-orders') return sum + acceptPendingOrders
                  if (child.badgeHref === '/whatsapp-orders') return sum + whatsappPendingOrders
                  return sum
                }, 0)
                const showBadge = groupBadgeCount > 0

                // Group locking logic
                const groupStatus = getFeatureStatus(group.feature)
                const isGroupLocked = groupStatus.isLocked

                // Check if all children are also locked (to mark parent as fully locked)
                const allChildrenLocked = filteredChildren.length > 0 && filteredChildren.every(child => getFeatureStatus(child.feature).isLocked)
                const isGroupFullyLocked = isGroupLocked || allChildrenLocked

                const GroupLockIcon = (group.feature && GOLD_ONLY_FEATURES.includes(group.feature))
                  ? (
                    <div className="flex items-center gap-0.5 flex-shrink-0">
                      <Lock className="h-3 w-3 text-muted-foreground/60" />
                      <Star className="h-2.5 w-2.5 text-amber-500 fill-amber-500" />
                    </div>
                  )
                  : <Lock className="h-3.5 w-3.5 text-muted-foreground/60 flex-shrink-0" />

                // Collapsed sidebar: show dropdown menu with child links
                if (!showExpanded) {
                  return (
                    <DropdownMenu key={group.id}>
                      <DropdownMenuTrigger asChild>
                        <button
                          type="button"
                          className={cn(
                            "relative flex items-center justify-center w-full rounded-md p-2 transition-all",
                            "hover:bg-sidebar-accent",
                            hasActiveChild ? "text-primary" : "text-muted-foreground hover:text-sidebar-foreground",
                            isGroupFullyLocked && "opacity-60"
                          )}
                          title={`${group.name}${isGroupFullyLocked ? ' (Locked)' : ''}`}
                        >
                          <Icon className="h-4 w-4" />
                          {isGroupFullyLocked && (
                            <div className="absolute -top-0.5 -right-0.5">
                              <Lock className="h-2.5 w-2.5 text-muted-foreground/80" />
                            </div>
                          )}
                          {!isGroupFullyLocked && showBadge && (
                            <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-destructive" />
                          )}
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent side="right" align="start" className="min-w-[180px]" sideOffset={8}>
                        {group.children
                          .filter(child => !child.adminOnly || isAdmin)
                          .map((child) => {
                            const ChildIcon = child.icon || group.icon
                            const isChildActive = location.pathname === child.href || (child.href !== '/' && child.href !== '/google-growth' && location.pathname.startsWith(child.href + '/'))

                            // Unified child locking logic
                            const childStatus = getFeatureStatus(child.feature)
                            const isChildLocked = childStatus.isLocked

                            const ChildLockIcon = (child.feature && GOLD_ONLY_FEATURES.includes(child.feature))
                              ? <Star className="h-3 w-3 text-amber-500 flex-shrink-0 ml-auto" />
                              : <Lock className="h-3 w-3 text-muted-foreground/60 flex-shrink-0 ml-auto" />
                            return (
                              <DropdownMenuItem key={child.href} asChild>
                                <Link
                                  to={child.href}
                                  onClick={(e) => {
                                    if (handleLockedClick(e, child.name, childStatus)) return
                                    setSidebarOpen(false)
                                  }}
                                  className={cn("flex items-center gap-2 cursor-pointer", isChildActive && "bg-primary/10 text-primary", isChildLocked && "opacity-60")}
                                >
                                  <ChildIcon className="h-4 w-4" />
                                  {child.name}
                                  {isChildLocked && ChildLockIcon}
                                  {!isChildLocked && child.badgeHref === '/orders' && pendingOrders > 0 && (
                                    <span className="ml-auto bg-destructive text-white text-xs px-1.5 rounded-full">
                                      {pendingOrders > 9 ? '9+' : pendingOrders}
                                    </span>
                                  )}
                                  {!isChildLocked && child.badgeHref === '/accept-orders' && acceptPendingOrders > 0 && (
                                    <span className="ml-auto bg-destructive text-white text-xs px-1.5 rounded-full">
                                      {acceptPendingOrders > 9 ? '9+' : acceptPendingOrders}
                                    </span>
                                  )}
                                  {!isChildLocked && child.badgeHref === '/whatsapp-orders' && whatsappPendingOrders > 0 && (
                                    <span className="ml-auto bg-destructive text-white text-xs px-1.5 rounded-full">
                                      {whatsappPendingOrders > 9 ? '9+' : whatsappPendingOrders}
                                    </span>
                                  )}
                                </Link>
                              </DropdownMenuItem>
                            )
                          })}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )
                }

                return (
                  <div key={group.id} className="space-y-0.5">
                    <button
                      type="button"
                      onClick={() => toggleGroup(group.id)}
                      className={cn(
                        "relative flex items-center rounded-md text-sm font-normal transition-all group w-full",
                        showExpanded ? "gap-3 px-3 py-2" : "justify-center px-2 py-2",
                        "hover:bg-sidebar-accent active:bg-sidebar-accent/80",
                        (hasActiveChild || isExpanded)
                          ? "text-sidebar-foreground hover:text-sidebar-foreground"
                          : "text-sidebar-foreground hover:text-sidebar-foreground",
                        isGroupFullyLocked && "opacity-60"
                      )}
                      title={!showExpanded ? group.name : undefined}
                    >
                      {hasActiveChild && !isExpanded && (
                        <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary rounded-r" />
                      )}
                      <Icon className={cn(
                        "h-4 w-4 flex-shrink-0",
                        hasActiveChild ? "text-primary" : "text-muted-foreground"
                      )} />
                      {showExpanded && (
                        <>
                          <span className="flex-1 text-left">{group.name}</span>
                          {isGroupFullyLocked && (
                            GroupLockIcon
                          )}
                          {!isGroupLocked && showBadge && (
                            <span className="h-5 min-w-[20px] px-1.5 rounded-full bg-destructive text-white text-xs flex items-center justify-center font-semibold">
                              {groupBadgeCount > 9 ? '9+' : groupBadgeCount}
                            </span>
                          )}
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                          ) : (
                            <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                          )}
                        </>
                      )}
                      {!showExpanded && (
                        <span className="absolute left-full ml-2 px-2 py-1 rounded-md bg-foreground text-background text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none z-50 shadow-lg">
                          {group.name}
                          {isGroupFullyLocked && ' 🔒'}
                          {showBadge && ` (${groupBadgeCount} pending)`}
                        </span>
                      )}
                    </button>
                    {showExpanded && isExpanded && (
                      <div className="ml-4 pl-2 border-l border-sidebar-border space-y-0.5">
                        {group.children
                          .filter(child => !child.adminOnly || isAdmin)
                          .map((child) => {
                            const ChildIcon = child.icon || group.icon
                            const isChildActive = location.pathname === child.href ||
                              (child.href !== '/' && child.href !== '/dashboard' && child.href !== '/marketing' && child.href !== '/google-growth' && location.pathname.startsWith(child.href + '/'))
                            const childBadgeCount = child.badgeHref === '/orders'
                              ? pendingOrders
                              : child.badgeHref === '/accept-orders'
                                ? acceptPendingOrders
                                : child.badgeHref === '/whatsapp-orders'
                                  ? whatsappPendingOrders
                                  : 0
                            const showChildBadge = childBadgeCount > 0

                            // Unified child locking logic (Expanded View)
                            const childStatus = getFeatureStatus(child.feature)
                            const isChildLocked = childStatus.isLocked

                            const ChildLockIcon = (child.feature && GOLD_ONLY_FEATURES.includes(child.feature))
                              ? (
                                <div className="flex items-center gap-0.5 flex-shrink-0">
                                  <Lock className="h-3 w-3 text-muted-foreground/60" />
                                  <Star className="h-2.5 w-2.5 text-amber-500 fill-amber-500" />
                                </div>
                              )
                              : <Lock className="h-3.5 w-3.5 text-muted-foreground/60 flex-shrink-0" />
                            return (
                              <Link
                                key={child.href}
                                to={child.href}
                                onClick={(e) => {
                                  if (handleLockedClick(e, child.name, childStatus)) return
                                  setSidebarOpen(false)
                                }}
                                className={cn(
                                  "relative flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-all group",
                                  "hover:bg-sidebar-accent",
                                  isChildActive
                                    ? "bg-primary/10 text-primary font-medium dark:bg-primary/20"
                                    : "text-muted-foreground hover:text-sidebar-foreground",
                                  isChildLocked && "opacity-60"
                                )}
                              >
                                <ChildIcon className="h-4 w-4 flex-shrink-0" />
                                <span className="flex-1">{child.name}</span>
                                {isChildLocked && ChildLockIcon}
                                {!isChildLocked && showChildBadge && (
                                  <span className="h-5 min-w-[20px] px-1.5 rounded-full bg-destructive text-white text-xs flex items-center justify-center font-semibold">
                                    {childBadgeCount > 9 ? '9+' : childBadgeCount}
                                  </span>
                                )}
                              </Link>
                            )
                          })}
                      </div>
                    )}
                  </div>
                )
              })}
          </nav>

          {/* Footer with Watch Preview, Theme Toggle and Tagline */}
          <div className="px-4 py-3 border-t border-sidebar-border bg-card space-y-2">
            {/* Watch Preview - always visible in sidebar on all pages */}
            {previewPath && (
              <div className={showExpanded ? "flex" : "flex justify-center"}>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    const baseUrl = restaurantDoc?.base_url || 'https://app.dinematters.com/'
                    const url = baseUrl.replace(/\/$/, '') + '/' + previewPath
                    window.open(url, '_blank', 'noopener,noreferrer')
                  }}
                  className={cn(
                    "w-full gap-2",
                    !showExpanded && "w-10 px-0 justify-center"
                  )}
                >
                  <Eye className="h-4 w-4 flex-shrink-0" />
                  {showExpanded && (
                    <>
                      Watch preview
                      <ExternalLink className="h-3 w-3 flex-shrink-0" />
                    </>
                  )}
                </Button>
              </div>
            )}
            {showExpanded ? (
              <div className="flex">
                <Button variant="outline" size="sm" onClick={() => navigate('/autopay-setup')} className="w-full gap-2">
                  <CreditCard className="h-3.5 w-3.5" />
                  Billing & Subscription
                </Button>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => navigate('/autopay-setup')} className="w-10 h-10 p-0" title="Billing & Subscription">
                  <CreditCard className="h-4 w-4" />
                </Button>
              </div>
            )}
            {showExpanded ? (
              <div className="flex items-center justify-between gap-3">
                <p className="text-base italic text-red-500 dark:text-red-400 font-light flex-1">
                  By Dinematters
                </p>
                {/* Animated Theme Switch - Expanded */}
                <button
                  onClick={toggleTheme}
                  className={cn(
                    "relative inline-flex h-7 w-12 items-center rounded-full transition-all duration-300 ease-in-out",
                    "focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-card",
                    "hover:scale-105 active:scale-95",
                    theme === 'dark'
                      ? "bg-primary shadow-md shadow-primary/30"
                      : "bg-muted-foreground/30 hover:bg-muted-foreground/40"
                  )}
                  title={theme === 'light' ? "Switch to dark mode" : "Switch to light mode"}
                  role="switch"
                  aria-checked={theme === 'dark'}
                >
                  <span
                    className={cn(
                      "absolute flex items-center justify-center h-5 w-5 transform rounded-full bg-white shadow-md transition-all duration-300 ease-in-out",
                      theme === 'dark' ? "translate-x-6" : "translate-x-1"
                    )}
                  >
                    {theme === 'dark' ? (
                      <Moon className="h-3 w-3 text-primary transition-all duration-300" />
                    ) : (
                      <Sun className="h-3 w-3 text-muted-foreground transition-all duration-300" />
                    )}
                  </span>
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                {previewPath && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const baseUrl = restaurantDoc?.base_url || 'https://app.dinematters.com/'
                      const url = baseUrl.replace(/\/$/, '') + '/' + previewPath
                      window.open(url, '_blank', 'noopener,noreferrer')
                    }}
                    className="w-10 h-10 p-0"
                    title="Watch preview"
                  >
                    <Eye className="h-4 w-4" />
                  </Button>
                )}
                {/* Animated Theme Switch - Collapsed */}
                <button
                  onClick={toggleTheme}
                  className={cn(
                    "relative inline-flex h-7 w-12 items-center rounded-full transition-all duration-300 ease-in-out",
                    "focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-sidebar",
                    "hover:scale-105 active:scale-95",
                    theme === 'dark'
                      ? "bg-primary shadow-md shadow-primary/30"
                      : "bg-muted-foreground/30 hover:bg-muted-foreground/40"
                  )}
                  title={theme === 'light' ? "Switch to dark mode" : "Switch to light mode"}
                  role="switch"
                  aria-checked={theme === 'dark'}
                >
                  <span
                    className={cn(
                      "absolute flex items-center justify-center h-5 w-5 transform rounded-full bg-white shadow-md transition-all duration-300 ease-in-out",
                      theme === 'dark' ? "translate-x-6" : "translate-x-1"
                    )}
                  >
                    {theme === 'dark' ? (
                      <Moon className="h-3 w-3 text-primary transition-all duration-300" />
                    ) : (
                      <Sun className="h-3 w-3 text-muted-foreground transition-all duration-300" />
                    )}
                  </span>
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 lg:hidden backdrop-blur-sm"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main Content */}
      <div className={cn(
        "transition-all duration-200",
        showExpanded ? "lg:pl-64" : "lg:pl-16"
      )}>
        {/* Top Header - Analytics Magic Panel - Unified with Sidebar */}
        <header className="sticky top-0 z-30 bg-card border-b border-border shadow-sm">
          <div className="flex items-center h-[3.5rem]">
            {/* Analytics Panel - Full Width from Start */}
            <div className="hidden lg:flex items-center gap-4 flex-1 pl-6 pr-6 flex-nowrap overflow-x-auto h-full">
              {/* Today's Revenue */}
              <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md hover:bg-muted transition-colors group whitespace-nowrap">
                <DollarSign className="h-3.5 w-3.5 text-primary flex-shrink-0" />
                <span className="text-xs text-muted-foreground">Today:</span>
                <span className="text-sm font-semibold text-foreground">
                  {formatAmountNoDecimals(analytics.todayRevenue)}
                </span>
                {analytics.revenueChange !== 0 && (
                  <div className={cn(
                    "flex items-center gap-0.5 text-[10px] font-semibold px-1.5 py-0.5 rounded-md ml-1",
                    analytics.revenueChange > 0
                      ? "text-[#107c10] bg-[#dff6dd] dark:text-[#81c784] dark:bg-[#1b5e20]"
                      : "text-[#d13438] bg-[#fde7e9] dark:text-white dark:bg-[#b71c1c]"
                  )}>
                    {analytics.revenueChange > 0 ? (
                      <TrendingUp className={cn(
                        "h-2.5 w-2.5",
                        analytics.revenueChange > 0
                          ? "text-[#107c10] dark:text-[#81c784]"
                          : "text-[#d13438] dark:text-white"
                      )} />
                    ) : (
                      <TrendingDown className={cn(
                        "h-2.5 w-2.5",
                        analytics.revenueChange > 0
                          ? "text-[#107c10] dark:text-[#81c784]"
                          : "text-[#d13438] dark:text-white"
                      )} />
                    )}
                    <span className="whitespace-nowrap">{Math.abs(analytics.revenueChange).toFixed(0)}%</span>
                  </div>
                )}
              </div>

              {/* Today's Orders */}
              <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md hover:bg-muted transition-colors group whitespace-nowrap">
                <ShoppingCart className="h-3.5 w-3.5 text-primary flex-shrink-0" />
                <span className="text-xs text-muted-foreground">Orders:</span>
                <span className="text-sm font-semibold text-foreground">
                  {analytics.todayOrders}
                </span>
                {analytics.ordersChange !== 0 && (
                  <div className={cn(
                    "flex items-center gap-0.5 text-[10px] font-semibold px-1.5 py-0.5 rounded-md ml-1",
                    analytics.ordersChange > 0
                      ? "text-[#107c10] bg-[#dff6dd] dark:text-[#81c784] dark:bg-[#1b5e20]"
                      : "text-[#d13438] bg-[#fde7e9] dark:text-white dark:bg-[#b71c1c]"
                  )}>
                    {analytics.ordersChange > 0 ? (
                      <TrendingUp className={cn(
                        "h-2.5 w-2.5",
                        analytics.ordersChange > 0
                          ? "text-[#107c10] dark:text-[#81c784]"
                          : "text-[#d13438] dark:text-white"
                      )} />
                    ) : (
                      <TrendingDown className={cn(
                        "h-2.5 w-2.5",
                        analytics.ordersChange > 0
                          ? "text-[#107c10] dark:text-[#81c784]"
                          : "text-[#d13438] dark:text-white"
                      )} />
                    )}
                    <span className="whitespace-nowrap">{Math.abs(analytics.ordersChange).toFixed(0)}%</span>
                  </div>
                )}
              </div>

              {/* Pending Orders Alert */}
              {analytics.pendingOrders > 0 && (
                <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-[#fff4ce] dark:bg-[#ca5010]/20 border border-[#ffe69d] dark:border-[#ca5010]/40 hover:bg-[#fff4ce]/80 dark:hover:bg-[#ca5010]/30 transition-colors whitespace-nowrap">
                  <AlertCircle className="h-3.5 w-3.5 text-[#ca5010] dark:text-[#ffaa44] flex-shrink-0" />
                  <span className="text-xs text-[#ca5010] dark:text-[#ffaa44] font-medium">Pending:</span>
                  <span className="text-sm font-semibold text-[#ca5010] dark:text-[#ffaa44]">
                    {analytics.pendingOrders}
                  </span>
                </div>
              )}

              {/* Average Order Value */}
              <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md hover:bg-muted transition-colors group whitespace-nowrap">
                <Activity className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                <span className="text-xs text-muted-foreground">Avg:</span>
                <span className="text-sm font-semibold text-foreground">
                  {formatAmountNoDecimals(analytics.avgOrderValue)}
                </span>
              </div>
            </div>
            <div className="lg:hidden flex items-center gap-1 flex-1 min-w-0">
              <button
                onClick={() => setSidebarOpen(true)}
                className="p-2 mr-1 rounded-md hover:bg-muted transition-colors"
                aria-label="Open menu"
              >
                <Menu className="h-5 w-5 text-foreground" />
              </button>

              <div className="flex items-center gap-2 overflow-x-auto no-scrollbar py-1">
                {/* Today's Revenue - Mobile */}
                <div className="flex items-center gap-1 px-2 py-1 rounded-md bg-muted whitespace-nowrap">
                  <DollarSign className="h-3 w-3 text-primary flex-shrink-0" />
                  <span className="text-[10px] font-bold text-foreground">
                    {formatAmountNoDecimals(analytics.todayRevenue)}
                  </span>
                </div>

                {/* Today's Orders - Mobile */}
                <div className="flex items-center gap-1 px-2 py-1 rounded-md bg-muted whitespace-nowrap">
                  <ShoppingCart className="h-3 w-3 text-primary flex-shrink-0" />
                  <span className="text-[10px] font-bold text-foreground">
                    {analytics.todayOrders}
                  </span>
                </div>

                {/* Pending Orders - Mobile Alert */}
                {analytics.pendingOrders > 0 && (
                  <div className="flex items-center gap-1 px-2 py-1 rounded-md bg-[#fff4ce] dark:bg-[#ca5010]/20 border border-[#ffe69d] dark:border-[#ca5010]/40 whitespace-nowrap animate-pulse">
                    <AlertCircle className="h-3 w-3 text-[#ca5010] dark:text-[#ffaa44] flex-shrink-0" />
                    <span className="text-[10px] font-bold text-[#ca5010] dark:text-[#ffaa44]">
                      {analytics.pendingOrders}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Wallet Balance Chip — always visible beside user avatar */}
            {coinsBalance !== null && selectedRestaurant && (
              <button
                type="button"
                onClick={() => setShowTopBarRecharge(true)}
                title={`Wallet Balance: ₹${coinsBalance.toLocaleString()} — click to top-up`}
                className="hidden lg:flex items-center gap-2.5 px-3 py-1.5 rounded-md border border-slate-200 bg-white hover:bg-slate-50/50 hover:border-slate-300 hover:shadow-sm transition-all focus:outline-none flex-shrink-0"
              >
                <div className="flex items-center justify-center p-1 rounded bg-slate-100/50">
                  <Wallet className="h-3.5 w-3.5 text-slate-500" />
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-slate-900 font-bold text-sm tracking-tight">₹{coinsBalance.toLocaleString()}</span>
                  <span className="text-[9px] text-slate-400 font-semibold uppercase tracking-widest">Balance</span>
                </div>
              </button>
            )}

            {/* User Profile Dropdown */}
            <div className="flex items-center pl-2 pr-4 lg:pr-6 flex-shrink-0">
              <UserProfileDropdown />
            </div>
          </div>
          {/* Global Billing Notifications */}
          <BillingNotificationBar billingInfo={billingInfo} planType={planType} isActive={isActive} />
        </header>

        {/* Page Content */}
        <main className="p-3 sm:p-4 md:p-6 bg-background min-h-[calc(100vh-4.5rem)] overflow-x-hidden relative">
          <div className="max-w-7xl mx-auto h-full">
            {(!isActive && location.pathname !== '/account') ? (
              <div className="flex flex-col items-center justify-center min-h-[60vh] h-full text-center space-y-6">
                {/* Billing Notification Banner inside deactivation overlay */}
                {billingInfo && planType === 'GOLD' && !billingInfo.mandate_active && (
                  <div className="w-full max-w-lg animate-in slide-in-from-top-4 duration-500">
                    <div className="w-full py-3 px-4 flex items-center justify-center gap-4 text-xs font-semibold rounded-xl shadow-inner bg-gradient-to-r from-amber-500 via-orange-500 to-red-500 text-white">
                      <div className="flex items-center gap-2 w-full">
                        <div className="flex items-center gap-2 flex-grow overflow-hidden">
                          <div className="p-1 rounded-md bg-white/20 shrink-0">
                            <AlertCircle className="h-4 w-4" />
                          </div>
                          <span className="truncate">{planType} requires active mandate. Set up Autopay now for seamless operation.</span>
                        </div>
                        <button
                          onClick={() => navigate('/autopay-setup')}
                          className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white text-black hover:bg-white/90 transition-all shrink-0 active:scale-95"
                        >
                          Set Up
                        </button>
                      </div>
                    </div>
                  </div>
                )}
                {billingInfo && billingInfo.billing_status === 'suspended' && (
                  <div className="w-full max-w-lg animate-in slide-in-from-top-4 duration-500">
                    <div className="w-full py-3 px-4 flex items-center justify-center gap-4 text-xs font-semibold rounded-xl shadow-inner bg-gradient-to-r from-red-600 via-red-500 to-orange-500 text-white">
                      <div className="flex items-center gap-2 w-full">
                        <div className="flex items-center gap-2 flex-grow overflow-hidden">
                          <div className="p-1 rounded-md bg-white/20 shrink-0">
                            <ShieldAlert className="h-4 w-4" />
                          </div>
                          <span className="truncate">Account suspended due to security reason. Please contact support to reactivate.</span>
                        </div>
                        <button
                          onClick={() => navigate('/autopay-setup?buy=true')}
                          className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white text-black hover:bg-white/90 transition-all shrink-0 active:scale-95"
                        >
                          Recharge Now
                        </button>
                      </div>
                    </div>
                  </div>
                )}
                {billingInfo && billingInfo.coins_balance < 0 && (
                  <div className="w-full max-w-lg animate-in slide-in-from-top-4 duration-500">
                    <div className="w-full py-3 px-4 flex items-center justify-center gap-4 text-xs font-semibold rounded-xl shadow-inner bg-gradient-to-r from-red-600 via-red-500 to-orange-500 text-white">
                      <div className="flex items-center gap-2 w-full">
                        <div className="flex items-center gap-2 flex-grow overflow-hidden">
                          <div className="p-1 rounded-md bg-white/20 shrink-0">
                            <ShieldAlert className="h-4 w-4" />
                          </div>
                          <span className="truncate">Account at risk due to negative balance (₹{billingInfo.coins_balance.toLocaleString()}). Recharge immediately.</span>
                        </div>
                        <button
                          onClick={() => navigate('/autopay-setup?buy=true')}
                          className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white text-black hover:bg-white/90 transition-all shrink-0 active:scale-95"
                        >
                          Pay Now
                        </button>
                      </div>
                    </div>
                  </div>
                )}
                <div className="bg-background max-w-lg p-10 rounded-2xl shadow-sm border border-border flex flex-col items-center">
                  <ShieldAlert className="h-16 w-16 text-rose-500 mb-6" />
                  <h1 className="text-2xl font-bold mb-3">Restaurant Deactivated</h1>
                  <p className="text-muted-foreground text-sm leading-relaxed mb-6">
                    Your Dinematters is deactivated due to security reason (something like production application) for that restaurant where nothing is accessible.
                  </p>
                  <p className="text-xs text-muted-foreground/60">
                    Please select another active restaurant from the top header or visit your <Link to="/account" className="text-primary underline">Account</Link> tab.
                  </p>
                </div>
              </div>
            ) : (
              <>
                {location.pathname !== '/account' && location.pathname !== '/menu' && <Breadcrumb />}
                {children || <Outlet />}
              </>
            )}
          </div>
        </main>
      </div>

      {/* Restaurant Selection Modal */}
      <Dialog open={showRestaurantSearch} onOpenChange={setShowRestaurantSearch}>
        <DialogContent className="sm:max-w-[500px] p-0 overflow-hidden">
          <DialogHeader className="p-6 pb-2">
            <DialogTitle>Search Restaurant</DialogTitle>
            <DialogDescription>
              Select a restaurant to switch the dashboard view
            </DialogDescription>
          </DialogHeader>
          <div className="p-4 pt-0">
            <div className="relative mb-4">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Type restaurant name..."
                className="pl-9 bg-muted/50 border-0 focus-visible:ring-1 focus-visible:ring-primary h-11"
                autoFocus
                value={restaurantSearchQuery}
                onChange={(e) => setRestaurantSearchQuery(e.target.value)}
              />
            </div>

            <div className="max-h-[350px] overflow-y-auto space-y-1 pr-1 custom-scrollbar">
              {restaurants
                .filter(r => r.restaurant_name.toLowerCase().includes(restaurantSearchQuery.toLowerCase()))
                .map((restaurant) => {
                  const isSelected = selectedRestaurant === restaurant.name
                  return (
                    <button
                      key={restaurant.name}
                      className={cn(
                        "w-full flex items-center justify-between p-3 rounded-xl transition-all group",
                        isSelected
                          ? "bg-primary/10 border border-primary/20"
                          : "hover:bg-muted border border-transparent"
                      )}
                      onClick={() => {
                        handleRestaurantChange(restaurant.name)
                        setShowRestaurantSearch(false)
                      }}
                    >
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "h-10 w-10 rounded-lg flex items-center justify-center shadow-sm",
                          isSelected ? "bg-primary text-white" : "bg-background text-muted-foreground group-hover:bg-primary/20 group-hover:text-primary transition-colors"
                        )}>
                          <Store className="h-5 w-5" />
                        </div>
                        <div className="text-left">
                          <p className={cn("text-sm font-bold", isSelected ? "text-primary" : "text-foreground")}>
                            {restaurant.restaurant_name}
                          </p>
                          <p className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium">#{restaurant.name.slice(-6)}</p>
                        </div>
                      </div>
                      {isSelected && (
                        <CheckCircle2 className="h-5 w-5 text-primary" />
                      )}
                    </button>
                  )
                })}
              {restaurants.filter(r => r.restaurant_name.toLowerCase().includes(restaurantSearchQuery.toLowerCase())).length === 0 && (
                <div className="py-12 text-center">
                  <Store className="h-12 w-12 text-muted-foreground/20 mx-auto mb-3" />
                  <p className="text-sm text-muted-foreground">No restaurants found matching "{restaurantSearchQuery}"</p>
                </div>
              )}
            </div>
          </div>
          <DialogFooter className="bg-muted/30 p-4 border-t border-border">
            <Button variant="ghost" onClick={() => setShowRestaurantSearch(false)} className="rounded-xl">Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create New Restaurant Modal */}
      <Dialog open={showCreateModal} onOpenChange={(open) => {
        if (!isCreating) {
          setShowCreateModal(open)
          if (!open) {
            setSendOnboarding(false)
            setSendPaymentInfo(false)
            setPaymentTier('SILVER')
          }
        }
      }}>
        <DialogContent className="sm:max-w-[520px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Create New Restaurant</DialogTitle>
            <DialogDescription>
              Enter the basic information to create your restaurant
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            {/* Restaurant Name */}
            <div className="space-y-2">
              <Label htmlFor="restaurant_name">
                Restaurant Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="restaurant_name"
                value={newRestaurantData.restaurant_name}
                onChange={(e) => setNewRestaurantData(prev => ({ ...prev, restaurant_name: e.target.value }))}
                disabled={isCreating}
                placeholder="e.g. Pizza Palace"
              />
            </div>

            {/* Owner Email */}
            <div className="space-y-2">
              <Label htmlFor="owner_email">
                Owner Email <span className="text-destructive">*</span>
              </Label>
              <Input
                id="owner_email"
                type="email"
                value={newRestaurantData.owner_email}
                onChange={(e) => setNewRestaurantData(prev => ({ ...prev, owner_email: e.target.value }))}
                disabled={isCreating}
                placeholder="owner@restaurant.com"
              />
            </div>

            {/* Owner Phone */}
            <div className="space-y-2">
              <Label htmlFor="owner_phone">Owner Phone</Label>
              <Input
                id="owner_phone"
                type="tel"
                value={newRestaurantData.owner_phone}
                onChange={(e) => setNewRestaurantData(prev => ({ ...prev, owner_phone: e.target.value }))}
                disabled={isCreating}
                placeholder="+91 98765 43210"
              />
              <p className="text-xs text-muted-foreground">Required if sending payment info via WhatsApp.</p>
            </div>

            {/* Referral Code */}
            <div className="space-y-2">
              <Label htmlFor="referral_code">Referral Code</Label>
              <Input
                id="referral_code"
                placeholder="DINE-XXXX-XXXX"
                value={newRestaurantData.referral_code}
                onChange={(e) => setNewRestaurantData(prev => ({ ...prev, referral_code: e.target.value }))}
                disabled={isCreating}
              />
              <p className="text-xs text-muted-foreground">If referred by another merchant — gives them ₹500.</p>
            </div>

            {/* Divider */}
            <div className="border-t border-border pt-2">
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">After Creation Actions</p>

              {/* Checkbox 1: Send Onboarding Details */}
              <div className={cn(
                "flex items-start gap-3 rounded-xl border p-3 transition-all cursor-pointer",
                sendOnboarding
                  ? "bg-blue-500/5 border-blue-200 dark:border-blue-800"
                  : "bg-muted/30 border-border hover:bg-muted/50"
              )}
                onClick={() => !isCreating && setSendOnboarding(v => !v)}
              >
                <Checkbox
                  id="send_onboarding"
                  checked={sendOnboarding}
                  onCheckedChange={(v) => setSendOnboarding(!!v)}
                  disabled={isCreating}
                  className="mt-0.5 shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <Mail className="h-4 w-4 text-blue-500 shrink-0" />
                    <Label htmlFor="send_onboarding" className="text-sm font-semibold cursor-pointer">
                      Send Onboarding Details
                    </Label>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Sends a secure password-setup link to the owner's email so they can log in.
                  </p>
                </div>
              </div>

              {/* Checkbox 2: Send Payment Info */}
              <div className={cn(
                "flex items-start gap-3 rounded-xl border p-3 mt-2 transition-all cursor-pointer",
                sendPaymentInfo
                  ? "bg-green-500/5 border-green-200 dark:border-green-800"
                  : "bg-muted/30 border-border hover:bg-muted/50"
              )}
                onClick={() => !isCreating && setSendPaymentInfo(v => !v)}
              >
                <Checkbox
                  id="send_payment_info"
                  checked={sendPaymentInfo}
                  onCheckedChange={(v) => setSendPaymentInfo(!!v)}
                  disabled={isCreating}
                  className="mt-0.5 shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <Smartphone className="h-4 w-4 text-green-500 shrink-0" />
                    <Label htmlFor="send_payment_info" className="text-sm font-semibold cursor-pointer">
                      Send Payment Info via WhatsApp
                    </Label>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Opens WhatsApp with a wallet purchase link based on the selected plan.
                  </p>

                  {/* Tier Selector — only visible when checkbox is checked */}
                  {sendPaymentInfo && (
                    <div className="mt-3" onClick={(e) => e.stopPropagation()}>
                      <RadioGroup
                        value={paymentTier}
                        onValueChange={(v: string) => setPaymentTier(v as 'SILVER' | 'GOLD')}
                        className="flex flex-col gap-2"
                        disabled={isCreating}
                      >
                        {/* Silver */}
                        <label
                          htmlFor="tier_silver"
                          className={cn(
                            "flex items-center gap-3 rounded-lg border px-3 py-2 cursor-pointer transition-all",
                            paymentTier === 'SILVER'
                              ? "bg-slate-100 dark:bg-slate-800 border-slate-400"
                              : "border-border hover:bg-muted/50"
                          )}
                        >
                          <RadioGroupItem value="SILVER" id="tier_silver" />
                          <div className="flex items-center gap-2 flex-1">
                            <Shield className="h-3.5 w-3.5 text-slate-500" />
                            <span className="text-sm font-medium">Silver</span>
                            <span className="ml-auto text-xs text-muted-foreground">Free — no link sent</span>
                          </div>
                        </label>

                        {/* Gold */}
                        <label
                          htmlFor="tier_gold"
                          className={cn(
                            "flex items-center gap-3 rounded-lg border px-3 py-2 cursor-pointer transition-all",
                            paymentTier === 'GOLD'
                              ? "bg-amber-50 dark:bg-amber-950/30 border-amber-400"
                              : "border-border hover:bg-muted/50"
                          )}
                        >
                          <RadioGroupItem value="GOLD" id="tier_gold" />
                          <div className="flex items-center gap-2 flex-1">
                            <Star className="h-3.5 w-3.5 text-amber-500" />
                            <span className="text-sm font-medium">Gold</span>
                            <span className="ml-auto text-xs font-semibold text-amber-600">₹1,178.82 inkl. GST</span>
                          </div>
                        </label>

                      </RadioGroup>

                      {paymentTier !== 'SILVER' && (
                        <p className="text-[10px] text-muted-foreground mt-2 flex items-center gap-1">
                          <Smartphone className="h-3 w-3" />
                          WhatsApp will open with the payment link pre-filled. Just hit Send.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          <DialogFooter className="pt-2">
            <Button
              variant="outline"
              onClick={() => setShowCreateModal(false)}
              disabled={isCreating}
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateRestaurant}
              disabled={isCreating || !newRestaurantData.restaurant_name.trim() || !newRestaurantData.owner_email.trim()}
            >
              {isCreating ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Plus className="mr-2 h-4 w-4" />
                  Create Restaurant
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* DineMatters Wallet Top-up Modal — triggered from top bar chip */}
      {selectedRestaurant && (
        <AiRechargeModal
          open={showTopBarRecharge}
          onClose={() => setShowTopBarRecharge(false)}
          restaurant={selectedRestaurant}
          onSuccess={refreshConfig}
        />
      )}

      {/* Hard Suspension Overlay */}
      {!isActive && billingStatus === 'suspended' && (
        <SuspendedOverlay
          restaurantName={restaurantDoc?.restaurant_name || currentRestaurant?.restaurant_name || "Your Restaurant"}
        />
      )}
      <Dialog open={isLinkModalOpen} onOpenChange={setIsLinkModalOpen}>
        <DialogContent className="sm:max-w-md p-6 rounded-2xl">
          <DialogHeader>
            <DialogTitle>Secure Payment Link</DialogTitle>
            <DialogDescription>
              Copy and share this payment link with the user.
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


