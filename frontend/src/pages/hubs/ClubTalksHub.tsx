import { lazy, Suspense } from 'react'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'

// Reuses the exact same page components the old separate sidebar rows
// pointed at — nothing about how each tab works has changed, only how
// they're reached. Lazy so switching tabs doesn't pay for the other two
// tabs' code/data until you actually open them.
const ClubTalks = lazy(() => import('../ClubTalks'))
const ClubUpload = lazy(() => import('../ClubUpload'))
const ClubAnalytics = lazy(() => import('../ClubAnalytics'))

const PATHS = {
  posts: '/club-talks/posts',
  upload: '/club-talks/upload',
  analytics: '/club-talks/analytics',
}

export default function ClubTalksHub() {
  const { activeTab, setTab } = useHubTab(PATHS, 'posts')

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Club Talks</h1>
        <p className="text-sm text-muted-foreground">Posts, uploads & analytics for your Club Talks feed</p>
      </div>
      <Tabs value={activeTab} onValueChange={setTab} className="w-full">
        <TabsList className="w-max max-w-full overflow-x-auto">
          <TabsTrigger value="posts">My Posts</TabsTrigger>
          <TabsTrigger value="upload">Upload Post</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>
      </Tabs>
      <Suspense fallback={<GenericPageSkeleton />}>
        {activeTab === 'posts' && <ClubTalks />}
        {activeTab === 'upload' && <ClubUpload />}
        {activeTab === 'analytics' && <ClubAnalytics />}
      </Suspense>
    </div>
  )
}
