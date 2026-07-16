import { useState, useMemo, useEffect } from 'react'
import { useFrappePostCall } from 'frappe-react-sdk'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { Percent, IndianRupee, TrendingUp, TrendingDown, Eye, Loader2, AlertTriangle } from 'lucide-react'

type Mode = 'percent' | 'flat'
type Direction = 'increase' | 'decrease'
type Scope = 'all' | 'category' | 'selected'

interface PreviewSample {
  name: string
  product_name: string
  old_price: number
  new_price: number
}

interface BulkPriceUpdateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  restaurantId: string | null
  /** Docnames of categories covered by the "current category" scope (selected + its sub-categories). */
  scopedCategoryNames: string[]
  /** Label shown for the "current category" option. */
  currentCategoryLabel?: string
  /** Docnames of currently checked products. */
  selectedProductIds: string[]
  /** Called after a successful (non dry-run) apply so the caller can refresh. */
  onApplied: () => void
}

const money = (n: number) =>
  `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`

export default function BulkPriceUpdateDialog({
  open,
  onOpenChange,
  restaurantId,
  scopedCategoryNames,
  currentCategoryLabel,
  selectedProductIds,
  onApplied,
}: BulkPriceUpdateDialogProps) {
  const [mode, setMode] = useState<Mode>('percent')
  const [direction, setDirection] = useState<Direction>('increase')
  const [scope, setScope] = useState<Scope>('all')
  const [value, setValue] = useState('')

  // Results are always rounded to the nearest ₹1 for clean menu prices.
  const ROUND_TO = 1

  const [preview, setPreview] = useState<{
    total_matched: number
    updated: number
    samples: PreviewSample[]
  } | null>(null)

  const { call, loading } = useFrappePostCall(
    'flamezo_backend.flamezo.api.products.bulk_update_prices'
  )
  const [applying, setApplying] = useState(false)

  const hasSelection = selectedProductIds.length > 0
  const hasCategory = scopedCategoryNames.length > 0

  // Reset when opened
  useEffect(() => {
    if (open) {
      setMode('percent')
      setDirection('increase')
      setScope(hasSelection ? 'selected' : 'all')
      setValue('')
      setPreview(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const numericValue = parseFloat(value)
  const isValidValue = !isNaN(numericValue) && numericValue > 0

  const buildPayload = (dryRun: boolean) => ({
    restaurant_id: restaurantId,
    mode,
    value: numericValue,
    direction,
    scope,
    categories: scope === 'category' ? scopedCategoryNames : undefined,
    product_ids: scope === 'selected' ? selectedProductIds : undefined,
    round_to: ROUND_TO,
    // Never touch the original/MRP price — only the actual selling price changes.
    include_original_price: 0,
    dry_run: dryRun ? 1 : 0,
  })

  // Invalidate preview whenever inputs change
  useEffect(() => {
    setPreview(null)
  }, [mode, direction, scope, value])

  const handlePreview = async () => {
    if (!isValidValue || !restaurantId) return
    try {
      const res = await call(buildPayload(true))
      const msg = res?.message
      if (msg?.success) {
        setPreview({
          total_matched: msg.total_matched,
          updated: msg.updated,
          samples: msg.samples || [],
        })
      } else {
        toast.error(msg?.error || 'Could not build preview')
      }
    } catch (e: any) {
      toast.error(e?.message || 'Could not build preview')
    }
  }

  const handleApply = async () => {
    if (!isValidValue || !restaurantId || !preview) return
    setApplying(true)
    try {
      const res = await call(buildPayload(false))
      const msg = res?.message
      if (msg?.success) {
        toast.success(
          msg.updated
            ? `Updated prices for ${msg.updated} item${msg.updated === 1 ? '' : 's'}`
            : 'No items needed updating'
        )
        onApplied()
        onOpenChange(false)
      } else {
        toast.error(msg?.error || 'Update failed')
      }
    } catch (e: any) {
      toast.error(e?.message || 'Update failed')
    } finally {
      setApplying(false)
    }
  }

  const scopeOptions: { key: Scope; label: string; hint: string; disabled?: boolean }[] = useMemo(
    () => [
      { key: 'all', label: 'Entire menu', hint: 'Every item in this restaurant' },
      {
        key: 'category',
        label: currentCategoryLabel ? `Category: ${currentCategoryLabel}` : 'Current category',
        hint: 'Selected category and its sub-categories',
        disabled: !hasCategory,
      },
      {
        key: 'selected',
        label: `Selected items (${selectedProductIds.length})`,
        hint: 'Only the items you have checked',
        disabled: !hasSelection,
      },
    ],
    [currentCategoryLabel, hasCategory, hasSelection, selectedProductIds.length]
  )

  const previewExample = useMemo(() => {
    if (!isValidValue) return null
    const base = 200
    const delta = mode === 'percent' ? base * (numericValue / 100) : numericValue
    const signed = direction === 'decrease' ? base - delta : base + delta
    const clamped = Math.max(0, signed)
    const rounded = Math.round(clamped / ROUND_TO) * ROUND_TO
    return { base, rounded }
  }, [isValidValue, mode, numericValue, direction])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-orange-500" />
            Bulk Price Update
          </DialogTitle>
          <DialogDescription>
            Change many item prices at once — add a flat ₹ amount or a % (e.g. GST) across your menu.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-2">
          {/* Direction */}
          <div className="space-y-2">
            <Label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Direction</Label>
            <div className="grid grid-cols-2 gap-2">
              {([
                { key: 'increase', label: 'Increase', icon: TrendingUp },
                { key: 'decrease', label: 'Decrease', icon: TrendingDown },
              ] as const).map(({ key, label, icon: Icon }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setDirection(key)}
                  className={cn(
                    'flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-semibold transition-colors',
                    direction === key
                      ? 'border-orange-500 bg-orange-50 text-orange-700 dark:bg-orange-950/30 dark:text-orange-400'
                      : 'border-border bg-background text-muted-foreground hover:bg-muted'
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Mode + value */}
          <div className="space-y-2">
            <Label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Amount</Label>
            <div className="flex gap-2">
              <div className="grid grid-cols-2 gap-1 rounded-lg border border-border bg-muted/40 p-1">
                {([
                  { key: 'percent', label: '%', icon: Percent },
                  { key: 'flat', label: '₹', icon: IndianRupee },
                ] as const).map(({ key, label, icon: Icon }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setMode(key)}
                    className={cn(
                      'flex items-center justify-center gap-1 rounded-md px-3 py-2 text-sm font-bold transition-colors',
                      mode === key
                        ? 'bg-orange-500 text-white shadow'
                        : 'text-muted-foreground hover:bg-background'
                    )}
                    aria-label={key === 'percent' ? 'Percent' : 'Rupees'}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {label}
                  </button>
                ))}
              </div>
              <Input
                type="number"
                inputMode="decimal"
                min={0}
                step="0.01"
                placeholder={mode === 'percent' ? 'e.g. 5 (for 5% GST)' : 'e.g. 20'}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="flex-1"
                autoFocus
              />
            </div>
            {previewExample && (
              <p className="text-xs text-muted-foreground">
                Example: an item at {money(previewExample.base)} becomes{' '}
                <span className="font-semibold text-foreground">{money(previewExample.rounded)}</span>.
              </p>
            )}
          </div>

          {/* Scope */}
          <div className="space-y-2">
            <Label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Apply to</Label>
            <div className="space-y-1.5">
              {scopeOptions.map((opt) => (
                <button
                  key={opt.key}
                  type="button"
                  disabled={opt.disabled}
                  onClick={() => setScope(opt.key)}
                  className={cn(
                    'flex w-full items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors',
                    scope === opt.key
                      ? 'border-orange-500 bg-orange-50 dark:bg-orange-950/30'
                      : 'border-border bg-background hover:bg-muted',
                    opt.disabled && 'cursor-not-allowed opacity-40'
                  )}
                >
                  <span
                    className={cn(
                      'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2',
                      scope === opt.key ? 'border-orange-500' : 'border-muted-foreground/40'
                    )}
                  >
                    {scope === opt.key && <span className="h-2 w-2 rounded-full bg-orange-500" />}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-foreground">{opt.label}</span>
                    <span className="block text-xs text-muted-foreground">{opt.hint}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Preview result */}
          {preview && (
            <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-2">
              {preview.updated === 0 ? (
                <p className="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400">
                  <AlertTriangle className="h-4 w-4" />
                  No items would change with these settings.
                </p>
              ) : (
                <>
                  <p className="text-sm font-semibold text-foreground">
                    {preview.updated} of {preview.total_matched} item{preview.total_matched === 1 ? '' : 's'} will change:
                  </p>
                  <ul className="space-y-1">
                    {preview.samples.map((s) => (
                      <li key={s.name} className="flex items-center justify-between gap-2 text-xs">
                        <span className="truncate text-muted-foreground">{s.product_name}</span>
                        <span className="shrink-0 font-medium">
                          <span className="text-muted-foreground line-through">{money(s.old_price)}</span>
                          {' → '}
                          <span className="text-foreground">{money(s.new_price)}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                  {preview.updated > preview.samples.length && (
                    <p className="text-[11px] text-muted-foreground">
                      …and {preview.updated - preview.samples.length} more.
                    </p>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          {!preview ? (
            <Button
              onClick={handlePreview}
              disabled={!isValidValue || loading}
              className="bg-[#ea580c] hover:bg-[#c2410c] gap-2"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
              Preview changes
            </Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => setPreview(null)} disabled={applying}>
                Back
              </Button>
              <Button
                onClick={handleApply}
                disabled={applying || preview.updated === 0}
                className="bg-[#ea580c] hover:bg-[#c2410c] gap-2"
              >
                {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : <TrendingUp className="h-4 w-4" />}
                Apply to {preview.updated} item{preview.updated === 1 ? '' : 's'}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
