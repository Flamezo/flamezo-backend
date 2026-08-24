import { lazy, Suspense } from 'react'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'
import HubHeader from '@/components/HubHeader'

const LoyaltySettings = lazy(() => import('../LoyaltySettings'))
const LoyaltyAnalytics = lazy(() => import('../LoyaltyAnalytics'))

const PATHS = {
  settings: '/loyalty-settings',
  analytics: '/loyalty-analytics',
}

export default function LoyaltyHub() {
  const { activeTab, setTab } = useHubTab(PATHS, 'settings')

  return (
    <div className="space-y-4">
      <HubHeader
        title="Loyalty"
        subtitle="Reward rules & how they're performing"
        tabs={[
          { value: 'settings', label: 'Settings' },
          { value: 'analytics', label: 'Analytics' },
        ]}
        activeTab={activeTab}
        onTabChange={setTab}
      />
      <Suspense fallback={<GenericPageSkeleton />}>
        {activeTab === 'settings' && <LoyaltySettings />}
        {activeTab === 'analytics' && <LoyaltyAnalytics />}
      </Suspense>
    </div>
  )
}
