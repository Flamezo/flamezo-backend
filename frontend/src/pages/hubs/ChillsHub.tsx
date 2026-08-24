import { lazy, Suspense } from 'react'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { useHubTab } from '@/lib/useHubTab'

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
      <div>
        <h1 className="text-2xl font-bold">Chills</h1>
        <p className="text-sm text-muted-foreground">Short videos, uploads & analytics</p>
      </div>
      <Tabs value={activeTab} onValueChange={setTab} className="w-full">
        <TabsList className="w-max max-w-full overflow-x-auto">
          <TabsTrigger value="videos">My Videos</TabsTrigger>
          <TabsTrigger value="upload">Upload Video</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>
      </Tabs>
      <Suspense fallback={<GenericPageSkeleton />}>
        {activeTab === 'videos' && <ChillsVideos />}
        {activeTab === 'upload' && <ChillsUpload />}
        {activeTab === 'analytics' && <ChillsAnalytics />}
      </Suspense>
    </div>
  )
}
