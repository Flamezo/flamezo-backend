import { lazy, Suspense } from 'react'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'

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
      <div>
        <h1 className="text-2xl font-bold">Google Growth</h1>
        <p className="text-sm text-muted-foreground">Discovery Loop & AI-assisted review replies</p>
      </div>
      <Tabs value={activeTab} onValueChange={setTab} className="w-full">
        <TabsList className="w-max max-w-full overflow-x-auto">
          <TabsTrigger value="discovery">Discovery Loop</TabsTrigger>
          <TabsTrigger value="reviews">Reviews & AI Reply</TabsTrigger>
        </TabsList>
      </Tabs>
      <Suspense fallback={<GenericPageSkeleton />}>
        {activeTab === 'discovery' && <GoogleGrowth />}
        {activeTab === 'reviews' && <GoogleGrowthReviews />}
      </Suspense>
    </div>
  )
}
