import { createContext, useContext, useEffect, useState, ReactNode, useCallback, useMemo } from 'react'
import { useFrappeGetCall } from '@/lib/frappe'

interface Outlet {
  name: string
  outlet_id: string
  outlet_name: string
  is_active: boolean
  city?: string
  state?: string
  company?: string
  logo?: string
}

/**
 * Razorpay Route hybrid settlement state for an outlet. Mirrors the
 * `payments` section of `get_outlet_config`. The merchant dashboard
 * uses this for:
 *   • the Success Share Settlement panel (outstanding paise, throttle)
 *   • route_mode badges (flamezo_hold / direct_split / disabled)
 *   • the Route KYC status indicator
 */
export interface OutletPayments {
  routeMode: 'flamezo_hold' | 'direct_split' | 'disabled'
  razorpayKycStatus: '' | 'under_review' | 'needs_clarification' | 'activated' | 'suspended' | 'rejected'
  outstandingSuccessSharePaise: number
  cashPaymentsDisabledUntil: string | null
  cashSweepFailureCount: number
  lastCashSweepError: string
}

interface OutletContextType {
  selectedOutlet: string | null
  setSelectedOutlet: (outletId: string | null) => void
  outlets: Outlet[]
  isLoading: boolean
  setOutletsData: (data: Outlet[]) => void
  outletConfig?: any | null
  setOutletConfig?: (cfg: any | null) => void
  refreshConfig: () => Promise<void>
  planType: 'GOLD'
  isGold: boolean
  coinsBalance: number
  billingStatus: 'active' | 'overdue' | 'suspended'
  isActive: boolean
  features: {
    ordering: boolean
    videoUpload: boolean
    analytics: boolean
    aiRecommendations: boolean
    loyalty: boolean
    coupons: boolean
    games: boolean
    tableBooking: boolean
    events: boolean
    offers: boolean
    experience_lounge: boolean
    marketing_studio: boolean
    google_growth: boolean
    whatsapp_orders: boolean
    order_settings: boolean
  }
  billingInfo: any | null
  /**
   * Razorpay Route hybrid payment-settlement state for the selected
   * outlet. Populated from the `payments` section of
   * `get_outlet_config`. `null` until the config has loaded.
   */
  payments: OutletPayments | null
  googleMapsApiKey: string | null
  referralCode: string | null
  /** Role of the current user for the selected outlet */
  userRole: 'Outlet Admin' | 'Outlet Staff' | null
  /** True if current user is Restaurant Admin (or system Administrator/Supervisor) */
  isAdmin: boolean
  /** True if current user has Flamezo Supervisor role */
  isSupervisor: boolean
  /** Outlet type for this merchant: dining | cafe | wellness | fitness | sports_court | sports_venue | fashion */
  outletType: string
}

const OutletContext = createContext<OutletContextType | undefined>(undefined)

const STORAGE_KEY = 'flamezo-selected-outlet'

export function OutletProvider({ children }: { children: ReactNode }) {
  // Helper to validate outlet IDs
  const isValidOutletId = (id: string | null) => {
    if (!id) return false
    // Reject 3-letter currency codes (e.g., INR, USD)
    if (/^[A-Z]{3}$/.test(id)) return false
    return true
  }

  const [selectedOutlet, setSelectedOutletState] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null
    const saved = localStorage.getItem(STORAGE_KEY)
    // Only initialize with saved value if it doesn't look like a currency code
    if (saved && /^[A-Z]{3}$/.test(saved)) {
      localStorage.removeItem(STORAGE_KEY)
      return null
    }
    return saved
  })

  const [outlets, setOutlets] = useState<Outlet[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [outletConfig, setOutletConfig] = useState<any | null>(null)
  const [googleMapsApiKey, setGoogleMapsApiKey] = useState<string | null>(null)

  // Root level fetch to break the render deadlock
  const { data: outletsData } = useFrappeGetCall<{ message: { restaurants: Outlet[] } }>(
    'flamezo_backend.flamezo.api.ui.get_user_outlets',
    {},
    'user-outlets'
  )

  const fetchedOutlets = useMemo(() => outletsData?.message?.restaurants || [], [outletsData])

  // Simplified loading logic for instant response

  useEffect(() => {
    // Only clear loading once we have BOTH the outlet list AND the subscription config
    // or if we have at least verified there is no config coming.
    if (outlets.length > 0 && outletConfig !== null) {
      setIsLoading(false)
    } else if (outletsData && outlets.length === 0) {
      // Handle the case where the user has no outlets at all
      setIsLoading(false)
    }
  }, [outlets, outletConfig, outletsData])

  // Automatically sync fetched data into state
  useEffect(() => {
    if (outletsData && fetchedOutlets.length >= 0) {
      setOutletsData(fetchedOutlets)
    }
  }, [fetchedOutlets, outletsData])

  // Load outlets (this will be set by Layout component)
  const setOutletsData = (data: Outlet[]) => {
    setOutlets(data)

    // Validate current state and localStorage to determine the correct active outlet
    const saved = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null
    let newSelectedOutlet: string | null = null

    // Priority 1: Use currently selected if it is valid in the new data
    const currentIsValid = selectedOutlet && data.find(r => r.name === selectedOutlet || r.outlet_id === selectedOutlet)

    if (currentIsValid) {
      newSelectedOutlet = selectedOutlet
    }
    // Priority 2: Use saved ID if it's valid for this user
    else if (saved && data.find(r => r.name === saved || r.outlet_id === saved)) {
      newSelectedOutlet = saved
    }
    // Priority 3: Default to first valid outlet
    else if (data.length > 0) {
      // Skip any that look like currency codes for default selection
      const firstNonCurrency = data.find(r => isValidOutletId(r.name))
      newSelectedOutlet = firstNonCurrency ? firstNonCurrency.name : data[0].name
      localStorage.setItem(STORAGE_KEY, newSelectedOutlet)
    }

    if (newSelectedOutlet !== selectedOutlet) {
      setSelectedOutletState(newSelectedOutlet)
      // Keep loading TRUE until the next render cycle when selectedOutlet state is applied
      setTimeout(() => setIsLoading(false), 0)
    } else {
      setIsLoading(false)
    }
  }

  const setSelectedOutlet = (outletId: string | null) => {
    // Defense: ignore values that look like currency codes (e.g., "INR", "USD")
    if (outletId && !isValidOutletId(outletId)) {
      console.warn(`[OutletContext] Ignored setting selectedOutlet to currency-like value: ${outletId}`)
      return
    }

    setSelectedOutletState(outletId)
    if (outletId) {
      try {
        localStorage.setItem(STORAGE_KEY, outletId)
      } catch {
        // Ignore errors
      }
    } else {
      try {
        localStorage.removeItem(STORAGE_KEY)
      } catch {
        // Ignore errors
      }
    }
  }

  const fetchConfig = useCallback(async () => {
    if (!selectedOutlet) {
      setOutletConfig(null)
      return
    }

    try {
      const resp = await fetch(
        `/api/method/flamezo_backend.flamezo.api.config.get_outlet_config?outlet_id=${encodeURIComponent(selectedOutlet)}`,
        { cache: 'no-store' }
      )
      const json = await resp.json()

      const payload = json?.message ?? json
      if (payload?.success) {
        const configData = payload.data || null
        setOutletConfig(configData)
        if (configData?.settings?.googleMapsApiKey) {
          setGoogleMapsApiKey(configData.settings.googleMapsApiKey)
        }
        setIsLoading(false)
      } else if (payload?.data) {
        setOutletConfig(payload.data)
        if (payload.data?.settings?.googleMapsApiKey) {
          setGoogleMapsApiKey(payload.data.settings.googleMapsApiKey)
        }
        setIsLoading(false)
      } else {
        setOutletConfig(null)
        setIsLoading(false)
      }
    } catch (e) {
      setOutletConfig(null)
      setIsLoading(false)
    }
  }, [selectedOutlet])

  // Fetch outlet config (branding, features) when selectedOutlet changes
  useEffect(() => {
    fetchConfig()
  }, [selectedOutlet])

  // Sync with localStorage changes (e.g., from Layout component)
  useEffect(() => {
    const handleStorageChange = () => {
      try {
        const saved = localStorage.getItem(STORAGE_KEY)
        if (saved !== selectedOutlet && isValidOutletId(saved)) {
          setSelectedOutletState(saved)
        }
      } catch {
        // Ignore errors
      }
    }

    window.addEventListener('storage', handleStorageChange)
    // Also listen for custom events (for same-tab updates)
    window.addEventListener('outlet-selected', handleStorageChange)

    return () => {
      window.removeEventListener('storage', handleStorageChange)
      window.removeEventListener('outlet-selected', handleStorageChange)
    }
  }, [selectedOutlet])

  const planType = 'GOLD' as const
  const billingStatus = outletConfig?.subscription?.billingStatus || 'active'
  const coinsBalance = outletConfig?.subscription?.coinsBalance || 0
  const isActive = outletConfig?.subscription?.isActive ?? true
  const isGold = true

  // User role for the selected outlet (populated by get_outlet_config)
  const userRole = (outletConfig?.subscription?.userRole as 'Outlet Admin' | 'Outlet Staff' | null) ?? null

  // Check for global supervisor role from boot data
  const userRoles = (window as any)?.frappe?.boot?.user_roles || []
  const isSupervisor = userRoles.includes('Flamezo Supervisor')

  // isAdmin is true if they are a restaurant admin, or if they are a supervisor, or if no config is loaded yet (guest/admin)
  const isAdmin = isSupervisor || userRole === 'Outlet Admin' || userRole === null

  // Under the single-tier model the backend reports every feature as `true`
  // for every outlet. The defaults below also resolve to `true` so the
  // dashboard doesn't briefly render a "locked" state while config is
  // loading.
  const features = outletConfig?.subscription?.features ? {
    ordering: outletConfig.subscription.features.ordering ?? true,
    videoUpload: outletConfig.subscription.features.videoUpload ?? true,
    analytics: outletConfig.subscription.features.analytics ?? true,
    aiRecommendations: outletConfig.subscription.features.aiRecommendations ?? true,
    loyalty: outletConfig.subscription.features.loyalty ?? true,
    coupons: outletConfig.subscription.features.coupons ?? true,
    games: outletConfig.subscription.features.games ?? true,
    tableBooking: outletConfig.subscription.features.tableBooking ?? true,
    events: outletConfig.subscription.features.events ?? true,
    offers: outletConfig.subscription.features.offers ?? true,
    experience_lounge: outletConfig.subscription.features.experience_lounge ?? true,
    marketing_studio: outletConfig.subscription.features.marketing_studio ?? true,
    google_growth: outletConfig.subscription.features.google_growth ?? true,
    whatsapp_orders: outletConfig.subscription.features.whatsapp_orders ?? true,
    order_settings: outletConfig.subscription.features.order_settings ?? true,
  } : {
    ordering: true,
    videoUpload: true,
    analytics: true,
    aiRecommendations: true,
    loyalty: true,
    coupons: true,
    games: true,
    tableBooking: true,
    events: true,
    offers: true,
    experience_lounge: true,
    marketing_studio: true,
    google_growth: true,
    whatsapp_orders: true,
    order_settings: true,
  }

  // Map the backend `payments` block onto our context shape. The backend
  // always emits this section (with safe defaults like routeMode='flamezo_hold')
  // so `null` here is really "config not loaded yet".
  const payments: OutletPayments | null = outletConfig?.payments ? {
    routeMode: (outletConfig.payments.routeMode || 'flamezo_hold') as OutletPayments['routeMode'],
    razorpayKycStatus: (outletConfig.payments.razorpayKycStatus || '') as OutletPayments['razorpayKycStatus'],
    outstandingSuccessSharePaise: Number(outletConfig.payments.outstandingSuccessSharePaise || 0),
    cashPaymentsDisabledUntil: outletConfig.payments.cashPaymentsDisabledUntil || null,
    cashSweepFailureCount: Number(outletConfig.payments.cashSweepFailureCount || 0),
    lastCashSweepError: outletConfig.payments.lastCashSweepError || '',
  } : null

  const billingInfo = outletConfig?.subscription ? {
    coins_balance: outletConfig.subscription.coinsBalance,
    deferred_plan_type: outletConfig.subscription.deferredPlanType,
    plan_change_date: outletConfig.subscription.planChangeDate,
    mandate_active: outletConfig.subscription.mandateActive,
    auto_recharge_enabled: outletConfig.subscription.autoRechargeEnabled,
    auto_recharge_threshold: outletConfig.subscription.autoRechargeThreshold,
    auto_recharge_amount: outletConfig.subscription.autoRechargeAmount,
    daily_limit: outletConfig.subscription.dailyLimit,
    current_daily_vol: outletConfig.subscription.currentDailyVol,
    billing_status: outletConfig.subscription.billingStatus,
    onboarding_date: outletConfig.subscription.onboardingDate,
    last_auto_recharge_date: outletConfig.subscription.lastAutoRechargeDate,
    platform_fee_percent: outletConfig.subscription.platform_fee_percent
  } : null

  return (
    <OutletContext.Provider
      value={{
        selectedOutlet,
        setSelectedOutlet,
        outlets,
        isLoading,
        setOutletsData,
        outletConfig,
        setOutletConfig,
        refreshConfig: fetchConfig,
        planType,
        isGold,
        coinsBalance,
        billingStatus,
        isActive,
        features,
        billingInfo,
        payments,
        googleMapsApiKey,
        referralCode: outletConfig?.subscription?.referral_code || null,
        userRole,
        isAdmin,
        isSupervisor,
        outletType: outletConfig?.restaurant?.outletType || 'dining',
      }}
    >
      {children}
    </OutletContext.Provider>
  )
}

export function useOutlet() {
  const context = useContext(OutletContext)
  if (context === undefined) {
    throw new Error('useOutlet must be used within an OutletProvider')
  }
  return context
}
