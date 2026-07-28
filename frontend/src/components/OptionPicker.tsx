import { useMemo, useState } from 'react'
import { ChevronDown, Search, Check, X } from 'lucide-react'

/**
 * Modal-safe searchable dropdown — single OR multi select, with optional
 * "Select all". Renders its panel in-flow (not absolute) so it never gets
 * clipped inside a scrollable modal. Multi shows chips in the trigger.
 */

export interface PickerOption { value: string; label: string }

export function OptionPicker({
  options,
  value,
  onChange,
  multiple = false,
  selectAll = false,
  placeholder = 'Select…',
}: {
  options: PickerOption[]
  value: string[]                       // always an array ([] / [id] for single)
  onChange: (values: string[]) => void
  multiple?: boolean
  selectAll?: boolean
  placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const sel = new Set(value)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return options
    return options.filter((o) => o.label.toLowerCase().includes(q))
  }, [options, query])

  const allFilteredSelected = multiple && filtered.length > 0 && filtered.every((o) => sel.has(o.value))

  const pick = (v: string) => {
    if (multiple) {
      const n = new Set(sel); n.has(v) ? n.delete(v) : n.add(v); onChange([...n])
    } else {
      onChange([v]); setOpen(false); setQuery('')
    }
  }
  const toggleAll = () => {
    const n = new Set(sel)
    if (allFilteredSelected) filtered.forEach((o) => n.delete(o.value))
    else filtered.forEach((o) => n.add(o.value))
    onChange([...n])
  }

  return (
    <div>
      {/* Trigger */}
      <div
        onClick={() => setOpen((o) => !o)}
        className="flex min-h-[38px] flex-wrap items-center gap-1 rounded-lg border border-input bg-background px-2 py-1.5 cursor-pointer"
      >
        {value.length === 0 ? (
          <span className="px-1 text-sm text-muted-foreground">{placeholder}</span>
        ) : multiple ? (
          value.map((v) => (
            <span key={v} className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium">
              {options.find((o) => o.value === v)?.label || v}
              <X className="h-3 w-3 cursor-pointer" onClick={(e) => { e.stopPropagation(); pick(v) }} />
            </span>
          ))
        ) : (
          <span className="px-1 text-sm font-medium">{options.find((o) => o.value === value[0])?.label || value[0]}</span>
        )}
        <ChevronDown className="ml-auto h-4 w-4 shrink-0 opacity-60" />
      </div>

      {/* Panel (in-flow) */}
      {open && (
        <div className="mt-1 rounded-lg border border-border bg-background shadow-sm">
          <div className="flex items-center gap-2 border-b border-border px-2 py-1.5">
            <Search className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search…"
              className="w-full bg-transparent text-sm outline-none"
            />
            {multiple && selectAll && filtered.length > 0 && (
              <button type="button" onClick={toggleAll} className="shrink-0 text-xs font-medium text-primary hover:underline">
                {allFilteredSelected ? 'Clear' : 'Select all'}
              </button>
            )}
          </div>
          <div className="max-h-48 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <div className="px-3 py-2 text-sm text-muted-foreground">No matches.</div>
            ) : (
              filtered.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => pick(o.value)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted/60"
                >
                  {multiple && (
                    <span className={`flex h-4 w-4 items-center justify-center rounded border ${sel.has(o.value) ? 'bg-primary border-primary text-primary-foreground' : 'border-border'}`}>
                      {sel.has(o.value) && <Check className="h-3 w-3" />}
                    </span>
                  )}
                  <span className="flex-1 truncate">{o.label}</span>
                  {!multiple && sel.has(o.value) && <Check className="h-3.5 w-3.5 shrink-0" />}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
