import { useEffect, useRef, useState } from 'react'
import { useFrappePostCall } from '@/lib/frappe'
import { Search, X, Check, Loader2, Store } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Server-side, single-select merchant (outlet) picker.
 *
 * Type-ahead: on every keystroke it queries the backend `search_branches`
 * (admin-only) and shows only the top `limit` matches — nothing is loaded
 * up-front, and results refresh per search. Reuses the exact endpoint the
 * Merchant Group tools use, so there's one search contract across the app.
 */

export interface MerchantRef { id: string; name: string }

interface Branch { id: string; restaurant_name?: string; outlet_name?: string; city?: string }

export function MerchantSearchSelect({
  value,
  onChange,
  placeholder = 'Search outlet…',
  limit = 5,
  disabled = false,
}: {
  value: MerchantRef | null
  onChange: (m: MerchantRef | null) => void
  placeholder?: string
  limit?: number
  disabled?: boolean
}) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [results, setResults] = useState<Branch[]>([])
  const [loading, setLoading] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  const { call: search } = useFrappePostCall<{ success: boolean; branches?: Branch[] }>(
    'flamezo_backend.flamezo.api.branch_clone.search_branches',
  )

  // Debounced server search — only the top `limit` rows come back.
  useEffect(() => {
    if (!open) return
    let alive = true
    setLoading(true)
    const t = setTimeout(async () => {
      try {
        const res: any = await search({ query, limit })
        const data = res?.message ?? res
        if (alive) setResults(data?.success ? (data.branches || []) : [])
      } catch {
        if (alive) setResults([])
      } finally {
        if (alive) setLoading(false)
      }
    }, 300)
    return () => { alive = false; clearTimeout(t) }
  }, [query, open, limit])

  // Close on outside click
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const pick = (b: Branch) => {
    onChange({ id: b.id, name: b.outlet_name || b.restaurant_name || b.id })
    setOpen(false)
    setQuery('')
  }

  return (
    <div ref={boxRef} className="relative">
      {value ? (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm">
          <span className="flex items-center gap-2 min-w-0">
            <Store className="h-4 w-4 shrink-0 text-muted-foreground" />
            <span className="truncate font-medium">{value.name}</span>
          </span>
          {!disabled && (
            <button type="button" onClick={() => onChange(null)} className="text-muted-foreground hover:text-foreground shrink-0">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      ) : (
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            className="w-full rounded-lg border border-border bg-background pl-9 pr-3 py-2 text-sm outline-none focus:border-primary/40"
            placeholder={placeholder}
            value={query}
            disabled={disabled}
            onFocus={() => setOpen(true)}
            onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
          />
        </div>
      )}

      {open && !value && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-border bg-popover shadow-lg max-h-64 overflow-y-auto">
          {loading ? (
            <div className="flex items-center gap-2 px-3 py-3 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Searching…
            </div>
          ) : results.length === 0 ? (
            <div className="px-3 py-3 text-sm text-muted-foreground">
              {query ? 'No outlets match' : 'Type to search outlets'}
            </div>
          ) : (
            results.map((b) => (
              <button
                key={b.id}
                type="button"
                onClick={() => pick(b)}
                className={cn('flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-muted/60')}
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">{b.outlet_name || b.restaurant_name || b.id}</span>
                  {b.city && <span className="block truncate text-xs text-muted-foreground">{b.city}</span>}
                </span>
                {value && (value as MerchantRef).id === b.id && <Check className="h-4 w-4 text-primary shrink-0" />}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
