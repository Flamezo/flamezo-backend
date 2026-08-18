import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Flame, ImagePlus, X, Loader2 } from 'lucide-react'
import { useFrappePostCall } from '@/lib/frappe'
import { toast } from 'sonner'
import { getFrappeError } from '@/lib/utils'

const MAX_STORY_PHOTOS = 3
const MAX_ACTIVE_SLOTS = 3

type DurationPreset = '2h' | 'tonight' | 'tomorrow' | 'weekend'

/** Quick-select duration presets — deliberately NOT a raw datetime picker as
 * the default path. Merchants pick the exact same words their customers
 * will see ("Tonight", "Tomorrow") instead of doing mental date math. A
 * custom option is still one click away for anything else. */
const PRESETS: { id: DurationPreset; label: string }[] = [
  { id: '2h', label: 'Next 2 hours' },
  { id: 'tonight', label: 'Tonight' },
  { id: 'tomorrow', label: 'Tomorrow' },
  { id: 'weekend', label: 'This weekend' },
]

function computeWindow(preset: DurationPreset | 'custom'): { start: Date; end: Date } {
  const now = new Date()
  if (preset === '2h') {
    return { start: now, end: new Date(now.getTime() + 2 * 60 * 60 * 1000) }
  }
  if (preset === 'tonight') {
    const end = new Date(now)
    end.setHours(23, 59, 0, 0)
    return { start: now, end: end > now ? end : new Date(now.getTime() + 2 * 60 * 60 * 1000) }
  }
  if (preset === 'tomorrow') {
    const start = new Date(now)
    start.setDate(start.getDate() + 1)
    start.setHours(0, 0, 0, 0)
    const end = new Date(start)
    end.setHours(23, 59, 0, 0)
    return { start, end }
  }
  // weekend — next Saturday 00:00 through Sunday 23:59
  const start = new Date(now)
  const daysUntilSat = (6 - start.getDay() + 7) % 7 || 7
  start.setDate(start.getDate() + daysUntilSat)
  start.setHours(0, 0, 0, 0)
  const end = new Date(start)
  end.setDate(end.getDate() + 1)
  end.setHours(23, 59, 0, 0)
  return { start, end }
}

interface CouponOption {
  name: string
  code: string
  description?: string
}

export function HotDropDialog({
  open, onClose, outletId, coupons, onSaved, presetCouponName,
}: {
  open: boolean
  onClose: () => void
  outletId: string
  coupons: CouponOption[]
  onSaved: () => void
  /** Pre-select a coupon when opened via a specific coupon row's "Feature as Hot Drop" action. */
  presetCouponName?: string | null
}) {
  const [dealLabel, setDealLabel] = useState('')
  const [preset, setPreset] = useState<DurationPreset>('tonight')
  const [couponName, setCouponName] = useState<string>('__none__')
  const [photos, setPhotos] = useState<File[]>([])
  const [saving, setSaving] = useState(false)
  const [slotUsage, setSlotUsage] = useState<{ used: number; max: number } | null>(null)

  const { call: listMine } = useFrappePostCall('flamezo_backend.flamezo.api.hot_drops.list_merchant_hot_drops')
  const { call: requestUpload } = useFrappePostCall('flamezo_backend.flamezo.api.hot_drops.request_hot_drop_story_upload')
  const { call: createHotDrop } = useFrappePostCall('flamezo_backend.flamezo.api.hot_drops.create_hot_drop')

  useEffect(() => {
    if (!open) return
    setDealLabel('')
    setPreset('tonight')
    setCouponName(presetCouponName || '__none__')
    setPhotos([])
    listMine({ outlet_id: outletId })
      .then((res: any) => {
        const d = res?.message?.data
        if (d) setSlotUsage({ used: d.active_slots_used, max: d.max_slots })
      })
      .catch(() => setSlotUsage(null))
  }, [open, outletId, presetCouponName])

  const atCap = !!slotUsage && slotUsage.used >= slotUsage.max

  const handlePickPhotos = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    setPhotos((prev) => [...prev, ...files].slice(0, MAX_STORY_PHOTOS))
    e.target.value = ''
  }

  const handleSave = async () => {
    const label = dealLabel.trim()
    if (!label) {
      toast.error('Give the deal a short headline, e.g. "1+1 Biryani"')
      return
    }
    setSaving(true)
    try {
      const { start, end } = computeWindow(preset)

      // Upload photos first (optional — never blocks posting if skipped).
      const objectKeys: string[] = []
      for (const file of photos) {
        const presign: any = await requestUpload({
          outlet_id: outletId,
          filename: file.name,
          content_type: file.type || 'image/jpeg',
        })
        const data = presign?.message?.data
        if (!data?.upload_url) continue
        const putRes = await fetch(data.upload_url, {
          method: 'PUT',
          headers: { 'Content-Type': file.type || 'image/jpeg' },
          body: file,
        })
        if (putRes.ok) objectKeys.push(data.object_key)
      }

      await createHotDrop({
        outlet_id: outletId,
        deal_label: label,
        starts_at: start.toISOString(),
        ends_at: end.toISOString(),
        story_image_keys: JSON.stringify(objectKeys),
        coupon: couponName === '__none__' ? undefined : couponName,
      })

      toast.success('Hot Drop is live')
      onSaved()
      onClose()
    } catch (err) {
      toast.error(getFrappeError(err) || 'Failed to post Hot Drop')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Flame className="h-5 w-5 text-orange-500" />
            Feature as a Hot Drop
          </DialogTitle>
          <DialogDescription>
            Shows at the very top of Discover, above everything else, while it's live.
            {slotUsage && (
              <span className="block mt-1 font-medium text-foreground">
                {slotUsage.used} / {slotUsage.max} active slots used
              </span>
            )}
          </DialogDescription>
        </DialogHeader>

        {atCap ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-900 p-3 text-sm text-amber-800 dark:text-amber-300">
            You already have {slotUsage?.max} active or upcoming Hot Drops. End one from your Hot Drops list, or wait for one to finish, before posting another.
          </div>
        ) : (
          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label>Deal headline</Label>
              <Input
                placeholder='e.g. "1+1 Biryani" or "Free live music tonight"'
                value={dealLabel}
                onChange={(e) => setDealLabel(e.target.value)}
                maxLength={60}
              />
            </div>

            <div className="space-y-1.5">
              <Label>When</Label>
              <div className="grid grid-cols-2 gap-2">
                {PRESETS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setPreset(p.id)}
                    className={`h-9 rounded-lg border text-xs font-semibold transition-colors ${
                      preset === p.id
                        ? 'border-orange-500 bg-orange-50 text-orange-700 dark:bg-orange-950/30 dark:text-orange-400'
                        : 'border-border text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Link an existing coupon (optional)</Label>
              <Select value={couponName} onValueChange={setCouponName}>
                <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">No coupon — just a teaser</SelectItem>
                  {coupons.map((c) => (
                    <SelectItem key={c.name} value={c.name}>{c.code}{c.description ? ` — ${c.description}` : ''}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground">
                Linking a coupon lets customers actually redeem it via your usual claim flow. Skip it for a pure "come by tonight" teaser.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label>Photos (optional, up to {MAX_STORY_PHOTOS})</Label>
              <div className="flex items-center gap-2 flex-wrap">
                {photos.map((f, i) => (
                  <div key={i} className="relative h-14 w-14 rounded-lg overflow-hidden border border-border">
                    <img src={URL.createObjectURL(f)} className="h-full w-full object-cover" />
                    <button
                      type="button"
                      onClick={() => setPhotos((prev) => prev.filter((_, idx) => idx !== i))}
                      className="absolute top-0.5 right-0.5 bg-black/60 rounded-full p-0.5"
                    >
                      <X className="h-2.5 w-2.5 text-white" />
                    </button>
                  </div>
                ))}
                {photos.length < MAX_STORY_PHOTOS && (
                  <label className="h-14 w-14 rounded-lg border border-dashed border-border flex items-center justify-center cursor-pointer text-muted-foreground hover:text-foreground">
                    <ImagePlus className="h-5 w-5" />
                    <input type="file" accept="image/*" multiple className="hidden" onChange={handlePickPhotos} />
                  </label>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground">
                Skip this and we'll use your outlet's existing photo — never blocks posting.
              </p>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={handleSave} disabled={atCap || saving} className="bg-orange-500 hover:bg-orange-600">
            {saving ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Flame className="h-4 w-4 mr-1.5" />}
            {saving ? 'Posting…' : 'Post Hot Drop'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
