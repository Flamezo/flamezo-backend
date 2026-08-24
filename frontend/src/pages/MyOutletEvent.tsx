import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOutlet } from '@/contexts/OutletContext'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useDataTable } from '@/hooks/useDataTable'
import { FilterCondition } from '@/components/ListFilters'
import { DataPagination } from '@/components/ui/DataPagination'
import { Calendar, Clock, MapPin, Eye, PartyPopper, Search } from 'lucide-react'

const fmtDate = (s?: string) => s ? new Date(s).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
const fmtTime = (s?: string) => {
  if (!s) return ''
  const [h, m] = s.split(':')
  const hh = parseInt(h, 10)
  return `${hh % 12 || 12}:${m ?? '00'} ${hh >= 12 ? 'PM' : 'AM'}`
}

export default function MyOutletEvent() {
  const { selectedOutlet } = useOutlet()
  const navigate = useNavigate()

  const initialFilters = useMemo<FilterCondition[]>(
    () => (selectedOutlet ? [{ fieldname: 'outlet', operator: '=', value: selectedOutlet }] : []),
    [selectedOutlet],
  )

  const {
    data: events, isLoading, page, setPage, pageSize, setPageSize, totalCount, searchQuery, setSearchQuery,
  } = useDataTable({
    doctype: 'Event',
    fields: ['name', 'title', 'description', 'category', 'is_active', 'date', 'time', 'end_time', 'location', 'image_src', 'featured', 'outlet'],
    initialFilters,
    searchFields: ['title', 'category', 'description', 'location'],
    // Active first; past/deactivated events shift to the bottom.
    orderBy: { field: 'is_active desc, date', order: 'desc' },
    initialPageSize: 12,
    debugId: `my-events-${selectedOutlet}`,
  })

  const rows = (events || []) as any[]
  const openEvent = (name: string) => navigate(`/my-event/${encodeURIComponent(name)}`)

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <PartyPopper className="h-6 w-6 text-primary" /> Live Events
          </h2>
          <p className="text-muted-foreground text-sm">Your events — tap one to view its details and who's joined. View-only.</p>
        </div>
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search your events…" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="pl-8 h-9" />
        </div>
      </div>

      {isLoading && rows.length === 0 ? (
        <div className="py-20 text-center text-muted-foreground">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center min-h-[300px] text-center">
          <div className="h-20 w-20 bg-muted rounded-full flex items-center justify-center mb-4">
            <PartyPopper className="h-10 w-10 text-muted-foreground/30" />
          </div>
          <h3 className="text-xl font-semibold mb-2">No events</h3>
          <p className="text-muted-foreground max-w-sm">No events found for this outlet.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {rows.map((ev) => (
            <div
              key={ev.name}
              onClick={() => openEvent(ev.name)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openEvent(ev.name) } }}
              className={cn('group relative flex flex-col rounded-2xl border bg-card shadow-sm transition-all hover:shadow-md overflow-hidden cursor-pointer', !ev.is_active && 'opacity-70 grayscale-[0.4]')}
            >
              <div className="aspect-[16/9] w-full overflow-hidden bg-muted relative">
                {ev.image_src ? (
                  <img src={ev.image_src} alt={ev.title} className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" />
                ) : (
                  <div className="h-full w-full flex items-center justify-center text-muted-foreground/20"><Calendar className="h-12 w-12" /></div>
                )}
                {ev.category && (
                  <div className="absolute top-3 left-3"><Badge className="bg-black/60 backdrop-blur-md text-white border-none">{ev.category}</Badge></div>
                )}
                {!ev.is_active && (
                  <div className="absolute top-3 right-3"><Badge variant="secondary" className="bg-stone-700/80 text-white border-none">Over</Badge></div>
                )}
              </div>
              <div className="flex flex-col flex-1 p-4 gap-3">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-bold text-lg leading-tight truncate">{ev.title}</h3>
                  <Button size="icon" variant="ghost" className="h-8 w-8 shrink-0" onClick={(e) => { e.stopPropagation(); openEvent(ev.name) }} title="View event">
                    <Eye className="h-4 w-4" />
                  </Button>
                </div>
                <div className="flex flex-col gap-1.5 text-xs text-muted-foreground font-medium">
                  <span className="inline-flex items-center gap-1.5"><Calendar className="h-3.5 w-3.5" /> {fmtDate(ev.date)}</span>
                  {ev.time && <span className="inline-flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" /> {fmtTime(ev.time)}</span>}
                  {ev.location && <span className="inline-flex items-center gap-1.5 truncate"><MapPin className="h-3.5 w-3.5 shrink-0" /> <span className="truncate">{ev.location}</span></span>}
                </div>
                {ev.description && <p className="text-sm text-muted-foreground line-clamp-2">{ev.description}</p>}
              </div>
            </div>
          ))}
        </div>
      )}

      <DataPagination currentPage={page} pageSize={pageSize} totalCount={totalCount} onPageChange={setPage} onPageSizeChange={setPageSize} isLoading={isLoading} />
    </div>
  )
}
