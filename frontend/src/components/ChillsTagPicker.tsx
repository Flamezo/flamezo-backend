import { useState, useCallback, useMemo, useRef } from 'react'
import { X, Search, Plus, ChevronDown, ChevronUp, Loader2, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useFrappePostCall } from '@/lib/frappe'
import { NICHE_TAXONOMY, findNode, getIndustryForNode } from '@/lib/niche-taxonomy'
import type { NicheNode } from '@/lib/niche-taxonomy'
import NicheSelector from '@/components/NicheSelector'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ChillsTagPickerProps {
  /** Selected taxonomy IDs */
  nicheTags: string[]
  onNicheChange: (ids: string[]) => void
  /** Novel custom tags (not in taxonomy) */
  customTags: string[]
  onCustomChange: (tags: string[]) => void
  /** Outlet ID for API calls */
  outletId: string
  /** Current caption — passed to suggest_chills_tags */
  caption: string
  disabled?: boolean
  className?: string
}

interface ResolveSuggestion {
  tag_id: string
  tag_label: string
  partial: boolean
  input: string
}

// ── Limits (must match backend MAX_NICHE_TAGS / MAX_CUSTOM_TAGS) ──────────────
const MAX_NICHE = 8
const MAX_CUSTOM = 5

// ── Taxonomy search helper ─────────────────────────────────────────────────────

function flattenTaxonomy(nodes: NicheNode[] = NICHE_TAXONOMY): NicheNode[] {
  const result: NicheNode[] = []
  function walk(n: NicheNode) {
    result.push(n)
    n.children?.forEach(walk)
  }
  nodes.forEach(walk)
  return result
}

const ALL_NODES = flattenTaxonomy()

function searchTaxonomy(query: string): NicheNode[] {
  const q = query.toLowerCase().trim()
  if (!q) return []
  return ALL_NODES.filter((n) => n.label.toLowerCase().includes(q)).slice(0, 8)
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ChillsTagPicker({
  nicheTags,
  onNicheChange,
  customTags,
  onCustomChange,
  outletId,
  caption,
  disabled,
  className,
}: ChillsTagPickerProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [isSuggesting, setIsSuggesting] = useState(false)
  const [suggestError, setSuggestError] = useState('')
  const [resolvePending, setResolvePending] = useState<ResolveSuggestion | null>(null)
  const [isResolving, setIsResolving] = useState(false)
  const [showBrowse, setShowBrowse] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)

  const { call: callSuggest } = useFrappePostCall<{ message: { success: boolean; data: { tags: string[] } } }>(
    'flamezo_backend.flamezo.api.chills.suggest_chills_tags'
  )
  const { call: callResolve } = useFrappePostCall<{
    message: { success: boolean; data: { matched: boolean; tag_id?: string; tag_label?: string; partial?: boolean } }
  }>('flamezo_backend.flamezo.api.chills.resolve_custom_tag')

  // ── AI suggest ────────────────────────────────────────────────────────────────

  const handleSuggest = useCallback(async () => {
    if (!caption.trim() || !outletId || isSuggesting) return
    setIsSuggesting(true)
    setSuggestError('')
    try {
      const res = await callSuggest({ outlet_id: outletId, caption })
      const body = (res as any)?.message ?? res
      const suggested: string[] = body?.data?.tags ?? []
      if (suggested.length === 0) {
        setSuggestError('No tags found for this caption. Try adding more detail.')
        return
      }
      // Merge with existing, deduplicate
      const merged = Array.from(new Set([...nicheTags, ...suggested]))
      const capped = merged.slice(0, MAX_NICHE)
      if (merged.length > MAX_NICHE) {
        setSuggestError(`Showing top ${MAX_NICHE} tags — some suggestions were trimmed to stay within the limit.`)
      }
      onNicheChange(capped)
    } catch {
      setSuggestError('AI suggestion failed. Try again.')
    } finally {
      setIsSuggesting(false)
    }
  }, [caption, outletId, isSuggesting, nicheTags, onNicheChange, callSuggest])

  // ── Custom tag resolve ────────────────────────────────────────────────────────

  const handleAddCustomTag = useCallback(async () => {
    const text = searchQuery.trim()
    if (!text || disabled) return

    // Check if it matches an existing taxonomy node first (fast path)
    const taxMatch = searchTaxonomy(text)
    if (taxMatch.length > 0 && taxMatch[0].label.toLowerCase() === text.toLowerCase()) {
      if (!nicheTags.includes(taxMatch[0].id)) {
        if (nicheTags.length >= MAX_NICHE) {
          setSuggestError(`You've reached the ${MAX_NICHE}-tag limit. Remove a tag first.`)
          return
        }
        onNicheChange([...nicheTags, taxMatch[0].id])
      }
      setSearchQuery('')
      return
    }

    setIsResolving(true)
    try {
      const res = await callResolve({ outlet_id: outletId, tag_text: text })
      const body = (res as any)?.message ?? res
      const data = body?.data ?? {}

      if (data.matched && data.tag_id) {
        setResolvePending({
          tag_id: data.tag_id,
          tag_label: data.tag_label || data.tag_id,
          partial: !!data.partial,
          input: text,
        })
      } else {
        // Novel tag — add directly to custom tags
        if (!customTags.includes(text)) {
          if (customTags.length >= MAX_CUSTOM) {
            setSuggestError(`Maximum ${MAX_CUSTOM} custom tags allowed. Remove one first.`)
            setIsResolving(false)
            return
          }
          onCustomChange([...customTags, text])
        }
        setSearchQuery('')
      }
    } catch {
      // On error fall back to adding as custom
      if (!customTags.includes(text)) {
        if (customTags.length < MAX_CUSTOM) {
          onCustomChange([...customTags, text])
        }
      }
      setSearchQuery('')
    } finally {
      setIsResolving(false)
    }
  }, [searchQuery, disabled, outletId, nicheTags, customTags, onNicheChange, onCustomChange, callResolve])

  const acceptResolveSuggestion = useCallback(() => {
    if (!resolvePending) return
    if (!nicheTags.includes(resolvePending.tag_id)) {
      if (nicheTags.length >= MAX_NICHE) {
        setSuggestError(`You've reached the ${MAX_NICHE}-tag limit. Remove a tag first.`)
        setResolvePending(null)
        return
      }
      onNicheChange([...nicheTags, resolvePending.tag_id])
    }
    setResolvePending(null)
    setSearchQuery('')
  }, [resolvePending, nicheTags, onNicheChange])

  const rejectResolveSuggestion = useCallback(() => {
    if (!resolvePending) return
    // Add as custom tag anyway
    if (!customTags.includes(resolvePending.input)) {
      onCustomChange([...customTags, resolvePending.input])
    }
    setResolvePending(null)
    setSearchQuery('')
  }, [resolvePending, customTags, onCustomChange])

  // ── Search results ────────────────────────────────────────────────────────────

  const searchResults = useMemo(() => searchTaxonomy(searchQuery), [searchQuery])

  const addSearchResult = useCallback((node: NicheNode) => {
    if (!nicheTags.includes(node.id)) {
      if (nicheTags.length >= MAX_NICHE) {
        setSuggestError(`You've reached the ${MAX_NICHE}-tag limit. Remove a tag first.`)
        return
      }
      onNicheChange([...nicheTags, node.id])
    }
    setSearchQuery('')
    searchRef.current?.focus()
  }, [nicheTags, onNicheChange])

  // ── Chip helpers ──────────────────────────────────────────────────────────────

  const nicheChips = useMemo(
    () =>
      nicheTags.map((id) => {
        const node = findNode(id)
        const industry = getIndustryForNode(id)
        return {
          id,
          label: node?.label ?? id,
          industryLabel: industry?.id !== id ? industry?.label : undefined,
        }
      }),
    [nicheTags],
  )

  const removeNicheChip = useCallback(
    (id: string) => onNicheChange(nicheTags.filter((t) => t !== id)),
    [nicheTags, onNicheChange],
  )
  const removeCustomTag = useCallback(
    (t: string) => onCustomChange(customTags.filter((c) => c !== t)),
    [customTags, onCustomChange],
  )

  const totalCount = nicheTags.length + customTags.length
  const hasCaption = caption.trim().length > 0

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className={cn('space-y-3', className)}>
      {/* Header row: label + AI suggest button */}
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">
            Niche Tags
          </p>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Tag your video so it reaches the right audience
          </p>
        </div>
        <button
          type="button"
          onClick={handleSuggest}
          disabled={!hasCaption || isSuggesting || disabled}
          title={hasCaption ? 'Auto-suggest tags from your caption' : 'Write a caption first to use AI suggestions'}
          className={cn(
            'flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-all duration-150 shrink-0',
            hasCaption && !isSuggesting && !disabled
              ? 'border-primary/40 bg-primary/8 text-primary hover:bg-primary/15'
              : 'border-border text-muted-foreground opacity-50 cursor-not-allowed',
          )}
        >
          {isSuggesting ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Sparkles className="h-3 w-3" />
          )}
          {isSuggesting ? 'Suggesting…' : 'AI Suggest'}
        </button>
      </div>

      {/* Suggest error */}
      {suggestError && (
        <p className="text-[11px] text-destructive">{suggestError}</p>
      )}

      {/* Selected chips */}
      {totalCount > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {nicheChips.map((chip) => (
            <span
              key={chip.id}
              className="inline-flex items-center gap-1 rounded-full bg-primary/10 border border-primary/20 px-2.5 py-0.5 text-xs font-medium text-primary"
            >
              {chip.industryLabel && (
                <span className="opacity-60">{chip.industryLabel} ·</span>
              )}
              {chip.label}
              {!disabled && (
                <button
                  type="button"
                  onClick={() => removeNicheChip(chip.id)}
                  className="ml-0.5 rounded-full hover:bg-primary/20 p-0.5 transition-colors"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              )}
            </span>
          ))}
          {customTags.map((t) => (
            <span
              key={t}
              className="inline-flex items-center gap-1 rounded-full bg-muted border border-border px-2.5 py-0.5 text-xs font-medium text-foreground"
            >
              {t}
              {!disabled && (
                <button
                  type="button"
                  onClick={() => removeCustomTag(t)}
                  className="ml-0.5 rounded-full hover:bg-destructive/20 p-0.5 transition-colors"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              )}
            </span>
          ))}
          {!disabled && totalCount > 0 && (
            <button
              type="button"
              onClick={() => { onNicheChange([]); onCustomChange([]) }}
              className="text-xs text-muted-foreground hover:text-destructive transition-colors px-1 self-center"
            >
              Clear all
            </button>
          )}
        </div>
      )}

      {/* Resolve suggestion card */}
      {resolvePending && (
        <div className="rounded-xl border border-primary/20 bg-primary/5 p-3 space-y-2">
          <p className="text-xs font-medium text-foreground">
            We found a matching tag for <span className="font-semibold">"{resolvePending.input}"</span>:
          </p>
          <p className="text-xs text-primary font-semibold">{resolvePending.tag_label}</p>
          {resolvePending.partial && (
            <p className="text-[11px] text-muted-foreground">
              This is the closest match — your tag is more specific than our taxonomy.
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={acceptResolveSuggestion}
              className="flex-1 rounded-lg border border-primary bg-primary text-primary-foreground text-xs font-semibold py-1.5 transition-all hover:opacity-90"
            >
              Use this tag
            </button>
            <button
              type="button"
              onClick={rejectResolveSuggestion}
              className="flex-1 rounded-lg border border-border bg-background text-foreground text-xs font-semibold py-1.5 transition-all hover:bg-muted"
            >
              Add "{resolvePending.input}" anyway
            </button>
          </div>
        </div>
      )}

      {/* Search / add input */}
      {!disabled && (
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
            <input
              ref={searchRef}
              type="text"
              value={searchQuery}
              onChange={(e) => { setSearchQuery(e.target.value); setSuggestError('') }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); handleAddCustomTag() }
              }}
              placeholder="Search tags or type to add custom…"
              disabled={disabled || isResolving}
              className="w-full h-9 rounded-lg border border-border bg-background pl-8 pr-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
            />
          </div>
          <button
            type="button"
            onClick={handleAddCustomTag}
            disabled={!searchQuery.trim() || isResolving || disabled}
            className={cn(
              'h-9 w-9 rounded-lg border flex items-center justify-center transition-all shrink-0',
              searchQuery.trim() && !isResolving
                ? 'border-primary bg-primary text-primary-foreground hover:opacity-90'
                : 'border-border bg-muted text-muted-foreground opacity-50 cursor-not-allowed',
            )}
          >
            {isResolving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          </button>
        </div>
      )}

      {/* Inline search results */}
      {searchQuery.trim() && searchResults.length > 0 && (
        <div className="flex flex-wrap gap-1.5 py-0.5">
          {searchResults.map((node) => {
            const alreadySelected = nicheTags.includes(node.id)
            return (
              <button
                key={node.id}
                type="button"
                disabled={alreadySelected || disabled}
                onClick={() => addSearchResult(node)}
                className={cn(
                  'inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium transition-all duration-150',
                  alreadySelected
                    ? 'border-primary/30 bg-primary/10 text-primary cursor-default'
                    : 'border-border bg-background text-foreground hover:border-primary/50 hover:bg-primary/5',
                  disabled && 'pointer-events-none opacity-40',
                )}
              >
                {alreadySelected && <span className="mr-1 opacity-60">✓</span>}
                {node.label}
              </button>
            )
          })}
          {/* Add as custom if no exact match */}
          {searchQuery.trim() && !searchResults.some(
            (n) => n.label.toLowerCase() === searchQuery.trim().toLowerCase()
          ) && (
            <button
              type="button"
              onClick={handleAddCustomTag}
              disabled={isResolving || disabled}
              className="inline-flex items-center gap-1 rounded-full border border-dashed border-border bg-background px-3 py-1 text-xs font-medium text-muted-foreground hover:border-primary/50 hover:text-foreground transition-all"
            >
              <Plus className="h-3 w-3" />
              Add "{searchQuery.trim()}"
            </button>
          )}
        </div>
      )}

      {/* Browse taxonomy toggle */}
      <button
        type="button"
        onClick={() => setShowBrowse((v) => !v)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {showBrowse ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        {showBrowse ? 'Hide taxonomy browser' : 'Browse all categories'}
      </button>

      {showBrowse && (
        <div className="border border-border rounded-xl p-3 bg-muted/30 animate-in fade-in slide-in-from-top-1 duration-200">
          <NicheSelector
            value={nicheTags}
            onChange={onNicheChange}
            maxSelections={8}
            disabled={disabled}
          />
        </div>
      )}

      <p className="text-[11px] text-muted-foreground">
        {nicheTags.length}/{MAX_NICHE} niche tags
        {' · '}
        {customTags.length}/{MAX_CUSTOM} custom tags
      </p>
    </div>
  )
}
