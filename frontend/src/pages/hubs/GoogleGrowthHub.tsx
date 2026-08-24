import { lazy, Suspense } from 'react'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'
import HubHeader from '@/components/HubHeader'

const GoogleGrowth = lazy(() => import('../GoogleGrowth'))
const GoogleGrowthReviews = lazy(() => import('../GoogleGrowthReviews'))

const PATHS = {
  discovery: '/google-growth',
  reviews: '/google-growth/reviews',
}

export default function GoogleGrowthHub() {
  const { activeTab, setTab } = useHubTab(PATHS, 'discovery')

  return (
    <div className="space-y-4">
      <HubHeader
        title="Google Growth"
        subtitle="Discovery Loop & AI-assisted review replies"
        tabs={[
          { value: 'discovery', label: 'Discovery Loop' },
          { value: 'reviews', label: 'Reviews & AI Reply' },
        ]}
        activeTab={activeTab}
        onTabChange={setTab}
      />
      <Suspense fallback={<GenericPageSkeleton />}>
        {activeTab === 'discovery' && <GoogleGrowth />}
        {activeTab === 'reviews' && <GoogleGrowthReviews />}
      </Suspense>
    </div>
  )
}
