import { lazy, Suspense } from 'react'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'
import HubHeader from '@/components/HubHeader'

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
      <HubHeader
        title="Club Talks"
        subtitle="Posts, uploads & analytics for your Club Talks feed"
        tabs={[
          { value: 'posts', label: 'My Posts' },
          { value: 'upload', label: 'Upload Post' },
          { value: 'analytics', label: 'Analytics' },
        ]}
        activeTab={activeTab}
        onTabChange={setTab}
      />
      <Suspense fallback={<GenericPageSkeleton />}>
        {activeTab === 'posts' && <ClubTalks />}
        {activeTab === 'upload' && <ClubUpload />}
        {activeTab === 'analytics' && <ClubAnalytics />}
      </Suspense>
    </div>
  )
}
