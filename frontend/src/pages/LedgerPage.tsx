import { useState, useEffect, useCallback } from 'react'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useCurrency } from '@/hooks/useCurrency'
import { useDataTable } from '@/hooks/useDataTable'
import { useFrappeGetCall } from '@/lib/frappe'
import { FilterCondition } from '@/components/ListFilters'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { DataPagination } from '@/components/ui/DataPagination'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { DatePicker } from '@/components/ui/date-picker'
import { 
  Plus, 
  Sparkles, 
  TrendingUp, 
  Zap, 
  ChevronRight, 
  ShoppingCart,
  RefreshCcw,
  Search,
  Clock,
  Download,
  Info,
  ArrowRightLeft,
  Filter,
  Layers,
  CircleDollarSign,
  ReceiptText,
  ShieldAlert,
  History
} from 'lucide-react'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { cn } from '@/lib/utils'
import { AiRechargeModal } from '@/components/AiRechargeModal'
import { format, subDays } from 'date-fns'

interface Transaction {
  name: string
  amount: number
  gst_amount?: number
  total_paid_inr?: number
  transaction_type: string
  description: string
  balance_after: number
  creation: string
  reference_doctype?: string
  reference_name?: string
  payment_id?: string
}

type FilterPreset = 'all' | 'today' | 'yesterday' | '7d' | '30d' | 'custom'

export default function LedgerPage() {
  const { selectedRestaurant, coinsBalance, refreshConfig } = useRestaurant()
  const { formatAmountNoDecimals } = useCurrency()
  
  // UI State
  const [showRecharge, setShowRecharge] = useState(false)
  const [selectedTxn, setSelectedTxn] = useState<Transaction | null>(null)
  const [balance, setBalance] = useState<number>(coinsBalance)
  
  const { data: platformSettingsData } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.admin.get_platform_settings',
    {},
    'platform-settings-ledger'
  )
  
  const platformSettings = platformSettingsData?.message?.data || {
    charge_gst: false,
    gst_percent: 18
  }
  
  // Filtering State
  const [typeFilter, setTypeFilter] = useState<'all' | 'credit' | 'debit'>('all')
  const [activePreset, setActivePreset] = useState<FilterPreset>('all')
  const [fromDate, setFromDate] = useState<string>('')
  const [toDate, setToDate] = useState<string>('')

  const today = format(new Date(), 'yyyy-MM-dd')

  const {
    data: activities,
    isLoading,
    page,
    setPage,
    pageSize,
    setPageSize,
    totalCount,
    mutate: refreshTable,
    setFilters: setDataTableFilters
  } = useDataTable({
    doctype: 'Coin Transaction',
    initialFilters: selectedRestaurant ? [
      { fieldname: 'restaurant', operator: '=', value: selectedRestaurant }
    ] : [],
    fields: ['name', 'creation', 'transaction_type', 'amount', 'gst_amount', 'total_paid_inr', 'balance_after', 'description', 'reference_doctype', 'reference_name', 'payment_id'],
    initialPageSize: 20,
    searchFields: ['description', 'payment_id', 'transaction_type', 'reference_name'],
    orderBy: { field: 'creation', order: 'desc' },
    debugId: `ledger-v5-${selectedRestaurant}`
  })

  useEffect(() => {
    setBalance(coinsBalance)
  }, [coinsBalance])

  const mutate = useCallback(async () => {
    await Promise.all([refreshTable(), refreshConfig()])
  }, [refreshTable, refreshConfig])

  // Apply filters based on presets and custom dates
  useEffect(() => {
    if (!selectedRestaurant) return

    const baseFilters: FilterCondition[] = [
      { fieldname: 'restaurant', operator: '=', value: selectedRestaurant }
    ]
    
    // Type Filter
    if (typeFilter !== 'all') {
      baseFilters.push({ 
        fieldname: 'amount', 
        operator: typeFilter === 'credit' ? '>' : '<', 
        value: 0 
      })
    }

    // Date Filters
    if (fromDate && toDate) {
        baseFilters.push({ fieldname: 'creation', operator: '>=', value: `${fromDate} 00:00:00` })
        baseFilters.push({ fieldname: 'creation', operator: '<=', value: `${toDate} 23:59:59` })
    } else if (fromDate) {
        baseFilters.push({ fieldname: 'creation', operator: '>=', value: `${fromDate} 00:00:00` })
    } else if (toDate) {
        baseFilters.push({ fieldname: 'creation', operator: '<=', value: `${toDate} 23:59:59` })
    }

    setDataTableFilters(baseFilters)
  }, [typeFilter, fromDate, toDate, selectedRestaurant, setDataTableFilters])

  const applyPreset = (preset: FilterPreset) => {
    setActivePreset(preset)
    let f = ''
    let t = ''

    if (preset === 'today') {
      f = today
      t = today
    } else if (preset === 'yesterday') {
      f = format(subDays(new Date(), 1), 'yyyy-MM-dd')
      t = f
    } else if (preset === '7d') {
      f = format(subDays(new Date(), 6), 'yyyy-MM-dd')
      t = today
    } else if (preset === '30d') {
      f = format(subDays(new Date(), 29), 'yyyy-MM-dd')
      t = today
    } else if (preset === 'all') {
      f = ''
      t = ''
    } else if (preset === 'custom') {
      return // Manual date selection
    }

    setFromDate(f)
    setToDate(t)
  }

  const getTxnIcon = (type: string) => {
    if (type?.includes('AI')) return <Sparkles className="h-4 w-4 text-purple-600" />
    if (type?.includes('Commission')) return <ShoppingCart className="h-4 w-4 text-blue-600" />
    if (type?.includes('Purchase') || type?.includes('Recharge')) return <TrendingUp className="h-4 w-4 text-emerald-600" />
    if (type?.includes('Refund')) return <RefreshCcw className="h-4 w-4 text-orange-600" />
    if (type === 'Lead Unlock') return <Zap className="h-4 w-4 text-amber-600" />
    if (type?.includes('Subscription')) return <Layers className="h-4 w-4 text-indigo-600" />
    return <CircleDollarSign className="h-4 w-4 text-slate-500" />
  }

  const getTxnColor = (amount: number) => {
    return amount > 0 ? 'text-emerald-600' : 'text-rose-500'
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-20 animate-in fade-in duration-700">
      {/* Header & Main Stats */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-0.5">
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            Wallet Ledger & History
            <History className="h-6 w-6 text-muted-foreground/30" />
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl font-medium">Manage credits, track usage, and monitor fiscal compliance.</p>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="p-1 rounded-xl bg-muted/50 border border-border/50 flex items-center gap-1">
             <Button 
               variant={typeFilter === 'all' ? 'default' : 'ghost'} 
               size="sm" 
               className="h-8 text-[10px] font-bold uppercase rounded-lg px-4"
               onClick={() => setTypeFilter('all')}
             >
               All
             </Button>
             <Button 
               variant={typeFilter === 'credit' ? 'default' : 'ghost'} 
               size="sm" 
               className="h-8 text-[10px] font-bold uppercase rounded-lg px-4"
               onClick={() => setTypeFilter('credit')}
             >
               Credits
             </Button>
             <Button 
               variant={typeFilter === 'debit' ? 'default' : 'ghost'} 
               size="sm" 
               className="h-8 text-[10px] font-bold uppercase rounded-lg px-4"
               onClick={() => setTypeFilter('debit')}
             >
               Debits
             </Button>
          </div>

          <Button 
            className="gap-2 bg-primary text-white shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-all rounded-xl h-10 px-6 font-bold" 
            onClick={() => setShowRecharge(true)}
          >
            <Plus className="h-4 w-4" />
            Top up
          </Button>
        </div>
      </div>

      {/* Stats Overview */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card className="relative overflow-hidden border-none bg-gradient-to-br from-primary/10 via-primary/5 to-background shadow-sm p-4 rounded-2xl">
          <div className="absolute -right-4 -top-4 opacity-5">
            <TrendingUp className="h-24 w-24 text-primary" />
          </div>
          <div className="space-y-1 relative z-10">
             <p className="text-[10px] font-bold uppercase tracking-wider text-primary/70">Wallet Balance</p>
             <div className="flex items-baseline gap-1.5">
                <span className="text-3xl font-bold tabular-nums tracking-tight">{formatAmountNoDecimals(balance)}</span>
                <span className="text-[10px] font-bold text-muted-foreground uppercase opacity-70">INR</span>
             </div>
             <div className="flex items-center gap-1.5 pt-1">
                <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                <p className="text-[10px] text-muted-foreground font-semibold">Live & Verified</p>
             </div>
          </div>
        </Card>

        <Card className="border-none bg-muted/10 p-4 rounded-2xl flex flex-col justify-center">
             <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1">Total Activities</p>
             <p className="text-2xl font-bold tabular-nums tracking-tight">{totalCount || 0}</p>
             <p className="text-[10px] text-muted-foreground font-semibold flex items-center gap-1 mt-1">
                <Layers className="h-3 w-3" />
                Across selected range
             </p>
        </Card>
      </div>

      {/* Filter Bar */}
      <Card className="border-none bg-muted/20 shadow-none rounded-2xl overflow-hidden px-4 py-3">
        <div className="flex flex-col space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground ml-1 mr-2 italic">
                <Filter className="h-3 w-3" /> Filters:
            </span>
            {(['all', 'today', 'yesterday', '7d', '30d', 'custom'] as FilterPreset[]).map((preset) => (
              <Button
                key={preset}
                variant={activePreset === preset ? 'default' : 'outline'}
                size="sm"
                className={cn(
                  "rounded-xl px-4 text-xs font-semibold h-8 transition-all",
                  activePreset === preset ? "shadow-md shadow-primary/20 border-primary" : "hover:border-primary/50 bg-background"
                )}
                onClick={() => applyPreset(preset)}
              >
                {preset === 'all' && 'All Time'}
                {preset === 'today' && 'Today'}
                {preset === 'yesterday' && 'Yesterday'}
                {preset === '7d' && 'Last 7 Days'}
                {preset === '30d' && 'Last 30 Days'}
                {preset === 'custom' && 'Custom Range'}
              </Button>
            ))}
          </div>

          {(activePreset === 'custom' || (fromDate && activePreset !== 'all')) && (
            <div className="flex flex-col md:flex-row items-end gap-3 p-4 rounded-2xl bg-background border border-border/50 animate-in slide-in-from-top-2 duration-300">
              <div className="flex-1 w-full">
                <DatePicker 
                  label="Start Date" 
                  value={fromDate} 
                  onChange={setFromDate}
                />
              </div>
              <div className="flex-1 w-full">
                <DatePicker 
                  label="End Date" 
                  value={toDate} 
                  onChange={setToDate}
                />
              </div>
              <Button 
                size="sm"
                className="rounded-xl px-6 h-10 font-bold bg-primary/10 text-primary hover:bg-primary/20 border-none shrink-0"
                onClick={() => refreshTable()}
              >
                <Search className="h-4 w-4 mr-2" />
                Apply Dates
              </Button>
            </div>
          )}
        </div>
      </Card>

      {/* Main Ledger Table */}
      <Card className="shadow-xl shadow-black/5 border-none bg-card overflow-hidden rounded-3xl">
        <CardHeader className="flex flex-row items-center justify-between border-b border-border/50 py-5 px-6">
            <div className="flex items-center gap-4">
                <div className="h-10 w-10 rounded-xl bg-orange-500/10 flex items-center justify-center">
                    <ReceiptText className="h-5 w-5 text-orange-600" />
                </div>
                <div>
                    <CardTitle className="text-xl font-bold tracking-tight">Financial Ledger</CardTitle>
                    <p className="text-[10px] text-muted-foreground font-bold flex items-center gap-1 uppercase tracking-wider">
                        <Clock className="h-3 w-3" /> Generated {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </p>
                </div>
            </div>
            
            <Button variant="ghost" size="sm" className="text-[10px] text-muted-foreground h-8 hover:bg-muted rounded-xl px-4 uppercase font-bold tracking-widest gap-2">
                <Download className="h-3 w-3" />
                Export Audit
            </Button>
        </CardHeader>

        <CardContent className="p-0">
            <Table className="w-full">
                <TableHeader className="bg-muted/30">
                <TableRow className="border-border/50 hover:bg-transparent">
                    <TableHead className="font-bold text-[10px] uppercase tracking-wider text-muted-foreground/80 pl-6 h-12 w-[140px]">Date & Time</TableHead>
                    <TableHead className="font-bold text-[10px] uppercase tracking-wider text-muted-foreground/80 h-12">Description</TableHead>
                    <TableHead className="font-bold text-[10px] uppercase tracking-wider text-muted-foreground/80 h-12 w-[180px]">Reference</TableHead>
                    <TableHead className="font-bold text-[10px] uppercase tracking-wider text-muted-foreground/80 text-right h-12 w-[120px]">Amount</TableHead>
                    <TableHead className="w-[50px] pr-6 h-12"></TableHead>
                </TableRow>
                </TableHeader>
                <TableBody>
                {isLoading && activities?.length === 0 ? (
                    [1, 2, 3, 4, 5].map(i => (
                    <TableRow key={i} className="border-border/40">
                        <TableCell colSpan={5} className="py-6 px-6"><Skeleton className="h-12 w-full rounded-xl" /></TableCell>
                    </TableRow>
                    ))
                ) : activities?.length === 0 ? (
                    <TableRow>
                    <TableCell colSpan={5} className="h-80 text-center">
                        <div className="flex flex-col items-center justify-center space-y-4 opacity-50">
                            <div className="h-20 w-20 rounded-full bg-muted flex items-center justify-center">
                                <Search className="h-10 w-10 text-muted-foreground" />
                            </div>
                            <div className="space-y-1">
                                <p className="text-sm font-bold text-foreground">No matching transactions</p>
                                <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Try adjusting your filters or search query</p>
                            </div>
                        </div>
                    </TableCell>
                    </TableRow>
                ) : activities?.map((log: any) => {
                    const isCredit = log.amount > 0
                    return (
                    <TableRow 
                        key={log.name} 
                        className="hover:bg-muted/20 transition-all group cursor-pointer border-border/40"
                        onClick={() => setSelectedTxn(log)}
                    >
                        <TableCell className="pl-6 py-5 whitespace-nowrap">
                        <div className="flex flex-col">
                            <span className="font-semibold text-sm text-foreground">
                            {new Date(log.creation).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
                            </span>
                            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-tight flex items-center gap-1 mt-0.5 opacity-60">
                            <Clock className="h-3 w-3 opacity-50" />
                            {new Date(log.creation).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
                            </span>
                        </div>
                        </TableCell>
                        <TableCell className="py-5 min-w-0 max-w-md">
                        <div className="flex items-center gap-3 min-w-0">
                            <div className="h-9 w-9 rounded-xl bg-muted/50 flex items-center justify-center shrink-0 border border-border/50 group-hover:bg-background transition-colors">
                                {getTxnIcon(log.transaction_type)}
                            </div>
                            <div className="flex flex-col gap-1 overflow-hidden min-w-0">
                                <span className="text-sm font-semibold leading-tight group-hover:text-primary transition-colors truncate block">
                                    {log.description || 'System Adjustment'}
                                </span>
                                <div className="flex items-center gap-2">
                                    <Badge variant="outline" className={cn(
                                        "w-fit text-[9px] h-4 py-0 font-bold uppercase tracking-wider border-none rounded-sm",
                                        isCredit ? 'bg-emerald-500/10 text-emerald-700' : 'bg-rose-500/10 text-rose-700'
                                    )}>
                                        {isCredit ? 'Credit' : 'Debit'}
                                    </Badge>
                                    <span className="text-[9px] text-muted-foreground font-bold px-1.5 py-0.5 rounded bg-muted/60 uppercase tracking-tighter tabular-nums">
                                        {log.transaction_type}
                                    </span>
                                </div>
                            </div>
                        </div>
                        </TableCell>
                        <TableCell className="py-5">
                        {log.reference_name ? (
                            <div className="flex flex-col gap-0.5">
                            <span className="text-[9px] font-bold text-muted-foreground/60 uppercase tracking-wider">{log.reference_doctype}</span>
                            <span className="font-mono text-[11px] font-semibold text-primary bg-primary/5 px-2 py-0.5 rounded w-fit">
                                #{log.reference_name.slice(-8)}
                            </span>
                            </div>
                        ) : (
                            log.payment_id ? (
                                <div className="flex flex-col gap-1">
                                    <span className="text-[9px] font-bold text-muted-foreground/60 uppercase tracking-wider">RAZORPAY ID</span>
                                    <span className="font-mono text-[11px] font-semibold text-slate-500 bg-muted/50 px-2 py-0.5 rounded w-fit">
                                        {log.payment_id}
                                    </span>
                                </div>
                            ) : <span className="text-muted-foreground text-[11px] font-medium opacity-30">NA</span>
                        )}
                        </TableCell>
                        <TableCell className={cn("text-right pr-4 py-5 font-bold text-base tabular-nums tracking-tighter", getTxnColor(log.amount))}>
                        {isCredit ? '+' : '−'}{formatAmountNoDecimals(Math.abs(log.amount))}
                        </TableCell>
                        <TableCell className="text-right pr-6 py-5">
                        <div className="h-8 w-8 rounded-full flex items-center justify-center group-hover:bg-muted/50 transition-all">
                            <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-all translate-x-[-2px] group-hover:translate-x-0" />
                        </div>
                        </TableCell>
                    </TableRow>
                    )
                })}
                </TableBody>
            </Table>

          <div className="p-6 bg-muted/5 border-t border-border/50">
            <DataPagination
              currentPage={page}
              totalCount={totalCount}
              pageSize={pageSize}
              onPageChange={setPage}
              onPageSizeChange={setPageSize}
              isLoading={isLoading}
            />
          </div>
        </CardContent>
      </Card>

      {/* Audit Transparency Note */}
      <div className="flex items-start gap-4 p-6 rounded-3xl bg-primary/5 border border-primary/10 max-w-2xl mx-auto shadow-sm">
        <div className="h-10 w-10 rounded-2xl bg-primary/10 flex items-center justify-center shrink-0">
          <Info className="h-5 w-5 text-primary" />
        </div>
        <div className="space-y-1.5">
          <p className="text-sm font-bold text-foreground">Fiscal Audit Transparency</p>
          <p className="text-[11px] text-muted-foreground leading-relaxed font-medium">
            Every transaction is recorded with a unique audit ID and balance snapshot. 
            {platformSettings.charge_gst ? `For top-ups, ${platformSettings.gst_percent}% GST is collected upfront and visible in the transaction details.` : 'Top-ups are currently GST-exempt.'} 
            Deductions for AI usage and commissions are calculated based on your current plans.
          </p>
        </div>
      </div>

      {/* Transaction Details Sheet */}
      {selectedTxn && (
        <Sheet open={!!selectedTxn} onOpenChange={(open) => !open && setSelectedTxn(null)}>
          <SheetContent className="sm:max-w-md bg-background/95 backdrop-blur-xl border-l-0 shadow-[-20px_0_50px_rgba(0,0,0,0.1)] p-0 flex flex-col">
            <div className="h-2 bg-primary w-full" />
            <div className="p-8 space-y-8 flex-1 overflow-y-auto">
                <SheetHeader className="mb-8">
                <div className="flex items-center gap-4">
                    <div className="h-12 w-12 rounded-2xl bg-primary/10 flex items-center justify-center shrink-0 shadow-inner">
                    {getTxnIcon(selectedTxn.transaction_type)}
                    </div>
                    <div>
                    <SheetTitle className="text-2xl font-bold tracking-tight">{selectedTxn.transaction_type}</SheetTitle>
                    <SheetDescription className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Audit ID: {selectedTxn.name}</SheetDescription>
                    </div>
                </div>
                </SheetHeader>

                <div className="space-y-6">
                    {/* Amount Card */}
                    <div className="p-6 rounded-3xl bg-muted/30 border border-border/50 relative overflow-hidden group hover:bg-muted/40 transition-all">
                        <ArrowRightLeft className="absolute -right-4 -bottom-4 h-24 w-24 opacity-5 text-foreground group-hover:opacity-10 transition-all" />
                        <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-4">Transaction Value</p>
                        <div className="flex flex-col gap-1">
                            <span className={cn("text-4xl font-bold tabular-nums tracking-tighter", getTxnColor(selectedTxn.amount))}>
                                {selectedTxn.amount > 0 ? '+' : '−'}{formatAmountNoDecimals(Math.abs(selectedTxn.amount))}
                            </span>
                            <div className="flex items-center gap-2 mt-1">
                                <Badge className={cn("text-[9px] font-bold uppercase tracking-wider py-0 h-5 border-none", selectedTxn.amount > 0 ? 'bg-emerald-500 text-white' : 'bg-rose-500 text-white')}>
                                    {selectedTxn.amount > 0 ? 'Credit' : 'Debit'}
                                </Badge>
                                <span className="text-[11px] text-muted-foreground font-bold tabular-nums">Balance After: {formatAmountNoDecimals(selectedTxn.balance_after)}</span>
                            </div>
                        </div>
                    </div>

                    {/* Tax & Breakdown Info (if applicable) */}
                    {(selectedTxn.gst_amount !== undefined || selectedTxn.total_paid_inr !== undefined) && (
                        <div className="grid grid-cols-2 gap-3">
                            <div className="p-4 rounded-2xl bg-background border border-border/50 shadow-sm">
                                <p className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground mb-1">GST ({platformSettings.charge_gst ? `${platformSettings.gst_percent}%` : 'Off'})</p>
                                <p className="text-lg font-bold tabular-nums text-slate-700">{formatAmountNoDecimals(selectedTxn.gst_amount || 0)}</p>
                            </div>
                            <div className="p-4 rounded-2xl bg-background border border-border/50 shadow-sm">
                                <p className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground mb-1">Total Paid</p>
                                <p className="text-lg font-bold tabular-nums text-slate-700">{formatAmountNoDecimals(selectedTxn.total_paid_inr || Math.abs(selectedTxn.amount))}</p>
                            </div>
                        </div>
                    )}

                    <div className="p-5 rounded-2xl border bg-muted/20 space-y-1">
                        <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Detailed Narrative</p>
                        <p className="text-sm font-semibold leading-relaxed text-foreground antialiased">
                        {selectedTxn.description || 'System generated automated adjustment record.'}
                        </p>
                    </div>

                    <div className="space-y-3 pt-2">
                        <div className="flex justify-between items-center py-2.5 border-b border-dashed border-border/80">
                            <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">System Status</span>
                            <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px] font-bold py-0 h-6">CONFIRMED</Badge>
                        </div>
                        <div className="flex justify-between items-center py-2.5 border-b border-dashed border-border/80">
                            <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Timestamp</span>
                            <span className="text-[11px] font-bold text-foreground tabular-nums">
                                {new Date(selectedTxn.creation).toLocaleString('en-IN', {
                                    day: '2-digit', month: 'short', year: 'numeric',
                                    hour: '2-digit', minute: '2-digit', second: '2-digit'
                                })}
                            </span>
                        </div>
                        {selectedTxn.payment_id && (
                            <div className="flex justify-between items-center py-2.5 border-b border-dashed border-border/80">
                                <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Razorpay ID</span>
                                <span className="text-[11px] font-mono font-bold text-slate-600 bg-muted px-2 py-0.5 rounded select-all cursor-copy">
                                    {selectedTxn.payment_id}
                                </span>
                            </div>
                        )}
                        {selectedTxn.reference_name && (
                            <div className="flex justify-between items-center py-3">
                                <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">External Ref</span>
                                <div className="flex flex-col items-end gap-0.5">
                                    <span className="text-[10px] font-bold text-primary bg-primary/5 px-2 py-0.5 rounded cursor-pointer hover:bg-primary/10 transition-colors uppercase">
                                        View {selectedTxn.reference_doctype}
                                    </span>
                                    <span className="text-[9px] font-mono font-bold text-muted-foreground">{selectedTxn.reference_name}</span>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                <div className="pt-8">
                    <Button 
                        variant="outline" 
                        className="w-full text-xs font-bold uppercase tracking-widest h-12 rounded-xl border-2 hover:bg-muted/50" 
                        onClick={() => setSelectedTxn(null)}
                    >
                        Dismiss Audit Details
                    </Button>
                </div>
            </div>
            <div className="p-8 pt-0 mt-auto">
                <div className="p-4 rounded-2xl bg-amber-50 border border-amber-100 flex items-start gap-3">
                    <ShieldAlert className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
                    <p className="text-[10px] text-amber-700 font-bold leading-tight">
                        Disputing this transaction? Please contact Flamezo support with the Audit ID provided at the top.
                    </p>
                </div>
            </div>
          </SheetContent>
        </Sheet>
      )}

      {selectedRestaurant && (
        <AiRechargeModal
          open={showRecharge}
          onClose={() => setShowRecharge(false)}
          restaurant={selectedRestaurant}
          onSuccess={() => {
            mutate()
            setBalance(0) // Will refresh via useEffect
          }}
        />
      )}
    </div>
  )
}
