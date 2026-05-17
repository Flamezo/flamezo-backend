import { useMemo } from 'react'
import { useFrappeGetDocList, useFrappeGetCall } from '@/lib/frappe'
import { useRestaurant } from '@/contexts/RestaurantContext'

const FALLBACK_SYMBOLS: Record<string, string> = {
  'USD': '$',
  'INR': '₹',
  'EUR': '€',
  'GBP': '£',
  'JPY': '¥',
  'AUD': 'A$',
  'CAD': 'C$',
  'CHF': 'CHF',
  'CNY': '¥',
  'SGD': 'S$',
}

/**
 * Hook to get currency symbol for the selected restaurant.
 * Uses restaurantConfig from get_restaurant_config API as primary source (avoids SWR cache).
 * Fallback to direct DocType fetch when config not yet loaded.
 */
export function useCurrency() {
  const { selectedRestaurant, restaurantConfig } = useRestaurant()
  const pricing = restaurantConfig?.pricing

  // Fallback: fetch only the currency field when pricing not from context (avoids fetching huge docs)
  const { data: configList } = useFrappeGetDocList('Restaurant Config', {
    filters: selectedRestaurant ? [['name', '=', selectedRestaurant]] : [],
    fields: ['currency'],
    limit: 1,
  })
  const configData = configList?.[0] || null

  const { data: restaurantList } = useFrappeGetDocList('Restaurant', {
    filters: selectedRestaurant ? [['name', '=', selectedRestaurant]] : [],
    fields: ['currency'],
    limit: 1,
  })
  const restaurantData = restaurantList?.[0] || null

  const currencyCode = pricing?.currency || configData?.currency || restaurantData?.currency || 'INR'

  // Fetch Currency info via whitelisted method to bypass DocType permissions
  const { data: currencyResponse } = useFrappeGetCall('flamezo_backend.flamezo.api.config.get_currency_info', {
    currency_code: currencyCode
  }, {
    revalidateOnFocus: false,
    enabled: !!currencyCode && !pricing?.symbol
  })
  const currencyInfo = currencyResponse?.message?.data

  const currencySymbol = useMemo(() => {
    if (pricing?.symbol) return pricing.symbol
    if (currencyInfo?.symbol) return currencyInfo.symbol
    return FALLBACK_SYMBOLS[currencyCode] || currencyCode
  }, [pricing?.symbol, currencyInfo?.symbol, currencyCode])

  const symbolOnRight = pricing?.symbolOnRight ?? currencyInfo?.symbolOnRight ?? false
  
  return {
    currency: currencyCode,
    symbol: currencySymbol,
    symbolOnRight,
    formatAmount: (amount: number | string | null | undefined): string => {
      const numAmount = typeof amount === 'string' ? parseFloat(amount) : (amount || 0)
      if (symbolOnRight) {
        return `${numAmount.toFixed(2)} ${currencySymbol}`
      }
      return `${currencySymbol}${numAmount.toFixed(2)}`
    },
    formatAmountNoDecimals: (amount: number | string | null | undefined): string => {
      const numAmount = typeof amount === 'string' ? parseFloat(amount) : (amount || 0)
      if (symbolOnRight) {
        return `${numAmount.toFixed(0)} ${currencySymbol}`
      }
      return `${currencySymbol}${numAmount.toFixed(0)}`
    }
  }
}

