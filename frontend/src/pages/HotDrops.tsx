import { useEffect, useState, useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Flame, Plus, Eye, Hand, Ticket, RefreshCw, Clock, Ban, Loader2 } from 'lucide-react'
import { useFrappePostCall, useFrappeGetDocList } from '@/lib/frappe'
import { useOutlet } from '@/contexts/OutletContext'
import { toast } from 'sonner'
import { getFrappeError } from '@/lib/utils'
import { EmptyState } from '@/components/EmptyState'
import { HotDropDialog } from '@/components/coupons/HotDropDialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'

interface HotDropRow {
  name: string
  deal_label: string
  coupon: string | null
  starts_at: string
  ends_at: string
  is_active: boolean
  is_live: boolean
  is_upcoming: boolean
  story_image_count: number
}

interface AnalyticsRow {
  name: string
  deal_label: string
  views: number
  taps: number
  claims: number
  view_to_claim_rate: number
}

function fmt(dt: string) {
  const d = new Date(dt)
  return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: 'numeric', minute: '2-digit' })
}

export default function HotDrops() {
  const { selectedOutlet } = useOutlet()
  const [rows, setRows] = useState<HotDropRow[]>([])
  const [slotUsage, setSlotUsage] = useState<{ used: number; max: number } | null>(null)
  const [analytics, setAnalytics] = useState<Record<string, AnalyticsRow>>({})
  const [isLoading, setIsLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [endTarget, setEndTarget] = useState<HotDropRow | null>(null)
  const [ending, setEnding] = useState(false)

  const { call: listMine } = useFrappePostCall('flamezo_backend.flamezo.api.hot_drops.list_merchant_hot_drops')
  const { call: endNow } = useFrappePostCall('flamezo_backend.flamezo.api.hot_drops.end_hot_drop_now')
  const { call: getAnalytics } = useFrappePostCall('flamezo_backend.flamezo.api.hot_drops.get_hot_drop_analytics')

  const { data: activeCoupons } = useFrappeGetDocList('Coupon', {
    fields: ['name', 'code', 'description'],
    filters: selectedOutlet ? [['outlet', '=', selectedOutlet], ['is_active', '=', 1]] : [],
    limit: 100,
  })

  const refresh = useCallback(async () => {
    if (!selectedOutlet) return
    setIsLoading(true)
    try {
      const res: any = await listMine({ outlet_id: selectedOutlet })
      const data = res?.message?.data
      setRows(data?.hot_drops || [])
      setSlotUsage({ used: data?.active_slots_used ?? 0, max: data?.max_slots ?? 3 })

      const analyticsRes: any = await getAnalytics({ outlet_id: selectedOutlet })
      const drops: AnalyticsRow[] = analyticsRes?.message?.data?.drops || []
      const map: Record<string, AnalyticsRow> = {}
      drops.forEach((d) => { map[d.name] = d })
      setAnalytics(map)
    } catch (err) {
      toast.error(getFrappeError(err) || 'Failed to load Hot Drops')
    } finally {
      setIsLoading(false)
    }
  }, [selectedOutlet])

  useEffect(() => { refresh() }, [refresh])

  const handleEndNow = async () => {
    if (!endTarget || !selectedOutlet) return
    setEnding(true)
    try {
      await endNow({ outlet_id: selectedOutlet, hot_drop_name: endTarget.name })
      toast.success('Hot Drop ended')
      setEndTarget(null)
      refresh()
    } catch (err) {
      toast.error(getFrappeError(err) || 'Failed to end Hot Drop')
    } finally {
      setEnding(false)
    }
  }

  const live = rows.filter((r) => r.is_live)
  const upcoming = rows.filter((r) => r.is_upcoming)
  const ended = rows.filter((r) => !r.is_live && !r.is_upcoming)

  const statusBadge = (r: HotDropRow) => {
    if (r.is_live) return <Badge className="bg-orange-500 hover:bg-orange-500 text-white gap-1"><span className="h-1.5 w-1.5 rounded-full bg-white animate-pulse" />LIVE</Badge>
    if (r.is_upcoming) return <Badge variant="outline" className="gap-1"><Clock className="h-3 w-3" />Upcoming</Badge>
    return <Badge variant="secondary" className="gap-1 text-muted-foreground">Ended</Badge>
  }

  const renderRow = (r: HotDropRow) => {
    const a = analytics[r.name]
    return (
      <div key={r.name} className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-xl border bg-card p-4">
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm">{r.deal_label}</span>
            {statusBadge(r)}
            {r.coupon && (
              <Badge variant="outline" className="gap-1 text-[10px]"><Ticket className="h-3 w-3" />{r.coupon.split('-').pop()}</Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {fmt(r.starts_at)} → {fmt(r.ends_at)} · {r.story_image_count} photo{r.story_image_count === 1 ? '' : 's'}
          </p>
          {a && (
            <div className="flex items-center gap-3 text-[11px] text-muted-foreground pt-1">
              <span className="flex items-center gap-1"><Eye className="h-3 w-3" />{a.views} views</span>
              <span className="flex items-center gap-1"><Hand className="h-3 w-3" />{a.taps} taps</span>
              {r.coupon && <span className="flex items-center gap-1"><Ticket className="h-3 w-3" />{a.claims} claimed{a.views > 0 ? ` (${a.view_to_claim_rate}%)` : ''}</span>}
            </div>
          )}
        </div>
        {(r.is_live || r.is_upcoming) && (
          <Button
            variant="outline" size="sm"
            className="text-destructive hover:bg-destructive/10 hover:border-destructive/30 shrink-0"
            onClick={() => setEndTarget(r)}
          >
            <Ban className="h-3.5 w-3.5 mr-1.5" />End now
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Flame className="h-6 w-6 text-orange-500" />
            Hot Drops
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Time-boxed flash deals shown at the very top of Discover — the first thing customers see.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={refresh} disabled={isLoading}>
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
          <Button
            className="bg-orange-500 hover:bg-orange-600"
            onClick={() => setDialogOpen(true)}
            disabled={!!slotUsage && slotUsage.used >= slotUsage.max}
          >
            <Plus className="h-4 w-4 mr-1.5" />Post Hot Drop
          </Button>
        </div>
      </div>

      {slotUsage && (
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Active slots</p>
                <p className="text-xs text-muted-foreground">Max {slotUsage.max} live or upcoming Hot Drops at once — keeps the top of Discover feeling curated, not crowded.</p>
              </div>
              <span className="text-2xl font-bold text-orange-500">{slotUsage.used}<span className="text-sm text-muted-foreground font-normal">/{slotUsage.max}</span></span>
            </div>
          </CardContent>
        </Card>
      )}

      {isLoading ? (
        <div className="py-20 flex justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : rows.length === 0 ? (
        <EmptyState
          icon={Flame}
          title="No Hot Drops yet"
          description="Post a time-boxed flash deal — it'll show at the very top of Discover while it's live."
          action={{ label: 'Post Hot Drop', onClick: () => setDialogOpen(true) }}
        />
      ) : (
        <div className="space-y-6">
          {live.length > 0 && (
            <Card>
              <CardHeader className="pb-3"><CardTitle className="text-sm">Live now ({live.length})</CardTitle></CardHeader>
              <CardContent className="space-y-2">{live.map(renderRow)}</CardContent>
            </Card>
          )}
          {upcoming.length > 0 && (
            <Card>
              <CardHeader className="pb-3"><CardTitle className="text-sm">Upcoming ({upcoming.length})</CardTitle></CardHeader>
              <CardContent className="space-y-2">{upcoming.map(renderRow)}</CardContent>
            </Card>
          )}
          {ended.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Past ({ended.length})</CardTitle>
                <CardDescription>Views, taps and claims from your last few Hot Drops.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">{ended.slice(0, 10).map(renderRow)}</CardContent>
            </Card>
          )}
        </div>
      )}

      <HotDropDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        outletId={selectedOutlet || ''}
        coupons={(activeCoupons || []).map((c: any) => ({ name: c.name, code: c.code, description: c.description }))}
        onSaved={refresh}
      />

      <AlertDialog open={!!endTarget} onOpenChange={(v) => !v && setEndTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>End this Hot Drop now?</AlertDialogTitle>
            <AlertDialogDescription>
              "{endTarget?.deal_label}" will disappear from Discover immediately. This frees up a slot for a new Hot Drop.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={ending}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleEndNow} disabled={ending} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              {ending ? 'Ending…' : 'End now'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
