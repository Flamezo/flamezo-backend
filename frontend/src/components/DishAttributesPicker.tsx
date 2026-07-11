import { useMemo, useState } from 'react'
import { useFrappeGetCall } from '@/lib/frappe'
import { cn } from '@/lib/utils'
import {
  Loader2, Check, ChevronDown, Plus,
  Sparkles, Flame, Star, ThumbsUp, Sun, Leaf, Drumstick, Egg, Sprout,
  Flower2, Ban, Gem, WheatOff, Beef, Dumbbell, Feather, TriangleAlert, Milk,
  type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'

// Maps the backend `icon` name (a Lucide component name) to the component.
// Shared with MenuProductCard so card + picker draw the same icons.
export const ATTR_ICONS: Record<string, LucideIcon> = {
  Sparkles, Flame, Star, ThumbsUp, Sun, Leaf, Drumstick, Egg, Sprout,
  Flower2, Ban, Gem, WheatOff, Beef, Dumbbell, Feather, TriangleAlert, Milk,
}

/** Renders a dish-attribute icon by name; nothing if the name is unknown. */
export function AttrIcon({ name, className }: { name?: string; className?: string }) {
  const Icon = name ? ATTR_ICONS[name] : undefined
  return Icon ? <Icon className={className} aria-hidden /> : null
}

interface DishAttribute {
  key: string
  label: string
  icon?: string
  primary?: boolean
}

interface DishAttributeGroup {
  group: string
  group_label: string
  attributes: DishAttribute[]
}

interface DishAttributesPickerProps {
  /** Stored value: a JSON array string (e.g. '["veg","spicy"]'), a plain array, or ''. */
  value?: string | string[]
  /** Called with the new value as a JSON array string. */
  onChange: (value: string) => void
  disabled?: boolean
}

/** Maximum attributes a merchant can assign to a single dish. */
const MAX_ATTRIBUTES = 10

type Tone = 'emerald' | 'red' | 'amber' | 'orange' | 'lime' | 'violet' | 'sky' | 'rose'

// Full class strings (Tailwind needs literals) for each semantic colour, in both
// the selected (filled) and unselected (tinted outline) states.
const TONE: Record<Tone, { on: string; off: string }> = {
  emerald: { on: 'bg-emerald-500 border-emerald-500 text-white', off: 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/10' },
  red:     { on: 'bg-red-500 border-red-500 text-white',         off: 'border-red-500/40 text-red-600 dark:text-red-400 hover:bg-red-500/10' },
  amber:   { on: 'bg-amber-500 border-amber-500 text-white',     off: 'border-amber-500/40 text-amber-600 dark:text-amber-400 hover:bg-amber-500/10' },
  orange:  { on: 'bg-orange-500 border-orange-500 text-white',   off: 'border-orange-500/40 text-orange-600 dark:text-orange-400 hover:bg-orange-500/10' },
  lime:    { on: 'bg-lime-500 border-lime-500 text-white',       off: 'border-lime-500/40 text-lime-600 dark:text-lime-500 hover:bg-lime-500/10' },
  violet:  { on: 'bg-violet-500 border-violet-500 text-white',   off: 'border-violet-500/40 text-violet-600 dark:text-violet-400 hover:bg-violet-500/10' },
  sky:     { on: 'bg-sky-500 border-sky-500 text-white',         off: 'border-sky-500/40 text-sky-600 dark:text-sky-400 hover:bg-sky-500/10' },
  rose:    { on: 'bg-rose-600 border-rose-600 text-white',       off: 'border-rose-600/40 text-rose-600 dark:text-rose-400 hover:bg-rose-600/10' },
}

// Per-attribute colour where the meaning is specific (veg green, non-veg red,
// chilli red, ...); everything else falls back to its group colour.
const KEY_TONE: Record<string, Tone> = {
  veg: 'emerald', 'non-veg': 'red', egg: 'amber', vegan: 'emerald',
  jain: 'orange', 'no-onion-garlic': 'lime', sattvic: 'violet',
  mild: 'amber', spicy: 'red', 'extra-spicy': 'rose',
}
const GROUP_TONE: Record<string, Tone> = {
  highlight: 'orange', diet: 'emerald', spice: 'red', health: 'sky', allergen: 'rose',
}
const toneFor = (attr: DishAttribute, group: string): Tone =>
  KEY_TONE[attr.key] || GROUP_TONE[group] || 'orange'

/** Colour classes for an attribute chip, so cards/peek match the picker. */
export const attrToneClass = (key: string, group: string, selected = false): string => {
  const tone = TONE[KEY_TONE[key] || GROUP_TONE[group] || 'orange']
  return selected ? tone.on : tone.off
}

/** Normalise the stored value into a list of selected attribute keys. */
function parseSelected(value?: string | string[]): string[] {
  if (!value) return []
  if (Array.isArray(value)) return value.filter(Boolean)
  const raw = value.trim()
  try {
    const parsed = raw.startsWith('[') ? JSON.parse(raw) : raw.split(',').map(k => k.trim())
    return Array.isArray(parsed) ? parsed.filter(Boolean) : []
  } catch {
    return raw.split(',').map(k => k.trim()).filter(Boolean)
  }
}

/**
 * Inline, colour-coded pill picker for dish attributes (Veg, Jain, Spicy, New, ...).
 * Everything is visible in one block — no popover, no inner scroll. The catalogue
 * is fetched from the backend so labels/icons never drift (single source of truth:
 * flamezo/api/dish_attributes.py). Only the selected *keys* are stored on the
 * product, as a JSON array string.
 */
export default function DishAttributesPicker({ value, onChange, disabled }: DishAttributesPickerProps) {
  const [open, setOpen] = useState(false)
  const { data, isLoading } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.dish_attributes.get_dish_attributes',
    {},
    'dish-attributes-catalogue',
  )

  const groups: DishAttributeGroup[] = data?.message?.groups || []
  const byKey = useMemo(() => {
    const map = new Map<string, { attr: DishAttribute; group: string }>()
    groups.forEach(g => g.attributes.forEach(a => map.set(a.key, { attr: a, group: g.group })))
    return map
  }, [groups])

  const selected = useMemo(() => parseSelected(value), [value])
  const selectedSet = useMemo(() => new Set(selected), [selected])
  const atLimit = selected.length >= MAX_ATTRIBUTES

  const commit = (next: string[]) => onChange(JSON.stringify(next))
  const toggle = (key: string) => {
    if (disabled) return
    const isSelected = selectedSet.has(key)
    if (!isSelected && atLimit) return
    commit(isSelected ? selected.filter(k => k !== key) : [...selected, key])
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-3 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading attributes...
      </div>
    )
  }
  if (groups.length === 0) {
    return <p className="text-sm text-muted-foreground">No attributes available.</p>
  }

  // ── Peek (collapsed) — show ONLY the selected attributes + an edit button ──
  const selectedResolved = selected
    .map(k => byKey.get(k))
    .filter(Boolean) as { attr: DishAttribute; group: string }[]

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {selectedResolved.length > 0 ? (
          selectedResolved.map(({ attr, group }) => {
            const tone = TONE[toneFor(attr, group)]
            return (
              <span
                key={attr.key}
                className={cn('badge-shine inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium', tone.off)}
              >
                <AttrIcon name={attr.icon} className="h-3.5 w-3.5" />
                {attr.label}
              </span>
            )
          })
        ) : (
          <span className="text-sm text-muted-foreground">No attributes selected yet.</span>
        )}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => setOpen(o => !o)}
          className="h-7 gap-1 rounded-full"
          aria-expanded={open}
        >
          {!open && <Plus className="h-3.5 w-3.5" />}
          {open ? 'Close' : selectedResolved.length > 0 ? 'Edit' : 'Select'}
          <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')} />
        </Button>
      </div>

      {/* ── Expanded (inline, no popover → scrolls with the page) ── */}
      {open && (
      <div className="rounded-xl border bg-muted/20 p-4">
        {/* Counter row */}
        <div className="mb-3 flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Tap all that apply.</span>
          <div className="flex items-center gap-2">
            {selected.length > 0 && (
              <button
                type="button"
                onClick={() => commit([])}
                disabled={disabled}
                className="text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
              >
                Clear
              </button>
            )}
            <span className={cn(
              'rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums',
              atLimit ? 'bg-amber-500/15 text-amber-600' : 'bg-primary/10 text-primary',
            )}>
              {selected.length}/{MAX_ATTRIBUTES}
            </span>
          </div>
        </div>

        <div className="space-y-4">
        {groups.map(group => {
          const groupCount = group.attributes.filter(a => selectedSet.has(a.key)).length
          return (
            <div key={group.group} className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                  {group.group_label}
                </span>
                {groupCount > 0 && (
                  <span className="rounded-full bg-primary/10 px-1.5 text-[10px] font-semibold text-primary">
                    {groupCount}
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {group.attributes.map(attr => {
                  const isSelected = selectedSet.has(attr.key)
                  const blocked = !isSelected && atLimit
                  const tone = TONE[toneFor(attr, group.group)]
                  return (
                    <button
                      key={attr.key}
                      type="button"
                      onClick={() => toggle(attr.key)}
                      disabled={disabled || blocked}
                      aria-pressed={isSelected}
                      title={blocked ? `Up to ${MAX_ATTRIBUTES} attributes per dish` : undefined}
                      className={cn(
                        'inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-all',
                        'focus:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        isSelected ? cn(tone.on, 'badge-shine shadow-sm') : cn('bg-transparent', tone.off),
                        blocked && 'cursor-not-allowed opacity-40 hover:bg-transparent',
                      )}
                    >
                      <AttrIcon name={attr.icon} className="h-4 w-4" />
                      {attr.label}
                      {isSelected && <Check className="h-3.5 w-3.5" />}
                    </button>
                  )
                })}
              </div>
            </div>
          )
        })}
        </div>
      </div>
      )}
    </div>
  )
}
