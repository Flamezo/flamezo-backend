import { lazy, Suspense } from 'react'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'

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
      <div>
        <h1 className="text-2xl font-bold">Loyalty</h1>
        <p className="text-sm text-muted-foreground">Reward rules & how they're performing</p>
      </div>
      <Tabs value={activeTab} onValueChange={setTab} className="w-full">
        <TabsList className="w-max max-w-full overflow-x-auto">
          <TabsTrigger value="settings">Settings</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>
      </Tabs>
      <Suspense fallback={<GenericPageSkeleton />}>
        {activeTab === 'settings' && <LoyaltySettings />}
        {activeTab === 'analytics' && <LoyaltyAnalytics />}
      </Suspense>
    </div>
  )
}
