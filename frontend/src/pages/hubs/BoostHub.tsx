import { lazy, Suspense } from 'react'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'

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
      <div>
        <h1 className="text-2xl font-bold">Boost</h1>
        <p className="text-sm text-muted-foreground">Run ads, launch new campaigns & redeem coupons</p>
      </div>
      <Tabs value={activeTab} onValueChange={setTab} className="w-full">
        <TabsList className="w-max max-w-full overflow-x-auto">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="new">New Campaign</TabsTrigger>
          <TabsTrigger value="redeem">Redeem Coupon</TabsTrigger>
        </TabsList>
      </Tabs>
      <Suspense fallback={<GenericPageSkeleton />}>
        {activeTab === 'overview' && <BoostOverview />}
        {activeTab === 'new' && <BoostNewCampaign />}
        {activeTab === 'redeem' && <BoostRedeem />}
      </Suspense>
    </div>
  )
}
