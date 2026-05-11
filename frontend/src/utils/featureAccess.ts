/**
 * Centralized Feature Access Control
 * 
 * Defines the mapping between features and subscription plans (SILVER/GOLD).
 */

export type PlanType = 'SILVER' | 'GOLD';

export const GOLD_ONLY_FEATURES = [
  'coupons',
  'pos_integration',
  'customer_pay_and_usage',
  'marketing_studio',
  'google_growth_sync',
  'google_growth_ai',
  'analytics',
  'ai_recommendations',
  'aiRecommendations', // mapping backend key
  'custom_branding',
  'customBranding', // mapping backend key
  'table_booking',
  'tableBooking', // mapping backend key
  'games',
  'events',
  'offers',
  'experience_lounge',
  'video_upload',
  'videoUpload', // mapping backend key
  'branding',
  'google_growth',
  'cart_milestones'
];

export const SILVER_FEATURES = [
  'ordering',
  'loyalty',
  'order_settings',
  'whatsapp_orders',
  'loyalty_insights',
  'customer'
];

/**
 * Checks if a feature is accessible for a given plan.
 * 
 * @param plan The restaurant's current plan
 * @param feature The feature key to check
 * @returns { isLocked: boolean, requiredTier: PlanType | null }
 */
export function getFeatureAccessStatus(plan: PlanType, feature?: string) {
  if (!feature) return { isLocked: false, requiredTier: null };

  const normalizedPlan = plan.toUpperCase() as PlanType;
  const isGold = normalizedPlan === 'GOLD';

  if (isGold) {
    return { isLocked: false, requiredTier: null };
  }

  // Check if it's explicitly a Silver feature
  if (SILVER_FEATURES.includes(feature)) {
    return { isLocked: false, requiredTier: null };
  }

  // Check if it's a Gold-only feature
  if (GOLD_ONLY_FEATURES.includes(feature)) {
    return { isLocked: true, requiredTier: 'GOLD' as PlanType };
  }

  // Default: if it's not explicitly Silver, assume it's Gold for safety
  // or if it's in the GOLD_FEATURES list from Layout.tsx
  return { isLocked: true, requiredTier: 'GOLD' as PlanType };
}
