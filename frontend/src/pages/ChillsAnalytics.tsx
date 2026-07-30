import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappeGetCall } from '@/lib/frappe'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Eye, Heart, Bookmark, Share2, Film, Upload, TrendingUp, Play } from 'lucide-react'
import { ChillsAnalyticsSkeleton } from '@/components/PageSkeletons'

// ── Types ─────────────────────────────────────────────────────────────────────

interface TopVideo {
  id: string
  thumbnail: string
  description: string
  views: number
  likes: number
  saves: number
  shares: number
  published_at: string
}

interface AnalyticsData {
  total_videos: number
  total_views: number
  total_likes: number
  total_saves: number
  total_shares: number
  avg_views_per_video: number
  engagement_rate: number
  top_video: TopVideo | null
}

interface VideoRow {
  id: string
  videoUrl: string
  thumbnail: string
  description: string
  views: number
  likes: number
  saves: number
  shares: number
  published_at: string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatDate(s: string): string {
  if (!s) return ''
  return new Date(s).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  accent,
}: {
  label: string
  value: string | number
  sub?: string
  icon: React.ElementType
  accent?: boolean
}) {
  return (
    <Card className={`p-4 ${accent ? 'border-primary/30 bg-primary/5' : ''}`}>
      <div className="flex items-center gap-2 text-muted-foreground mb-2">
        <Icon className={`h-4 w-4 ${accent ? 'text-primary' : ''}`} />
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className={`text-3xl font-bold tabular-nums ${accent ? 'text-primary' : ''}`}>{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
    </Card>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ChillsAnalytics() {
  const navigate = useNavigate()
  const { selectedRestaurant, isLoading: outletLoading } = useRestaurant()

  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null)
  const [allVideos, setAllVideos] = useState<VideoRow[]>([])

  // Aggregate analytics
  const { data: analyticsRes, isLoading: analyticsLoading } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.chills.get_chills_outlet_analytics',
    selectedRestaurant ? { outlet_id: selectedRestaurant } : undefined,
    selectedRestaurant ? `chills-analytics-${selectedRestaurant}` : undefined,
  )

  // All videos for per-video table (top 50)
  const { data: videosRes, isLoading: videosLoading } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.chills.get_merchant_chills',
    selectedRestaurant ? { outlet_id: selectedRestaurant, limit: 50 } : undefined,
    selectedRestaurant ? `chills-all-${selectedRestaurant}` : undefined,
  )

  useEffect(() => {
    const body = (analyticsRes as any)?.message ?? analyticsRes
    if (body?.success && body.data) setAnalytics(body.data)
  }, [analyticsRes])

  useEffect(() => {
    const body = (videosRes as any)?.message ?? videosRes
    if (body?.success && body.data?.videos) setAllVideos(body.data.videos)
  }, [videosRes])

  if (outletLoading || analyticsLoading || videosLoading) return <ChillsAnalyticsSkeleton />

  const noData = !analytics || analytics.total_videos === 0

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Chills Analytics</h1>
          <p className="text-sm text-muted-foreground">Performance overview for all your Chills videos</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => navigate('/chills/videos')}>
            <Film className="h-4 w-4 mr-2" />
            My Videos
          </Button>
          <Button size="sm" onClick={() => navigate('/chills/upload')}>
            <Upload className="h-4 w-4 mr-2" />
            Upload
          </Button>
        </div>
      </div>

      {noData ? (
        <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4">
          <div className="h-20 w-20 rounded-2xl bg-muted flex items-center justify-center">
            <TrendingUp className="h-10 w-10 text-muted-foreground" />
          </div>
          <div className="text-center">
            <p className="font-medium">No analytics yet</p>
            <p className="text-sm text-muted-foreground mt-1">Upload your first Chills video to start tracking performance.</p>
          </div>
          <Button onClick={() => navigate('/chills/upload')}>
            <Upload className="h-4 w-4 mr-2" />
            Upload Video
          </Button>
        </div>
      ) : (
        <>
          {/* Top stat grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard label="Total Views" value={formatCount(analytics!.total_views)} sub={`${formatCount(analytics!.avg_views_per_video)} avg per video`} icon={Eye} accent />
            <StatCard label="Total Likes" value={formatCount(analytics!.total_likes)} icon={Heart} />
            <StatCard label="Total Saves" value={formatCount(analytics!.total_saves)} icon={Bookmark} />
            <StatCard label="Total Shares" value={formatCount(analytics!.total_shares)} icon={Share2} />
          </div>

          {/* Engagement + top video */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Engagement breakdown */}
            <Card className="lg:col-span-2 p-4 space-y-4">
              <CardHeader className="p-0">
                <CardTitle className="text-sm font-medium">Engagement Breakdown</CardTitle>
              </CardHeader>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="rounded-xl border border-border p-4 space-y-1">
                  <Film className="h-5 w-5 text-muted-foreground" />
                  <p className="text-2xl font-bold tabular-nums">{analytics!.total_videos}</p>
                  <p className="text-xs text-muted-foreground">Videos published</p>
                </div>
                <div className="rounded-xl border border-border p-4 space-y-1">
                  <Eye className="h-5 w-5 text-muted-foreground" />
                  <p className="text-2xl font-bold tabular-nums">{formatCount(analytics!.avg_views_per_video)}</p>
                  <p className="text-xs text-muted-foreground">Avg views per video</p>
                </div>
                <div className="rounded-xl border border-border p-4 space-y-1">
                  <TrendingUp className="h-5 w-5 text-muted-foreground" />
                  <p className="text-2xl font-bold tabular-nums">{analytics!.engagement_rate}%</p>
                  <p className="text-xs text-muted-foreground">Engagement rate</p>
                </div>
              </div>

              {/* Interaction bar breakdown */}
              {analytics!.total_views > 0 && (
                <div className="space-y-3 pt-2">
                  {[
                    { label: 'Likes', value: analytics!.total_likes, color: 'bg-red-400' },
                    { label: 'Saves', value: analytics!.total_saves, color: 'bg-blue-400' },
                    { label: 'Shares', value: analytics!.total_shares, color: 'bg-green-400' },
                  ].map(({ label, value, color }) => {
                    const pct = analytics!.total_views > 0
                      ? Math.min(100, Math.round((value / analytics!.total_views) * 100))
                      : 0
                    return (
                      <div key={label} className="space-y-1">
                        <div className="flex justify-between text-xs text-muted-foreground">
                          <span>{label}</span>
                          <span>{formatCount(value)} ({pct}%)</span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                          <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </Card>

            {/* Top video */}
            {analytics!.top_video && (
              <Card className="p-4 space-y-3">
                <CardHeader className="p-0">
                  <CardTitle className="text-sm font-medium">Top Video</CardTitle>
                </CardHeader>
                {analytics!.top_video.thumbnail ? (
                  <div className="relative rounded-xl overflow-hidden aspect-[9/16] max-h-44 bg-black">
                    <img
                      src={analytics!.top_video.thumbnail}
                      alt="Top video"
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="h-9 w-9 rounded-full bg-black/40 flex items-center justify-center">
                        <Play className="h-4 w-4 text-white ml-0.5" />
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-xl bg-muted aspect-video flex items-center justify-center">
                    <Film className="h-8 w-8 text-muted-foreground" />
                  </div>
                )}
                <p className="text-xs text-muted-foreground line-clamp-2">
                  {analytics!.top_video.description || <span className="italic">No caption</span>}
                </p>
                <div className="flex items-center gap-3 flex-wrap">
                  {[
                    { icon: Eye, v: analytics!.top_video.views },
                    { icon: Heart, v: analytics!.top_video.likes },
                    { icon: Bookmark, v: analytics!.top_video.saves },
                    { icon: Share2, v: analytics!.top_video.shares },
                  ].map(({ icon: Icon, v }, i) => (
                    <span key={i} className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Icon className="h-3 w-3" />
                      {formatCount(v)}
                    </span>
                  ))}
                </div>
                <p className="text-[10px] text-muted-foreground">{formatDate(analytics!.top_video.published_at)}</p>
              </Card>
            )}
          </div>

          {/* Per-video performance table */}
          {allVideos.length > 0 && (
            <Card>
              <CardHeader className="px-4 py-3 border-b border-border">
                <CardTitle className="text-sm font-medium">All Videos Performance</CardTitle>
              </CardHeader>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted/30 text-xs text-muted-foreground">
                      <th className="text-left px-4 py-3 font-medium min-w-[220px]">Video</th>
                      <th className="text-right px-4 py-3 font-medium w-20">Views</th>
                      <th className="text-right px-4 py-3 font-medium w-20">Likes</th>
                      <th className="text-right px-4 py-3 font-medium w-20">Saves</th>
                      <th className="text-right px-4 py-3 font-medium w-20">Shares</th>
                      <th className="text-right px-4 py-3 font-medium w-24">Engagement</th>
                      <th className="text-right px-4 py-3 font-medium w-28">Published</th>
                    </tr>
                  </thead>
                  <tbody>
                    {allVideos.map((v) => {
                      const eng = v.views > 0
                        ? ((v.likes + v.saves) / v.views * 100).toFixed(1)
                        : '0.0'
                      return (
                        <tr key={v.id} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-3">
                              {v.thumbnail ? (
                                <img src={v.thumbnail} alt="" className="h-10 w-16 rounded-md object-cover flex-shrink-0 bg-muted" />
                              ) : (
                                <div className="h-10 w-16 rounded-md bg-muted flex items-center justify-center flex-shrink-0">
                                  <Film className="h-4 w-4 text-muted-foreground" />
                                </div>
                              )}
                              <div className="min-w-0">
                                <p className="text-xs font-medium truncate max-w-[140px]">{v.description || '—'}</p>
                                <p className="text-[10px] text-muted-foreground font-mono">{v.id}</p>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-right tabular-nums font-medium">{formatCount(v.views)}</td>
                          <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">{formatCount(v.likes)}</td>
                          <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">{formatCount(v.saves)}</td>
                          <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">{formatCount(v.shares)}</td>
                          <td className="px-4 py-3 text-right">
                            <Badge variant={parseFloat(eng) >= 5 ? 'default' : 'secondary'} className="text-[10px]">
                              {eng}%
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-right text-xs text-muted-foreground whitespace-nowrap">{formatDate(v.published_at)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
