import { useState, useRef, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOutlet } from '@/contexts/OutletContext'
import { useFrappePostCall } from '@/lib/frappe'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { toast } from 'sonner'
import {
  Megaphone, ChevronRight, Loader2,
  Image as ImageIcon, X, CheckCircle2, AlertCircle,
  Upload, AlignLeft
} from 'lucide-react'
import { uploadClubMedia, clubMediaKind } from '@/lib/clubUpload'
import ChillsTagPicker from '@/components/ChillsTagPicker'
import ChillsLocationPicker, { type ChillsLocationValue } from '@/components/ChillsLocationPicker'
import ClubCollaboratorPicker, { type CollabOutlet } from '@/components/clubtalks/ClubCollaboratorPicker'
import { MapPin } from 'lucide-react'

type UploadStage = 'idle' | 'uploading' | 'publishing' | 'done' | 'error'

const PAGE = 'flamezo_backend.flamezo.api.merchant_clubs'

export default function ClubUpload() {
  const navigate = useNavigate()
  const { selectedOutlet, outletConfig } = useOutlet()

  const [mediaFile, setMediaFile] = useState<File | null>(null)
  const [mediaPreviewUrl, setMediaPreviewUrl] = useState<string | null>(null)
  const [content, setContent] = useState('')
  const [stage, setStage] = useState<UploadStage>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [publishedId, setPublishedId] = useState('')
  
  const [nicheTags, setNicheTags] = useState<string[]>([])
  const [customTags, setCustomTags] = useState<string[]>([])
  const [chillsLocation, setChillsLocation] = useState<ChillsLocationValue | null>(null)
  const [collaborators, setCollaborators] = useState<CollabOutlet[]>([])

  const fileInputRef = useRef<HTMLInputElement>(null)

  const { call: requestUpload } = useFrappePostCall(`${PAGE}.merchant_request_upload`)
  const { call: createPost } = useFrappePostCall(`${PAGE}.merchant_create_post`)

  const outletLat = outletConfig?.restaurant?.latitude as number | undefined
  const outletLng = outletConfig?.restaurant?.longitude as number | undefined
  const outletName = outletConfig?.restaurant?.name || 'Your Outlet'

  const seedOutletLocation = useCallback(() => {
    if (outletLat && outletLng && outletName !== 'Your Outlet') {
      setChillsLocation({ name: outletName, lat: outletLat, lng: outletLng, radius: 300 })
    }
  }, [outletLat, outletLng, outletName])

  useEffect(() => {
    if (!chillsLocation) seedOutletLocation()
  }, [outletConfig, chillsLocation, seedOutletLocation])

  const handleMediaSelected = useCallback((file: File) => {
    if (!file.type.startsWith('image/') && !file.type.startsWith('video/')) {
      toast.error('Please select an image or video.')
      return
    }
    if (file.size > 500 * 1024 * 1024) {
      toast.error('File must be under 500 MB.')
      return
    }
    const url = URL.createObjectURL(file)
    if (mediaPreviewUrl) URL.revokeObjectURL(mediaPreviewUrl)
    setMediaFile(file)
    setMediaPreviewUrl(url)
    setErrorMsg('')
  }, [mediaPreviewUrl])

  const handleMediaDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleMediaSelected(file)
  }, [handleMediaSelected])

  const handlePublish = useCallback(async () => {
    if (!selectedOutlet || (!mediaFile && !content.trim())) return
    try {
      setStage('uploading')
      
      const args: Record<string, unknown> = {
        outlet_id: selectedOutlet,
        content: content.trim(),
        niche_tags: JSON.stringify(nicheTags),
        custom_tags: JSON.stringify(customTags),
        location_name: chillsLocation?.name || '',
        location_lat: chillsLocation?.lat ?? '',
        location_lng: chillsLocation?.lng ?? '',
        location_radius: chillsLocation?.radius ?? '',
        tagged_outlet_ids: collaborators.map((c) => c.name).join(','),
      }

      if (mediaFile) {
        const { objectKey, kind } = await uploadClubMedia(selectedOutlet, mediaFile, requestUpload)
        args.post_type = kind
        args[kind === 'video' ? 'video_key' : 'image_key'] = objectKey
      } else {
        args.post_type = 'text'
      }

      setStage('publishing')
      const res: any = await createPost(args)
      const data = res?.message?.data || res?.data
      
      setPublishedId(data?.id || 'new_post')
      setStage('done')
      toast.success('Post published successfully!')
    } catch (err: any) {
      setErrorMsg(err?.message ?? 'Upload failed. Please try again.')
      setStage('error')
      toast.error(err?.message ?? 'Upload failed.')
    }
  }, [selectedOutlet, mediaFile, content, nicheTags, customTags, chillsLocation, collaborators, requestUpload, createPost])

  const resetForm = useCallback(() => {
    if (mediaPreviewUrl) URL.revokeObjectURL(mediaPreviewUrl)
    setMediaFile(null)
    setMediaPreviewUrl(null)
    setContent('')
    setNicheTags([])
    setCustomTags([])
    setCollaborators([])
    seedOutletLocation()
    setStage('idle')
    setErrorMsg('')
    setPublishedId('')
  }, [mediaPreviewUrl, seedOutletLocation])

  const isUploading = stage === 'uploading' || stage === 'publishing'
  const canPublish = !isUploading && (content.trim().length > 0 || mediaFile !== null)
  const isVideo = mediaFile ? clubMediaKind(mediaFile) === 'video' : false

  if (!selectedOutlet) {
    return <div className="p-8 text-center text-muted-foreground">Select an outlet to use Club Talks.</div>
  }

  if (stage === 'done') {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 p-6">
        <div className="h-20 w-20 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
          <CheckCircle2 className="h-10 w-10 text-green-600 dark:text-green-400" />
        </div>
        <div className="text-center space-y-2">
          <h2 className="text-2xl font-semibold">Published!</h2>
          <p className="text-muted-foreground">Your post is now live in Club Talks.</p>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" onClick={() => navigate('/club-talks/posts')}>View My Posts</Button>
          <Button onClick={resetForm}>Upload Another</Button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
          <Megaphone className="h-5 w-5" style={{ color: '#E23744' }} />
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-semibold">New Club Post</h1>
          <p className="text-sm text-muted-foreground">Broadcast an update, photo, or video to your followers</p>
        </div>
        <Button
          className="h-10 px-5 text-sm font-semibold shrink-0"
          style={{ backgroundColor: canPublish ? '#E23744' : undefined }}
          onClick={handlePublish}
          disabled={!canPublish}
        >
          {isUploading ? (
            <><Loader2 className="h-4 w-4 mr-2 animate-spin" />{stage === 'publishing' ? 'Publishing…' : 'Uploading…'}</>
          ) : stage === 'error' ? (
            'Retry'
          ) : (
            <>Publish<ChevronRight className="h-4 w-4 ml-1" /></>
          )}
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[auto_1fr] gap-8 items-start pt-4">
        {/* ── Left: Phone preview ── */}
        <div className="flex flex-col items-center gap-3">
          <div className="flex flex-col items-center gap-2">
            <p className="text-xs font-semibold text-foreground tracking-wide uppercase">Preview</p>
            <div className="relative rounded-[2.2rem] border-[5px] border-gray-900 bg-background shadow-2xl overflow-hidden flex flex-col"
              style={{ width: 280, aspectRatio: '9/16' }}>
              <div className="absolute top-0 left-0 right-0 h-7 bg-background z-20 flex items-center justify-center">
                <div className="w-20 h-4 rounded-b-xl bg-gray-900" />
              </div>
              
              {/* Fake post header */}
              <div className="flex items-center gap-2 p-3 pt-9 bg-background z-10 border-b">
                <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center text-white text-xs font-bold shrink-0">
                  {outletName.charAt(0)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold truncate">{outletName}</p>
                  <p className="text-[10px] text-muted-foreground">Just now</p>
                </div>
              </div>

              {/* Media area */}
              {mediaPreviewUrl && (
                <div className="w-full bg-black aspect-[4/3] flex items-center justify-center overflow-hidden shrink-0">
                  {isVideo ? (
                    <video src={mediaPreviewUrl} className="w-full h-full object-cover" autoPlay muted loop playsInline />
                  ) : (
                    <img src={mediaPreviewUrl} alt="Preview" className="w-full h-full object-cover" />
                  )}
                </div>
              )}

              {/* Caption area */}
              <div className="p-3 flex-1 bg-background overflow-hidden">
                <p className="text-xs leading-relaxed break-words whitespace-pre-wrap line-clamp-[8]">
                  {content || <span className="text-muted-foreground italic">Your caption will appear here...</span>}
                </p>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">Live preview</p>
          </div>
        </div>

        {/* ── Right: form ── */}
        <div className="space-y-3">
          {/* Caption */}
          <Card className="p-4 space-y-2">
            <p className="text-sm font-medium">Post Caption</p>
            {/* Media — a small button at the top (optional). The phone preview shows the file. */}
            <div onDragOver={(e) => e.preventDefault()} onDrop={handleMediaDrop}>
              {!mediaFile ? (
                <Button type="button" variant="outline" onClick={() => fileInputRef.current?.click()} disabled={isUploading} className="w-full gap-2">
                  <ImageIcon className="h-4 w-4" />
                  Add Media
                </Button>
              ) : (
                <div className="flex items-center justify-between p-2.5 rounded-lg border bg-muted/30">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="h-10 w-16 rounded-md bg-black flex items-center justify-center shrink-0 overflow-hidden">
                      {isVideo ? (
                        <video src={mediaPreviewUrl!} className="w-full h-full object-cover" muted playsInline preload="metadata" />
                      ) : (
                        <img src={mediaPreviewUrl!} alt="Thumb" className="w-full h-full object-cover" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{mediaFile.name}</p>
                      <p className="text-xs text-muted-foreground">{(mediaFile.size / 1024 / 1024).toFixed(1)} MB</p>
                    </div>
                  </div>
                  <Button variant="ghost" size="icon" onClick={() => { setMediaFile(null); setMediaPreviewUrl(null) }} disabled={isUploading} className="text-muted-foreground hover:text-destructive shrink-0">
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              )}
              <input ref={fileInputRef} type="file" accept="image/*,video/*" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleMediaSelected(f); if(fileInputRef.current) fileInputRef.current.value='' }} />
            </div>

            {/* Caption */}
            <div className="space-y-2">
              <Label htmlFor="content" className="sr-only">Caption</Label>
              <Textarea
                id="content"
                placeholder="What's happening at your outlet? (Optional if media is attached)"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                maxLength={1000}
                rows={5}
                className="resize-none text-base"
                disabled={isUploading}
              />
              <p className="text-xs text-muted-foreground text-right">{content.length}/1000</p>
            </div>

            {/* Collaborators — tag other outlets */}
            <div className="border-t pt-2.5">
              <ClubCollaboratorPicker
                outletId={selectedOutlet}
                selected={collaborators}
                onChange={setCollaborators}
                disabled={isUploading}
              />
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
              caption={content}
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

          {/* Progress / Error */}
          {isUploading && (
            <Card className="p-4 flex items-center gap-3">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
              <p className="text-sm font-medium">
                {stage === 'uploading' ? 'Uploading media...' : 'Publishing post...'}
              </p>
            </Card>
          )}

          {stage === 'error' && (
            <div className="flex items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-4">
              <AlertCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-destructive">Publish failed</p>
                <p className="text-sm text-muted-foreground">{errorMsg}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
