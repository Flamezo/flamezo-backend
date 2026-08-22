import { useEffect, useRef, useState } from 'react'
import { Search, X, Users2, Loader2 } from 'lucide-react'
import { useFrappePostCall } from '@/lib/frappe'

const PAGE = 'flamezo_backend.flamezo.api.merchant_clubs'

export interface CollabOutlet { name: string; outlet_name: string; logo?: string }

function initials(name?: string) {
  const p = (name || '').trim().split(/\s+/).filter(Boolean)
  return p.length ? (p[0][0] + (p[1]?.[0] || '')).toUpperCase() : '?'
}

interface Props {
  outletId: string
  selected: CollabOutlet[]
  onChange: (next: CollabOutlet[]) => void
  disabled?: boolean
}

/** Tag up to 5 other outlets as collaborators on a post. */
export default function ClubCollaboratorPicker({ outletId, selected, onChange, disabled }: Props) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<CollabOutlet[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const timer = useRef<any>(null)
  const { call: search } = useFrappePostCall(`${PAGE}.merchant_search_outlets`)

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current)
    if (!q.trim()) { setResults([]); return }
    timer.current = setTimeout(async () => {
      setLoading(true)
      try {
        const res: any = await search({ outlet_id: outletId, q: q.trim(), limit: 8 })
        setResults((res?.message || res)?.data?.outlets || [])
      } catch { setResults([]) } finally { setLoading(false) }
    }, 300)
    return () => timer.current && clearTimeout(timer.current)
  }, [q, outletId, search])

  const add = (o: CollabOutlet) => {
    if (selected.length >= 5) return
    if (!selected.some(s => s.name === o.name)) onChange([...selected, o])
    setQ(''); setResults([]); setOpen(false)
  }
  const remove = (name: string) => onChange(selected.filter(s => s.name !== name))

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Users2 className="h-4 w-4 text-muted-foreground" /> Collaborators
        <span className="text-xs text-muted-foreground font-normal">Tag other outlets ({selected.length}/5)</span>
      </div>

      {selected.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selected.map(o => (
            <span key={o.name} className="inline-flex items-center gap-1.5 rounded-full border bg-muted/40 pl-1 pr-1.5 py-0.5">
              <span className="h-5 w-5 rounded-full overflow-hidden bg-muted flex items-center justify-center text-[9px] font-bold">
                {o.logo ? <img src={o.logo} alt="" className="h-full w-full object-cover" /> : initials(o.outlet_name)}
              </span>
              <span className="text-[12px] font-medium">{o.outlet_name}</span>
              <button onClick={() => remove(o.name)} disabled={disabled} className="text-muted-foreground hover:text-destructive"><X className="h-3 w-3" /></button>
            </span>
          ))}
        </div>
      )}

      {selected.length < 5 && (
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={q}
            onChange={e => { setQ(e.target.value); setOpen(true) }}
            onFocus={() => setOpen(true)}
            placeholder="Search outlets to tag…"
            disabled={disabled}
            className="w-full rounded-lg border bg-background pl-8 pr-3 h-9 text-sm outline-none focus:ring-1 focus:ring-ring"
          />
          {open && (q.trim() || loading) && (
            <div className="absolute z-20 mt-1 w-full rounded-lg border bg-popover shadow-md max-h-56 overflow-y-auto">
              {loading ? (
                <div className="py-4 text-center"><Loader2 className="h-4 w-4 animate-spin mx-auto text-muted-foreground" /></div>
              ) : results.length === 0 ? (
                <p className="py-3 px-3 text-sm text-muted-foreground">No outlets found.</p>
              ) : results.map(o => (
                <button key={o.name} onClick={() => add(o)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-accent text-left">
                  <span className="h-6 w-6 rounded-full overflow-hidden bg-muted flex items-center justify-center text-[9px] font-bold shrink-0">
                    {o.logo ? <img src={o.logo} alt="" className="h-full w-full object-cover" /> : initials(o.outlet_name)}
                  </span>
                  <span className="truncate">{o.outlet_name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
