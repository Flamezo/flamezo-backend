import { useEffect, useMemo, useRef, useState } from 'react'
import { Search, X, Loader2, Users, Check } from 'lucide-react'
import { useFrappePostCall } from '@/lib/frappe'

/**
 * Tom-Select-style single-select dropdown of Merchant Groups (admin-only).
 * Type to filter; the dropdown lists all created groups. Selecting one shows a
 * chip you can clear.
 */

export interface Group { id: string; group_name: string; branch_count?: number }

export function GroupPicker({
  value,
  valueLabel,
  onChange,
  placeholder = 'Select a group…',
  reloadKey,
}: {
  value: string | null
  valueLabel?: string
  onChange: (id: string | null, label?: string) => void
  placeholder?: string
  reloadKey?: number            // bump to refetch after creating a group
}) {
  const [groups, setGroups] = useState<Group[]>([])
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const loadedRef = useRef(false)

  const { call: listGroups } = useFrappePostCall<{ success: boolean; groups?: Group[] }>(
    'flamezo_backend.flamezo.api.branch_clone.list_groups',
  )

  const load = async () => {
    setLoading(true)
    try {
      const res: any = await listGroups({})
      const data = res?.message ?? res
      setGroups(data?.groups || [])
    } catch {
      setGroups([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(); loadedRef.current = true }, [reloadKey])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return groups
    return groups.filter((g) => g.group_name.toLowerCase().includes(q))
  }, [groups, query])

  if (value) {
    return (
      <div className="flex items-center justify-between rounded-lg border border-border bg-muted/40 px-3 py-2">
        <span className="flex items-center gap-2 min-w-0 text-sm font-medium">
          <Users className="h-4 w-4 text-muted-foreground shrink-0" />
          <span className="truncate">{valueLabel || value}</span>
        </span>
        <button type="button" onClick={() => onChange(null)} className="text-muted-foreground hover:text-foreground shrink-0" aria-label="Clear">
          <X className="h-4 w-4" />
        </button>
      </div>
    )
  }

  return (
    <div className="relative">
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
      {open && (
        <div className="mt-1 w-full max-h-56 overflow-y-auto rounded-lg border border-border bg-background shadow-sm">
          {filtered.length === 0 ? (
            <div className="px-3 py-3 text-sm text-muted-foreground">{loading ? 'Loading…' : 'No groups yet.'}</div>
          ) : (
            filtered.map((g) => (
              <button
                key={g.id}
                type="button"
                className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/60"
                onMouseDown={(e) => { e.preventDefault(); onChange(g.id, g.group_name); setOpen(false); setQuery('') }}
              >
                <Users className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="flex-1 truncate text-sm font-medium">{g.group_name}</span>
                {typeof g.branch_count === 'number' && (
                  <span className="text-xs text-muted-foreground shrink-0">{g.branch_count} branch{g.branch_count === 1 ? '' : 'es'}</span>
                )}
                {value === g.id && <Check className="h-3.5 w-3.5" />}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
