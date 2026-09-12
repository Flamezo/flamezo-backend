import { useState } from 'react'
import { useFrappeGetCall, useFrappePostCall } from 'frappe-react-sdk'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { DataPagination } from '@/components/ui/DataPagination'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import {
  ShieldAlert, RefreshCw, Check, Trash2, XCircle, Flag,
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ReportRow {
  id: string
  chills_id: string
  chills_status: string | null
  outlet: string | null
  video_url: string | null
  thumbnail_url: string | null
  reporter_phone: string
  reason: string
  details: string | null
  status: 'Pending' | 'Reviewed' | 'Actioned' | 'Dismissed'
  reviewed_by: string | null
  reviewed_at: string | null
  reported_at: string
}

const STATUS_FILTERS = ['Pending', 'Reviewed', 'Actioned', 'Dismissed'] as const

const fmtDate = (s: string) => s
  ? new Date(s).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
  : '—'

function statusBadgeClass(status: string) {
  switch (status) {
    case 'Pending': return 'text-amber-700 bg-amber-50 border-amber-200'
    case 'Reviewed': return 'text-blue-700 bg-blue-50 border-blue-200'
    case 'Actioned': return 'text-red-700 bg-red-50 border-red-200'
    case 'Dismissed': return 'text-muted-foreground'
    default: return ''
  }
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function AdminContentModeration() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState<string>('Pending')
  const [actingOn, setActingOn] = useState<string | null>(null)

  const cacheKey = `admin-chills-reports-${page}-${pageSize}-${statusFilter}`

  const { data: response, isLoading, mutate } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.admin.admin_get_chills_reports',
    { page, page_size: pageSize, status: statusFilter || undefined },
    cacheKey
  )

  const { call: updateStatus } = useFrappePostCall(
    'flamezo_backend.flamezo.api.admin.admin_update_chills_report_status'
  )

  const result = (response as any)?.message || response
  const reports = (result?.data?.reports ?? []) as ReportRow[]
  const totalCount = result?.data?.total ?? reports.length

  async function act(report: ReportRow, status: string, takeDown: boolean) {
    setActingOn(report.id)
    try {
      const res: any = await updateStatus({ report_id: report.id, status, take_down: takeDown })
      const body = res?.message ?? res
      if (body?.success) {
        toast.success(
          takeDown && body.data?.took_down
            ? 'Report actioned — video taken down.'
            : `Report marked ${status}.`
        )
        mutate()
      } else {
        toast.error(body?.error || 'Something went wrong.')
      }
    } catch (e: any) {
      toast.error(e?.message || 'Failed to update report.')
    } finally {
      setActingOn(null)
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Header ── */}
      <div className="px-6 pt-6 pb-4 border-b shrink-0">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-xl bg-primary/10">
            <ShieldAlert className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Content Moderation</h1>
            <p className="text-sm text-muted-foreground">Chills videos reported by users, platform-wide</p>
          </div>
          {totalCount > 0 && (
            <Badge variant="secondary" className="ml-auto text-sm px-3 py-1">
              {totalCount.toLocaleString('en-IN')} {statusFilter.toLowerCase()}
            </Badge>
          )}
        </div>

        <div className="flex gap-2 items-center">
          <div className="flex gap-1.5">
            {STATUS_FILTERS.map(s => (
              <Button
                key={s}
                size="sm"
                variant={statusFilter === s ? 'default' : 'outline'}
                onClick={() => { setStatusFilter(s); setPage(1) }}>
                {s}
              </Button>
            ))}
          </div>
          <Button variant="outline" size="icon" onClick={() => mutate()} disabled={isLoading} title="Refresh" className="ml-auto">
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {/* ── Table ── */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <RefreshCw className="w-5 h-5 animate-spin mr-2" /> Loading reports…
          </div>
        ) : !reports.length ? (
          <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
            <Flag className="w-10 h-10 mb-3 opacity-25" />
            <p className="font-medium">No {statusFilter.toLowerCase()} reports</p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Video</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Reported by</TableHead>
                <TableHead>Reported</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {reports.map(r => (
                <TableRow key={r.id}>
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      {r.thumbnail_url ? (
                        <img src={r.thumbnail_url} alt="" className="w-10 h-14 rounded-md object-cover bg-muted shrink-0" />
                      ) : (
                        <div className="w-10 h-14 rounded-md bg-muted shrink-0" />
                      )}
                      <div className="min-w-0">
                        <p className="text-xs font-mono text-muted-foreground truncate max-w-[140px]">{r.chills_id}</p>
                        {r.chills_status === 'removed' && (
                          <Badge variant="secondary" className="text-[10px] text-red-700 bg-red-50 border-red-200 mt-0.5">
                            Already removed
                          </Badge>
                        )}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <p className="text-sm font-medium">{r.reason}</p>
                    {r.details && <p className="text-xs text-muted-foreground mt-0.5 max-w-[220px]">{r.details}</p>}
                  </TableCell>
                  <TableCell className="font-mono text-sm text-muted-foreground">{r.reporter_phone}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{fmtDate(r.reported_at)}</TableCell>
                  <TableCell>
                    <Badge variant="secondary" className={statusBadgeClass(r.status)}>{r.status}</Badge>
                    {r.reviewed_by && (
                      <p className="text-[10px] text-muted-foreground mt-1">by {r.reviewed_by}</p>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1.5">
                      {r.status === 'Pending' && (
                        <>
                          <Button
                            size="sm" variant="outline"
                            disabled={actingOn === r.id}
                            onClick={() => act(r, 'Dismissed', false)}
                            title="Dismiss — not a violation">
                            <XCircle className="w-3.5 h-3.5" />
                          </Button>
                          <Button
                            size="sm" variant="outline"
                            disabled={actingOn === r.id}
                            onClick={() => act(r, 'Reviewed', false)}
                            title="Mark reviewed, no action">
                            <Check className="w-3.5 h-3.5" />
                          </Button>
                          <Button
                            size="sm" variant="destructive"
                            disabled={actingOn === r.id || r.chills_status === 'removed'}
                            onClick={() => act(r, 'Actioned', true)}
                            title="Take down the video">
                            <Trash2 className="w-3.5 h-3.5 mr-1" /> Take down
                          </Button>
                        </>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {/* ── Pagination ── */}
      <div className="border-t px-4 py-3 shrink-0">
        <DataPagination
          currentPage={page}
          pageSize={pageSize}
          totalCount={totalCount}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
          isLoading={isLoading}
        />
      </div>

    </div>
  )
}
