/**
 * Feature Gate Utilities
 *
 * Under the single-tier (GOLD-only) model every restaurant has access to every
 * feature on day one. These helpers are retained as no-op stubs for backwards
 * compatibility with existing call sites and always report unlocked.
 */

export interface FeatureAccess {
  hasAccess: boolean;
  currentPlan: 'GOLD';
  requiredPlans: string[];
  feature: string;
}

export const FEATURES = {
  ORDERING: 'ordering',
  VIDEO_UPLOAD: 'video_upload',
  ANALYTICS: 'analytics',
  AI_RECOMMENDATIONS: 'ai_recommendations',
  LOYALTY: 'loyalty',
  COUPONS: 'coupons',
  POS_INTEGRATION: 'pos_integration',
  DATA_EXPORT: 'data_export',
  GAMES: 'games',
  TABLE_BOOKING: 'table_booking',
  CUSTOM_BRANDING: 'custom_branding',
  CUSTOMER: 'customer',
  EXPERIENCE_LOUNGE: 'experience_lounge',
  EVENTS: 'events',
  OFFERS: 'offers',
} as const;

export type FeatureKey = typeof FEATURES[keyof typeof FEATURES];

export async function checkFeatureAccess(
  _restaurantId: string,
  feature: FeatureKey,
): Promise<FeatureAccess> {
  return {
    hasAccess: true,
    currentPlan: 'GOLD',
    requiredPlans: ['GOLD'],
    feature,
  };
}

export async function getRestaurantPlan(_restaurantId: string) {
  return { plan_type: 'GOLD' };
}

export async function getUpgradeBenefits(_restaurantId: string) {
  return null;
}
