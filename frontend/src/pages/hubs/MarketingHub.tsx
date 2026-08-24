import { lazy, Suspense } from 'react'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'
import HubHeader from '@/components/HubHeader'

const MarketingOverview = lazy(() => import('../MarketingOverview'))
const MarketingCampaigns = lazy(() => import('../MarketingCampaigns'))
const MarketingAutomation = lazy(() => import('../MarketingAutomation'))
const MarketingSegments = lazy(() => import('../MarketingSegments'))
const MarketingAnalytics = lazy(() => import('../MarketingAnalytics'))

const PATHS = {
  performance: '/marketing',
  campaigns: '/marketing/campaigns',
  automation: '/marketing/automation',
  segments: '/marketing/segments',
  analytics: '/marketing/analytics',
}

export default function MarketingHub() {
  const { activeTab, setTab } = useHubTab(PATHS, 'performance')

  return (
    <div className="space-y-4">
      <HubHeader
        title="Marketing Management"
        subtitle="Campaigns, automation & segments"
        tabs={[
          { value: 'performance', label: 'Performance' },
          { value: 'campaigns', label: 'Campaigns' },
          { value: 'automation', label: 'Automation' },
          { value: 'segments', label: 'Segments' },
          { value: 'analytics', label: 'Analytics' },
        ]}
        activeTab={activeTab}
        onTabChange={setTab}
      />
      <Suspense fallback={<GenericPageSkeleton />}>
        {activeTab === 'performance' && <MarketingOverview />}
        {activeTab === 'campaigns' && <MarketingCampaigns />}
        {activeTab === 'automation' && <MarketingAutomation />}
        {activeTab === 'segments' && <MarketingSegments />}
        {activeTab === 'analytics' && <MarketingAnalytics />}
      </Suspense>
    </div>
  )
}
