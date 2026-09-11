import { lazy, Suspense } from 'react'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'
import HubHeader from '@/components/HubHeader'

const CreatorMarketplaceDiscover = lazy(() => import('../CreatorMarketplaceDiscover'))
const CreatorMarketplaceGigs = lazy(() => import('../CreatorMarketplaceGigs'))
const CreatorMarketplaceDeals = lazy(() => import('../CreatorMarketplaceDeals'))

const PATHS = {
  discover: '/creator-marketplace/discover',
  gigs: '/creator-marketplace/gigs',
  deals: '/creator-marketplace/deals',
}

export default function CreatorMarketplaceHub() {
  const { activeTab, setTab } = useHubTab(PATHS, 'discover')

  return (
    <div className="space-y-4">
      <HubHeader
        title="Creator & Collab"
        subtitle="Find creators, start collabs & track every deal from offer to payout"
        tabs={[
          { value: 'discover', label: 'Explore Creators' },
          { value: 'gigs', label: 'My Collabs' },
          { value: 'deals', label: 'Deals' },
        ]}
        activeTab={activeTab}
        onTabChange={setTab}
      />
      <Suspense fallback={<GenericPageSkeleton />}>
        {activeTab === 'discover' && <CreatorMarketplaceDiscover />}
        {activeTab === 'gigs' && <CreatorMarketplaceGigs />}
        {activeTab === 'deals' && <CreatorMarketplaceDeals />}
      </Suspense>
    </div>
  )
}
