import { lazy, Suspense } from 'react'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'
import HubHeader from '@/components/HubHeader'

const BoostOverview = lazy(() => import('../BoostOverview'))
const BoostNewCampaign = lazy(() => import('../BoostNewCampaign'))
const BoostRedeem = lazy(() => import('../BoostRedeem'))

const PATHS = {
  overview: '/boost',
  new: '/boost/new',
  redeem: '/boost/redeem',
}

export default function BoostHub() {
  const { activeTab, setTab } = useHubTab(PATHS, 'overview')

  return (
    <div className="space-y-4">
      <HubHeader
        title="Boost"
        subtitle="Run ads, launch new campaigns & redeem coupons"
        tabs={[
          { value: 'overview', label: 'Overview' },
          { value: 'new', label: 'New Campaign' },
          { value: 'redeem', label: 'Redeem Coupon' },
        ]}
        activeTab={activeTab}
        onTabChange={setTab}
      />
      <Suspense fallback={<GenericPageSkeleton />}>
        {activeTab === 'overview' && <BoostOverview />}
        {activeTab === 'new' && <BoostNewCampaign />}
        {activeTab === 'redeem' && <BoostRedeem />}
      </Suspense>
    </div>
  )
}
