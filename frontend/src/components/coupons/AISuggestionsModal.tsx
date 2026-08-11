/**
 * AISuggestionsModal
 * Displays AI-generated coupon suggestions with tone selector, offer type filter,
 * quota display, and one-click "Use This" to pre-fill the coupon form.
 */

import { useState, useEffect, useRef } from 'react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Sparkles, Zap, Flame, Leaf, Tag, Gift, TrendingUp,
  RefreshCw, ChevronRight, AlertCircle, Info, Coins, CheckSquare, Square, CheckCheck,
  Wand2, ImageIcon, MessageSquareText, Upload, X,
} from 'lucide-react'
import { useFrappePostCall } from '@/lib/frappe'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

// ── Types ──────────────────────────────────────────────────────────────────────

export interface AISuggestion {
  code: string
  offer_type: 'coupon' | 'auto' | 'combo'
  discount_type: 'flat' | 'percent'
  discount_value: number
  min_order_amount: number
  max_discount_cap: number | null
  description: string
  detailed_description: string
  category: string
  valid_days_of_week: string[] | null
  valid_time_start: string | null
  valid_time_end: string | null
  valid_from?: string | null
  valid_until?: string | null
  max_uses: number
  max_uses_per_user: number
  can_stack: boolean
  priority: number
  // Display-only (not saved)
  goal: string
  rationale: string
  expected_impact: string
  economics?: {
    perceived_discount_pct: number | null
    est_margin_pct: number | null
    real_cost: number | null
    verdict: 'safe' | 'ok' | 'thin'
    headline: string
    resolved: boolean
  } | null
}

interface QuotaInfo {
  used: number
  limit: number
  free_remaining: number
  resets_on: string
  coins_per_paid_generation?: number
  wallet_balance?: number
}

// Input modes: auto (menu-derived), prompt (merchant NLP), poster (offer image → vision)
export type InputMode = 'auto' | 'prompt' | 'poster'

interface AISuggestionsModalProps {
  open: boolean
  onClose: () => void
  outletId: string
  onUseSuggestion: (suggestion: AISuggestion) => void
  onSaveAll?: (suggestions: AISuggestion[]) => Promise<void>
  walletBalance?: number
  /** Which input mode to open in (from the toolbar button that launched it). */
  initialMode?: InputMode
}

// ── Constants ──────────────────────────────────────────────────────────────────

type Tone = 'calm' | 'attractive' | 'aggressive'

const INPUT_MODES: { value: InputMode; label: string; icon: React.ReactNode; hint: string }[] = [
  { value: 'auto',   label: 'Smart Auto',    icon: <Wand2 className="h-4 w-4" />,             hint: 'AI reads your menu & profile and suggests offers.' },
  { value: 'prompt', label: 'Describe It',   icon: <MessageSquareText className="h-4 w-4" />, hint: 'Describe the offer in your own words — AI builds it.' },
  { value: 'poster', label: 'Snap & Create', icon: <ImageIcon className="h-4 w-4" />,         hint: 'Snap or upload your offer — AI reads it and creates the offer.' },
]

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
]

const GOAL_COLORS: Record<string, string> = {
  acquisition: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  aov:         'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  frequency:   'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
  retention:   'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  upsell:      'bg-pink-100 text-pink-700 dark:bg-pink-900/40 dark:text-pink-300',
  offpeak:     'bg-slate-100 text-slate-700 dark:bg-slate-900/40 dark:text-slate-300',
}

const GOAL_LABELS: Record<string, string> = {
  acquisition: 'New Customers',
  aov:         'Grow AOV',
  frequency:   'More Orders',
  retention:   'Retention',
  upsell:      'Upsell',
  offpeak:     'Off-Peak',
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function getOfferTypeIcon(type: string) {
  switch (type) {
    case 'combo':    return <Gift className="h-3.5 w-3.5" />
    case 'auto':     return <TrendingUp className="h-3.5 w-3.5" />
    default:         return <Tag className="h-3.5 w-3.5" />
  }
}

function getOfferTypeLabel(type: string) {
  return { coupon: 'Coupon', auto: 'Auto', combo: 'Combo' }[type] ?? type
}

function formatDiscount(s: AISuggestion): string {
  if (s.offer_type === 'combo') {
    if (s.combo_type === 'bogo') return 'BUY 1 GET 1'
    if (s.combo_price && s.combo_price > 0) return `₹${s.combo_price} COMBO`
    return 'COMBO DEAL'
  }
  if (s.discount_type === 'percent') {
    const cap = s.max_discount_cap ? ` (max ₹${s.max_discount_cap})` : ''
    return `${s.discount_value}% OFF${cap}`
  }
  return `₹${s.discount_value} OFF`
}

function getStripeColor(s: AISuggestion): string {
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

        {/* Profit-safety badge — feels big to the customer, safe for the owner */}
        {suggestion.economics?.headline && (
          <div
            className={
              'flex items-center gap-1.5 rounded-lg border px-2 py-1.5 text-[11px] font-medium ' +
              (suggestion.economics.verdict === 'safe'
                ? 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-900/50 text-green-700 dark:text-green-400'
                : suggestion.economics.verdict === 'ok'
                ? 'bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400'
                : 'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-900/50 text-red-700 dark:text-red-400')
            }
          >
            <span className="font-bold">
              {suggestion.economics.verdict === 'safe' ? 'Profit-safe ✓' : suggestion.economics.verdict === 'ok' ? 'OK margin' : 'Thin margin'}
            </span>
            <span className="opacity-80">· {suggestion.economics.headline}</span>
          </div>
        )}

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
  outletId,
  onUseSuggestion,
  onSaveAll,
  walletBalance = 0,
  initialMode = 'auto',
}: AISuggestionsModalProps) {
  const [mode, setMode] = useState<InputMode>(initialMode)
  const [userPrompt, setUserPrompt] = useState('')
  const [posterImages, setPosterImages] = useState<string[]>([]) // up to 3 shots of the SAME offer
  const fileInputRef = useRef<HTMLInputElement>(null)
  const MAX_POSTER_IMAGES = 3
  const [tone, setTone] = useState<Tone>('attractive')
  const [offerTypeFilter, setOfferTypeFilter] = useState<string>('any')
  const [suggestions, setSuggestions] = useState<AISuggestion[]>([])
  const [quota, setQuota] = useState<QuotaInfo | null>(null)
  const [hasGenerated, setHasGenerated] = useState(false)
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)

  // When the modal (re)opens, jump to the mode of the button that launched it and
  // start clean — never carry over the previous prompt, poster or results.
  useEffect(() => {
    if (!open) return
    setMode(initialMode)
    setUserPrompt('')
    setPosterImages([])
    setSuggestions([])
    setHasGenerated(false)
    setSelectedCodes(new Set())
    setQuota(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [open, initialMode])

  const { call: generateSuggestions, loading } = useFrappePostCall(
    'flamezo_backend.flamezo.api.coupons.generate_coupon_suggestions'
  )

  const handlePosterSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (fileInputRef.current) fileInputRef.current.value = '' // allow re-selecting same file
    if (!files.length) return

    const remaining = MAX_POSTER_IMAGES - posterImages.length
    if (remaining <= 0) {
      toast.error(`You can attach up to ${MAX_POSTER_IMAGES} images of the same offer.`)
      return
    }
    const valid = files.filter(f => {
      if (!f.type.startsWith('image/')) {
        toast.error('Please choose image files (poster/screenshot).')
        return false
      }
      if (f.size > 10 * 1024 * 1024) {
        toast.error('Image too large', { description: `"${f.name}" is over 10 MB.` })
        return false
      }
      return true
    }).slice(0, remaining)
    if (files.length > remaining) {
      toast.info(`Only ${remaining} more image${remaining === 1 ? '' : 's'} added — max ${MAX_POSTER_IMAGES}.`)
    }

    valid.forEach(file => {
      const reader = new FileReader()
      reader.onloadend = () => {
        const result = reader.result as string // data:image/...;base64,....
        setPosterImages(prev => (prev.length >= MAX_POSTER_IMAGES ? prev : [...prev, result]))
      }
      reader.readAsDataURL(file)
    })
  }

  const removePosterImage = (idx: number) => {
    setPosterImages(prev => prev.filter((_, i) => i !== idx))
  }

  // Switching tabs starts a fresh generation — clear the previous mode's results
  // so a card generated under (e.g.) "Describe It" doesn't linger under other tabs.
  const handleModeChange = (next: InputMode) => {
    if (next === mode) return
    setMode(next)
    setSuggestions([])
    setHasGenerated(false)
    setSelectedCodes(new Set())
    setQuota(null)
  }

  const handleGenerate = async () => {
    // Mode-specific input validation
    if (mode === 'prompt' && !userPrompt.trim()) {
      toast.error('Describe the offer first', { description: 'e.g. "Flat 20% off on orders above ₹500 every weekend".' })
      return
    }
    if (mode === 'poster' && posterImages.length === 0) {
      toast.error('Attach an offer poster first')
      return
    }
    try {
      const res = await generateSuggestions({
        outlet_id: outletId,
        tone,
        offer_type_filter: offerTypeFilter === 'any' ? null : offerTypeFilter,
        count: 6,
        user_prompt: mode === 'prompt' ? userPrompt.trim() : null,
        poster_base64: mode === 'poster' ? JSON.stringify(posterImages) : null,
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
        } else if (errCode === 'FOOD_COST_REQUIRED') {
          toast.error('Food cost missing', {
            description: payload.message || 'Set food cost for all menu items in the Food Cost page first.',
            duration: 7000,
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
              {INPUT_MODES.find(m => m.value === mode)?.hint}
            </DialogDescription>
          </DialogHeader>

          {/* Input-mode switcher (shared modal, 3 modes) */}
          <div className="mt-4 grid grid-cols-3 gap-2">
            {INPUT_MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                onClick={() => handleModeChange(m.value)}
                className={cn(
                  'flex items-center justify-center gap-1.5 rounded-xl border-2 px-2 py-2 text-center transition-all cursor-pointer',
                  mode === m.value
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border hover:border-muted-foreground/40 text-muted-foreground',
                )}
              >
                {m.icon}
                <span className="text-xs font-semibold">{m.label}</span>
              </button>
            ))}
          </div>

          {/* Mode: From Prompt — merchant describes the offer */}
          {mode === 'prompt' && (
            <div className="mt-3 flex flex-col gap-1">
              <span className="text-xs text-muted-foreground font-medium">Describe your offer</span>
              <textarea
                value={userPrompt}
                onChange={(e) => setUserPrompt(e.target.value)}
                rows={3}
                maxLength={500}
                placeholder='e.g. "Flat 20% off on all pizzas above ₹500, every Friday & Saturday evening" or "Buy 1 Get 1 free on cold coffee this week"'
                className="w-full resize-none rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <span className="text-[11px] text-muted-foreground self-end">{userPrompt.length}/500</span>
            </div>
          )}

          {/* Mode: From Poster — merchant attaches up to 3 shots of the SAME offer */}
          {mode === 'poster' && (
            <div className="mt-3">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                onChange={handlePosterSelect}
                className="hidden"
              />
              {posterImages.length > 0 ? (
                <div className="flex flex-col gap-2">
                  <div className="grid grid-cols-3 gap-2">
                    {posterImages.map((img, idx) => (
                      <div key={idx} className="relative aspect-square rounded-lg border overflow-hidden bg-muted/30">
                        <img src={img} alt={`Offer ${idx + 1}`} className="h-full w-full object-cover" />
                        <button
                          type="button"
                          onClick={() => removePosterImage(idx)}
                          className="absolute top-1 right-1 rounded-full bg-background/90 border shadow p-0.5 hover:bg-muted"
                          aria-label="Remove image"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                    {posterImages.length < MAX_POSTER_IMAGES && (
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="aspect-square flex flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-muted-foreground/30 hover:border-primary/50 text-muted-foreground transition-colors"
                      >
                        <Upload className="h-5 w-5 opacity-60" />
                        <span className="text-[11px] font-medium">Add more</span>
                      </button>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    {posterImages.length}/{MAX_POSTER_IMAGES} images · all should be the <strong>same offer</strong> (tile, details, terms). The AI merges them into one offer.
                  </p>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full flex flex-col items-center gap-2 rounded-xl border-2 border-dashed border-muted-foreground/30 hover:border-primary/50 py-8 text-muted-foreground transition-colors"
                >
                  <Upload className="h-7 w-7 opacity-50" />
                  <span className="text-sm font-medium">Click to attach your offer (up to {MAX_POSTER_IMAGES} images)</span>
                  <span className="text-xs opacity-70 text-center max-w-sm">
                    PNG / JPG — add the offer tile plus its details / terms screens. They should all be the <strong>same offer</strong>; the AI reads them together and creates one offer.
                  </span>
                </button>
              )}
            </div>
          )}

          {/* Tone + offer-type controls — Smart Auto only.
              From Prompt reads intent from the merchant's words; From Poster reads the image. */}
          {mode === 'auto' && (
            <>
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
            </>
          )}

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
              disabled={loading || (mode === 'prompt' && !userPrompt.trim()) || (mode === 'poster' && posterImages.length === 0)}
              className="gap-2 min-w-[160px]"
            >
              {loading ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  {mode === 'poster' ? 'Reading poster…' : 'Generating…'}
                </>
              ) : hasGenerated ? (
                <>
                  <RefreshCw className="h-4 w-4" />
                  Regenerate
                </>
              ) : mode === 'poster' ? (
                <>
                  <ImageIcon className="h-4 w-4" />
                  Read Poster & Create
                </>
              ) : mode === 'prompt' ? (
                <>
                  <MessageSquareText className="h-4 w-4" />
                  Generate from Prompt
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
              {mode === 'poster' ? (
                <>
                  <ImageIcon className="h-12 w-12 opacity-20" />
                  <p className="text-sm font-medium">Attach your offer poster</p>
                  <p className="text-xs max-w-xs">
                    Upload a poster or screenshot that shows your offer. The AI reads it and turns
                    it into a ready-to-save offer — review and publish.
                  </p>
                </>
              ) : mode === 'prompt' ? (
                <>
                  <MessageSquareText className="h-12 w-12 opacity-20" />
                  <p className="text-sm font-medium">Describe the offer you want</p>
                  <p className="text-xs max-w-xs">
                    Type it in plain words — the AI turns your request into a profit-safe,
                    ready-to-save offer.
                  </p>
                </>
              ) : (
                <>
                  <Sparkles className="h-12 w-12 opacity-20" />
                  <p className="text-sm font-medium">Choose a tone and hit Generate</p>
                  <p className="text-xs max-w-xs">
                    The AI will analyse your menu, pricing, and restaurant profile to suggest
                    6 ready-to-use coupons tailored for your business.
                  </p>
                </>
              )}
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
