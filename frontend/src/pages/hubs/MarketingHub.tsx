import { lazy, Suspense } from 'react'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'

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
      <div>
        <h1 className="text-2xl font-bold">Marketing Management</h1>
        <p className="text-sm text-muted-foreground">Campaigns, automation & segments</p>
      </div>
      <Tabs value={activeTab} onValueChange={setTab} className="w-full">
        <TabsList className="w-max max-w-full overflow-x-auto">
          <TabsTrigger value="performance">Performance</TabsTrigger>
          <TabsTrigger value="campaigns">Campaigns</TabsTrigger>
          <TabsTrigger value="automation">Automation</TabsTrigger>
          <TabsTrigger value="segments">Segments</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>
      </Tabs>
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
