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
  Users, Search, RefreshCw, ChevronRight,
  ArrowUpDown, ArrowUp, ArrowDown,
  ShoppingBag, Wallet, TrendingUp, Clock,
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface CustomerRow {
  id: string
  name: string
  phone: string
  birthday: string | null
  created: string
  last_seen: string
  total_orders: number
  total_spend: number
  loyalty_balance: number
  lifetime_earned: number
  total_redeemed: number
}

type SortField = 'name' | 'total_orders' | 'total_spend' | 'loyalty_balance' | 'lifetime_earned' | 'last_seen' | 'created'
type SortOrder = 'asc' | 'desc'

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmtR    = (n: number) => `₹${n.toLocaleString('en-IN')}`
const fmtDate = (s: string) => s ? new Date(s).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

function SortIcon({ field, sortBy, sortOrder }: { field: SortField; sortBy: SortField; sortOrder: SortOrder }) {
  if (sortBy !== field) return <ArrowUpDown className="w-3.5 h-3.5 opacity-30" />
  return sortOrder === 'asc'
    ? <ArrowUp className="w-3.5 h-3.5 text-primary" />
    : <ArrowDown className="w-3.5 h-3.5 text-primary" />
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function AdminCustomerManagement() {
  const navigate = useNavigate()

  const [page, setPage]           = useState(1)
  const [pageSize, setPageSize]   = useState(20)
  const [search, setSearch]       = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [sortBy, setSortBy]       = useState<SortField>('last_seen')
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc')

  // Debounce search to avoid hammering backend on every keystroke
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350)
    return () => clearTimeout(t)
  }, [search])

  // Reset to page 1 on any filter change
  useEffect(() => { setPage(1) }, [debouncedSearch, sortBy, sortOrder, pageSize])

  const cacheKey = `admin-customers-${page}-${pageSize}-${debouncedSearch}-${sortBy}-${sortOrder}`

  const { data: response, isLoading, mutate } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.admin.admin_get_all_customers',
    {
      page,
      page_size: pageSize,
      search: debouncedSearch || undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
    },
    cacheKey
  )

  const result     = (response as any)?.message || response
  const customers  = (result?.data?.customers ?? result?.data ?? []) as CustomerRow[]
  const totalCount = result?.data?.total ?? result?.total_count ?? result?.total ?? customers.length

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

  // Summary stats derived from current page — shows range feel
  const pageStats = customers.length > 0 ? {
    totalOrders:    customers.reduce((s, c) => s + c.total_orders, 0),
    totalSpend:     customers.reduce((s, c) => s + c.total_spend, 0),
    totalBalance:   customers.reduce((s, c) => s + c.loyalty_balance, 0),
    withBalance:    customers.filter(c => c.loyalty_balance > 0).length,
  } : null

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Header ── */}
      <div className="px-6 pt-6 pb-4 border-b shrink-0">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-xl bg-primary/10">
            <Users className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Customer Management</h1>
            <p className="text-sm text-muted-foreground">Platform-wide customer data, loyalty, referrals & UGC</p>
          </div>
          {totalCount > 0 && (
            <Badge variant="secondary" className="ml-auto text-sm px-3 py-1">
              {totalCount.toLocaleString('en-IN')} total
            </Badge>
          )}
        </div>

        <div className="flex gap-2">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search by name or phone…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <Button variant="outline" size="icon" onClick={() => mutate()} disabled={isLoading} title="Refresh">
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {/* ── Summary strip ── */}
      {pageStats && !isLoading && (
        <div className="flex items-center gap-6 px-6 py-2.5 border-b bg-muted/30 text-xs text-muted-foreground shrink-0 overflow-x-auto">
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <ShoppingBag className="w-3.5 h-3.5" />
            {pageStats.totalOrders.toLocaleString('en-IN')} orders on this page
          </span>
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <TrendingUp className="w-3.5 h-3.5" />
            {fmtR(pageStats.totalSpend)} spend
          </span>
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <Wallet className="w-3.5 h-3.5" />
            {fmtR(pageStats.totalBalance)} loyalty balance held
          </span>
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <Clock className="w-3.5 h-3.5" />
            {pageStats.withBalance} with active balance
          </span>
        </div>
      )}

      {/* ── Table ── */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <RefreshCw className="w-5 h-5 animate-spin mr-2" /> Loading customers…
          </div>
        ) : !customers.length ? (
          <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
            <Users className="w-10 h-10 mb-3 opacity-25" />
            <p className="font-medium">No customers found</p>
            {debouncedSearch && <p className="text-xs mt-1">Try a different search term</p>}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <SortableHead field="name">Customer</SortableHead>
                <TableHead>Phone</TableHead>
                <SortableHead field="total_orders">Orders</SortableHead>
                <SortableHead field="total_spend">Total Spend</SortableHead>
                <SortableHead field="loyalty_balance">Cash Balance</SortableHead>
                <SortableHead field="lifetime_earned">Lifetime Earned</SortableHead>
                <SortableHead field="last_seen">Last Seen</SortableHead>
                <SortableHead field="created" className="hidden lg:table-cell">Joined</SortableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {customers.map(c => (
                <TableRow
                  key={c.id}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => navigate(`/admin/customers/${encodeURIComponent(c.id)}`)}>
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm shrink-0">
                        {(c.name || '?')[0].toUpperCase()}
                      </div>
                      <span className="font-medium text-sm">{c.name}</span>
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-sm text-muted-foreground">{c.phone || '—'}</TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="font-semibold">{c.total_orders}</Badge>
                  </TableCell>
                  <TableCell className="font-semibold text-sm">{fmtR(c.total_spend)}</TableCell>
                  <TableCell>
                    <Badge
                      variant="secondary"
                      className={cn(
                        c.loyalty_balance > 0
                          ? 'text-green-700 bg-green-50 border-green-200 font-semibold'
                          : 'text-muted-foreground'
                      )}>
                      {fmtR(c.loyalty_balance)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{fmtR(c.lifetime_earned)}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{fmtDate(c.last_seen)}</TableCell>
                  <TableCell className="text-xs text-muted-foreground hidden lg:table-cell">{fmtDate(c.created)}</TableCell>
                  <TableCell className="w-8">
                    <ChevronRight className="w-4 h-4 text-muted-foreground" />
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
