/**
 * Feature Gate Utilities
 * 
 * Provides utilities for checking feature access based on subscription plans
 */

export interface FeatureAccess {
  hasAccess: boolean;
  currentPlan: 'SILVER' | 'GOLD';
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
  CART_MILESTONES: 'cart_milestones',
} as const;

export type FeatureKey = typeof FEATURES[keyof typeof FEATURES];

/**
 * Check if a feature is accessible based on subscription plan
 */
export async function checkFeatureAccess(
  restaurantId: string,
  feature: FeatureKey
): Promise<FeatureAccess> {
  try {
    const response = await fetch('/api/method/dinematters.api.subscription.check_access', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': (window as any).csrf_token || '',
      },
      body: JSON.stringify({
        restaurant_id: restaurantId,
        feature_name: feature,
      }),
    });

    if (!response.ok) {
      throw new Error('Failed to check feature access');
    }

    const data = await response.json();
    return data.message;
  } catch (error) {
    console.error('Error checking feature access:', error);
    // Default to no access on error
    return {
      hasAccess: false,
      currentPlan: 'SILVER',
      requiredPlans: ['GOLD', 'GOLD'],
      feature,
    };
  }
}

/**
 * Get restaurant plan information
 */
export async function getRestaurantPlan(restaurantId: string) {
  try {
    const response = await fetch('/api/method/dinematters.api.subscription.get_restaurant_plan', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': (window as any).csrf_token || '',
      },
      body: JSON.stringify({
        restaurant_id: restaurantId,
      }),
    });

    if (!response.ok) {
      throw new Error('Failed to get restaurant plan');
    }

    const data = await response.json();
    return data.message;
  } catch (error) {
    console.error('Error getting restaurant plan:', error);
    return null;
  }
}

/**
 * Get upgrade benefits for a restaurant
 */
export async function getUpgradeBenefits(restaurantId: string) {
  try {
    const response = await fetch('/api/method/dinematters.api.subscription.get_upgrade_benefits', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': (window as any).csrf_token || '',
      },
      body: JSON.stringify({
        restaurant_id: restaurantId,
      }),
    });

    if (!response.ok) {
      throw new Error('Failed to get upgrade benefits');
    }

    const data = await response.json();
    return data.message;
  } catch (error) {
    console.error('Error getting upgrade benefits:', error);
    return null;
  }
}
