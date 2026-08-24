import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOutlet } from '@/contexts/OutletContext'
import { useFrappeGetCall, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Eye, Heart, MessageCircle, Megaphone, Upload, TrendingUp, Image as ImageIcon, Film, AlignLeft, Play } from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface TopPost {
  id: string
  thumbnail: string
  description: string
  views: number
  likes: number
  comments: number
  published_at: string
}

interface AnalyticsData {
  total_posts: number
  total_views: number
  total_likes: number
  total_comments: number
  avg_views_per_post: number
  engagement_rate: number
  top_post: TopPost | null
}

interface PostRow {
  id: string
  post_type: 'text' | 'image' | 'video' | 'chills'
  content: string
  image_url?: string
  video_url?: string
  views_count: number
  likes_count: number
  comments_count: number
  creation: string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatDate(s: string): string {
  if (!s) return ''
  return new Date(s.replace(' ', 'T')).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
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

const PAGE = 'flamezo_backend.flamezo.api.merchant_clubs'

export default function ClubAnalytics() {
  const navigate = useNavigate()
  const { selectedOutlet, isLoading: outletLoading } = useOutlet()

  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null)
  const [allPosts, setAllPosts] = useState<PostRow[]>([])

  // Aggregate analytics
  const { data: analyticsRes, isLoading: analyticsLoading } = useFrappeGetCall(
    `${PAGE}.merchant_get_club_analytics`,
    selectedOutlet ? { outlet_id: selectedOutlet } : undefined,
    selectedOutlet ? `club-analytics-${selectedOutlet}` : undefined,
  )

  // All posts for per-post table (top 50)
  const { data: postsRes, isLoading: postsLoading } = useFrappePostCall(
    `${PAGE}.merchant_get_my_posts`,
    selectedOutlet ? { outlet_id: selectedOutlet, limit: 50 } : undefined,
    selectedOutlet ? `club-all-${selectedOutlet}` : undefined,
  )

  useEffect(() => {
    const body = (analyticsRes as any)?.message ?? analyticsRes
    if (body?.success && body.data) setAnalytics(body.data)
  }, [analyticsRes])

  useEffect(() => {
    const body = (postsRes as any)?.message ?? postsRes
    if (body?.success && body.data?.posts) setAllPosts(body.data.posts)
  }, [postsRes])

  if (outletLoading || analyticsLoading || postsLoading) return <div className="p-10 text-center"><TrendingUp className="animate-pulse mx-auto opacity-50" /></div>

  const noData = !analytics || analytics.total_posts === 0

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Club Talks Analytics</h1>
          <p className="text-sm text-muted-foreground">Performance overview for all your club posts</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => navigate('/club-talks/posts')}>
            <Megaphone className="h-4 w-4 mr-2" />
            My Posts
          </Button>
          <Button size="sm" onClick={() => navigate('/club-talks/upload')}>
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
            <p className="text-sm text-muted-foreground mt-1">Broadcast your first post to start tracking performance.</p>
          </div>
          <Button onClick={() => navigate('/club-talks/upload')}>
            <Upload className="h-4 w-4 mr-2" />
            Upload Post
          </Button>
        </div>
      ) : (
        <>
          {/* Top stat grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard label="Total Views" value={formatCount(analytics!.total_views)} sub={`${formatCount(analytics!.avg_views_per_post)} avg per post`} icon={Eye} accent />
            <StatCard label="Total Likes" value={formatCount(analytics!.total_likes)} icon={Heart} />
            <StatCard label="Total Comments" value={formatCount(analytics!.total_comments)} icon={MessageCircle} />
            <StatCard label="Total Posts" value={formatCount(analytics!.total_posts)} icon={Megaphone} />
          </div>

          {/* Engagement + top post */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Engagement breakdown */}
            <Card className="lg:col-span-2 p-4 space-y-4">
              <CardHeader className="p-0">
                <CardTitle className="text-sm font-medium">Engagement Breakdown</CardTitle>
              </CardHeader>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="rounded-xl border border-border p-4 space-y-1">
                  <Megaphone className="h-5 w-5 text-muted-foreground" />
                  <p className="text-2xl font-bold tabular-nums">{analytics!.total_posts}</p>
                  <p className="text-xs text-muted-foreground">Posts published</p>
                </div>
                <div className="rounded-xl border border-border p-4 space-y-1">
                  <Eye className="h-5 w-5 text-muted-foreground" />
                  <p className="text-2xl font-bold tabular-nums">{formatCount(analytics!.avg_views_per_post)}</p>
                  <p className="text-xs text-muted-foreground">Avg views per post</p>
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
                    { label: 'Comments', value: analytics!.total_comments, color: 'bg-blue-400' },
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

            {/* Top post */}
            {analytics!.top_post && (
              <Card className="p-4 space-y-3">
                <CardHeader className="p-0">
                  <CardTitle className="text-sm font-medium">Top Post</CardTitle>
                </CardHeader>
                {analytics!.top_post.thumbnail ? (
                  <div className="relative rounded-xl overflow-hidden aspect-[9/16] max-h-44 bg-black">
                    <img
                      src={analytics!.top_post.thumbnail}
                      alt="Top post media"
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                      <div className="h-9 w-9 rounded-full bg-black/40 flex items-center justify-center">
                        <Play className="h-4 w-4 text-white ml-0.5" />
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-xl bg-muted aspect-[9/16] max-h-44 flex items-center justify-center">
                    <AlignLeft className="h-8 w-8 text-muted-foreground" />
                  </div>
                )}
                <p className="text-xs text-muted-foreground line-clamp-2">
                  {analytics!.top_post.description || <span className="italic">No text content</span>}
                </p>
                <div className="flex items-center gap-3 flex-wrap">
                  {[
                    { icon: Eye, v: analytics!.top_post.views },
                    { icon: Heart, v: analytics!.top_post.likes },
                    { icon: MessageCircle, v: analytics!.top_post.comments },
                  ].map(({ icon: Icon, v }, i) => (
                    <span key={i} className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Icon className="h-3 w-3" />
                      {formatCount(v)}
                    </span>
                  ))}
                </div>
                <p className="text-[10px] text-muted-foreground">{formatDate(analytics!.top_post.published_at)}</p>
              </Card>
            )}
          </div>

          {/* Per-post performance table */}
          {allPosts.length > 0 && (
            <Card>
              <CardHeader className="px-4 py-3 border-b border-border">
                <CardTitle className="text-sm font-medium">All Posts Performance</CardTitle>
              </CardHeader>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted/30 text-xs text-muted-foreground">
                      <th className="text-left px-4 py-3 font-medium min-w-[220px]">Post</th>
                      <th className="text-right px-4 py-3 font-medium w-20">Views</th>
                      <th className="text-right px-4 py-3 font-medium w-20">Likes</th>
                      <th className="text-right px-4 py-3 font-medium w-20">Comments</th>
                      <th className="text-right px-4 py-3 font-medium w-24">Engagement</th>
                      <th className="text-right px-4 py-3 font-medium w-28">Published</th>
                    </tr>
                  </thead>
                  <tbody>
                    {allPosts.map((p) => {
                      const eng = p.views_count > 0
                        ? ((p.likes_count + p.comments_count) / p.views_count * 100).toFixed(1)
                        : '0.0'
                      
                      const mediaUrl = p.video_url || p.image_url
                      return (
                        <tr key={p.id} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-3">
                              {mediaUrl ? (
                                <img src={mediaUrl} alt="" className="h-10 w-16 rounded-md object-cover flex-shrink-0 bg-muted" />
                              ) : (
                                <div className="h-10 w-16 rounded-md bg-muted flex items-center justify-center flex-shrink-0">
                                  <AlignLeft className="h-4 w-4 text-muted-foreground" />
                                </div>
                              )}
                              <div className="min-w-0">
                                <p className="text-xs font-medium truncate max-w-[140px]">{p.content || '—'}</p>
                                <p className="text-[10px] text-muted-foreground font-mono">{p.id}</p>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-right tabular-nums font-medium">{formatCount(p.views_count)}</td>
                          <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">{formatCount(p.likes_count)}</td>
                          <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">{formatCount(p.comments_count)}</td>
                          <td className="px-4 py-3 text-right">
                            <Badge variant={parseFloat(eng) >= 5 ? 'default' : 'secondary'} className="text-[10px]">
                              {eng}%
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-right text-xs text-muted-foreground whitespace-nowrap">{formatDate(p.creation)}</td>
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
