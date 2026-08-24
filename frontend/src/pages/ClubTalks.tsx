import { useState, useEffect, useCallback, useRef, type ElementType } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOutlet } from '@/contexts/OutletContext'
import { useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { toast } from 'sonner'
import {
  Eye, MessageCircle, Heart, Trash2, Upload, BarChart3,
  Loader2, ChevronDown, Megaphone,
  Play, Share2, MapPin, Phone
} from 'lucide-react'
import { ClubPost } from '@/components/clubtalks/ClubPostCard'
import StatTiles from '@/components/StatTiles'
import ClubPostDetail from '@/components/clubtalks/ClubPostDetail'

// ── MOCK engagement (placeholder until real app data flows) ──────────────────
// Deterministic per post id so numbers stay stable across renders. Only fills in
// when the real count is 0. To revert: delete these two fns and the .map(withMockCounts)
// call in load(), and pass posts through untouched.
function hashNum(seed: string, min: number, max: number): number {
  let h = 2166136261
  for (let i = 0; i < seed.length; i++) { h ^= seed.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0 }
  return min + (h % (max - min + 1))
}
function withMockCounts(p: ClubPost): ClubPost {
  return {
    ...p,
    views_count: p.views_count || hashNum(p.id + 'v', 300, 6000),
    likes_count: p.likes_count || hashNum(p.id + 'l', 25, 500),
    comments_count: p.comments_count || hashNum(p.id + 'c', 2, 90),
  }
}

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatDate(s: string): string {
  if (!s) return ''
  const d = new Date(s.replace(' ', 'T'))
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

function StatChip({ icon: Icon, value }: { icon: ElementType; value: number }) {
  return (
    <span className="flex items-center gap-1 text-xs text-muted-foreground">
      <Icon className="h-3 w-3" />
      {formatCount(value)}
    </span>
  )
}

function PostCard({
  post,
  onDelete,
  onOpen,
  onShare,
  deleting,
}: {
  post: ClubPost
  onDelete: (id: string) => void
  onOpen: (post: ClubPost) => void
  onShare: (post: ClubPost) => void
  deleting: boolean
}) {
  const [hovered, setHovered] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)

  const isVideo = post.post_type === 'video' || !!post.chills?.videoUrl
  const mediaUrl = post.video_url || post.chills?.videoUrl || post.image_url

  const handleMouseEnter = () => {
    setHovered(true)
    videoRef.current?.play().catch(() => {})
  }
  const handleMouseLeave = () => {
    setHovered(false)
    if (videoRef.current) {
      videoRef.current.pause()
      videoRef.current.currentTime = 0
    }
  }

  return (
    <Card className="overflow-hidden group flex flex-col h-full">
      {/* Top block — media for image/video posts, a readable text block for text posts */}
      {mediaUrl ? (
        <div
          className="relative bg-black aspect-[9/16] max-h-56 overflow-hidden cursor-pointer"
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
          onClick={() => onOpen(post)}
        >
          {isVideo ? (
            <>
              <video
                ref={videoRef}
                src={mediaUrl}
                className={`w-full h-full object-cover transition-opacity duration-200 ${hovered ? 'opacity-100' : 'opacity-80'}`}
                muted
                loop
                playsInline
                preload="metadata"
              />
              {!hovered && (
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <div className="h-10 w-10 rounded-full bg-black/40 flex items-center justify-center">
                    <Play className="h-5 w-5 text-white ml-0.5" />
                  </div>
                </div>
              )}
            </>
          ) : (
            <img src={mediaUrl} className="w-full h-full object-cover transition-opacity duration-200" alt="" />
          )}
          <div className="absolute top-2 left-2 z-10">
            <span className="inline-flex items-center rounded-full bg-[#E23744] px-2 py-0.5 text-[10px] font-semibold text-white">published</span>
          </div>
        </div>
      ) : (
        <div
          className="relative cursor-pointer bg-gradient-to-br from-muted/40 to-muted/80 p-4 pt-8 min-h-[9rem] flex items-start"
          onClick={() => onOpen(post)}
        >
          <p className="text-sm font-medium leading-relaxed text-foreground line-clamp-6 whitespace-pre-wrap break-words">
            {post.content || <span className="italic opacity-50">No caption</span>}
          </p>
          <div className="absolute top-2 left-2 z-10">
            <span className="inline-flex items-center rounded-full bg-[#E23744] px-2 py-0.5 text-[10px] font-semibold text-white">published</span>
          </div>
        </div>
      )}

      <CardContent className="p-3 space-y-2 flex flex-col flex-1">
        {/* Caption below the media (text posts already show it in the block above) */}
        {mediaUrl && (
          <p className="text-xs text-muted-foreground line-clamp-2 min-h-[2rem]">
            {post.content || <span className="italic opacity-50">No caption</span>}
          </p>
        )}

        {/* Tag chips */}
        {(post.nicheTags?.length || post.customTags?.length) ? (
          <div className="flex flex-wrap gap-1">
            {(post.nicheTags ?? []).map((id) => (
              <span
                key={id}
                className="inline-flex items-center rounded-full bg-primary/10 border border-primary/20 px-2 py-0.5 text-[10px] font-medium text-primary"
              >
                {id}
              </span>
            ))}
            {(post.customTags ?? []).map((t) => (
              <span
                key={t}
                className="inline-flex items-center rounded-full bg-muted border border-border px-2 py-0.5 text-[10px] font-medium text-foreground"
              >
                {t}
              </span>
            ))}
          </div>
        ) : null}

        {/* Location chip */}
        {post.location?.name && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <MapPin className="h-3 w-3 shrink-0" />
            <span className="truncate">{post.location.name}</span>
          </div>
        )}

        {/* Stats row */}
        <div className="flex items-center gap-3 flex-wrap mt-auto">
          <StatChip icon={Eye} value={post.views_count || 0} />
          <StatChip icon={Heart} value={post.likes_count || 0} />
          <StatChip icon={MessageCircle} value={post.comments_count || 0} />
        </div>

        <p className="text-[10px] text-muted-foreground">{formatDate(post.created_at)}</p>

        {/* Actions */}
        <div className="flex gap-2 pt-1 border-t mt-2">
          <Button
            variant="ghost"
            size="sm"
            className="flex-1 h-7 text-xs"
            onClick={() => onOpen(post)}
          >
            <Eye className="h-3 w-3 mr-1" />
            View
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-foreground"
            title="Share"
            onClick={() => onShare(post)}
          >
            <Share2 className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-destructive"
            onClick={() => onDelete(post.id)}
            disabled={deleting}
          >
            {deleting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

const PAGE = 'flamezo_backend.flamezo.api.merchant_clubs'

export default function ClubTalks() {
  const navigate = useNavigate()
  const { selectedOutlet } = useOutlet()

  const [posts, setPosts] = useState<ClubPost[]>([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [detailPost, setDetailPost] = useState<ClubPost | null>(null)
  const [needsPhone, setNeedsPhone] = useState(false)

  const { call: getMyPosts } = useFrappePostCall(`${PAGE}.merchant_get_my_posts`)
  const { call: deletePostCall } = useFrappePostCall(`${PAGE}.merchant_delete_post`)

  const load = useCallback(async (p: number, overwrite = false) => {
    if (!selectedOutlet) return
    setLoading(true)
    try {
      const res: any = await getMyPosts({ outlet_id: selectedOutlet, page: p, limit: 15 })
      const data = (res?.message || res)?.data
      const fresh: ClubPost[] = (data?.posts || []).map(withMockCounts)  // MOCK: placeholder counts
      setPosts(prev => (overwrite ? fresh : [...prev, ...fresh]))
      setHasMore(!!data?.has_more)
      setNeedsPhone(!!data?.needs_phone)
      setPage(p)
    } catch (e: any) {
      toast.error(e.message || 'Could not load your posts')
    } finally {
      setLoading(false)
    }
  }, [selectedOutlet, getMyPosts])

  useEffect(() => {
    if (selectedOutlet) load(1, true)
  }, [selectedOutlet, load])

  const handleShare = useCallback(async (post: ClubPost) => {
    const url = `https://flamezo.in/club/${post.club_id}`
    const text = `${post.content ? post.content + '\n\n' : ''}via ${post.club_name || 'Flamezo'} 🔥\n${url}`
    try {
      if (navigator.share) await navigator.share({ text })
      else { await navigator.clipboard.writeText(text); toast.success('Link copied') }
    } catch { /* user dismissed the share sheet */ }
  }, [])

  const handleDelete = useCallback(async () => {
    if (!deleteTarget || !selectedOutlet) return
    setDeletingId(deleteTarget)
    setDeleteTarget(null)
    try {
      await deletePostCall({ outlet_id: selectedOutlet, post_id: deleteTarget })
      setPosts((prev) => prev.filter((p) => p.id !== deleteTarget))
      toast.success('Post deleted.')
    } catch {
      toast.error('Failed to delete post.')
    } finally {
      setDeletingId(null)
    }
  }, [deleteTarget, selectedOutlet, deletePostCall])

  if (!selectedOutlet) {
    return <div className="p-8 text-center text-muted-foreground">Select an outlet to use Club Talks.</div>
  }

  const totalViews = posts.reduce((s, p) => s + p.views_count, 0)
  const totalLikes = posts.reduce((s, p) => s + p.likes_count, 0)
  const totalComments = posts.reduce((s, p) => s + p.comments_count, 0)

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <Megaphone className="h-5 w-5" style={{ color: '#E23744' }} />
            My Club Posts
          </h1>
          <p className="text-sm text-muted-foreground">{posts.length} post{posts.length !== 1 ? 's' : ''} published</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => navigate('/club-talks/analytics')}>
            <BarChart3 className="h-4 w-4 mr-2" />
            Analytics
          </Button>
          <Button size="sm" onClick={() => navigate('/club-talks/upload')} disabled={needsPhone}>
            <Upload className="h-4 w-4 mr-2" />
            New Post
          </Button>
        </div>
      </div>

      {/* Needs owner phone before posting */}
      {needsPhone && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-300/50 bg-amber-50 dark:bg-amber-950/20 p-4">
          <Phone className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium text-amber-800 dark:text-amber-300">Add your outlet's phone number first</p>
            <p className="text-amber-700/80 dark:text-amber-400/80">
              Club Talks needs your outlet's owner phone number before you can post. Add it in your outlet settings, then come back.
            </p>
          </div>
        </div>
      )}

      {/* Quick stats (from loaded page, not full analytics but useful overview) */}
      {posts.length > 0 && (
        <StatTiles
          stats={[
            { label: 'Total Views', value: formatCount(totalViews), icon: Eye },
            { label: 'Total Likes', value: formatCount(totalLikes), icon: Heart },
            { label: 'Total Comments', value: formatCount(totalComments), icon: MessageCircle },
            { label: 'Total Posts', value: formatCount(posts.length), icon: Megaphone },
          ]}
        />
      )}

      {/* Empty state */}
      {posts.length === 0 && !loading && (
        <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4">
          <div className="h-20 w-20 rounded-2xl bg-muted flex items-center justify-center">
            <Megaphone className="h-10 w-10 text-muted-foreground opacity-50" />
          </div>
          <div className="text-center">
            <p className="font-medium">No posts yet</p>
            <p className="text-sm text-muted-foreground mt-1">Share an update, photo, or video.</p>
          </div>
          <Button onClick={() => navigate('/club-talks/upload')}>
            <Upload className="h-4 w-4 mr-2" />
            New Post
          </Button>
        </div>
      )}

      {/* Loading state */}
      {posts.length === 0 && loading && (
        <div className="py-16 text-center">
          <Loader2 className="h-6 w-6 animate-spin mx-auto text-muted-foreground" />
        </div>
      )}

      {/* Post grid */}
      {posts.length > 0 && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {posts.map((p) => (
              <PostCard
                key={p.id}
                post={p}
                onDelete={(id) => setDeleteTarget(id)}
                onOpen={setDetailPost}
                onShare={handleShare}
                deleting={deletingId === p.id}
              />
            ))}
          </div>

          {hasMore && (
            <div className="flex justify-center pt-4">
              <Button variant="outline" onClick={() => load(page + 1)} disabled={loading}>
                {loading ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <ChevronDown className="h-4 w-4 mr-2" />
                )}
                Load more
              </Button>
            </div>
          )}
        </>
      )}

      {/* Post detail — opens on click (works for text posts too) */}
      <ClubPostDetail
        outletId={selectedOutlet}
        post={detailPost}
        onClose={() => setDetailPost(null)}
        onDelete={(p) => setDeleteTarget(p.id)}
        onCommentDelta={(id, delta) =>
          setPosts((prev) => prev.map((p) => p.id === id ? { ...p, comments_count: Math.max(0, p.comments_count + delta) } : p))}
      />

      {/* Delete confirmation */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this post?</AlertDialogTitle>
            <AlertDialogDescription>
              This post will be permanently removed from Club Talks. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={handleDelete}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
