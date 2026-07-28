import { useEffect, useRef, useState } from 'react'
import { Search, X, Loader2, Store } from 'lucide-react'
import { useFrappePostCall } from '@/lib/frappe'

/**
 * Async, type-to-search, MULTI-select "Branch of…" picker (admin-only).
 *
 * The dropdown stays hidden until the admin types (never pre-loads all
 * merchants). Selecting outlets adds them as chips; picking any member of an
 * existing group pulls the new outlet into that whole group (backend resolves
 * the shared root). Controlled: parent owns the selected list.
 */

export interface BranchRef { id: string; name: string }

interface Branch {
  id: string
  restaurant_name?: string
  city?: string
  branch_group?: string | null
}

export function BranchOfPicker({
  value,
  onChange,
  placeholder = 'Search an existing outlet…',
  excludeIds = [],
}: {
  value: BranchRef[]
  onChange: (items: BranchRef[]) => void
  placeholder?: string
  excludeIds?: string[]        // ids never offered (e.g. the outlet being edited)
}) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<Branch[]>([])
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { call: search } = useFrappePostCall<{ success: boolean; branches?: Branch[] }>(
    'flamezo_backend.flamezo.api.branch_clone.search_branches',
  )

  const selectedIds = new Set(value.map((v) => v.id))

  useEffect(() => {
    if (!open) return
    // Nothing typed → no results, no dropdown (never pre-load all merchants).
    if (!query.trim()) { setResults([]); setLoading(false); return }
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const res: any = await search({ query, limit: 20 })
        const data = res?.message ?? res
        const list: Branch[] = (data?.branches || []).filter(
          (b: Branch) => b.id !== undefined && !excludeIds.includes(b.id) && !selectedIds.has(b.id),
        )
        setResults(list)
      } catch {
        setResults([])
      } finally {
        setLoading(false)
      }
    }, 300)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, open])

  const add = (b: Branch) => {
    onChange([...value, { id: b.id, name: b.restaurant_name || b.id }])
    setQuery('')
    // keep the box open for quick multi-add
  }
  const remove = (id: string) => onChange(value.filter((v) => v.id !== id))

  return (
    <div className="relative">
      {/* Selected chips */}
      {value.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {value.map((v) => (
            <span key={v.id} className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-xs font-medium">
              <Store className="h-3 w-3 text-muted-foreground" />
              {v.name}
              <button type="button" onClick={() => remove(v.id)} className="text-muted-foreground hover:text-foreground" aria-label="Remove">
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 rounded-lg border border-border px-3 py-2">
        <Search className="h-4 w-4 text-muted-foreground shrink-0" />
        <input
          className="w-full bg-transparent text-sm outline-none"
          value={query}
          placeholder={placeholder}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
        />
        {loading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
      </div>

      {/* In-flow (not absolute) so it never gets clipped inside a scrollable modal. */}
      {open && query.trim().length > 0 && (
        <div className="mt-1 w-full max-h-56 overflow-y-auto rounded-lg border border-border bg-background shadow-sm">
          {results.length === 0 && !loading ? (
            <div className="px-3 py-3 text-sm text-muted-foreground">No matching outlets.</div>
          ) : (
            results.map((b) => (
              <button
                key={b.id}
                type="button"
                className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/60"
                onMouseDown={(e) => { e.preventDefault(); add(b) }}
              >
                <Store className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{b.restaurant_name || b.id}</span>
                  {b.city && <span className="block truncate text-xs text-muted-foreground">{b.city}</span>}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
