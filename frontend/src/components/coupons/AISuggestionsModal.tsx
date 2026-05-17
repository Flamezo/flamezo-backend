/**
 * AISuggestionsModal
 * Displays AI-generated coupon suggestions with tone selector, offer type filter,
 * quota display, and one-click "Use This" to pre-fill the coupon form.
 */

import { useState } from 'react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Sparkles, Zap, Flame, Leaf, Tag, Gift, Bike, TrendingUp,
  RefreshCw, ChevronRight, AlertCircle, Info, Coins, CheckSquare, Square, CheckCheck,
} from 'lucide-react'
import { useFrappePostCall } from '@/lib/frappe'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

// ── Types ──────────────────────────────────────────────────────────────────────

export interface AISuggestion {
  code: string
  offer_type: 'coupon' | 'auto' | 'combo' | 'delivery'
  discount_type: 'flat' | 'percent' | 'delivery'
  discount_value: number
  min_order_amount: number
  max_discount_cap: number | null
  description: string
  detailed_description: string
  category: string
  valid_days_of_week: string[] | null
  valid_time_start: string | null
  valid_time_end: string | null
  max_uses: number
  max_uses_per_user: number
  can_stack: boolean
  priority: number
  // Display-only (not saved)
  goal: string
  rationale: string
  expected_impact: string
}

interface QuotaInfo {
  used: number
  limit: number
  free_remaining: number
  resets_on: string
  coins_per_paid_generation?: number
  wallet_balance?: number
}

interface AISuggestionsModalProps {
  open: boolean
  onClose: () => void
  restaurantId: string
  onUseSuggestion: (suggestion: AISuggestion) => void
  onSaveAll?: (suggestions: AISuggestion[]) => Promise<void>
  walletBalance?: number
}

// ── Constants ──────────────────────────────────────────────────────────────────

type Tone = 'calm' | 'attractive' | 'aggressive'

const TONES: { value: Tone; label: string; icon: React.ReactNode; description: string; color: string }[] = [
  {
    value: 'calm',
    label: 'Calm',
    icon: <Leaf className="h-4 w-4" />,
    description: 'Small, sustainable discounts (5–15%). Protects margins, builds loyalty.',
    color: 'border-emerald-400 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-400',
  },
  {
    value: 'attractive',
    label: 'Attractive',
    icon: <Zap className="h-4 w-4" />,
    description: 'Balanced offers (15–30%). Strong perceived value, competitive.',
    color: 'border-blue-400 bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-400',
  },
  {
    value: 'aggressive',
    label: 'Aggressive',
    icon: <Flame className="h-4 w-4" />,
    description: 'High-impact (25–50%) with safety caps. Maximum buzz, zero loss risk.',
    color: 'border-orange-400 bg-orange-50 dark:bg-orange-950/30 text-orange-700 dark:text-orange-400',
  },
]

const OFFER_TYPE_OPTIONS = [
  { value: 'any', label: 'Any Type' },
  { value: 'coupon', label: 'Coupon Code' },
  { value: 'auto', label: 'Auto Offer' },
  { value: 'combo', label: 'Combo Deal' },
  { value: 'delivery', label: 'Delivery Offer' },
]

const GOAL_COLORS: Record<string, string> = {
  acquisition: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  aov:         'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  frequency:   'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
  retention:   'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  delivery:    'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300',
  upsell:      'bg-pink-100 text-pink-700 dark:bg-pink-900/40 dark:text-pink-300',
  offpeak:     'bg-slate-100 text-slate-700 dark:bg-slate-900/40 dark:text-slate-300',
}

const GOAL_LABELS: Record<string, string> = {
  acquisition: 'New Customers',
  aov:         'Grow AOV',
  frequency:   'More Orders',
  retention:   'Retention',
  delivery:    'Delivery',
  upsell:      'Upsell',
  offpeak:     'Off-Peak',
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function getOfferTypeIcon(type: string) {
  switch (type) {
    case 'combo':    return <Gift className="h-3.5 w-3.5" />
    case 'auto':     return <TrendingUp className="h-3.5 w-3.5" />
    case 'delivery': return <Bike className="h-3.5 w-3.5" />
    default:         return <Tag className="h-3.5 w-3.5" />
  }
}

function getOfferTypeLabel(type: string) {
  return { coupon: 'Coupon', auto: 'Auto', combo: 'Combo', delivery: 'Delivery' }[type] ?? type
}

function formatDiscount(s: AISuggestion): string {
  if (s.discount_type === 'delivery') return 'FREE DELIVERY'
  if (s.discount_type === 'percent') {
    const cap = s.max_discount_cap ? ` (max ₹${s.max_discount_cap})` : ''
    return `${s.discount_value}% OFF${cap}`
  }
  return `₹${s.discount_value} OFF`
}

function getStripeColor(s: AISuggestion): string {
  if (s.discount_type === 'delivery' || s.offer_type === 'delivery') return 'bg-blue-500'
  if (s.offer_type === 'combo') return 'bg-purple-500'
  if (s.offer_type === 'auto') return 'bg-orange-500'
  return 'bg-green-500'
}

// ── SuggestionCard ─────────────────────────────────────────────────────────────

function SuggestionCard({
  suggestion,
  onUse,
  selected,
  onToggle,
}: {
  suggestion: AISuggestion
  onUse: () => void
  selected: boolean
  onToggle: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const discountLabel = formatDiscount(suggestion)
  const goalColor = GOAL_COLORS[suggestion.goal] ?? GOAL_COLORS.aov
  const goalLabel = GOAL_LABELS[suggestion.goal] ?? suggestion.goal

  return (
    <div
      className={cn(
        'relative flex flex-col rounded-xl border bg-card shadow-sm hover:shadow-md transition-all cursor-pointer',
        selected && 'ring-2 ring-primary border-primary',
      )}
      onClick={onToggle}
    >
      {/* Stripe */}
      <div className={cn('h-1 w-full rounded-t-xl', getStripeColor(suggestion))} />

      <div className="flex flex-col flex-1 p-4 gap-3">
        {/* Header row */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-col gap-1 min-w-0">
            <div className="flex items-center gap-1.5">
              {getOfferTypeIcon(suggestion.offer_type)}
              <span className="font-bold text-sm tracking-wider uppercase">{suggestion.code}</span>
            </div>
            <span className={cn('text-xs font-medium px-1.5 py-0.5 rounded-full w-fit', goalColor)}>
              {goalLabel}
            </span>
          </div>
          <div className="flex items-start gap-2 shrink-0">
            <div className="text-right">
              <div className="text-base font-bold text-green-600 dark:text-green-400 leading-tight">
                {discountLabel}
              </div>
              <Badge variant="outline" className="text-[10px] px-1.5 py-0 mt-0.5">
                {getOfferTypeLabel(suggestion.offer_type)}
              </Badge>
            </div>
            <div
              className="mt-0.5 text-primary"
              onClick={(e) => { e.stopPropagation(); onToggle() }}
            >
              {selected
                ? <CheckSquare className="h-5 w-5" />
                : <Square className="h-5 w-5 text-muted-foreground" />
              }
            </div>
          </div>
        </div>

        {/* Description */}
        <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
          {suggestion.description}
        </p>

        {/* Key parameters */}
        <div className="flex flex-wrap gap-1.5">
          {suggestion.min_order_amount > 0 && (
            <span className="text-[11px] bg-muted rounded px-1.5 py-0.5">
              Min ₹{suggestion.min_order_amount}
            </span>
          )}
          {suggestion.max_uses_per_user === 1 && (
            <span className="text-[11px] bg-muted rounded px-1.5 py-0.5">One-time</span>
          )}
          {suggestion.valid_days_of_week && suggestion.valid_days_of_week.length > 0 && (
            <span className="text-[11px] bg-muted rounded px-1.5 py-0.5">
              {suggestion.valid_days_of_week.map(d => d.slice(0, 3)).join(', ')}
            </span>
          )}
          {suggestion.valid_time_start && (
            <span className="text-[11px] bg-muted rounded px-1.5 py-0.5">
              {suggestion.valid_time_start.slice(0, 5)}–{suggestion.valid_time_end?.slice(0, 5)}
            </span>
          )}
          {suggestion.priority >= 8 && (
            <span className="text-[11px] bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300 rounded px-1.5 py-0.5">
              High priority
            </span>
          )}
        </div>

        {/* Rationale toggle */}
        {suggestion.rationale && (
          <button
            className="text-left"
            onClick={() => setExpanded(!expanded)}
            type="button"
          >
            <div className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors">
              <Info className="h-3 w-3" />
              <span>Why this works</span>
              <ChevronRight className={cn('h-3 w-3 transition-transform', expanded && 'rotate-90')} />
            </div>
            {expanded && (
              <div className="mt-1.5 text-[11px] text-muted-foreground bg-muted/50 rounded-lg p-2.5 leading-relaxed">
                <p>{suggestion.rationale}</p>
                {suggestion.expected_impact && (
                  <p className="mt-1 font-medium text-foreground/80">{suggestion.expected_impact}</p>
                )}
              </div>
            )}
          </button>
        )}

        {/* CTA */}
        <Button
          size="sm"
          variant="outline"
          className="w-full mt-auto gap-1.5"
          onClick={(e) => { e.stopPropagation(); onUse() }}
        >
          Edit &amp; Use
          <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  )
}

// ── Main Modal ─────────────────────────────────────────────────────────────────

export function AISuggestionsModal({
  open,
  onClose,
  restaurantId,
  onUseSuggestion,
  onSaveAll,
  walletBalance = 0,
}: AISuggestionsModalProps) {
  const [tone, setTone] = useState<Tone>('attractive')
  const [offerTypeFilter, setOfferTypeFilter] = useState<string>('any')
  const [suggestions, setSuggestions] = useState<AISuggestion[]>([])
  const [quota, setQuota] = useState<QuotaInfo | null>(null)
  const [hasGenerated, setHasGenerated] = useState(false)
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)

  const { call: generateSuggestions, loading } = useFrappePostCall(
    'flamezo_backend.flamezo.api.coupons.generate_coupon_suggestions'
  )

  const handleGenerate = async () => {
    try {
      const res = await generateSuggestions({
        restaurant_id: restaurantId,
        tone,
        offer_type_filter: offerTypeFilter === 'any' ? null : offerTypeFilter,
        count: 6,
      })

      // Frappe wraps all responses in { message: ... }
      const payload = res?.message ?? res

      if (!payload?.success) {
        const errCode = payload?.error_code || payload?.error?.code
        if (errCode === 'QUOTA_EXCEEDED') {
          toast.error('Monthly quota reached', {
            description: payload.message || 'Upgrade or wait for next month.',
          })
        } else if (errCode === 'INSUFFICIENT_BALANCE') {
          toast.error('Insufficient wallet balance', {
            description: payload.message,
          })
        } else {
          toast.error('Generation failed', { description: payload?.message || payload?.error?.message })
        }
        if (payload?.quota) setQuota(payload.quota)
        return
      }

      const data = payload.data ?? payload
      setSuggestions(data.suggestions ?? [])
      setQuota(data.quota ?? null)
      setHasGenerated(true)
      setSelectedCodes(new Set())

      if (data.coins_deducted > 0) {
        toast.info(`${data.coins_deducted} coins deducted`, {
          description: 'Paid generation — free quota was exhausted.',
        })
      }
    } catch (err: any) {
      toast.error('Something went wrong', { description: err?.message })
    }
  }

  const toggleCode = (code: string) => {
    setSelectedCodes(prev => {
      const next = new Set(prev)
      next.has(code) ? next.delete(code) : next.add(code)
      return next
    })
  }

  const allSelected = suggestions.length > 0 && selectedCodes.size === suggestions.length
  const toggleSelectAll = () => {
    setSelectedCodes(allSelected ? new Set() : new Set(suggestions.map(s => s.code)))
  }

  const handleSaveSelected = async () => {
    if (!onSaveAll || selectedCodes.size === 0) return
    const toSave = suggestions.filter(s => selectedCodes.has(s.code))
    setSaving(true)
    try {
      await onSaveAll(toSave)
      onClose()
    } finally {
      setSaving(false)
    }
  }

  const handleUse = (suggestion: AISuggestion) => {
    onUseSuggestion(suggestion)
    onClose()
    toast.success(`"${suggestion.code}" loaded into the form — review and save!`)
  }

  const selectedTone = TONES.find(t => t.value === tone)!
  const isPaid = quota ? quota.free_remaining <= 0 : false

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto p-0">
        {/* Header */}
        <div className="sticky top-0 z-10 bg-background border-b px-6 py-4">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-xl">
              <Sparkles className="h-5 w-5 text-primary" />
              AI Coupon Generator
            </DialogTitle>
            <DialogDescription className="text-sm">
              Generates smart, context-aware offers based on your menu and restaurant profile.
            </DialogDescription>
          </DialogHeader>

          {/* Controls */}
          <div className="mt-4 flex flex-col sm:flex-row gap-3">
            {/* Tone selector */}
            <div className="flex gap-2 flex-1">
              {TONES.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => setTone(t.value)}
                  className={cn(
                    'flex-1 flex flex-col items-center gap-1 rounded-xl border-2 p-2.5 text-center transition-all cursor-pointer',
                    tone === t.value ? t.color + ' border-2' : 'border-border hover:border-muted-foreground/40',
                  )}
                >
                  {t.icon}
                  <span className="text-xs font-semibold">{t.label}</span>
                </button>
              ))}
            </div>

            {/* Offer type filter */}
            <div className="flex flex-col gap-1 min-w-[160px]">
              <span className="text-xs text-muted-foreground font-medium">Offer Type</span>
              <Select value={offerTypeFilter} onValueChange={setOfferTypeFilter}>
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OFFER_TYPE_OPTIONS.map(o => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Tone description */}
          <p className="mt-2 text-xs text-muted-foreground italic">
            {selectedTone.description}
          </p>

          {/* Quota bar */}
          {quota && (
            <div className="mt-3 flex items-center gap-2 text-xs">
              {isPaid ? (
                <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                  <Coins className="h-3.5 w-3.5" />
                  <span>Free quota used — next generation costs <strong>2 coins</strong> (wallet: ₹{walletBalance})</span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <Sparkles className="h-3.5 w-3.5" />
                  <span>
                    <strong>{quota.free_remaining}</strong> of <strong>{quota.limit}</strong> free generations remaining this month
                    <span className="ml-1 opacity-60">(resets {quota.resets_on})</span>
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Generate button */}
          <div className="mt-3 flex justify-end">
            <Button
              onClick={handleGenerate}
              disabled={loading}
              className="gap-2 min-w-[160px]"
            >
              {loading ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  Generating…
                </>
              ) : hasGenerated ? (
                <>
                  <RefreshCw className="h-4 w-4" />
                  Regenerate
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Generate Suggestions
                </>
              )}
            </Button>
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-4">
          {/* Empty state */}
          {!hasGenerated && !loading && (
            <div className="py-16 flex flex-col items-center gap-3 text-center text-muted-foreground">
              <Sparkles className="h-12 w-12 opacity-20" />
              <p className="text-sm font-medium">Choose a tone and hit Generate</p>
              <p className="text-xs max-w-xs">
                The AI will analyse your menu, pricing, and restaurant profile to suggest
                6 ready-to-use coupons tailored for your business.
              </p>
            </div>
          )}

          {/* Loading skeleton */}
          {loading && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="rounded-xl border bg-card h-52 animate-pulse">
                  <div className="h-1 bg-muted rounded-t-xl" />
                  <div className="p-4 space-y-3">
                    <div className="h-4 bg-muted rounded w-2/3" />
                    <div className="h-3 bg-muted rounded w-full" />
                    <div className="h-3 bg-muted rounded w-4/5" />
                    <div className="h-8 bg-muted rounded mt-4" />
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Suggestions grid */}
          {hasGenerated && !loading && suggestions.length > 0 && (
            <>
              <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
                <p className="text-sm font-medium">
                  {suggestions.length} suggestions generated
                  <span className="ml-2 text-xs text-muted-foreground font-normal">
                    — select to save directly, or "Edit &amp; Use" to review first
                  </span>
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={toggleSelectAll}
                    className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {allSelected
                      ? <CheckSquare className="h-4 w-4 text-primary" />
                      : <Square className="h-4 w-4" />
                    }
                    {allSelected ? 'Deselect All' : 'Select All'}
                  </button>
                  {selectedCodes.size > 0 && onSaveAll && (
                    <Button
                      size="sm"
                      className="gap-1.5"
                      onClick={handleSaveSelected}
                      disabled={saving}
                    >
                      {saving ? (
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <CheckCheck className="h-3.5 w-3.5" />
                      )}
                      Save Selected ({selectedCodes.size})
                    </Button>
                  )}
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {suggestions.map((s) => (
                  <SuggestionCard
                    key={s.code}
                    suggestion={s}
                    onUse={() => handleUse(s)}
                    selected={selectedCodes.has(s.code)}
                    onToggle={() => toggleCode(s.code)}
                  />
                ))}
              </div>
            </>
          )}

          {/* Empty after generation */}
          {hasGenerated && !loading && suggestions.length === 0 && (
            <div className="py-12 flex flex-col items-center gap-2 text-muted-foreground">
              <AlertCircle className="h-8 w-8 opacity-40" />
              <p className="text-sm">No suggestions returned. Try regenerating.</p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
