import { lazy, Suspense } from 'react'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'
import HubHeader from '@/components/HubHeader'

const ChillsVideos = lazy(() => import('../ChillsVideos'))
const ChillsUpload = lazy(() => import('../ChillsUpload'))
const ChillsAnalytics = lazy(() => import('../ChillsAnalytics'))

const PATHS = {
  videos: '/chills/videos',
  upload: '/chills/upload',
  analytics: '/chills/analytics',
}

export default function ChillsHub() {
  const { activeTab, setTab } = useHubTab(PATHS, 'videos')

  return (
    <div className="space-y-4">
      <HubHeader
        title="Chills"
        subtitle="Short videos, uploads & analytics"
        tabs={[
          { value: 'videos', label: 'My Videos' },
          { value: 'upload', label: 'Upload Video' },
          { value: 'analytics', label: 'Analytics' },
        ]}
        activeTab={activeTab}
        onTabChange={setTab}
      />
      <Suspense fallback={<GenericPageSkeleton />}>
        {activeTab === 'videos' && <ChillsVideos />}
        {activeTab === 'upload' && <ChillsUpload />}
        {activeTab === 'analytics' && <ChillsAnalytics />}
      </Suspense>
    </div>
  )
}
