import { lazy, Suspense } from 'react'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'
import HubHeader from '@/components/HubHeader'

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
      <HubHeader
        title="UGC Cashback"
        subtitle="Configure the offer, approve story proofs & see results"
        tabs={[
          { value: 'config', label: 'Configure' },
          { value: 'approvals', label: 'Story Approvals' },
          { value: 'analytics', label: 'Analytics' },
        ]}
        activeTab={activeTab}
        onTabChange={setTab}
      />
      <Suspense fallback={<GenericPageSkeleton />}>
        {activeTab === 'config' && <UGCConfig />}
        {activeTab === 'approvals' && <UGCApprovals />}
        {activeTab === 'analytics' && <UGCAnalytics />}
      </Suspense>
    </div>
  )
}
