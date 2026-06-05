import { createContext, useContext, useEffect, useState, ReactNode, useCallback, useMemo } from 'react'
import { useFrappeGetCall } from '@/lib/frappe'

interface Restaurant {
  name: string
  restaurant_id: string
  restaurant_name: string
  is_active: boolean
  city?: string
  state?: string
  company?: string
  logo?: string
}

/**
 * Razorpay Route hybrid settlement state for a restaurant. Mirrors the
 * `payments` section of `get_restaurant_config`. The merchant dashboard
 * uses this for:
 *   • the Success Share Settlement panel (outstanding paise, throttle)
 *   • route_mode badges (flamezo_hold / direct_split / disabled)
 *   • the Route KYC status indicator
 */
export interface RestaurantPayments {
  routeMode: 'flamezo_hold' | 'direct_split' | 'disabled'
  razorpayKycStatus: '' | 'under_review' | 'needs_clarification' | 'activated' | 'suspended' | 'rejected'
  outstandingSuccessSharePaise: number
  cashPaymentsDisabledUntil: string | null
  cashSweepFailureCount: number
  lastCashSweepError: string
}

interface RestaurantContextType {
  selectedRestaurant: string | null
  setSelectedRestaurant: (restaurantId: string | null) => void
  restaurants: Restaurant[]
  isLoading: boolean
  setRestaurantsData: (data: Restaurant[]) => void
  restaurantConfig?: any | null
  setRestaurantConfig?: (cfg: any | null) => void
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
   * restaurant. Populated from the `payments` section of
   * `get_restaurant_config`. `null` until the config has loaded.
   */
  payments: RestaurantPayments | null
  googleMapsApiKey: string | null
  referralCode: string | null
  /** Role of the current user for the selected restaurant */
  userRole: 'Restaurant Admin' | 'Restaurant Staff' | null
  /** True if current user is Restaurant Admin (or system Administrator/Supervisor) */
  isAdmin: boolean
  /** True if current user has Flamezo Supervisor role */
  isSupervisor: boolean
}

const RestaurantContext = createContext<RestaurantContextType | undefined>(undefined)

const STORAGE_KEY = 'flamezo-selected-restaurant'

export function RestaurantProvider({ children }: { children: ReactNode }) {
  // Helper to validate restaurant IDs
  const isValidRestaurantId = (id: string | null) => {
    if (!id) return false
    // Reject 3-letter currency codes (e.g., INR, USD)
    if (/^[A-Z]{3}$/.test(id)) return false
    return true
  }

  const [selectedRestaurant, setSelectedRestaurantState] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null
    const saved = localStorage.getItem(STORAGE_KEY)
    // Only initialize with saved value if it doesn't look like a currency code
    if (saved && /^[A-Z]{3}$/.test(saved)) {
      localStorage.removeItem(STORAGE_KEY)
      return null
    }
    return saved
  })

  const [restaurants, setRestaurants] = useState<Restaurant[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [restaurantConfig, setRestaurantConfig] = useState<any | null>(null)
  const [googleMapsApiKey, setGoogleMapsApiKey] = useState<string | null>(null)

  // Root level fetch to break the render deadlock
  const { data: restaurantsData } = useFrappeGetCall<{ message: { restaurants: Restaurant[] } }>(
    'flamezo_backend.flamezo.api.ui.get_user_restaurants',
    {},
    'user-restaurants'
  )

  const fetchedRestaurants = useMemo(() => restaurantsData?.message?.restaurants || [], [restaurantsData])

  // Simplified loading logic for instant response

  useEffect(() => {
    // Only clear loading once we have BOTH the restaurant list AND the subscription config
    // or if we have at least verified there is no config coming.
    if (restaurants.length > 0 && restaurantConfig !== null) {
      setIsLoading(false)
    } else if (restaurantsData && restaurants.length === 0) {
      // Handle the case where the user has no restaurants at all
      setIsLoading(false)
    }
  }, [restaurants, restaurantConfig, restaurantsData])

  // Automatically sync fetched data into state
  useEffect(() => {
    if (restaurantsData && fetchedRestaurants.length >= 0) {
      setRestaurantsData(fetchedRestaurants)
    }
  }, [fetchedRestaurants, restaurantsData])

  // Load restaurants (this will be set by Layout component)
  const setRestaurantsData = (data: Restaurant[]) => {
    setRestaurants(data)
    
    // Validate current state and localStorage to determine the correct active restaurant
    const saved = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null
    let newSelectedRestaurant: string | null = null
    
    // Priority 1: Use currently selected if it is valid in the new data
    const currentIsValid = selectedRestaurant && data.find(r => r.name === selectedRestaurant || r.restaurant_id === selectedRestaurant)
    
    if (currentIsValid) {
      newSelectedRestaurant = selectedRestaurant
    } 
    // Priority 2: Use saved ID if it's valid for this user
    else if (saved && data.find(r => r.name === saved || r.restaurant_id === saved)) {
      newSelectedRestaurant = saved
    } 
    // Priority 3: Default to first valid restaurant
    else if (data.length > 0) {
      // Skip any that look like currency codes for default selection
      const firstNonCurrency = data.find(r => isValidRestaurantId(r.name))
      newSelectedRestaurant = firstNonCurrency ? firstNonCurrency.name : data[0].name
      localStorage.setItem(STORAGE_KEY, newSelectedRestaurant)
    }

    if (newSelectedRestaurant !== selectedRestaurant) {
      setSelectedRestaurantState(newSelectedRestaurant)
      // Keep loading TRUE until the next render cycle when selectedRestaurant state is applied
      setTimeout(() => setIsLoading(false), 0)
    } else {
      setIsLoading(false)
    }
  }

  const setSelectedRestaurant = (restaurantId: string | null) => {
    // Defense: ignore values that look like currency codes (e.g., "INR", "USD")
    if (restaurantId && !isValidRestaurantId(restaurantId)) {
      console.warn(`[RestaurantContext] Ignored setting selectedRestaurant to currency-like value: ${restaurantId}`)
      return
    }

    setSelectedRestaurantState(restaurantId)
    if (restaurantId) {
      try {
        localStorage.setItem(STORAGE_KEY, restaurantId)
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
    if (!selectedRestaurant) {
      setRestaurantConfig(null)
      return
    }
    
    try {
      const resp = await fetch(
        `/api/method/flamezo_backend.flamezo.api.config.get_restaurant_config?restaurant_id=${encodeURIComponent(selectedRestaurant)}`,
        { cache: 'no-store' }
      )
      const json = await resp.json()
      
      const payload = json?.message ?? json
      if (payload?.success) {
        const configData = payload.data || null
        setRestaurantConfig(configData)
        if (configData?.settings?.googleMapsApiKey) {
          setGoogleMapsApiKey(configData.settings.googleMapsApiKey)
        }
        setIsLoading(false)
      } else if (payload?.data) {
        setRestaurantConfig(payload.data)
        if (payload.data?.settings?.googleMapsApiKey) {
          setGoogleMapsApiKey(payload.data.settings.googleMapsApiKey)
        }
        setIsLoading(false)
      } else {
        setRestaurantConfig(null)
        setIsLoading(false)
      }
    } catch (e) {
      setRestaurantConfig(null)
      setIsLoading(false)
    }
  }, [selectedRestaurant])

  // Fetch restaurant config (branding, features) when selectedRestaurant changes
  useEffect(() => {
    fetchConfig()
  }, [selectedRestaurant])

  // Sync with localStorage changes (e.g., from Layout component)
  useEffect(() => {
    const handleStorageChange = () => {
      try {
        const saved = localStorage.getItem(STORAGE_KEY)
        if (saved !== selectedRestaurant && isValidRestaurantId(saved)) {
          setSelectedRestaurantState(saved)
        }
      } catch {
        // Ignore errors
      }
    }

    window.addEventListener('storage', handleStorageChange)
    // Also listen for custom events (for same-tab updates)
    window.addEventListener('restaurant-selected', handleStorageChange)

    return () => {
      window.removeEventListener('storage', handleStorageChange)
      window.removeEventListener('restaurant-selected', handleStorageChange)
    }
  }, [selectedRestaurant])

  const planType = 'GOLD' as const
  const billingStatus = restaurantConfig?.subscription?.billingStatus || 'active'
  const coinsBalance = restaurantConfig?.subscription?.coinsBalance || 0
  const isActive = restaurantConfig?.subscription?.isActive ?? true
  const isGold = true

  // User role for the selected restaurant (populated by get_restaurant_config)
  const userRole = (restaurantConfig?.subscription?.userRole as 'Restaurant Admin' | 'Restaurant Staff' | null) ?? null
  
  // Check for global supervisor role from boot data
  const userRoles = (window as any)?.frappe?.boot?.user_roles || []
  const isSupervisor = userRoles.includes('Flamezo Supervisor')
  
  // isAdmin is true if they are a restaurant admin, or if they are a supervisor, or if no config is loaded yet (guest/admin)
  const isAdmin = isSupervisor || userRole === 'Restaurant Admin' || userRole === null 
  
  // Under the single-tier model the backend reports every feature as `true`
  // for every restaurant. The defaults below also resolve to `true` so the
  // dashboard doesn't briefly render a "locked" state while config is
  // loading.
  const features = restaurantConfig?.subscription?.features ? {
    ordering: restaurantConfig.subscription.features.ordering ?? true,
    videoUpload: restaurantConfig.subscription.features.videoUpload ?? true,
    analytics: restaurantConfig.subscription.features.analytics ?? true,
    aiRecommendations: restaurantConfig.subscription.features.aiRecommendations ?? true,
    loyalty: restaurantConfig.subscription.features.loyalty ?? true,
    coupons: restaurantConfig.subscription.features.coupons ?? true,
    games: restaurantConfig.subscription.features.games ?? true,
    tableBooking: restaurantConfig.subscription.features.tableBooking ?? true,
    events: restaurantConfig.subscription.features.events ?? true,
    offers: restaurantConfig.subscription.features.offers ?? true,
    experience_lounge: restaurantConfig.subscription.features.experience_lounge ?? true,
    marketing_studio: restaurantConfig.subscription.features.marketing_studio ?? true,
    google_growth: restaurantConfig.subscription.features.google_growth ?? true,
    whatsapp_orders: restaurantConfig.subscription.features.whatsapp_orders ?? true,
    order_settings: restaurantConfig.subscription.features.order_settings ?? true,
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
  const payments: RestaurantPayments | null = restaurantConfig?.payments ? {
    routeMode: (restaurantConfig.payments.routeMode || 'flamezo_hold') as RestaurantPayments['routeMode'],
    razorpayKycStatus: (restaurantConfig.payments.razorpayKycStatus || '') as RestaurantPayments['razorpayKycStatus'],
    outstandingSuccessSharePaise: Number(restaurantConfig.payments.outstandingSuccessSharePaise || 0),
    cashPaymentsDisabledUntil: restaurantConfig.payments.cashPaymentsDisabledUntil || null,
    cashSweepFailureCount: Number(restaurantConfig.payments.cashSweepFailureCount || 0),
    lastCashSweepError: restaurantConfig.payments.lastCashSweepError || '',
  } : null

  const billingInfo = restaurantConfig?.subscription ? {
    coins_balance: restaurantConfig.subscription.coinsBalance,
    deferred_plan_type: restaurantConfig.subscription.deferredPlanType,
    plan_change_date: restaurantConfig.subscription.planChangeDate,
    mandate_active: restaurantConfig.subscription.mandateActive,
    auto_recharge_enabled: restaurantConfig.subscription.autoRechargeEnabled,
    auto_recharge_threshold: restaurantConfig.subscription.autoRechargeThreshold,
    auto_recharge_amount: restaurantConfig.subscription.autoRechargeAmount,
    daily_limit: restaurantConfig.subscription.dailyLimit,
    current_daily_vol: restaurantConfig.subscription.currentDailyVol,
    billing_status: restaurantConfig.subscription.billingStatus,
    onboarding_date: restaurantConfig.subscription.onboardingDate,
    last_auto_recharge_date: restaurantConfig.subscription.lastAutoRechargeDate,
    monthly_minimum: restaurantConfig.subscription.monthly_minimum,
    platform_fee_percent: restaurantConfig.subscription.platform_fee_percent
  } : null

  return (
    <RestaurantContext.Provider 
      value={{ 
        selectedRestaurant, 
        setSelectedRestaurant,
        restaurants,
        isLoading,
        setRestaurantsData,
        restaurantConfig,
        setRestaurantConfig,
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
        referralCode: restaurantConfig?.subscription?.referral_code || null,
        userRole,
        isAdmin,
        isSupervisor,
      }}
    >
      {children}
    </RestaurantContext.Provider>
  )
}

export function useRestaurant() {
  const context = useContext(RestaurantContext)
  if (context === undefined) {
    throw new Error('useRestaurant must be used within a RestaurantProvider')
  }
  return context
}

