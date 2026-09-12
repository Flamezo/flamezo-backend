import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useFrappeGetCall } from '@/lib/frappe'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { DataPagination } from '@/components/ui/DataPagination'
import { cn } from '@/lib/utils'
import {
  Sparkles, Search, RefreshCw, ChevronRight,
  ArrowUpDown, ArrowUp, ArrowDown, Instagram,
  Video, Wallet, ShieldAlert,
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface CreatorRow {
  id: string
  name: string
  phone: string
  instagram_handle: string
  followers: number
  status: 'pending' | 'approved' | 'rejected' | 'suspended'
  kyc_status: string
  city: string
  badge_tier: string
  collabs_done: number
  total_earned_inr: number
  open_disputes: number
  created: string
  last_seen: string
}

type SortField = 'name' | 'followers' | 'created' | 'last_seen' | 'status'
type SortOrder = 'asc' | 'desc'

const STATUS_FILTERS: { id: CreatorRow['status'] | null; label: string }[] = [
  { id: null, label: 'All' },
  { id: 'pending', label: 'Pending' },
  { id: 'approved', label: 'Approved' },
  { id: 'suspended', label: 'Suspended' },
  { id: 'rejected', label: 'Rejected' },
]

const BADGE_TIER_LABELS: Record<string, string> = {
  new_creator: 'New Creator',
  verified_creator: 'Verified',
  top_rated: 'Top Rated',
  elite_creator: 'Elite',
}

const STATUS_STYLES: Record<CreatorRow['status'], string> = {
  approved: 'text-green-700 bg-green-50 border-green-200',
  pending: 'text-amber-700 bg-amber-50 border-amber-200',
  suspended: 'text-red-700 bg-red-50 border-red-200',
  rejected: 'text-muted-foreground bg-muted border-transparent',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmtR    = (n?: number) => `₹${(n ?? 0).toLocaleString('en-IN')}`
const fmtDate = (s: string) => s ? new Date(s).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

function SortIcon({ field, sortBy, sortOrder }: { field: SortField; sortBy: SortField; sortOrder: SortOrder }) {
  if (sortBy !== field) return <ArrowUpDown className="w-3.5 h-3.5 opacity-30" />
  return sortOrder === 'asc'
    ? <ArrowUp className="w-3.5 h-3.5 text-primary" />
    : <ArrowDown className="w-3.5 h-3.5 text-primary" />
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function AdminCreatorManagement() {
  const navigate = useNavigate()

  const [page, setPage]           = useState(1)
  const [pageSize, setPageSize]   = useState(20)
  const [search, setSearch]       = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<CreatorRow['status'] | null>(null)
  const [sortBy, setSortBy]       = useState<SortField>('last_seen')
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc')

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350)
    return () => clearTimeout(t)
  }, [search])

  useEffect(() => { setPage(1) }, [debouncedSearch, statusFilter, sortBy, sortOrder, pageSize])

  const cacheKey = `admin-creators-${page}-${pageSize}-${debouncedSearch}-${statusFilter}-${sortBy}-${sortOrder}`

  const { data: response, isLoading, mutate } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.admin.admin_get_all_creators',
    {
      page,
      page_size: pageSize,
      search: debouncedSearch || undefined,
      status: statusFilter || undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
    },
    cacheKey
  )

  const result     = (response as any)?.message || response
  const creators    = (result?.data?.creators ?? []) as CreatorRow[]
  const totalCount = result?.data?.total ?? creators.length

  function toggleSort(field: SortField) {
    if (sortBy === field) {
      setSortOrder(o => o === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(field)
      setSortOrder('desc')
    }
  }

  function SortableHead({ field, children, className }: { field: SortField; children: React.ReactNode; className?: string }) {
    return (
      <TableHead
        className={cn('cursor-pointer select-none hover:text-foreground transition-colors', className)}
        onClick={() => toggleSort(field)}>
        <span className="flex items-center gap-1.5">
          {children}
          <SortIcon field={field} sortBy={sortBy} sortOrder={sortOrder} />
        </span>
      </TableHead>
    )
  }

  const pageStats = creators.length > 0 ? {
    totalEarned:  creators.reduce((s, c) => s + (c.total_earned_inr ?? 0), 0),
    openDisputes: creators.reduce((s, c) => s + (c.open_disputes ?? 0), 0),
    pendingCount: creators.filter(c => c.status === 'pending').length,
  } : null

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Header ── */}
      <div className="px-6 pt-6 pb-4 border-b shrink-0">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-xl bg-primary/10">
            <Sparkles className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Creator Management</h1>
            <p className="text-sm text-muted-foreground">Platform-wide creator status, KYC, earnings & disputes</p>
          </div>
          {totalCount > 0 && (
            <Badge variant="secondary" className="ml-auto text-sm px-3 py-1">
              {totalCount.toLocaleString('en-IN')} total
            </Badge>
          )}
        </div>

        <div className="flex gap-2 mb-3">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search by name, phone or Instagram…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <Button variant="outline" size="icon" onClick={() => mutate()} disabled={isLoading} title="Refresh">
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
          </Button>
        </div>

        <div className="flex gap-2">
          {STATUS_FILTERS.map(f => (
            <button
              key={f.label}
              onClick={() => setStatusFilter(f.id)}
              className={cn(
                'text-xs font-medium px-3 py-1.5 rounded-full border transition-colors',
                statusFilter === f.id
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-background text-muted-foreground border-border hover:text-foreground'
              )}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Summary strip ── */}
      {pageStats && !isLoading && (
        <div className="flex items-center gap-6 px-6 py-2.5 border-b bg-muted/30 text-xs text-muted-foreground shrink-0 overflow-x-auto">
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <Wallet className="w-3.5 h-3.5" />
            {fmtR(pageStats.totalEarned)} paid out
          </span>
          <span className={cn('flex items-center gap-1.5 whitespace-nowrap', pageStats.openDisputes > 0 && 'text-red-600 font-medium')}>
            <ShieldAlert className="w-3.5 h-3.5" />
            {pageStats.openDisputes} open dispute{pageStats.openDisputes === 1 ? '' : 's'}
          </span>
          {pageStats.pendingCount > 0 && (
            <span className="flex items-center gap-1.5 whitespace-nowrap text-amber-600 font-medium">
              {pageStats.pendingCount} pending review
            </span>
          )}
        </div>
      )}

      {/* ── Table ── */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <RefreshCw className="w-5 h-5 animate-spin mr-2" /> Loading creators…
          </div>
        ) : !creators.length ? (
          <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
            <Sparkles className="w-10 h-10 mb-3 opacity-25" />
            <p className="font-medium">No creators found</p>
            {debouncedSearch && <p className="text-xs mt-1">Try a different search term</p>}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <SortableHead field="name">Creator</SortableHead>
                <TableHead>Instagram</TableHead>
                <SortableHead field="followers">Followers</SortableHead>
                <TableHead>Badge</TableHead>
                <SortableHead field="status">Status</SortableHead>
                <TableHead>KYC</TableHead>
                <TableHead>Collabs</TableHead>
                <TableHead>Earned</TableHead>
                <SortableHead field="last_seen" className="hidden lg:table-cell">Last Seen</SortableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {creators.map(c => (
                <TableRow
                  key={c.id}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => navigate(`/admin/creators/${encodeURIComponent(c.id)}`)}>
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm shrink-0">
                        {(c.name || '?')[0].toUpperCase()}
                      </div>
                      <div>
                        <div className="font-medium text-sm">{c.name}</div>
                        <div className="text-xs text-muted-foreground font-mono">{c.phone || '—'}</div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {c.instagram_handle ? (
                      <span className="flex items-center gap-1"><Instagram className="w-3.5 h-3.5" /> @{c.instagram_handle}</span>
                    ) : '—'}
                  </TableCell>
                  <TableCell className="text-sm font-medium">{c.followers.toLocaleString('en-IN')}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs">{BADGE_TIER_LABELS[c.badge_tier] || c.badge_tier}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className={cn('capitalize', STATUS_STYLES[c.status])}>
                      {c.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground capitalize">{c.kyc_status.replace(/_/g, ' ')}</TableCell>
                  <TableCell className="text-sm">
                    <span className="flex items-center gap-1"><Video className="w-3.5 h-3.5 text-muted-foreground" /> {c.collabs_done}</span>
                  </TableCell>
                  <TableCell className="text-sm font-semibold">{fmtR(c.total_earned_inr)}</TableCell>
                  <TableCell className="text-xs text-muted-foreground hidden lg:table-cell">{fmtDate(c.last_seen)}</TableCell>
                  <TableCell className="w-8">
                    {c.open_disputes > 0 ? (
                      <Badge variant="destructive" className="text-[10px] px-1.5">{c.open_disputes}</Badge>
                    ) : (
                      <ChevronRight className="w-4 h-4 text-muted-foreground" />
                    )}
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
