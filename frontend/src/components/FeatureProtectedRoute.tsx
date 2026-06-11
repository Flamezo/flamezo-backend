import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useState, useEffect } from 'react'
import { getFeatureAccessStatus } from '@/utils/featureAccess'

interface FeatureProtectedRouteProps {
  feature?: string
  /** Grant access if ANY of these features is available (OR-gating). */
  anyOf?: string[]
  requireGold?: boolean
}

export default function FeatureProtectedRoute({ feature, anyOf, requireGold = false }: FeatureProtectedRouteProps) {
  const { isGold, features, isLoading, planType } = useRestaurant()
  const location = useLocation()
  const [hasTimedOut, setHasTimedOut] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => {
      setHasTimedOut(true)
    }, 5000)
    return () => clearTimeout(timer)
  }, [])

  // Always return a valid JSX element
  if (isLoading && !hasTimedOut) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  // A single feature is "granted" if the restaurant has the flag OR it's unlocked for the plan.
  const featureGranted = (f: string) =>
    Boolean((features as any)?.[f]) || !getFeatureAccessStatus(planType, f).isLocked

  const checkList = anyOf?.length ? anyOf : (feature ? [feature] : [])

  const hasAccess = Boolean(
    (requireGold && isGold) ||
    (!requireGold && checkList.length === 0) ||
    (checkList.length > 0 && checkList.some(featureGranted)) ||
    hasTimedOut
  )

  if (!hasAccess) {
    return <Navigate to="/feature-locked" state={{ from: location.pathname }} replace />
  }

  return <Outlet />
}
