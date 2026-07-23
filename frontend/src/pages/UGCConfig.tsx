import { useState, useEffect, useRef } from 'react'
import StoryTemplateFrame from '@/components/StoryTemplateFrame'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappeGetCall, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { toast } from 'sonner'
import { Megaphone, Info, ImagePlus, Trash2, Upload, Loader2, Film, Ticket, CheckCircle2, XCircle, Wallet, PlayCircle, Expand, Download, ShieldCheck, Lock, Unlock, Eye, EyeOff, RefreshCw } from 'lucide-react'
import { uploadToR2, getMediaType } from '@/lib/r2Upload'
import UGCGrowthSimulatorModal from '@/components/UGCGrowthSimulatorModal'
import { Button } from '@/components/ui/button'
import { UGCConfigSkeleton } from '@/components/PageSkeletons'

type TemplateRow = { media_asset: string; label?: string; is_default?: number; url?: string; kind?: string }

const isVideo = (t: TemplateRow) =>
  t.kind === 'video' || (!!t.url && /\.(mp4|webm|mov|m4v|ogg)(\?|$)/i.test(t.url))

export default function UGCConfig() {
  const { selectedRestaurant, restaurants } = useRestaurant()
  const [configName, setConfigName] = useState<string>('')
  const [templates, setTemplates] = useState<TemplateRow[]>([])

  // Inline viewer coupon state
  const [viewerCouponCode, setViewerCouponCode] = useState<string>('')
  const [viewerDiscountType, setViewerDiscountType] = useState<'flat' | 'percent'>('flat')
  const [viewerDiscountValue, setViewerDiscountValue] = useState<string>('')
  const [viewerDiscountCap, setViewerDiscountCap] = useState<string>('')
  const [viewerCouponDesc, setViewerCouponDesc] = useState<string>('')
  const [savingCoupon, setSavingCoupon] = useState(false)

  const [ugcIsActive, setUgcIsActive] = useState<boolean>(false)
  const [ugcEnabled, setUgcEnabled] = useState<boolean>(true)
  const [togglingUgc, setTogglingUgc] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [isSimulatorOpen, setIsSimulatorOpen] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const previewRef = useRef<HTMLDivElement>(null)

const { data: configRes, mutate, isLoading } = useFrappeGetCall(
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
useEffect(() => {
    const body: any = (configRes as any)?.message || configRes
    if (body?.success && body.data) {
      setConfigName(body.data.name || '')
      setTemplates(body.data.templates || [])
      setUgcIsActive(!!body.data.ugc_is_active)
      setUgcEnabled(body.data.is_active !== 0)

      // Hydrate inline coupon fields from server
      const vc = body.data.viewer_coupon
      if (vc) {
        setViewerCouponCode(vc.code || '')
        setViewerDiscountType((vc.discount_type as 'flat' | 'percent') || 'flat')
        setViewerDiscountValue(vc.discount_value != null ? String(vc.discount_value) : '')
        setViewerDiscountCap(vc.discount_cap != null ? String(vc.discount_cap) : '')
        setViewerCouponDesc(vc.description || '')
      } else {
        // Check scalar fields directly (returned from _CONFIG_SCALAR_FIELDS)
        setViewerCouponCode(body.data.viewer_coupon_code || '')
        setViewerDiscountType(body.data.viewer_discount_type || 'flat')
        setViewerDiscountValue(body.data.viewer_discount_value != null ? String(body.data.viewer_discount_value) : '')
        setViewerDiscountCap(body.data.viewer_discount_cap != null ? String(body.data.viewer_discount_cap) : '')
        setViewerCouponDesc(body.data.viewer_coupon_description || '')
      }
    }
  }, [configRes])

  const toggleUgc = async () => {
    if (!selectedRestaurant || togglingUgc) return
    setTogglingUgc(true)
    const next = !ugcEnabled
    try {
      const res: any = await saveConfig({ restaurant_id: selectedRestaurant, payload: { is_active: next ? 1 : 0 } })
      const body = res?.message || res
      if (body?.success) {
        setUgcEnabled(next)
        setUgcIsActive(!!body.data?.ugc_is_active)
        toast.success(next ? 'UGC cashback enabled' : 'UGC cashback paused')
      } else throw new Error(body?.message || 'Save failed')
    } catch (e: any) { toast.error(e.message) } finally { setTogglingUgc(false) }
  }

  const saveCoupon = async () => {
    if (!selectedRestaurant) return
    if (!viewerCouponCode.trim()) { toast.error('Coupon code is required'); return }
    if (!viewerDiscountValue || parseFloat(viewerDiscountValue) <= 0) { toast.error('Discount value must be greater than 0'); return }
    if (viewerDiscountType === 'percent') {
      if (parseFloat(viewerDiscountValue) > 100) { toast.error('Percent discount cannot exceed 100%'); return }
      if (viewerDiscountCap && parseFloat(viewerDiscountCap) <= 0) { toast.error('Max Discount Cap must be greater than 0 if provided'); return }
    }
    setSavingCoupon(true)
    try {
      const patch = {
        viewer_coupon_code: viewerCouponCode.trim().toUpperCase(),
        viewer_discount_type: viewerDiscountType,
        viewer_discount_value: parseFloat(viewerDiscountValue),
        viewer_discount_cap: (viewerDiscountType === 'percent' && viewerDiscountCap) ? parseFloat(viewerDiscountCap) : 0,
        viewer_coupon_description: viewerCouponDesc.trim(),
      }
      const res: any = await saveConfig({ restaurant_id: selectedRestaurant, payload: patch })
      const body = res?.message || res
      if (body?.success) { toast.success('Viewer coupon saved'); await mutate() }
      else throw new Error(body?.message || 'Save failed')
    } catch (e: any) { toast.error(e.message || 'Failed to save') }
    finally { setSavingCoupon(false) }
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
      // The app stores the CSRF token at window.csrf_token (see lib/session.ts),
      // NOT window.frappe.csrf_token — reading the wrong source left it empty, so
      // the logged-in POST to start_story_download failed CSRF → "Could not download".
      const csrf = (window as any).csrf_token || ''
      const mediaType = isVideo(tpl) ? 'video' : 'image'

      const startRes = await fetch(
        '/api/method/flamezo_backend.flamezo.api.story_generator.start_story_download',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrf },
          body: JSON.stringify({
            template_url:      tpl.url,
            media_type:        mediaType,
            restaurant_name:   restaurantName,
            coupon_code:       viewerCouponCode || null,
            discount_type:     viewerDiscountType || null,
            discount_value:    viewerDiscountValue ? parseFloat(viewerDiscountValue) : null,
            offer_description: viewerCouponDesc || null,
            valid_until:       null,
          }),
        },
      )
      const startJson = await startRes.json()
      const jobId: string = startJson.message?.job_id
      if (!jobId) throw new Error('Failed to start download job')

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
      }

      if (!cdnUrl) throw new Error('Timed out waiting for download')

      const ext  = mediaType === 'video' ? 'mp4' : 'jpg'
      const filename = `${restaurantName || 'story'}-preview.${ext}`
      const proxyUrl = `/api/method/flamezo_backend.flamezo.api.ai_media.download_proxy?file_url=${encodeURIComponent(cdnUrl)}&filename=${encodeURIComponent(filename)}`

      // Fetch the file as a blob and download via a blob URL. A plain <a href>
      // navigation here happens AFTER the ~10s compositing await, so the user
      // gesture is gone and the browser silently drops the download. A blob
      // download is reliable post-await and shows up in the browser's download bar.
      const res = await fetch(proxyUrl)
      if (!res.ok) throw new Error(`Download failed (${res.status})`)
      const blob = await res.blob()
      const objectUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = objectUrl
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(objectUrl)

      toast.success('Downloaded!', { id: loadingToast })
    } catch (err) {
      console.error('[download]', err)
      toast.error('Could not download preview', { id: loadingToast })
    } finally {
      setDownloading(false)
    }
  }

  if (!selectedRestaurant) {
    return <div className="p-8 text-center text-muted-foreground">Select an outlet to configure UGC cashback.</div>
  }

  if (isLoading) return <UGCConfigSkeleton />

  const tpl = templates[0]
  const vStats = ((voucherStatsRes as any)?.message || voucherStatsRes)?.data
  const restaurantName = (restaurants as any[]).find(
    r => r.name === selectedRestaurant || r.restaurant_id === selectedRestaurant
  )?.restaurant_name || ''

  const couponIsSet = !!viewerCouponCode.trim() && parseFloat(viewerDiscountValue) > 0

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
            {/* Manual on/off toggle — only shown once setup is complete */}
            {(templates.length > 0 && couponIsSet) && (
              <button
                onClick={toggleUgc}
                disabled={togglingUgc}
                className="flex items-center gap-2 text-xs font-medium border rounded-full px-3 py-1 transition-colors hover:bg-muted disabled:opacity-60"
                title={ugcEnabled ? 'Pause UGC cashback' : 'Enable UGC cashback'}
              >
                {togglingUgc
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : (
                    <span className={`relative inline-flex h-4 w-7 shrink-0 rounded-full border-2 border-transparent transition-colors ${ugcEnabled ? 'bg-green-500' : 'bg-muted-foreground/30'}`}>
                      <span className={`pointer-events-none inline-block h-3 w-3 transform rounded-full bg-white shadow ring-0 transition duration-200 ${ugcEnabled ? 'translate-x-3' : 'translate-x-0'}`} />
                    </span>
                  )
                }
                {ugcEnabled ? 'Enabled' : 'Paused'}
              </button>
            )}
          </div>
          <Button onClick={() => setIsSimulatorOpen(true)} className="gap-2 bg-gradient-to-r from-orange-500 to-pink-500 hover:from-orange-600 hover:to-pink-600 text-white shadow-md rounded-full px-5 w-full sm:w-auto">
            <PlayCircle className="w-4 h-4" />
            Show how it works
          </Button>
        </div>
        <p className="text-muted-foreground mt-2">
          Customers keep a story for your outlet and earn wallet cashback — <strong>your story views in ₹, up to 100% of the bill</strong>.
        </p>
      </div>

      {!ugcIsActive && (
        <div className={`border rounded-lg p-4 flex gap-3 ${
          templates.length > 0 && couponIsSet
            ? 'bg-blue-50 border-blue-200 text-blue-900 dark:bg-blue-900/10 dark:border-blue-900/20 dark:text-blue-400'
            : 'bg-amber-50 border-amber-200 text-amber-900 dark:bg-amber-900/10 dark:border-amber-900/20 dark:text-amber-400'
        }`}>
          <Info className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <p className="text-sm">
            {templates.length > 0 && couponIsSet ? (
              <>
                <strong>Story preview is generating…</strong>
                <span className="block mt-1">Your template and coupon are set. UGC will activate automatically once the branded story preview is ready (usually under a minute).</span>
              </>
            ) : (
              <>
                UGC cashback is <strong>inactive</strong>. To activate it:
                {templates.length === 0 && <span className="block mt-1">① Upload your <strong>story template</strong> below.</span>}
                {!couponIsSet && <span className="block mt-1">{templates.length === 0 ? '②' : '①'} Set up a <strong>viewer coupon</strong> in the Story Viewer Coupon section below and save it.</span>}
              </>
            )}
          </p>
        </div>
      )}

      {/* Voucher stats — last 30 days */}
      {vStats && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2"><Wallet className="w-4 h-4 text-primary" />Story Cashback Vouchers <span className="text-xs font-normal text-muted-foreground ml-1">last 30 days</span></CardTitle>
            <CardDescription>Vouchers issued, redeemed, and outstanding for this outlet.</CardDescription>
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
            <CardDescription>Upload <strong>one</strong> ready-made image or video customers share. Bake your coupon code & branding into it.</CardDescription>
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
              <CardDescription>Live preview — updates as you configure the coupon below.</CardDescription>
            </CardHeader>
            <CardContent className="flex justify-center">
              <div ref={previewRef} className="rounded-[1.6rem] overflow-hidden shadow-xl border-4 border-gray-900 bg-black">
                <StoryTemplateFrame
                  mediaUrl={tpl?.url || ''}
                  mediaType={tpl && isVideo(tpl) ? 'video' : 'image'}
                  width={210}
                  couponCode={viewerCouponCode || undefined}
                  discountType={viewerDiscountType || undefined}
                  discountValue={viewerDiscountValue ? parseFloat(viewerDiscountValue) : undefined}
                  offerDescription={viewerCouponDesc || undefined}
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
              couponCode={viewerCouponCode || undefined}
              discountType={viewerDiscountType || undefined}
              discountValue={viewerDiscountValue ? parseFloat(viewerDiscountValue) : undefined}
              offerDescription={viewerCouponDesc || undefined}
              restaurantName={restaurantName}
            />
          </div>
        </DialogContent>
      </Dialog>

      {/* Story Viewer Coupon — inline form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2"><Ticket className="w-4 h-4 text-primary" />Story Viewer Coupon</CardTitle>
          <CardDescription>
            Exclusive coupon shown to friends who view the story. <strong>Required to activate UGC.</strong> Supports flat (₹) or percent (%) discount.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* Left — form */}
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="vc-code">Coupon Code <span className="text-red-500">*</span></Label>
                <Input
                  id="vc-code"
                  placeholder="e.g. RASNA99"
                  value={viewerCouponCode}
                  onChange={e => setViewerCouponCode(e.target.value.toUpperCase())}
                  className="font-mono uppercase"
                />
                <p className="text-[11px] text-muted-foreground">Shown on the story overlay and used at checkout by friends.</p>
              </div>

              <div className="space-y-1.5">
                <Label>Discount Type <span className="text-red-500">*</span></Label>
                <Select value={viewerDiscountType} onValueChange={(v: 'flat' | 'percent') => setViewerDiscountType(v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="flat">Flat (₹ off)</SelectItem>
                    <SelectItem value="percent">Percent (% off)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="vc-value">
                  {viewerDiscountType === 'flat' ? 'Amount (₹)' : 'Percent (%)'} <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="vc-value"
                  type="number"
                  placeholder={viewerDiscountType === 'flat' ? '99' : '15'}
                  value={viewerDiscountValue}
                  onChange={e => setViewerDiscountValue(e.target.value)}
                  min={1}
                  max={viewerDiscountType === 'percent' ? 100 : undefined}
                />
              </div>

              {viewerDiscountType === 'percent' && (
                <div className="space-y-1.5">
                  <Label htmlFor="vc-cap">Max Discount Cap (₹) <span className="text-muted-foreground font-normal">(optional)</span></Label>
                  <Input
                    id="vc-cap"
                    type="number"
                    placeholder="e.g. 150"
                    value={viewerDiscountCap}
                    onChange={e => setViewerDiscountCap(e.target.value)}
                    min={1}
                  />
                  <p className="text-[11px] text-muted-foreground">Maximum ₹ discount regardless of bill size.</p>
                </div>
              )}

              <div className="space-y-1.5">
                <Label htmlFor="vc-desc">Offer Label <span className="text-muted-foreground font-normal">(optional)</span></Label>
                <Input
                  id="vc-desc"
                  placeholder={viewerDiscountType === 'flat'
                    ? `₹${viewerDiscountValue || 'XX'} off your next visit`
                    : `${viewerDiscountValue || 'XX'}% off (up to ₹${viewerDiscountCap || 'XXX'})`}
                  value={viewerCouponDesc}
                  onChange={e => setViewerCouponDesc(e.target.value)}
                />
                <p className="text-[11px] text-muted-foreground">Short text shown on the story overlay. Auto-generated if left blank.</p>
              </div>

              <Button onClick={saveCoupon} disabled={savingCoupon} className="w-full">
                {savingCoupon ? <><Loader2 className="w-4 h-4 animate-spin mr-2" />Saving…</> : 'Save Viewer Coupon'}
              </Button>
            </div>

            {/* Right — info box */}
            <div className="rounded-lg border bg-muted/40 p-4 space-y-3">
              <p className="text-sm font-medium">What the story poster earns (platform-fixed)</p>
              <p className="text-sm text-muted-foreground">
                Flamezo automatically issues the poster a <strong className="text-foreground">Story Cashback Voucher = min(story views, bill, ₹2,000)</strong>.
              </p>
              <p className="text-sm text-muted-foreground">
                They redeem this by picking a <strong className="text-foreground">Free Item (up to 33% of their bill)</strong> on return visits. Because it's a free item, you only pay the <strong className="text-foreground">Item Cost (33%)</strong> instead of losing 100% in a cash discount, protecting your profit margins!
              </p>
              <p className="text-[11px] text-muted-foreground">Voucher valid 90 days · redeemable only at this outlet · max ₹2,000 per claim · managed by Flamezo.</p>
              <hr className="border-border" />
              <p className="text-sm font-medium">About the viewer coupon</p>
              <p className="text-sm text-muted-foreground">
                The viewer coupon is exclusive to UGC — it won't appear in general coupon management.
                Flamezo creates and manages the underlying coupon doc automatically when you save.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Staff Verification PIN */}
      <UGCPinSetupCard restaurantId={selectedRestaurant} />

      {/* Platform-managed rules — read-only guidelines */}
      <Card className="bg-muted/30 border-dashed">
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2 text-muted-foreground">
            <Info className="w-4 h-4" /> How it works (managed by Flamezo)
          </CardTitle>
          <CardDescription>Cashback rules, caps and verification are standardised across all Flamezo outlets.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-1.5">
          <p>• <strong className="text-foreground">"Keep a story, get up to 100% cashback"</strong> — cashback = story views in ₹, capped at the bill (max ₹2,000).</p>
          <p>• Cashback is issued as a <strong className="text-foreground">outlet-locked voucher</strong> — customer picks a free item worth up to 33% of each return visit's bill until fully redeemed. Valid 90 days.</p>
          <p>• <strong className="text-foreground">Zero Revenue Cannibalization</strong> — Customers pay their full bill in cash. The reward costs you only the raw cost (33%) of the free item, making UGC practically painless to fund.</p>
          <p>• Your staff verify the customer's story at the counter; the next day the customer uploads their view count and AI reads it.</p>
          <p>• Up to 2 claims per outlet per 30 days · stories must stay live 24h · fraud is auto-screened.</p>
        </CardContent>
      </Card>

      <UGCGrowthSimulatorModal isOpen={isSimulatorOpen} onClose={() => setIsSimulatorOpen(false)} />
    </div>
  )
}

// ─── Staff Verification PIN ───────────────────────────────────────────────────

function UGCPinSetupCard({ restaurantId }: { restaurantId: string }) {
  const [pin, setPin] = useState(['', '', '', ''])
  const [isSet, setIsSet] = useState<boolean | null>(null)
  const [currentPin, setCurrentPin] = useState('')
  const [saving, setSaving] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [showPin, setShowPin] = useState(false)
  const [showCurrentPin, setShowCurrentPin] = useState(false)

  const { call: setPinCall } = useFrappePostCall('flamezo_backend.flamezo.api.coupons.set_offer_pin')
  const { call: getPinStatus } = useFrappePostCall('flamezo_backend.flamezo.api.coupons.get_offer_pin_status')

  useEffect(() => {
    if (!restaurantId) return
    getPinStatus({ restaurant_id: restaurantId })
      .then((res: any) => {
        const payload = res?.message ?? res
        setIsSet(!!payload?.data?.is_set)
        setCurrentPin(payload?.data?.pin || '')
      })
      .catch(() => setIsSet(false))
  }, [restaurantId])

  const handleDigit = (index: number, value: string) => {
    if (!/^\d*$/.test(value)) return
    const next = [...pin]
    next[index] = value.slice(-1)
    setPin(next)
    if (value && index < 3) {
      const nextInput = document.getElementById(`ugc-pin-digit-${index + 1}`) as HTMLInputElement | null
      nextInput?.focus()
    }
  }

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !pin[index] && index > 0) {
      const prevInput = document.getElementById(`ugc-pin-digit-${index - 1}`) as HTMLInputElement | null
      prevInput?.focus()
    }
  }

  const handleSave = async () => {
    const fullPin = pin.join('')
    if (fullPin.length !== 4) { toast.error('Enter all 4 digits'); return }
    setSaving(true)
    try {
      const res = await setPinCall({ restaurant_id: restaurantId, pin: fullPin })
      const payload = (res as any)?.message ?? res
      if (payload?.success) {
        toast.success('PIN saved — staff can now verify UGC stories at the counter')
        setIsSet(true)
        setCurrentPin(fullPin)
        setShowForm(false)
        setPin(['', '', '', ''])
        setShowPin(false)
      } else {
        toast.error(payload?.error?.message || 'Failed to save PIN')
      }
    } catch { toast.error('Failed to save PIN') } finally { setSaving(false) }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-primary/10">
              <ShieldCheck className="h-4 w-4 text-primary" />
            </div>
            <div>
              <CardTitle className="text-base">Staff Verification PIN</CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Staff enter this on the customer's phone after they post their story
              </CardDescription>
            </div>
          </div>
          {isSet !== null && (
            <Badge variant={isSet ? 'default' : 'secondary'} className={isSet ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400 border-green-200' : ''}>
              {isSet ? <><Unlock className="h-3 w-3 mr-1" />PIN Set</> : <><Lock className="h-3 w-3 mr-1" />Not Set</>}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {!showForm ? (
          <div className="space-y-4">
            {isSet && currentPin ? (
              <div className="space-y-3">
                <p className="text-xs text-muted-foreground">Current PIN — share with your staff</p>
                <div className="flex items-center gap-3">
                  {(showCurrentPin ? currentPin.split('') : ['•', '•', '•', '•']).map((ch, i) => (
                    <div key={i} className="w-12 h-12 flex items-center justify-center text-xl font-bold rounded-xl border-2 border-border bg-muted/40 select-none">
                      {ch}
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() => setShowCurrentPin(v => !v)}
                    className="ml-1 p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  >
                    {showCurrentPin ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground leading-relaxed">
                Set a 4-digit PIN that staff enter on a customer's phone to confirm they posted a UGC story. Once the PIN is entered, cashback is unlocked immediately — no admin approval needed.
              </p>
            )}
            <Button size="sm" variant={isSet ? 'outline' : 'default'} onClick={() => setShowForm(true)}>
              {isSet ? 'Change PIN' : 'Set PIN'}
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">Enter a new 4-digit PIN:</p>
            <div className="flex items-center gap-3">
              {pin.map((digit, i) => (
                <input
                  key={i}
                  id={`ugc-pin-digit-${i}`}
                  type={showPin ? 'text' : 'password'}
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleDigit(i, e.target.value)}
                  onKeyDown={(e) => handleKeyDown(i, e)}
                  className="w-12 h-12 text-center text-xl font-bold rounded-xl border-2 bg-background focus:border-primary focus:outline-none transition-colors"
                />
              ))}
              <button
                type="button"
                onClick={() => setShowPin(v => !v)}
                className="ml-1 p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              >
                {showPin ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={handleSave} disabled={saving || pin.join('').length < 4}>
                {saving && <RefreshCw className="h-3.5 w-3.5 animate-spin mr-1.5" />}
                Save PIN
              </Button>
              <Button size="sm" variant="outline" onClick={() => { setShowForm(false); setPin(['', '', '', '']); setShowPin(false) }}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
