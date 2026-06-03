import { useState, useEffect, useRef } from 'react'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappeGetCall, useFrappePostCall, useFrappeGetDocList } from '@/lib/frappe'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from '@/components/ui/select'
import { toast } from 'sonner'
import { Megaphone, Info, ImagePlus, Trash2, Upload, Loader2 } from 'lucide-react'
import { uploadToR2 } from '@/lib/r2Upload'

type TemplateRow = { media_asset: string; label?: string; is_default?: number; url?: string }

const BLANK = {
  is_active: 0,
  min_order_amount: 0,
  max_per_customer_per_month: 1,
  proof_window_hours: 48,
  monthly_budget_coins: 0,
  cashback_percent_cap: 100,
  absolute_cap_coins: 1000,
  ai_provider: 'Gemini',
  ai_confidence_threshold: 0.85,
  coupon_for_viewers: '',
  next_visit_coupon: '',
  instructions: '',
  terms: '',
}

export default function UGCConfig() {
  const { selectedRestaurant } = useRestaurant()
  const [form, setForm] = useState<any>({ ...BLANK })
  const [configName, setConfigName] = useState<string>('')
  const [templates, setTemplates] = useState<TemplateRow[]>([])
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const { data: configRes, isLoading, mutate } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.ugc.get_ugc_config',
    selectedRestaurant ? { restaurant_id: selectedRestaurant } : undefined,
    selectedRestaurant ? `ugc-config-${selectedRestaurant}` : undefined,
  )
  const { call: saveConfig } = useFrappePostCall('flamezo_backend.flamezo.api.ugc.save_ugc_config')

  const { data: coupons } = useFrappeGetDocList('Coupon', {
    fields: ['name', 'code'],
    filters: selectedRestaurant ? [['restaurant', '=', selectedRestaurant]] : [],
    limit: 200,
  } as any, selectedRestaurant ? `ugc-coupons-${selectedRestaurant}` : null)

  useEffect(() => {
    const body: any = (configRes as any)?.message || configRes
    if (body?.success && body.data) {
      const d = body.data
      setConfigName(d.name || '')
      setTemplates(d.templates || [])
      setForm({
        ...BLANK,
        ...Object.fromEntries(Object.keys(BLANK).map(k => [k, d[k] ?? (BLANK as any)[k]])),
      })
    }
  }, [configRes])

  const set = (patch: Partial<typeof BLANK>) => setForm((p: any) => ({ ...p, ...patch }))

  const persist = async (overrides: any = {}, templatesOverride?: TemplateRow[]) => {
    if (!selectedRestaurant) return
    setSaving(true)
    try {
      const payload = {
        ...form, ...overrides,
        templates: (templatesOverride || templates).map(t => ({
          media_asset: t.media_asset, label: t.label, is_default: t.is_default ? 1 : 0,
        })),
      }
      const res: any = await saveConfig({ restaurant_id: selectedRestaurant, payload })
      const body = res?.message || res
      if (body?.success) {
        toast.success('UGC cashback settings saved')
        await mutate()
      } else {
        throw new Error(body?.message || 'Save failed')
      }
    } catch (e: any) {
      toast.error(e.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = (checked: boolean) => {
    set({ is_active: checked ? 1 : 0 })
    persist({ is_active: checked ? 1 : 0 })
  }

  const handleUpload = async (file: File) => {
    if (!configName) { toast.error('Config not ready yet'); return }
    if (!file.type.startsWith('image/')) { toast.error('Please upload an image'); return }
    setUploading(true)
    try {
      const result = await uploadToR2({
        ownerDoctype: 'UGC Cashback Config',
        ownerName: configName,
        mediaRole: 'ugc_template_image',
        file,
      })
      const next = [...templates, {
        media_asset: result.name, url: result.primary_url,
        label: file.name.replace(/\.[^.]+$/, ''), is_default: templates.length === 0 ? 1 : 0,
      }]
      setTemplates(next)
      await persist({}, next)
    } catch (e: any) {
      toast.error(e.message || 'Upload failed')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const removeTemplate = async (media_asset: string) => {
    const next = templates.filter(t => t.media_asset !== media_asset)
    setTemplates(next)
    await persist({}, next)
  }

  if (!selectedRestaurant) {
    return <div className="p-8 text-center text-muted-foreground">Select a restaurant to configure UGC cashback.</div>
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-12">
      {/* Header + master toggle */}
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <Megaphone className="w-8 h-8 text-primary" />
            <h1 className="text-3xl font-bold tracking-tight">UGC Cashback</h1>
            <Badge variant="secondary" className="text-xs">Growth Loop</Badge>
          </div>
          <p className="text-muted-foreground mt-2">
            Diners post a story for your restaurant and earn wallet cashback (= story views, capped at the order).
          </p>
        </div>
        <div className="flex items-center gap-4 bg-muted/50 p-3 px-4 rounded-xl border h-14 shrink-0">
          <div className="flex flex-col">
            <Label htmlFor="ugc-active" className="text-sm font-semibold">Enable Offer</Label>
            <p className="text-[10px] text-muted-foreground">
              {saving ? <span className="text-primary animate-pulse">Saving…</span> : 'Show on diner receipts'}
            </p>
          </div>
          <Switch id="ugc-active" checked={!!form.is_active} onCheckedChange={handleToggle} disabled={saving || isLoading} />
        </div>
      </div>

      {!form.is_active && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex gap-3 text-amber-900 dark:bg-amber-900/10 dark:border-amber-900/20 dark:text-amber-400">
          <Info className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <p className="text-sm">UGC cashback is <strong>off</strong>. Diners won't see the offer after ordering.</p>
        </div>
      )}

      {/* Templates */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2"><ImagePlus className="w-4 h-4 text-primary" />Story Templates</CardTitle>
          <CardDescription>Upload the pre-approved images diners share to their story. Bake the coupon code & your branding into the image.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {templates.map(t => (
              <div key={t.media_asset} className="relative group rounded-lg border overflow-hidden aspect-[9/16] bg-muted">
                {t.url ? <img src={t.url} alt={t.label} className="w-full h-full object-cover" /> : <div className="flex items-center justify-center h-full text-xs text-muted-foreground">processing…</div>}
                {!!t.is_default && <Badge className="absolute top-1 left-1 text-[10px]">Default</Badge>}
                <button onClick={() => removeTemplate(t.media_asset)} className="absolute top-1 right-1 bg-black/60 rounded-full p-1 opacity-0 group-hover:opacity-100 transition">
                  <Trash2 className="w-3.5 h-3.5 text-white" />
                </button>
              </div>
            ))}
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="rounded-lg border-2 border-dashed aspect-[9/16] flex flex-col items-center justify-center gap-2 text-muted-foreground hover:border-primary hover:text-primary transition"
            >
              {uploading ? <Loader2 className="w-6 h-6 animate-spin" /> : <Upload className="w-6 h-6" />}
              <span className="text-xs">{uploading ? 'Uploading…' : 'Add image'}</span>
            </button>
          </div>
          <input ref={fileRef} type="file" accept="image/*" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleUpload(f) }} />
        </CardContent>
      </Card>

      {/* Rules */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader><CardTitle className="text-base">Eligibility & Caps</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <Field label="Minimum order amount (₹)" hint="0 = any completed order">
              <Input type="number" min="0" value={form.min_order_amount} onChange={e => set({ min_order_amount: Number(e.target.value) })} />
            </Field>
            <Field label="Max claims per customer / month">
              <Input type="number" min="0" value={form.max_per_customer_per_month} onChange={e => set({ max_per_customer_per_month: Number(e.target.value) })} />
            </Field>
            <Field label="Cashback cap (% of order)">
              <Input type="number" min="1" max="100" value={form.cashback_percent_cap} onChange={e => set({ cashback_percent_cap: Number(e.target.value) })} />
            </Field>
            <Field label="Absolute cap per claim (₹)">
              <Input type="number" min="0" value={form.absolute_cap_coins} onChange={e => set({ absolute_cap_coins: Number(e.target.value) })} />
            </Field>
            <Field label="Monthly budget (₹)" hint="0 = unlimited; offer hides when exhausted">
              <Input type="number" min="0" value={form.monthly_budget_coins} onChange={e => set({ monthly_budget_coins: Number(e.target.value) })} />
            </Field>
            <Field label="Proof upload window (hours)">
              <Input type="number" min="1" value={form.proof_window_hours} onChange={e => set({ proof_window_hours: Number(e.target.value) })} />
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Verification & Coupons</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <Field label="AI provider (view-count reader)">
              <Select value={form.ai_provider} onValueChange={v => set({ ai_provider: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="Gemini">Gemini 2.5 Flash (recommended)</SelectItem>
                  <SelectItem value="OpenAI">GPT-4o</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label="Auto-approve confidence (0–1)" hint="Below this → staff review">
              <Input type="number" min="0" max="1" step="0.05" value={form.ai_confidence_threshold} onChange={e => set({ ai_confidence_threshold: Number(e.target.value) })} />
            </Field>
            <Field label="Coupon for story viewers" hint="Shown to friends who see the story">
              <Select value={form.coupon_for_viewers || 'none'} onValueChange={v => set({ coupon_for_viewers: v === 'none' ? '' : v })}>
                <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {(coupons || []).map((c: any) => <SelectItem key={c.name} value={c.name}>{c.code}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Next-visit coupon for poster">
              <Select value={form.next_visit_coupon || 'none'} onValueChange={v => set({ next_visit_coupon: v === 'none' ? '' : v })}>
                <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {(coupons || []).map((c: any) => <SelectItem key={c.name} value={c.name}>{c.code}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
          </CardContent>
        </Card>
      </div>

      {/* Copy */}
      <Card>
        <CardHeader><CardTitle className="text-base">Customer-Facing Copy</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <Field label="Short instructions" hint="e.g. Tag us & keep the story live for 24h">
            <Input value={form.instructions} onChange={e => set({ instructions: e.target.value })} />
          </Field>
          <Field label="Terms & conditions">
            <textarea
              className="w-full min-h-[100px] rounded-md border bg-background p-3 text-sm"
              value={form.terms} onChange={e => set({ terms: e.target.value })}
            />
          </Field>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={() => persist()} disabled={saving}>
          {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
          Save Settings
        </Button>
      </div>
    </div>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-sm">{label}</Label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  )
}
