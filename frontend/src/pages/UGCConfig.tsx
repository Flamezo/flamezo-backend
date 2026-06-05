import { useState, useEffect, useRef } from 'react'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappeGetCall, useFrappePostCall, useFrappeGetDocList } from '@/lib/frappe'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { toast } from 'sonner'
import { Megaphone, Info, ImagePlus, Trash2, Upload, Loader2, Film, Ticket } from 'lucide-react'
import { uploadToR2, getMediaType } from '@/lib/r2Upload'

type TemplateRow = { media_asset: string; label?: string; is_default?: number; url?: string; kind?: string }

const isVideo = (t: TemplateRow) =>
  t.kind === 'video' || (!!t.url && /\.(mp4|webm|mov|m4v|ogg)(\?|$)/i.test(t.url))

export default function UGCConfig() {
  const { selectedRestaurant, restaurant } = useRestaurant()
  const [configName, setConfigName] = useState<string>('')
  const [templates, setTemplates] = useState<TemplateRow[]>([])
  const [viewerCoupon, setViewerCoupon] = useState<string>('')
  const [nextVisitCoupon, setNextVisitCoupon] = useState<string>('')
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const { data: configRes, mutate } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.ugc.get_ugc_config',
    selectedRestaurant ? { restaurant_id: selectedRestaurant } : undefined,
    selectedRestaurant ? `ugc-config-${selectedRestaurant}` : undefined,
  )
  const { call: saveConfig } = useFrappePostCall('flamezo_backend.flamezo.api.ugc.save_ugc_config')
  const { call: deleteTemplate } = useFrappePostCall('flamezo_backend.flamezo.api.ugc.delete_ugc_template')

  const { data: coupons } = useFrappeGetDocList('Coupon', {
    fields: ['name', 'code'],
    filters: selectedRestaurant ? [['restaurant', '=', selectedRestaurant]] : [],
    limit: 200,
  } as any, selectedRestaurant ? `ugc-coupons-${selectedRestaurant}` : null)

  useEffect(() => {
    const body: any = (configRes as any)?.message || configRes
    if (body?.success && body.data) {
      setConfigName(body.data.name || '')
      setTemplates(body.data.templates || [])
      setViewerCoupon(body.data.coupon_for_viewers || '')
      setNextVisitCoupon(body.data.next_visit_coupon || '')
    }
  }, [configRes])

  const saveCoupons = async (patch: { coupon_for_viewers?: string; next_visit_coupon?: string }) => {
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

  if (!selectedRestaurant) {
    return <div className="p-8 text-center text-muted-foreground">Select a restaurant to configure UGC cashback.</div>
  }

  const tpl = templates[0]
  const restaurantName = (restaurant as any)?.restaurant_name || 'your restaurant'

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <Megaphone className="w-8 h-8 text-primary" />
          <h1 className="text-3xl font-bold tracking-tight">UGC Cashback</h1>
          <Badge variant="secondary" className="text-xs">Growth Loop</Badge>
        </div>
        <p className="text-muted-foreground mt-2">
          Diners keep a story for your restaurant and earn wallet cashback — <strong>your story views in ₹, up to 100% of the bill</strong>.
        </p>
      </div>

      {templates.length === 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex gap-3 text-amber-900 dark:bg-amber-900/10 dark:border-amber-900/20 dark:text-amber-400">
          <Info className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <p className="text-sm">Upload your <strong>story template</strong> below to activate the offer for your diners.</p>
        </div>
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

        {/* Story preview mockup */}
        <Card>
          <CardHeader><CardTitle className="text-base">Story Preview</CardTitle><CardDescription>How it appears on a diner's story.</CardDescription></CardHeader>
          <CardContent className="flex justify-center">
            <div className="relative w-[210px] aspect-[9/16] rounded-[1.6rem] overflow-hidden bg-black shadow-xl border-4 border-gray-900">
              {tpl?.url ? (
                isVideo(tpl)
                  ? <video src={tpl.url} autoPlay muted loop playsInline className="absolute inset-0 w-full h-full object-cover" />
                  : <img src={tpl.url} className="absolute inset-0 w-full h-full object-cover" />
              ) : (
                <div className="absolute inset-0 flex items-center justify-center text-white/50 text-xs text-center px-4">Upload a template to preview</div>
              )}
              <div className="absolute top-2 left-2 right-2 h-0.5 rounded-full bg-white/40 overflow-hidden"><div className="h-full w-1/3 bg-white" /></div>
              <div className="absolute top-4 left-2.5 right-2.5 flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-yellow-400 via-pink-500 to-purple-600 p-[2px]"><div className="w-full h-full rounded-full bg-gray-300" /></div>
                <span className="text-white text-[11px] font-semibold drop-shadow truncate">{restaurantName}</span>
                <span className="text-white/70 text-[10px]">now</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Coupons — the one restaurant-managed control */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2"><Ticket className="w-4 h-4 text-primary" />Story Coupons <span className="text-xs font-normal text-muted-foreground">(optional)</span></CardTitle>
          <CardDescription>Attach your own coupons — one shown to friends who see the story, one for the poster's next visit.</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label className="text-sm">Coupon for story viewers</Label>
            <Select value={viewerCoupon || 'none'} onValueChange={v => { const val = v === 'none' ? '' : v; setViewerCoupon(val); saveCoupons({ coupon_for_viewers: val }) }}>
              <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                {(coupons || []).map((c: any) => <SelectItem key={c.name} value={c.name}>{c.code}</SelectItem>)}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-muted-foreground">Shown to friends who see the story.</p>
          </div>
          <div className="space-y-1.5">
            <Label className="text-sm">Next-visit coupon for poster</Label>
            <Select value={nextVisitCoupon || 'none'} onValueChange={v => { const val = v === 'none' ? '' : v; setNextVisitCoupon(val); saveCoupons({ next_visit_coupon: val }) }}>
              <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                {(coupons || []).map((c: any) => <SelectItem key={c.name} value={c.name}>{c.code}</SelectItem>)}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-muted-foreground">Rewarded to the diner for coming back.</p>
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
          <p>• <strong className="text-foreground">“Keep a story, get up to 100% cashback”</strong> — cashback = story views in ₹, capped at the bill: min(views, bill).</p>
          <p>• Your staff verify the diner's story at the table; the next day the diner uploads their view count and AI reads it.</p>
          <p>• One claim per order · paid as Flamezo wallet cash · stories must stay live 24h · fraud is auto-screened.</p>
        </CardContent>
      </Card>
    </div>
  )
}
