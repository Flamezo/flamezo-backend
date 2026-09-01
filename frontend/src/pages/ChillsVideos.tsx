import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOutlet } from '@/contexts/OutletContext'
import { useFrappeGetCall, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent } from '@/components/ui/card'
import StatTiles from '@/components/StatTiles'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet'
import { toast } from 'sonner'
import {
  Eye, Heart, Bookmark, Share2, Trash2, Upload, BarChart3,
  Play, Loader2, Film, ChevronDown, Tag, MapPin,
} from 'lucide-react'
import { ChillsVideosSkeleton } from '@/components/PageSkeletons'
import ChillsTagPicker from '@/components/ChillsTagPicker'
import ChillsLocationPicker, { type ChillsLocationValue } from '@/components/ChillsLocationPicker'
import { findNode } from '@/lib/niche-taxonomy'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ChillsVideo {
  id: string
  videoUrl: string
  thumbnail: string
  description: string
  audio: string
  nicheTags: string[]
  customTags: string[]
  location: ChillsLocationValue | null
  views: number
  likes: number
  saves: number
  shares: number
  status: string
  published_at: string
}

interface ChillsListResponse {
  videos: ChillsVideo[]
  next_cursor: string | null
  has_more: boolean
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatDate(s: string): string {
  if (!s) return ''
  const d = new Date(s)
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

// ── Stat chip ─────────────────────────────────────────────────────────────────

function StatChip({ icon: Icon, value }: { icon: React.ElementType; value: number }) {
  return (
    <span className="flex items-center gap-1 text-xs text-muted-foreground">
      <Icon className="h-3 w-3" />
      {formatCount(value)}
    </span>
  )
}

// ── Video card ────────────────────────────────────────────────────────────────

function VideoCard({
  video,
  onDelete,
  onEditTags,
  onEditLocation,
  deleting,
}: {
  video: ChillsVideo
  onDelete: (id: string) => void
  onEditTags: (video: ChillsVideo) => void
  onEditLocation: (video: ChillsVideo) => void
  deleting: boolean
}) {
  const [hovered, setHovered] = useState(false)
  const [captionExpanded, setCaptionExpanded] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)

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
    <Card className="overflow-hidden group">
      {/* Thumbnail / video preview */}
      <div
        className="relative bg-black aspect-[9/16] max-h-56 overflow-hidden cursor-pointer"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        {video.thumbnail ? (
          <img
            src={video.thumbnail}
            alt={video.description || 'Chills video'}
            className={`w-full h-full object-cover transition-opacity duration-200 ${hovered ? 'opacity-0' : 'opacity-100'}`}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-muted">
            <Film className="h-8 w-8 text-muted-foreground" />
          </div>
        )}
        {video.videoUrl && (
          <video
            ref={videoRef}
            src={video.videoUrl}
            className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-200 ${hovered ? 'opacity-100' : 'opacity-0'}`}
            muted
            loop
            playsInline
            preload="none"
          />
        )}
        {/* Play icon overlay */}
        {!hovered && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="h-10 w-10 rounded-full bg-black/40 flex items-center justify-center">
              <Play className="h-5 w-5 text-white ml-0.5" />
            </div>
          </div>
        )}
        {/* Status badge */}
        <div className="absolute top-2 left-2">
          <Badge variant={video.status === 'published' ? 'default' : 'secondary'} className="text-[10px]">
            {video.status}
          </Badge>
        </div>
      </div>

      {/* Meta */}
      <CardContent className="p-3 space-y-2">
        <p
          className={`text-xs text-muted-foreground min-h-[2rem] ${captionExpanded ? '' : 'line-clamp-2'} ${video.description ? 'cursor-pointer' : ''}`}
          onClick={() => video.description && setCaptionExpanded((v) => !v)}
          title={captionExpanded ? 'Show less' : 'Show full caption'}
        >
          {video.description || <span className="italic opacity-50">No caption</span>}
        </p>

        {/* Tag chips */}
        {(video.nicheTags?.length > 0 || video.customTags?.length > 0) && (
          <div className="flex flex-wrap gap-1">
            {(video.nicheTags ?? []).map((id) => (
              <span
                key={id}
                className="inline-flex items-center rounded-full bg-primary/10 border border-primary/20 px-2 py-0.5 text-[10px] font-medium text-primary"
              >
                {findNode(id)?.label ?? id}
              </span>
            ))}
            {(video.customTags ?? []).map((t) => (
              <span
                key={t}
                className="inline-flex items-center rounded-full bg-muted border border-border px-2 py-0.5 text-[10px] font-medium text-foreground"
              >
                {t}
              </span>
            ))}
          </div>
        )}

        {/* Location chip */}
        {video.location?.name && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <MapPin className="h-3 w-3 shrink-0" />
            <span className="truncate">{video.location.name}</span>
          </div>
        )}

        {/* Stats row */}
        <div className="flex items-center gap-3 flex-wrap">
          <StatChip icon={Eye} value={video.views} />
          <StatChip icon={Heart} value={video.likes} />
          <StatChip icon={Bookmark} value={video.saves} />
          <StatChip icon={Share2} value={video.shares} />
        </div>

        <p className="text-[10px] text-muted-foreground">{formatDate(video.published_at)}</p>

        {/* Actions */}
        <div className="flex gap-2 pt-1">
          <Button
            variant="ghost"
            size="sm"
            className="flex-1 h-7 text-xs"
            onClick={() => window.open(video.videoUrl, '_blank')}
          >
            <Eye className="h-3 w-3 mr-1" />
            View
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-foreground"
            onClick={() => onEditTags(video)}
            title="Edit tags"
          >
            <Tag className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-foreground"
            onClick={() => onEditLocation(video)}
            title="Edit location"
          >
            <MapPin className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-destructive"
            onClick={() => onDelete(video.id)}
            disabled={deleting}
          >
            {deleting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ChillsVideos() {
  const navigate = useNavigate()
  const { selectedOutlet, isLoading: outletLoading, outletConfig } = useOutlet()
  const outletLat = outletConfig?.restaurant?.latitude as number | undefined
  const outletLng = outletConfig?.restaurant?.longitude as number | undefined
  const outletName = outletConfig?.restaurant?.name as string | undefined

  const [videos, setVideos] = useState<ChillsVideo[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  // Edit tags sheet
  const [editTagsVideo, setEditTagsVideo] = useState<ChillsVideo | null>(null)
  const [editNicheTags, setEditNicheTags] = useState<string[]>([])
  const [editCustomTags, setEditCustomTags] = useState<string[]>([])
  const [isSavingTags, setIsSavingTags] = useState(false)

  // Edit location sheet
  const [editLocationVideo, setEditLocationVideo] = useState<ChillsVideo | null>(null)
  const [editLocation, setEditLocation] = useState<ChillsLocationValue | null>(null)
  const [isSavingLocation, setIsSavingLocation] = useState(false)

  const { data, isLoading, mutate } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.chills.get_merchant_chills',
    selectedOutlet ? { outlet_id: selectedOutlet, limit: 20 } : undefined,
    selectedOutlet ? `merchant-chills-${selectedOutlet}` : undefined,
  )

  const { call: deleteChills } = useFrappePostCall(
    'flamezo_backend.flamezo.api.chills.delete_merchant_chills'
  )

  const { call: loadMoreCall } = useFrappePostCall(
    'flamezo_backend.flamezo.api.chills.get_merchant_chills'
  )

  const { call: updateTagsCall } = useFrappePostCall(
    'flamezo_backend.flamezo.api.chills.merchant_update_chills_tags'
  )

  const { call: updateLocationCall } = useFrappePostCall(
    'flamezo_backend.flamezo.api.chills.merchant_update_chills_location'
  )

  // Hydrate initial page
  useEffect(() => {
    const body = (data as any)?.message ?? data
    if (body?.success && body.data) {
      setVideos(body.data.videos ?? [])
      setCursor(body.data.next_cursor ?? null)
      setHasMore(body.data.has_more ?? false)
    }
  }, [data])

  const handleLoadMore = useCallback(async () => {
    if (!cursor || !selectedOutlet || loadingMore) return
    setLoadingMore(true)
    try {
      const res = await loadMoreCall({ outlet_id: selectedOutlet, cursor, limit: 20 }) as any
      const body = res?.message ?? res
      if (body?.success && body.data) {
        setVideos((prev) => [...prev, ...(body.data.videos ?? [])])
        setCursor(body.data.next_cursor ?? null)
        setHasMore(body.data.has_more ?? false)
      }
    } finally {
      setLoadingMore(false)
    }
  }, [cursor, selectedOutlet, loadingMore, loadMoreCall])

  const handleOpenEditTags = useCallback((video: ChillsVideo) => {
    setEditTagsVideo(video)
    setEditNicheTags(video.nicheTags ?? [])
    setEditCustomTags(video.customTags ?? [])
  }, [])

  const handleOpenEditLocation = useCallback((video: ChillsVideo) => {
    setEditLocationVideo(video)
    setEditLocation(video.location ?? null)
  }, [])

  const handleSaveLocation = useCallback(async () => {
    if (!editLocationVideo || !selectedOutlet) return
    setIsSavingLocation(true)
    try {
      await updateLocationCall({
        outlet_id: selectedOutlet,
        chills_id: editLocationVideo.id,
        location_name: editLocation?.name ?? '',
        location_lat: editLocation?.lat ?? 0,
        location_lng: editLocation?.lng ?? 0,
        location_radius: editLocation?.radius ?? 0,
      })
      setVideos((prev) =>
        prev.map((v) => v.id === editLocationVideo.id ? { ...v, location: editLocation } : v)
      )
      toast.success('Location updated.')
      setEditLocationVideo(null)
    } catch (err: any) {
      toast.error(err?.message ?? 'Failed to save location.')
    } finally {
      setIsSavingLocation(false)
    }
  }, [editLocationVideo, selectedOutlet, editLocation, updateLocationCall])

  const handleSaveTags = useCallback(async () => {
    if (!editTagsVideo || !selectedOutlet) return
    setIsSavingTags(true)
    try {
      await updateTagsCall({
        outlet_id: selectedOutlet,
        chills_id: editTagsVideo.id,
        niche_tags: JSON.stringify(editNicheTags),
        custom_tags: JSON.stringify(editCustomTags),
      })
      setVideos((prev) =>
        prev.map((v) =>
          v.id === editTagsVideo.id
            ? { ...v, nicheTags: editNicheTags, customTags: editCustomTags }
            : v
        )
      )
      toast.success('Tags updated.')
      setEditTagsVideo(null)
    } catch (err: any) {
      toast.error(err?.message ?? 'Failed to save tags.')
    } finally {
      setIsSavingTags(false)
    }
  }, [editTagsVideo, selectedOutlet, editNicheTags, editCustomTags, updateTagsCall])

  const handleDelete = useCallback(async () => {
    if (!deleteTarget || !selectedOutlet) return
    setDeletingId(deleteTarget)
    setDeleteTarget(null)
    try {
      await deleteChills({ outlet_id: selectedOutlet, chills_id: deleteTarget })
      setVideos((prev) => prev.filter((v) => v.id !== deleteTarget))
      mutate()
      toast.success('Video removed.')
    } catch {
      toast.error('Failed to remove video.')
    } finally {
      setDeletingId(null)
    }
  }, [deleteTarget, selectedOutlet, deleteChills, mutate])

  if (outletLoading || isLoading) return <ChillsVideosSkeleton />

  const totalViews = videos.reduce((s, v) => s + v.views, 0)
  const totalLikes = videos.reduce((s, v) => s + v.likes, 0)
  const totalSaves = videos.reduce((s, v) => s + v.saves, 0)
  const totalShares = videos.reduce((s, v) => s + v.shares, 0)

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">My Chills</h1>
          <p className="text-sm text-muted-foreground">{videos.length} video{videos.length !== 1 ? 's' : ''} published</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => navigate('/chills/analytics')}>
            <BarChart3 className="h-4 w-4 mr-2" />
            Analytics
          </Button>
          <Button size="sm" onClick={() => navigate('/chills/upload')}>
            <Upload className="h-4 w-4 mr-2" />
            Upload Video
          </Button>
        </div>
      </div>

      {/* Quick stats */}
      {videos.length > 0 && (
        <StatTiles
          stats={[
            { label: 'Total Views', value: formatCount(totalViews), icon: Eye },
            { label: 'Total Likes', value: formatCount(totalLikes), icon: Heart },
            { label: 'Total Saves', value: formatCount(totalSaves), icon: Bookmark },
            { label: 'Total Shares', value: formatCount(totalShares), icon: Share2 },
          ]}
        />
      )}

      {/* Empty state */}
      {videos.length === 0 && (
        <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4">
          <div className="h-20 w-20 rounded-2xl bg-muted flex items-center justify-center">
            <Film className="h-10 w-10 text-muted-foreground" />
          </div>
          <div className="text-center">
            <p className="font-medium">No videos yet</p>
            <p className="text-sm text-muted-foreground mt-1">Upload your first Chills to start growing your audience.</p>
          </div>
          <Button onClick={() => navigate('/chills/upload')}>
            <Upload className="h-4 w-4 mr-2" />
            Upload Video
          </Button>
        </div>
      )}

      {/* Video grid */}
      {videos.length > 0 && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {videos.map((v) => (
              <VideoCard
                key={v.id}
                video={v}
                onDelete={(id) => setDeleteTarget(id)}
                onEditTags={handleOpenEditTags}
                onEditLocation={handleOpenEditLocation}
                deleting={deletingId === v.id}
              />
            ))}
          </div>

          {hasMore && (
            <div className="flex justify-center pt-2">
              <Button variant="outline" onClick={handleLoadMore} disabled={loadingMore}>
                {loadingMore ? (
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

      {/* Edit Tags sheet */}
      <Sheet open={!!editTagsVideo} onOpenChange={(o) => !o && setEditTagsVideo(null)}>
        <SheetContent side="right" className="w-full sm:max-w-md overflow-y-auto">
          <SheetHeader className="mb-4">
            <SheetTitle>Edit Tags</SheetTitle>
            <SheetDescription>
              Update the niche and custom tags for this Chills video.
            </SheetDescription>
          </SheetHeader>
          {editTagsVideo && (
            <div className="space-y-4">
              <ChillsTagPicker
                nicheTags={editNicheTags}
                onNicheChange={setEditNicheTags}
                customTags={editCustomTags}
                onCustomChange={setEditCustomTags}
                outletId={selectedOutlet ?? ''}
                caption={editTagsVideo.description}
              />
              <div className="flex gap-2 pt-2">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => setEditTagsVideo(null)}
                  disabled={isSavingTags}
                >
                  Cancel
                </Button>
                <Button
                  className="flex-1"
                  onClick={handleSaveTags}
                  disabled={isSavingTags}
                >
                  {isSavingTags ? (
                    <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</>
                  ) : 'Save Tags'}
                </Button>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* Edit Location sheet */}
      <Sheet open={!!editLocationVideo} onOpenChange={(o) => !o && setEditLocationVideo(null)}>
        <SheetContent side="right" className="w-full sm:max-w-md overflow-y-auto">
          <SheetHeader className="mb-4">
            <SheetTitle>Edit Location</SheetTitle>
            <SheetDescription>
              Pin this video to a place. Radius is auto-set by the type of location you choose.
            </SheetDescription>
          </SheetHeader>
          {editLocationVideo && (
            <div className="space-y-4">
              <ChillsLocationPicker
                value={editLocation}
                onChange={setEditLocation}
                outletName={outletName}
                outletLat={outletLat}
                outletLng={outletLng}
              />
              <div className="flex gap-2 pt-2">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => setEditLocationVideo(null)}
                  disabled={isSavingLocation}
                >
                  Cancel
                </Button>
                <Button
                  className="flex-1"
                  onClick={handleSaveLocation}
                  disabled={isSavingLocation}
                >
                  {isSavingLocation ? (
                    <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</>
                  ) : 'Save Location'}
                </Button>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* Delete confirmation */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this video?</AlertDialogTitle>
            <AlertDialogDescription>
              The video will be removed from the Flamezo app feed. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={handleDelete}
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
