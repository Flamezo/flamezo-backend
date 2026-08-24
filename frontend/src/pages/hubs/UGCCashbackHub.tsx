import { lazy, Suspense } from 'react'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'

const UGCConfig = lazy(() => import('../UGCConfig'))
const UGCApprovals = lazy(() => import('../UGCApprovals'))
const UGCAnalytics = lazy(() => import('../UGCAnalytics'))

const PATHS = {
  config: '/ugc-cashback/config',
  approvals: '/ugc-cashback/approvals',
  analytics: '/ugc-cashback/analytics',
}

export default function UGCCashbackHub() {
  const { activeTab, setTab } = useHubTab(PATHS, 'config')

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">UGC Cashback</h1>
        <p className="text-sm text-muted-foreground">Configure the offer, approve story proofs & see results</p>
      </div>
      <Tabs value={activeTab} onValueChange={setTab} className="w-full">
        <TabsList className="w-max max-w-full overflow-x-auto">
          <TabsTrigger value="config">Configure</TabsTrigger>
          <TabsTrigger value="approvals">Story Approvals</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>
      </Tabs>
      <Suspense fallback={<GenericPageSkeleton />}>
        {activeTab === 'config' && <UGCConfig />}
        {activeTab === 'approvals' && <UGCApprovals />}
        {activeTab === 'analytics' && <UGCAnalytics />}
      </Suspense>
    </div>
  )
}
