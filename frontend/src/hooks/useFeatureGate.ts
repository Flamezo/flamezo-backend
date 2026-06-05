/**
 * useFeatureGate Hook
 *
 * Under the single-tier (GOLD-only) model every feature is unlocked for every
 * restaurant, so this hook reports `hasAccess: true` synchronously. The
 * signature is preserved for the many components that already import it.
 */

import { FeatureAccess, FeatureKey } from '../utils/featureGate';

export function useFeatureGate(feature: FeatureKey, _restaurantId?: string) {
  const access: FeatureAccess = {
    hasAccess: true,
    currentPlan: 'GOLD',
    requiredPlans: ['GOLD'],
    feature,
  };
  return { access, loading: false };
}

export function usePlanType(_restaurantId?: string) {
  return {
    planType: 'GOLD' as const,
    isGold: true,
    loading: false,
  };
}
