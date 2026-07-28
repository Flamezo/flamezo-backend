import { useMemo, useState } from 'react'
import { ChevronDown, Check, Search } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Compact Tom-Select-style single-select: a filter-bar-sized trigger that opens a
 * dropdown with a search box + filtered options (instead of listing options
 * directly). Drop-in for the merchant filter bar.
 */

export interface SelectOption { value: string; label: string }

export function SearchableSelect({
  value,
  options,
  onChange,
  placeholder = 'Select…',
  className,
  triggerClassName,
}: {
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  triggerClassName?: string
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')

  const selected = options.find((o) => o.value === value)
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return options
    return options.filter((o) => o.label.toLowerCase().includes(q))
  }, [options, query])

  return (
    <div className={cn('relative', className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'flex h-8 items-center justify-between gap-1 rounded-md border border-input bg-background px-2.5 text-xs',
          triggerClassName,
        )}
      >
        <span className="truncate">{selected?.label || placeholder}</span>
        <ChevronDown className="h-3.5 w-3.5 opacity-60 shrink-0" />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 min-w-[200px] rounded-md border border-border bg-background shadow-lg">
          <div className="flex items-center gap-1.5 border-b border-border px-2 py-1.5">
            <Search className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search…"
              className="w-full bg-transparent text-xs outline-none"
            />
          </div>
          <div className="max-h-56 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <div className="px-3 py-2 text-xs text-muted-foreground">No matches.</div>
            ) : (
              filtered.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs hover:bg-muted/60"
                  onClick={() => { onChange(o.value); setOpen(false); setQuery('') }}
                >
                  <span className="truncate">{o.label}</span>
                  {value === o.value && <Check className="h-3.5 w-3.5 shrink-0" />}
                </button>
              ))
            )}
          </div>
        </div>
      )}
      {open && <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />}
    </div>
  )
}
