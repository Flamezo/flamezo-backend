import { useState, useRef, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOutlet } from '@/contexts/OutletContext'
import { useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Progress } from '@/components/ui/progress'
import { toast } from 'sonner'
import {
  Film, Upload, X, CheckCircle2, AlertCircle, Image,
  ChevronRight, Loader2, FileVideo, Flame, Tag, Send, MapPin,
} from 'lucide-react'
import { ChillsUploadSkeleton } from '@/components/PageSkeletons'
import ChillsTagPicker from '@/components/ChillsTagPicker'
import ChillsLocationPicker, { type ChillsLocationValue } from '@/components/ChillsLocationPicker'

// ── Types ─────────────────────────────────────────────────────────────────────

type UploadStage = 'idle' | 'uploading-video' | 'uploading-thumbnail' | 'publishing' | 'done' | 'error'

interface PresignedResponse {
  upload_url: string
  object_key: string
  expires_in: number
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDuration(secs: number): string {
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

// Chills is discovery content, not storytelling — keep it short. Enforced
// here (fail fast, don't upload a doomed file) AND authoritatively
// server-side in chills.py's MAX_CHILLS_DURATION_SECONDS. Keep both in sync.
const MAX_CHILLS_DURATION_SECONDS = 60

async function getVideoDuration(file: File): Promise<number> {
  return new Promise((resolve) => {
    const video = document.createElement('video')
    const url = URL.createObjectURL(file)
    video.src = url
    video.onloadedmetadata = () => { URL.revokeObjectURL(url); resolve(video.duration) }
    video.onerror = () => { URL.revokeObjectURL(url); resolve(0) }
  })
}

async function captureVideoThumbnail(file: File): Promise<Blob | null> {
  return new Promise((resolve) => {
    const video = document.createElement('video')
    const url = URL.createObjectURL(file)
    video.src = url
    video.currentTime = 0.5
    video.muted = true
    video.onloadeddata = () => {
      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      const ctx = canvas.getContext('2d')
      if (!ctx) { URL.revokeObjectURL(url); resolve(null); return }
      ctx.drawImage(video, 0, 0)
      canvas.toBlob((blob) => { URL.revokeObjectURL(url); resolve(blob) }, 'image/jpeg', 0.85)
    }
    video.onerror = () => { URL.revokeObjectURL(url); resolve(null) }
  })
}

async function putToR2(uploadUrl: string, file: File | Blob, contentType: string, onProgress: (p: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', uploadUrl)
    xhr.setRequestHeader('Content-Type', contentType)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`R2 PUT failed: ${xhr.status}`)))
    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.send(file)
  })
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ChillsUpload() {
  const navigate = useNavigate()
  const { selectedOutlet, isLoading: outletLoading, outletConfig } = useOutlet()

  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [videoPreviewUrl, setVideoPreviewUrl] = useState<string | null>(null)
  const [videoDuration, setVideoDuration] = useState<number>(0)
  const [thumbnailBlob, setThumbnailBlob] = useState<Blob | null>(null)
  const [thumbnailPreviewUrl, setThumbnailPreviewUrl] = useState<string | null>(null)
  const [customThumbnailFile, setCustomThumbnailFile] = useState<File | null>(null)
  const [description, setDescription] = useState('')
  const [nicheTags, setNicheTags] = useState<string[]>([])
  const [customTags, setCustomTags] = useState<string[]>([])
  const [chillsLocation, setChillsLocation] = useState<ChillsLocationValue | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [stage, setStage] = useState<UploadStage>('idle')
  const [videoProgress, setVideoProgress] = useState(0)
  const [thumbProgress, setThumbProgress] = useState(0)
  const [errorMsg, setErrorMsg] = useState('')
  const [publishedId, setPublishedId] = useState('')

  const outletLat = outletConfig?.restaurant?.latitude as number | undefined
  const outletLng = outletConfig?.restaurant?.longitude as number | undefined
  const outletName = outletConfig?.restaurant?.name as string | undefined

  const seedOutletLocation = useCallback(() => {
    if (outletLat && outletLng && outletName) {
      setChillsLocation({ name: outletName, lat: outletLat, lng: outletLng, radius: 300 })
    }
  }, [outletLat, outletLng, outletName])

  // Pre-seed when config first loads
  useEffect(() => {
    if (!chillsLocation) seedOutletLocation()
  }, [outletConfig]) // eslint-disable-line react-hooks/exhaustive-deps

  const videoInputRef = useRef<HTMLInputElement>(null)
  const thumbInputRef = useRef<HTMLInputElement>(null)

  const { call: requestUpload } = useFrappePostCall<{ message: { success: boolean; data: PresignedResponse } }>(
    'flamezo_backend.flamezo.api.chills.merchant_request_chills_upload'
  )
  const { call: publishChills } = useFrappePostCall<{ message: { success: boolean; data: { chills_id: string; video_url: string } } }>(
    'flamezo_backend.flamezo.api.chills.merchant_publish_chills'
  )

  // ── File selection ──────────────────────────────────────────────────────────

  const handleVideoSelected = useCallback(async (file: File) => {
    if (!file.type.startsWith('video/')) { toast.error('Please select a video file.'); return }
    if (file.size > 500 * 1024 * 1024) { toast.error('Video must be under 500 MB.'); return }
    const duration = await getVideoDuration(file)
    if (duration > MAX_CHILLS_DURATION_SECONDS) {
      toast.error(`Chills videos can be up to ${MAX_CHILLS_DURATION_SECONDS} seconds — this one is ${Math.round(duration)}s. Trim it and try again.`)
      return
    }
    const url = URL.createObjectURL(file)
    setVideoFile(file)
    setVideoPreviewUrl(url)
    setStage('idle')
    setVideoProgress(0)
    setThumbProgress(0)
    setErrorMsg('')
    setPublishedId('')

    const blob = await captureVideoThumbnail(file)
    if (blob) {
      setThumbnailBlob(blob)
      setThumbnailPreviewUrl(URL.createObjectURL(blob))
    }
  }, [])

  const handleVideoDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleVideoSelected(file)
  }, [handleVideoSelected])

  const handleCustomThumbnail = useCallback((file: File) => {
    if (!file.type.startsWith('image/')) { toast.error('Please select an image.'); return }
    setCustomThumbnailFile(file)
    if (thumbnailPreviewUrl) URL.revokeObjectURL(thumbnailPreviewUrl)
    setThumbnailPreviewUrl(URL.createObjectURL(file))
    setThumbnailBlob(null)
  }, [thumbnailPreviewUrl])

  // ── Upload & publish ────────────────────────────────────────────────────────

  const handlePublish = useCallback(async () => {
    if (!videoFile || !selectedOutlet) return
    try {
      setStage('uploading-video')
      setVideoProgress(0)
      const mimeType = videoFile.type || 'video/mp4'
      const videoRes = await requestUpload({
        outlet_id: selectedOutlet,
        filename: videoFile.name,
        content_type: mimeType,
        kind: 'video',
      })
      const videoBody = (videoRes as any)?.message ?? videoRes
      const videoSession = videoBody?.data
      if (!videoSession?.upload_url) throw new Error('Failed to get video upload URL.')

      await putToR2(videoSession.upload_url, videoFile, mimeType, setVideoProgress)
      setVideoProgress(100)

      let thumbnailKey: string | undefined
      const thumbSource: File | Blob | null = customThumbnailFile ?? thumbnailBlob
      if (thumbSource) {
        setStage('uploading-thumbnail')
        setThumbProgress(0)
        const thumbRes = await requestUpload({
          outlet_id: selectedOutlet,
          filename: 'thumbnail.jpg',
          content_type: 'image/jpeg',
          kind: 'thumbnail',
        })
        const thumbBody = (thumbRes as any)?.message ?? thumbRes
        const thumbSession = thumbBody?.data
        if (thumbSession?.upload_url) {
          await putToR2(thumbSession.upload_url, thumbSource, 'image/jpeg', setThumbProgress)
          setThumbProgress(100)
          thumbnailKey = thumbSession.object_key
        }
      }

      setStage('publishing')
      const pubRes = await publishChills({
        outlet_id: selectedOutlet,
        object_key: videoSession.object_key,
        description: description.trim(),
        thumbnail_key: thumbnailKey,
        niche_tags: nicheTags.length ? JSON.stringify(nicheTags) : undefined,
        custom_tags: customTags.length ? JSON.stringify(customTags) : undefined,
        location_name: chillsLocation?.name || undefined,
        location_lat: chillsLocation?.lat ?? undefined,
        location_lng: chillsLocation?.lng ?? undefined,
        location_radius: chillsLocation?.radius ?? undefined,
      })
      const pubBody = (pubRes as any)?.message ?? pubRes
      const pubData = pubBody?.data
      if (!pubData?.chills_id) throw new Error('Publish failed — no chills_id returned.')

      setPublishedId(pubData.chills_id)
      setStage('done')
      toast.success('Chills video published!')
    } catch (err: any) {
      setErrorMsg(err?.message ?? 'Upload failed. Please try again.')
      setStage('error')
      toast.error(err?.message ?? 'Upload failed.')
    }
  }, [videoFile, selectedOutlet, description, customThumbnailFile, thumbnailBlob, nicheTags, customTags, chillsLocation, requestUpload, publishChills])

  const resetForm = useCallback(() => {
    if (videoPreviewUrl) URL.revokeObjectURL(videoPreviewUrl)
    if (thumbnailPreviewUrl) URL.revokeObjectURL(thumbnailPreviewUrl)
    setVideoFile(null); setVideoPreviewUrl(null)
    setThumbnailBlob(null); setThumbnailPreviewUrl(null); setCustomThumbnailFile(null)
    setDescription(''); setNicheTags([]); setCustomTags([]); setStage('idle'); setVideoProgress(0); setThumbProgress(0)
    seedOutletLocation()
    setErrorMsg(''); setPublishedId('')
  }, [videoPreviewUrl, thumbnailPreviewUrl, seedOutletLocation])

  // ── Render ──────────────────────────────────────────────────────────────────

  if (outletLoading) return <ChillsUploadSkeleton />

  const isUploading = stage === 'uploading-video' || stage === 'uploading-thumbnail' || stage === 'publishing'

  if (stage === 'done') {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 p-6">
        <div className="h-20 w-20 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
          <CheckCircle2 className="h-10 w-10 text-green-600 dark:text-green-400" />
        </div>
        <div className="text-center space-y-2">
          <h2 className="text-2xl font-semibold">Published!</h2>
          <p className="text-muted-foreground">Your Chills video is now live on the app.</p>
          <p className="text-xs text-muted-foreground font-mono">{publishedId}</p>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" onClick={() => navigate('/chills/videos')}>View My Videos</Button>
          <Button onClick={resetForm}>Upload Another</Button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
          <Film className="h-5 w-5 text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-semibold">Upload Chills</h1>
          <p className="text-sm text-muted-foreground">Publish a short video to the Flamezo app feed</p>
        </div>
        {videoFile && (
          <Button
            className="h-10 px-5 text-sm font-semibold shrink-0"
            onClick={handlePublish}
            disabled={isUploading || !videoFile}
          >
            {isUploading ? (
              <><Loader2 className="h-4 w-4 mr-2 animate-spin" />{stage === 'publishing' ? 'Publishing…' : 'Uploading…'}</>
            ) : stage === 'error' ? (
              'Retry'
            ) : (
              <>Publish<ChevronRight className="h-4 w-4 ml-1" /></>
            )}
          </Button>
        )}
      </div>

      {!videoFile ? (
        /* Drop zone */
        <Card
          className={`border-2 border-dashed transition-colors cursor-pointer ${isDragging ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50'}`}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleVideoDrop}
          onClick={() => videoInputRef.current?.click()}
        >
          <CardContent className="flex flex-col items-center gap-4 py-16">
            <div className="h-16 w-16 rounded-2xl bg-muted flex items-center justify-center">
              <FileVideo className="h-8 w-8 text-muted-foreground" />
            </div>
            <div className="text-center">
              <p className="font-medium">Drop your video here</p>
              <p className="text-sm text-muted-foreground mt-1">MP4, MOV or WebM · up to 500 MB</p>
            </div>
            <Button variant="outline" size="sm" className="pointer-events-none">
              <Upload className="h-4 w-4 mr-2" />Browse files
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-[auto_1fr] gap-8 items-start">
          {/* ── Left: both phone frames side by side ── */}
          <div className="flex flex-col items-center gap-3">
            <div className="flex items-start gap-4">
              {/* Video frame */}
              <div className="flex flex-col items-center gap-2">
                <p className="text-xs font-semibold text-foreground tracking-wide uppercase">Video</p>
                <div className="relative rounded-[2.2rem] border-[5px] border-gray-900 bg-black shadow-2xl overflow-hidden"
                  style={{ width: 200, aspectRatio: '9/16' }}>
                  <div className="absolute top-0 left-0 right-0 h-7 bg-black z-10 flex items-center justify-center">
                    <div className="w-20 h-4 rounded-b-xl bg-gray-900" />
                  </div>
                  {videoPreviewUrl && (
                    <video
                      src={videoPreviewUrl}
                      className="w-full h-full object-cover"
                      autoPlay
                      muted
                      loop
                      playsInline
                      onLoadedMetadata={(e) => setVideoDuration((e.target as HTMLVideoElement).duration)}
                    />
                  )}
                  <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-black/80 to-transparent z-10 flex flex-col justify-end px-3 pb-3 gap-1">
                    {description && (
                      <p className="text-white text-[10px] leading-tight line-clamp-2">{description}</p>
                    )}
                    <div className="flex items-center gap-1.5">
                      <div className="w-4 h-4 rounded-full bg-white/30" />
                      <p className="text-white/70 text-[9px]">Your Outlet</p>
                    </div>
                  </div>
                  <div className="absolute right-2 bottom-20 z-10 flex flex-col items-center gap-4">
                    {[
                      { icon: Flame, label: '0' },
                      { icon: Tag, label: 'Offers' },
                      { icon: Send, label: '0' },
                      { icon: MapPin, label: 'Locate' },
                    ].map(({ icon: Icon, label }) => (
                      <div key={label} className="flex flex-col items-center gap-0.5">
                        <Icon className="h-5 w-5 text-white drop-shadow-md" />
                        <span className="text-white text-[9px] font-medium drop-shadow-md">{label}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">Live preview</p>
              </div>

              {/* Thumbnail frame */}
              <div className="flex flex-col items-center gap-2">
                <p className="text-xs font-semibold text-foreground tracking-wide uppercase">Thumbnail</p>
                <div
                  className="relative rounded-[2.2rem] border-[5px] border-gray-900 bg-black shadow-2xl overflow-hidden cursor-pointer group"
                  style={{ width: 200, aspectRatio: '9/16' }}
                  onClick={() => !isUploading && thumbInputRef.current?.click()}
                >
                  <div className="absolute top-0 left-0 right-0 h-7 bg-black z-10 flex items-center justify-center">
                    <div className="w-20 h-4 rounded-b-xl bg-gray-900" />
                  </div>
                  {thumbnailPreviewUrl ? (
                    <img src={thumbnailPreviewUrl} alt="Thumbnail" className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full flex flex-col items-center justify-center gap-2 bg-gray-900">
                      <Image className="h-7 w-7 text-gray-500" />
                      <p className="text-[11px] text-gray-500 text-center px-4">Click to set cover</p>
                    </div>
                  )}
                  {/* Hover overlay */}
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity z-20 flex items-center justify-center">
                    <div className="flex items-center gap-1.5 bg-black/60 rounded-full px-3 py-1.5">
                      <Image className="h-3.5 w-3.5 text-white" />
                      <span className="text-white text-[11px] font-medium">Change</span>
                    </div>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">
                  {customThumbnailFile ? 'Custom image' : thumbnailBlob ? 'Auto-captured · click to change' : 'Click to upload'}
                </p>
              </div>
            </div>

            {/* File info + remove */}
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="truncate max-w-[160px]">{videoFile.name}</span>
              {videoDuration > 0 && <span>· {formatDuration(videoDuration)}</span>}
              {videoFile.size > 0 && <span>· {formatFileSize(videoFile.size)}</span>}
            </div>
            <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-destructive h-7 text-xs" onClick={resetForm} disabled={isUploading}>
              <X className="h-3 w-3 mr-1" />Remove
            </Button>
          </div>

          {/* ── Right: caption + progress + error ── */}
          <div className="space-y-4">
            {/* Caption */}
            <Card className="p-4 space-y-3">
              <CardHeader className="p-0">
                <CardTitle className="text-sm font-medium">Video details</CardTitle>
              </CardHeader>
              <div className="space-y-2">
                <Label htmlFor="description">Caption</Label>
                <Textarea
                  id="description"
                  placeholder="Tell people what this video is about…"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={500}
                  rows={4}
                  className="resize-none"
                  disabled={isUploading}
                />
                <p className="text-xs text-muted-foreground text-right">{description.length}/500</p>
              </div>
            </Card>

            {/* Niche tags */}
            <Card className="p-4">
              <ChillsTagPicker
                nicheTags={nicheTags}
                onNicheChange={setNicheTags}
                customTags={customTags}
                onCustomChange={setCustomTags}
                outletId={selectedOutlet ?? ''}
                caption={description}
                disabled={isUploading}
              />
            </Card>

            {/* Location */}
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <MapPin className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-medium">Location</h3>
              </div>
              <ChillsLocationPicker
                value={chillsLocation}
                onChange={setChillsLocation}
                outletName={outletName}
                outletLat={outletLat}
                outletLng={outletLng}
              />
            </Card>

            {/* Progress */}
            {isUploading && (
              <Card className="p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                  <p className="text-sm font-medium">
                    {stage === 'uploading-video' && 'Uploading video…'}
                    {stage === 'uploading-thumbnail' && 'Uploading thumbnail…'}
                    {stage === 'publishing' && 'Publishing…'}
                  </p>
                </div>
                {stage === 'uploading-video' && (
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Video</span><span>{videoProgress}%</span>
                    </div>
                    <Progress value={videoProgress} className="h-2" />
                  </div>
                )}
                {stage === 'uploading-thumbnail' && (
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Thumbnail</span><span>{thumbProgress}%</span>
                    </div>
                    <Progress value={thumbProgress} className="h-2" />
                  </div>
                )}
              </Card>
            )}

            {/* Error */}
            {stage === 'error' && (
              <div className="flex items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-4">
                <AlertCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-destructive">Upload failed</p>
                  <p className="text-sm text-muted-foreground">{errorMsg}</p>
                </div>
              </div>
            )}

            <p className="text-xs text-center text-muted-foreground">Your video will appear instantly on the Flamezo app feed.</p>
          </div>
        </div>
      )}

      {/* Hidden inputs */}
      <input ref={videoInputRef} type="file" accept="video/*" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleVideoSelected(f) }} />
      <input ref={thumbInputRef} type="file" accept="image/*" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleCustomThumbnail(f) }} />
    </div>
  )
}
