import { lazy, Suspense } from 'react'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'

const CreatorMarketplaceDiscover = lazy(() => import('../CreatorMarketplaceDiscover'))
const CreatorMarketplaceGigs = lazy(() => import('../CreatorMarketplaceGigs'))
const CreatorMarketplaceDeals = lazy(() => import('../CreatorMarketplaceDeals'))

const PATHS = {
  discover: '/creator-marketplace/discover',
  gigs: '/creator-marketplace/gigs',
  deals: '/creator-marketplace/deals',
}

// No in-page tab switcher here on purpose — unlike the other hubs (Chills,
// UGC, Loyalty, ...), Creator & Collab's three sections are each their own
// row in the sidebar (see industryConfig.ts's creatorCollabsGroup), so a
// second tab bar above the page would just duplicate that navigation.
// useHubTab still does the real job: reading which of the three routes is
// active so the right page renders.
export default function CreatorMarketplaceHub() {
  const { activeTab } = useHubTab(PATHS, 'discover')

  return (
    <Suspense fallback={<GenericPageSkeleton />}>
      {activeTab === 'discover' && <CreatorMarketplaceDiscover />}
      {activeTab === 'gigs' && <CreatorMarketplaceGigs />}
      {activeTab === 'deals' && <CreatorMarketplaceDeals />}
    </Suspense>
  )
}
