import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useFrappePostCall } from '@/lib/frappe'
import { useOutlet } from '@/contexts/OutletContext'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import {
  ArrowLeft, CalendarDays, Clock, MapPin, Store, Star, Tag, Users, ExternalLink,
  Repeat, Loader2,
} from 'lucide-react'

interface EventDetail {
  id: string
  title: string
  description: string
  category: string
  status: string
  is_active: number
  featured: number
  date: string | null
  time: string | null
  end_time: string | null
  location: string
  google_maps_link: string
  registration_link: string
  image_src: string
  image_alt: string
  media?: { type: string; url: string }[]
  repeat_this_event: number
  repeat_on: string
  repeat_till: string | null
  repeat_days: string[]
}

const fmtDate = (s?: string | null) =>
  s ? new Date(s).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
const fmtTime = (s?: string | null) => {
  if (!s) return ''
  const [h, m] = s.split(':')
  const hh = parseInt(h, 10)
  return `${hh % 12 || 12}:${m ?? '00'} ${hh >= 12 ? 'PM' : 'AM'}`
}

const STATUS_CLS: Record<string, string> = {
  upcoming:  'bg-emerald-50 text-emerald-700 border-emerald-200',
  recurring: 'bg-blue-50 text-blue-700 border-blue-200',
  past:      'bg-stone-100 text-stone-600 border-stone-200',
}

/** Merchant's own view of an event — read-only. Shows event details + the joined
 *  customers, exactly like admin Event Management, but with no edit controls. */
export default function MyOutletEventDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { selectedOutlet } = useOutlet()
  const [loading, setLoading] = useState(true)
  const [event, setEvent] = useState<EventDetail | null>(null)
  const [outletName, setOutletName] = useState('')
  const [attendees, setAttendees] = useState<any[]>([])
  const [tab, setTab] = useState<'details' | 'attendees'>('details')

  const { call: fetchEvent } = useFrappePostCall('flamezo_backend.flamezo.api.events.merchant_get_event_detail')

  useEffect(() => {
    if (!id || !selectedOutlet) return
    let alive = true
    setLoading(true)
    fetchEvent({ outlet_id: selectedOutlet, event_id: id })
      .then((res: any) => {
        const data = res?.message?.data ?? res?.data
        if (!alive) return
        if (data?.event) {
          setEvent(data.event)
          setOutletName(data.outlet_name || '')
          setAttendees(Array.isArray(data.attendees) ? data.attendees : [])
        } else {
          setEvent(null)
        }
      })
      .catch(() => alive && setEvent(null))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [id, selectedOutlet, fetchEvent])

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center text-muted-foreground gap-2">
        <Loader2 className="h-5 w-5 animate-spin" /> Loading event…
      </div>
    )
  }

  if (!event) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">Event not found.</p>
        <Button variant="outline" onClick={() => navigate('/my-event')}>Back to Live Events</Button>
      </div>
    )
  }

  const timeRange = [fmtTime(event.time), fmtTime(event.end_time)].filter(Boolean).join(' – ')

  return (
    <div className="p-4 sm:p-6 space-y-6 max-w-5xl mx-auto">
      <div>
        <Button variant="ghost" size="sm" className="gap-1.5 -ml-2 mb-3 text-muted-foreground" onClick={() => navigate('/my-event')}>
          <ArrowLeft className="h-4 w-4" /> Back to Live Events
        </Button>
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
              {event.title}
              {!!event.featured && <Star className="h-5 w-5 fill-amber-500 text-amber-500 shrink-0" />}
            </h1>
            <span className="mt-1 inline-flex items-center gap-1.5 text-sm text-muted-foreground">
              <Store className="h-4 w-4" /> {outletName || 'Your outlet'}
            </span>
          </div>
          <Badge variant="outline" className={cn('capitalize', STATUS_CLS[event.status] || 'bg-muted')}>
            {event.status || '—'}
          </Badge>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b">
        {(['details', 'attendees'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
              tab === t ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t === 'details' ? 'Event details' : (
              <span className="inline-flex items-center gap-1.5"><Users className="h-4 w-4" /> Joined customers</span>
            )}
          </button>
        ))}
      </div>

      {tab === 'details' ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-1">
            {event.image_src ? (
              <img src={event.image_src} alt={event.image_alt || event.title}
                className="w-full rounded-xl border object-cover aspect-square" />
            ) : (
              <div className="w-full rounded-xl border bg-muted/40 aspect-square flex items-center justify-center text-muted-foreground">
                <CalendarDays className="h-10 w-10 opacity-40" />
              </div>
            )}
          </div>

          <div className="md:col-span-2 space-y-4">
            <Card>
              <CardContent className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Detail icon={CalendarDays} label="Date" value={fmtDate(event.date)} />
                <Detail icon={Clock} label="Time" value={timeRange || '—'} />
                <Detail icon={Tag} label="Category" value={event.category || '—'} />
                <Detail icon={Store} label="Organised by" value={outletName || 'Your outlet'} />
                <Detail icon={MapPin} label="Location" value={event.location || '—'} className="sm:col-span-2" />
                {!!event.repeat_this_event && (
                  <Detail icon={Repeat} label="Repeats" className="sm:col-span-2"
                    value={`${event.repeat_on || 'Recurring'}${event.repeat_days?.length ? ` · ${event.repeat_days.join(', ')}` : ''}${event.repeat_till ? ` · till ${fmtDate(event.repeat_till)}` : ''}`} />
                )}
              </CardContent>
            </Card>

            {event.description && (
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-sm">About</CardTitle></CardHeader>
                <CardContent className="pt-0 text-sm text-muted-foreground whitespace-pre-wrap">{event.description}</CardContent>
              </Card>
            )}

            {event.media && event.media.length > 0 && (
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-sm">Media</CardTitle></CardHeader>
                <CardContent className="pt-0 grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {event.media.map((m, i) => (
                    m.type === 'video'
                      ? <video key={i} src={m.url} controls className="w-full rounded-lg border aspect-square object-cover bg-muted" />
                      : <img key={i} src={m.url} alt="" className="w-full rounded-lg border aspect-square object-cover bg-muted" />
                  ))}
                </CardContent>
              </Card>
            )}

            {(event.google_maps_link || event.registration_link) && (
              <div className="flex flex-wrap gap-2">
                {event.google_maps_link && (
                  <a href={event.google_maps_link} target="_blank" rel="noreferrer">
                    <Button variant="outline" size="sm" className="gap-1.5"><MapPin className="h-4 w-4" /> Map <ExternalLink className="h-3 w-3" /></Button>
                  </a>
                )}
                {event.registration_link && (
                  <a href={event.registration_link} target="_blank" rel="noreferrer">
                    <Button variant="outline" size="sm" className="gap-1.5"><ExternalLink className="h-4 w-4" /> Registration link</Button>
                  </a>
                )}
              </div>
            )}
          </div>
        </div>
      ) : attendees.length === 0 ? (
        <Card>
          <CardContent className="py-16 flex flex-col items-center text-center gap-3">
            <div className="rounded-full bg-muted p-3"><Users className="h-7 w-7 text-muted-foreground" /></div>
            <p className="font-semibold">No one has joined yet</p>
            <p className="text-sm text-muted-foreground max-w-md">Customers who tap “Join” on this event in the app will appear here.</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2"><Users className="h-4 w-4" /> {attendees.length} joined</CardTitle>
          </CardHeader>
          <CardContent className="pt-0 divide-y">
            {attendees.map((a, i) => (
              <div key={a.id || i} className="w-full flex items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="font-medium truncate">{a.name || 'Guest'}</p>
                  {a.phone && <p className="text-xs text-muted-foreground">{a.phone}</p>}
                </div>
                <span className="text-xs text-muted-foreground shrink-0">{a.joined_at ? fmtDate(a.joined_at) : ''}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function Detail({ icon: Icon, label, value, className }:
  { icon: React.ElementType; label: string; value: string; className?: string }) {
  return (
    <div className={cn('flex items-start gap-2.5', className)}>
      <Icon className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
      <div className="min-w-0">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="text-sm font-medium break-words">{value}</p>
      </div>
    </div>
  )
}
