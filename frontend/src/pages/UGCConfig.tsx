import { useState, useEffect, useRef } from 'react'
import StoryTemplateFrame from '@/components/StoryTemplateFrame'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappeGetCall, useFrappePostCall, useFrappeGetDocList } from '@/lib/frappe'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { toast } from 'sonner'
import { Megaphone, Info, ImagePlus, Trash2, Upload, Loader2, Film, Ticket, CheckCircle2, XCircle, Wallet, PlayCircle, Expand, Download } from 'lucide-react'
import { uploadToR2, getMediaType } from '@/lib/r2Upload'
import UGCGrowthSimulatorModal from '@/components/UGCGrowthSimulatorModal'
import { Button } from '@/components/ui/button'

type TemplateRow = { media_asset: string; label?: string; is_default?: number; url?: string; kind?: string }

const isVideo = (t: TemplateRow) =>
  t.kind === 'video' || (!!t.url && /\.(mp4|webm|mov|m4v|ogg)(\?|$)/i.test(t.url))

export default function UGCConfig() {
  const { selectedRestaurant, restaurants } = useRestaurant()
  const [configName, setConfigName] = useState<string>('')
  const [templates, setTemplates] = useState<TemplateRow[]>([])
  const [viewerCoupon, setViewerCoupon] = useState<string>('')
  const [ugcIsActive, setUgcIsActive] = useState<boolean>(false)
  const [uploading, setUploading] = useState(false)
  const [isSimulatorOpen, setIsSimulatorOpen] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const previewRef = useRef<HTMLDivElement>(null)

  const { data: configRes, mutate } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.ugc.get_ugc_config',
    selectedRestaurant ? { restaurant_id: selectedRestaurant } : undefined,
    selectedRestaurant ? `ugc-config-${selectedRestaurant}` : undefined,
  )

  const { data: voucherStatsRes } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.ugc.get_voucher_stats',
    selectedRestaurant ? { restaurant_id: selectedRestaurant, days: 30 } : undefined,
    selectedRestaurant ? `ugc-voucher-stats-${selectedRestaurant}` : undefined,
  )
  const { call: saveConfig } = useFrappePostCall('flamezo_backend.flamezo.api.ugc.save_ugc_config')
  const { call: deleteTemplate } = useFrappePostCall('flamezo_backend.flamezo.api.ugc.delete_ugc_template')

  const { data: coupons } = useFrappeGetDocList('Coupon', {
    fields: ['name', 'code', 'discount_type', 'discount_value', 'description', 'valid_until'],
    filters: selectedRestaurant ? [['restaurant', '=', selectedRestaurant]] : [],
    limit: 200,
  } as any, selectedRestaurant ? `ugc-coupons-${selectedRestaurant}` : null)

  useEffect(() => {
    const body: any = (configRes as any)?.message || configRes
    if (body?.success && body.data) {
      setConfigName(body.data.name || '')
      setTemplates(body.data.templates || [])
      setViewerCoupon(body.data.coupon_for_viewers || '')
      setUgcIsActive(!!body.data.ugc_is_active)
    }
  }, [configRes])

  const saveCoupons = async (patch: { coupon_for_viewers?: string }) => {
    if (!selectedRestaurant) return
    try {
      const res: any = await saveConfig({ restaurant_id: selectedRestaurant, payload: patch })
      const body = res?.message || res
      if (body?.success) { toast.success('Coupons updated'); await mutate() }
      else throw new Error(body?.message || 'Save failed')
    } catch (e: any) { toast.error(e.message || 'Failed to save') }
  }

  const persistTemplates = async (next: TemplateRow[]) => {
    if (!selectedRestaurant) return
    try {
      const payload = { templates: next.map(t => ({ media_asset: t.media_asset, label: t.label, is_default: 1 })) }
      const res: any = await saveConfig({ restaurant_id: selectedRestaurant, payload })
      const body = res?.message || res
      if (body?.success) await mutate()
      else throw new Error(body?.message || 'Save failed')
    } catch (e: any) { toast.error(e.message || 'Failed to save') }
  }

  const handleUpload = async (file: File) => {
    if (!configName) { toast.error('Config not ready yet'); return }
    if (templates.length >= 1) { toast.error('Only one template is allowed. Delete the current one to replace it.'); return }
    const kind = getMediaType(file)
    setUploading(true)
    try {
      const result = await uploadToR2({
        ownerDoctype: 'UGC Cashback Config', ownerName: configName,
        mediaRole: 'ugc_template_image', file, skipCompression: kind === 'video',
      })
      const next = [{ media_asset: result.name, url: result.primary_url, kind, label: file.name.replace(/\.[^.]+$/, ''), is_default: 1 }]
      setTemplates(next)
      await persistTemplates(next)
      toast.success('Template uploaded')
    } catch (e: any) { toast.error(e.message || 'Upload failed') }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = '' }
  }

  const removeTemplate = async (media_asset: string) => {
    setTemplates([])  // optimistic
    try {
      const res: any = await deleteTemplate({ restaurant_id: selectedRestaurant, media_asset })
      const body = res?.message || res
      if (body?.success) { toast.success('Template removed'); await mutate() }
      else throw new Error(body?.message || 'Delete failed')
    } catch (e: any) {
      toast.error(e.message || 'Failed to delete')
      await mutate()  // resync on failure
    }
  }

  const downloadPreview = async () => {
    if (!tpl) return
    setDownloading(true)
    const loadingToast = toast.loading('Preparing download…')
    try {
      const csrf = (window as any).frappe?.csrf_token || ''
      const mediaType = isVideo(tpl) ? 'video' : 'image'

      // 1. Enqueue background job on the server — returns immediately with job_id.
      //    Server generates overlay at native resolution + composites via ffmpeg/Pillow
      //    + uploads to R2. No Frappe worker is blocked; 100 concurrent downloads
      //    just queue up.
      const startRes = await fetch(
        '/api/method/flamezo_backend.flamezo.api.story_generator.start_story_download',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrf },
          body: JSON.stringify({
            template_url:      tpl.url,
            media_type:        mediaType,
            restaurant_name:   restaurantName,
            coupon_code:       selectedCoupon?.code        ?? null,
            discount_type:     selectedCoupon?.discount_type  ?? null,
            discount_value:    selectedCoupon?.discount_value  ?? null,
            offer_description: selectedCoupon?.description  ?? null,
            valid_until:       selectedCoupon?.valid_until  ?? null,
          }),
        },
      )
      const startJson = await startRes.json()
      const jobId: string = startJson.message?.job_id
      if (!jobId) throw new Error('Failed to start download job')

      // 2. Poll status every 2 s until done or error (60 s timeout).
      const deadline = Date.now() + 60_000
      let cdnUrl: string | null = null

      while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 2000))

        const pollRes  = await fetch(
          `/api/method/flamezo_backend.flamezo.api.story_generator.get_story_download_status?job_id=${jobId}`,
          { headers: { 'X-Frappe-CSRF-Token': csrf } },
        )
        const pollJson = await pollRes.json()
        const status   = pollJson.message?.status

        if (status === 'done') {
          cdnUrl = pollJson.message?.url
          break
        }
        if (status === 'error') {
          throw new Error(pollJson.message?.error || 'Generation failed')
        }
        // 'pending' | 'processing' → keep polling
      }

      if (!cdnUrl) throw new Error('Timed out waiting for download')

      // 3. Download directly from CDN — fast, no Frappe bandwidth used.
      const ext  = mediaType === 'video' ? 'mp4' : 'jpg'
      const a    = document.createElement('a')
      a.href     = cdnUrl
      a.download = `${restaurantName || 'story'}-preview.${ext}`
      a.click()

      toast.success('Downloaded!', { id: loadingToast })
    } catch (err) {
      console.error('[download]', err)
      toast.error('Could not download preview', { id: loadingToast })
    } finally {
      setDownloading(false)
    }
  }

  if (!selectedRestaurant) {
    return <div className="p-8 text-center text-muted-foreground">Select a restaurant to configure UGC cashback.</div>
  }

  const tpl = templates[0]
  const vStats = ((voucherStatsRes as any)?.message || voucherStatsRes)?.data
  const restaurantName = (restaurants as any[]).find(
    r => r.name === selectedRestaurant || r.restaurant_id === selectedRestaurant
  )?.restaurant_name || ''
  const selectedCoupon = (coupons as any[] | undefined)?.find((c: any) => c.name === viewerCoupon)

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-wrap">
            <Megaphone className="w-8 h-8 text-primary" />
            <h1 className="text-3xl font-bold tracking-tight">UGC Cashback</h1>
            <Badge variant="secondary" className="text-xs">Growth Loop</Badge>
            {ugcIsActive ? (
              <span className="flex items-center gap-1 text-xs font-semibold text-green-600 bg-green-50 border border-green-200 rounded-full px-2.5 py-0.5 dark:bg-green-900/20 dark:border-green-800 dark:text-green-400">
                <CheckCircle2 className="w-3.5 h-3.5" /> UGC Active
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2.5 py-0.5 dark:bg-amber-900/20 dark:border-amber-800 dark:text-amber-400">
                <XCircle className="w-3.5 h-3.5" /> Setup incomplete
              </span>
            )}
          </div>
          <Button onClick={() => setIsSimulatorOpen(true)} className="gap-2 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white shadow-md rounded-full px-5 w-full sm:w-auto">
            <PlayCircle className="w-4 h-4" />
            Show how it works
          </Button>
        </div>
        <p className="text-muted-foreground mt-2">
          Diners keep a story for your restaurant and earn wallet cashback — <strong>your story views in ₹, up to 100% of the bill</strong>.
        </p>
      </div>

      {!ugcIsActive && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex gap-3 text-amber-900 dark:bg-amber-900/10 dark:border-amber-900/20 dark:text-amber-400">
          <Info className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <p className="text-sm">
            UGC cashback is <strong>inactive</strong>. To activate it:
            {templates.length === 0 && <span className="block mt-1">① Upload your <strong>story template</strong> below.</span>}
            {!viewerCoupon && <span className="block mt-1">{templates.length === 0 ? '②' : '①'} Set a <strong>flat-discount coupon for story viewers</strong> in the Story Coupons section below.</span>}
            {viewerCoupon && templates.length > 0 && <span className="block mt-1"> Viewer coupon must use <strong>flat discount</strong> (not percent).</span>}
          </p>
        </div>
      )}

      {/* Voucher stats — last 30 days */}
      {vStats && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2"><Wallet className="w-4 h-4 text-primary" />Story Cashback Vouchers <span className="text-xs font-normal text-muted-foreground ml-1">last 30 days</span></CardTitle>
            <CardDescription>Vouchers issued, redeemed, and outstanding for this restaurant.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="rounded-lg border bg-muted/30 p-4">
                <p className="text-2xl font-black">{vStats.totalIssued ?? 0}</p>
                <p className="text-xs text-muted-foreground mt-0.5">Vouchers Issued</p>
              </div>
              <div className="rounded-lg border bg-muted/30 p-4">
                <p className="text-2xl font-black">₹{vStats.totalIssuedValue ?? 0}</p>
                <p className="text-xs text-muted-foreground mt-0.5">Total Value Issued</p>
              </div>
              <div className="rounded-lg border bg-muted/30 p-4">
                <p className="text-2xl font-black">₹{vStats.totalRedeemedValue ?? 0}</p>
                <p className="text-xs text-muted-foreground mt-0.5">Total Redeemed</p>
              </div>
              <div className="rounded-lg border bg-muted/30 p-4">
                <p className="text-2xl font-black">{vStats.active ?? 0}</p>
                <p className="text-xs text-muted-foreground mt-0.5">Active Vouchers</p>
                {(vStats.expiringSoon ?? 0) > 0 && (
                  <p className="text-[10px] text-amber-600 mt-1">{vStats.expiringSoon} expiring in 7 days</p>
                )}
              </div>
            </div>
            <div className="flex gap-4 mt-4 text-xs text-muted-foreground">
              <span>{vStats.exhausted ?? 0} fully redeemed</span>
              <span>·</span>
              <span>{vStats.expired ?? 0} expired</span>
              <span>·</span>
              <span>{vStats.redemptionCount ?? 0} total redemption events</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Template + preview — 50 / 50 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2"><ImagePlus className="w-4 h-4 text-primary" />Story Template</CardTitle>
            <CardDescription>Upload <strong>one</strong> ready-made image or video diners share. Bake your coupon code & branding into it.</CardDescription>
          </CardHeader>
          <CardContent className="flex justify-center">
            {tpl ? (
              <div className="relative rounded-xl border overflow-hidden w-[210px] aspect-[9/16] bg-muted">
                {tpl.url ? (
                  isVideo(tpl)
                    ? <video src={tpl.url} muted playsInline className="w-full h-full object-cover" />
                    : <img src={tpl.url} alt={tpl.label} className="w-full h-full object-cover" />
                ) : <div className="flex items-center justify-center h-full text-xs text-muted-foreground">processing…</div>}
                {isVideo(tpl) && <Film className="absolute bottom-2 left-2 w-4 h-4 text-white drop-shadow" />}
                <button onClick={() => removeTemplate(tpl.media_asset)}
                  className="absolute top-2 right-2 flex items-center gap-1 bg-red-600/90 hover:bg-red-600 text-white text-[11px] font-semibold rounded-full px-2.5 py-1 shadow">
                  <Trash2 className="w-3 h-3" /> Delete
                </button>
              </div>
            ) : (
              <button onClick={() => fileRef.current?.click()} disabled={uploading}
                className="rounded-xl border-2 border-dashed w-[210px] aspect-[9/16] flex flex-col items-center justify-center gap-2 text-muted-foreground hover:border-primary hover:text-primary transition">
                {uploading ? <Loader2 className="w-7 h-7 animate-spin" /> : <Upload className="w-7 h-7" />}
                <span className="text-sm">{uploading ? 'Uploading…' : 'Add image / video'}</span>
              </button>
            )}
            <input ref={fileRef} type="file" accept="image/*,video/*" className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if (f) handleUpload(f) }} />
          </CardContent>
        </Card>

        {/* Story preview — with Flamezo brand overlay */}
        <div className="flex flex-col gap-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Story Preview</CardTitle>
              <CardDescription>Live preview — updates as you change the coupon selection below.</CardDescription>
            </CardHeader>
            <CardContent className="flex justify-center">
              <div ref={previewRef} className="rounded-[1.6rem] overflow-hidden shadow-xl border-4 border-gray-900 bg-black">
                <StoryTemplateFrame
                  mediaUrl={tpl?.url || ''}
                  mediaType={tpl && isVideo(tpl) ? 'video' : 'image'}
                  width={210}
                  couponCode={selectedCoupon?.code}
                  discountType={selectedCoupon?.discount_type}
                  discountValue={selectedCoupon?.discount_value}
                  validUntil={selectedCoupon?.valid_until}
                  offerDescription={selectedCoupon?.description}
                  restaurantName={restaurantName}
                />
              </div>
            </CardContent>
          </Card>

          {/* Action buttons below the preview card */}
          <div className="flex gap-2">
            <Button variant="outline" size="sm" className="flex-1 gap-1.5" onClick={() => setPreviewOpen(true)}>
              <Expand className="w-3.5 h-3.5" /> Preview
            </Button>
            <Button variant="outline" size="sm" className="flex-1 gap-1.5" onClick={downloadPreview} disabled={downloading}>
              {downloading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
              {downloading ? 'Saving…' : 'Download'}
            </Button>
            {tpl && (
              <Button variant="destructive" size="sm" className="flex-1 gap-1.5 text-white" onClick={() => removeTemplate(tpl.media_asset)}>
                <Trash2 className="w-3.5 h-3.5 text-white" /> Delete
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* ── Full-size preview modal ── */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-[420px] flex flex-col items-center gap-4 p-6">
          <DialogHeader className="w-full">
            <DialogTitle>Story Preview</DialogTitle>
          </DialogHeader>
          <div className="rounded-[2rem] overflow-hidden shadow-2xl border-4 border-gray-900 bg-black">
            <StoryTemplateFrame
              mediaUrl={tpl?.url || ''}
              mediaType={tpl && isVideo(tpl) ? 'video' : 'image'}
              width={360}
              couponCode={selectedCoupon?.code}
              discountType={selectedCoupon?.discount_type}
              discountValue={selectedCoupon?.discount_value}
              validUntil={selectedCoupon?.valid_until}
              offerDescription={selectedCoupon?.description}
              restaurantName={restaurantName}
            />
          </div>
        </DialogContent>
      </Dialog>

      {/* Coupons — the one restaurant-managed control */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2"><Ticket className="w-4 h-4 text-primary" />Story Coupons</CardTitle>
          <CardDescription>Set the coupon shown to friends who view the story. Required to activate UGC — must be a flat (₹) discount.</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label className="text-sm">Coupon for story viewers <span className="text-red-500">*</span></Label>
            <Select value={viewerCoupon || 'none'} onValueChange={v => { const val = v === 'none' ? '' : v; setViewerCoupon(val); saveCoupons({ coupon_for_viewers: val }) }}>
              <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                {(coupons || []).filter((c: any) => c.discount_type === 'flat').map((c: any) => (
                  <SelectItem key={c.name} value={c.name}>{c.code}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-muted-foreground">Required for UGC activation — must be a flat (₹) discount. Shown to friends who see the story.</p>
            {!(coupons || []).some((c: any) => c.discount_type === 'flat') && (coupons || []).length > 0 && (
              <p className="text-[11px] text-amber-600 dark:text-amber-400">No flat-discount coupons found. Go to Coupons and create one with a fixed ₹ amount.</p>
            )}
          </div>
          <div className="rounded-lg border bg-muted/40 p-4 space-y-2">
            <p className="text-sm font-medium">What the poster earns (platform-fixed)</p>
            <p className="text-sm text-muted-foreground">Flamezo automatically issues the poster a <strong className="text-foreground">Story Cashback Voucher = min(story views, bill, ₹2,000)</strong>. They get <strong className="text-foreground">33% off each return visit</strong> until the balance is fully redeemed.</p>
            <p className="text-[11px] text-muted-foreground">Voucher valid 45 days · redeemable only at this restaurant · max ₹2,000 per claim · managed by Flamezo.</p>
          </div>
        </CardContent>
      </Card>

      {/* Platform-managed rules — read-only guidelines */}
      <Card className="bg-muted/30 border-dashed">
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2 text-muted-foreground">
            <Info className="w-4 h-4" /> How it works (managed by Flamezo)
          </CardTitle>
          <CardDescription>Cashback rules, caps and verification are standardised across all Flamezo restaurants.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-1.5">
          <p>• <strong className="text-foreground">"Keep a story, get up to 100% cashback"</strong> — cashback = story views in ₹, capped at the bill (max ₹2,000).</p>
          <p>• Cashback is issued as a <strong className="text-foreground">restaurant-locked voucher</strong> — 33% off each return visit until fully redeemed. Valid 45 days.</p>
          <p>• Your staff verify the diner's story at the table; the next day the diner uploads their view count and AI reads it.</p>
          <p>• Up to 2 claims per restaurant per 30 days · stories must stay live 24h · fraud is auto-screened.</p>
        </CardContent>
      </Card>

      <UGCGrowthSimulatorModal isOpen={isSimulatorOpen} onClose={() => setIsSimulatorOpen(false)} />
    </div>
  )
}

