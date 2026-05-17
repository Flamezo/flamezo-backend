import { Lock, Star } from 'lucide-react';
import { FeatureKey } from '../../utils/featureGate';
import { useRestaurant } from '../../contexts/RestaurantContext';
import { getFeatureAccessStatus } from '../../utils/featureAccess';

interface LockedFeatureProps {
  feature: FeatureKey;
  requiredPlan?: string[];
}

const FEATURE_LABELS: Record<string, string> = {
  ordering: 'Direct Online Ordering',
  video_upload: 'Video & Media Upload',
  analytics: 'Advanced Sales Analytics',
  ai_recommendations: 'AI Recommendations',
  loyalty: 'Loyalty & Rewards',
  coupons: 'Digital Coupons',
  pos_integration: 'POS Sync & Integration',
  data_export: 'Customer Data Export',
  games: 'Customer Engagement Games',
  table_booking: 'Table Reservations',
  custom_branding: 'Custom White-label Branding',
};

const FEATURE_DESCRIPTIONS: Record<string, string> = {
  ordering: 'Turn your menu into a revenue machine. Accept direct orders and payments.',
  loyalty: 'Build a fanbase. Reward your regulars and grow your customer database.',
  coupons: 'Run targeted campaigns. Create discounts to drive traffic during slow hours.',
  table_booking: 'Manage your floor like a pro. Enable customers to book tables in advance.',
  pos_integration: 'Synchronize your kitchen and billing. Connect directly with your POS system.',
};

export function LockedFeature({ feature }: LockedFeatureProps) {
  const { planType } = useRestaurant();
  const featureLabel = FEATURE_LABELS[feature] || feature;
  const description = FEATURE_DESCRIPTIONS[feature] || "Unlock this premium feature to automate your restaurant and grow your revenue.";
  
  const { requiredTier } = getFeatureAccessStatus(planType, feature);
  const isGoldOnly = requiredTier === 'GOLD';

  return (
    <div className="flex flex-col items-center justify-center p-12 bg-white rounded-2xl border border-gray-200 shadow-sm max-w-2xl mx-auto my-8">
      <div className={`flex items-center justify-center w-20 h-20 ${isGoldOnly ? 'bg-amber-50/50' : 'bg-gray-50'} rounded-full mb-6 relative`}>
        {isGoldOnly ? (
          <div className="relative">
            <Lock className="w-10 h-10 text-muted-foreground/40" />
            <Star className="w-6 h-6 text-amber-500 absolute -top-1 -right-1 fill-amber-500 stroke-white stroke-2" />
          </div>
        ) : (
          <Lock className="w-10 h-10 text-muted-foreground/60" />
        )}
      </div>
      
      <div className={`inline-flex items-center space-x-2 px-3 py-1 ${isGoldOnly ? 'bg-indigo-100/50 text-indigo-700' : 'bg-gray-100 text-gray-700'} rounded-full text-xs font-bold uppercase tracking-wider mb-4`}>
        {isGoldOnly ? <Star className="w-3 h-3 text-amber-500" /> : <Lock className="w-3 h-3 text-gray-500" />}
        <span>{requiredTier} Feature</span>
      </div>

      <h3 className="text-2xl font-bold text-gray-900 mb-3">
        {featureLabel} is Archived
      </h3>
      
      <p className="text-gray-600 text-center mb-8 leading-relaxed max-w-md">
        {description} Your past data and access are safely stored. Upgrade to **{requiredTier}** to unlock your full potential.
      </p>

      <div className="grid grid-cols-1 gap-4 w-full max-w-sm">
        <button
          onClick={() => {
            window.location.href = '/flamezo_backend/autopay-setup';
          }}
          className={`w-full px-8 py-4 ${isGoldOnly ? 'bg-indigo-600 hover:bg-indigo-700' : 'bg-gray-900 hover:bg-black'} text-white font-bold rounded-xl transition-all shadow-lg hover:shadow-xl active:scale-95 flex items-center justify-center space-x-2`}
        >
          <span>Upgrade to {requiredTier} Plan</span>
        </button>
        
        <button
          onClick={() => {
            window.location.href = '/support';
          }}
          className="w-full px-8 py-3 bg-white text-gray-600 font-medium rounded-xl border border-gray-200 hover:bg-gray-50 transition-all text-sm"
        >
          Talk to sales
        </button>
      </div>
      
      <p className="mt-8 text-xs text-gray-400">
        Current Plan: <span className="font-semibold">{planType}</span>
      </p>
    </div>
  );
}
