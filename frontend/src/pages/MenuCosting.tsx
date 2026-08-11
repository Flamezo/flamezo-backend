import { useState, useMemo, useEffect } from 'react'
import { useFrappeGetCall, useFrappePostCall } from '@/lib/frappe'
import { useOutlet } from '@/contexts/OutletContext'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NumberInput } from '@/components/ui/number-input'
import { Skeleton } from '@/components/ui/skeleton'
import { useConfirm } from '@/hooks/useConfirm'
import {
  Search, Save, Calculator, TrendingUp, PieChart, IndianRupee, Percent,
  AlertTriangle, ChevronRight, LayoutGrid, Trash2
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

// ── types ────────────────────────────────────────────────────────────────
interface CostingProduct {
  docname: string
  name: string
  category: string
  price: number
  food_cost: number
  is_active: number
  is_vegetarian: number
  hasCost: boolean
  margin: number
  marginPct: number
  foodCostPct: number
}
interface Summary {
  totalItems: number
  itemsWithCost: number
  itemsWithoutCost: number
  coveragePct: number
  avgFoodCostPct: number
  avgMarginPct: number
  migrationPending?: boolean
}

// ── helpers ──────────────────────────────────────────────────────────────
const rupee = (n: number) => `₹${Math.round(n).toLocaleString('en-IN')}`

function costTone(foodCostPct: number, hasCost: boolean) {
  if (!hasCost) return { text: 'text-muted-foreground', bg: 'bg-muted', ring: 'border-dashed border-muted-foreground/30' }
  if (foodCostPct <= 30) return { text: 'text-green-600 dark:text-green-400', bg: 'bg-green-50 dark:bg-green-950/30', ring: 'border-green-200 dark:border-green-900/50' }
  if (foodCostPct <= 40) return { text: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-950/30', ring: 'border-amber-200 dark:border-amber-900/50' }
  return { text: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-950/30', ring: 'border-red-200 dark:border-red-900/50' }
}

export default function MenuCosting() {
  const { selectedOutlet } = useOutlet()

  const { data, isLoading, mutate } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.costing.get_menu_costing',
    { outlet_id: selectedOutlet },
    selectedOutlet ? `menu-costing-${selectedOutlet}` : null,
  )

  const products: CostingProduct[] = data?.message?.data?.products || []
  const categories: { name: string; category_name: string; display_name?: string; parent_category?: string }[] =
    data?.message?.data?.categories || []
  const summary: Summary | undefined = data?.message?.data?.summary

  const { call: bulkSet } = useFrappePostCall('flamezo_backend.flamezo.api.costing.bulk_set_costs')
  const { call: applyCategoryPct } = useFrappePostCall('flamezo_backend.flamezo.api.costing.apply_category_cost_pct')
  const { call: applyGlobalPct } = useFrappePostCall('flamezo_backend.flamezo.api.costing.apply_global_cost_pct')

  const { confirm, ConfirmDialogComponent } = useConfirm()

  // ── layout state ──
  const [sidebarWidth, setSidebarWidth] = useState(320)
  const [isResizing, setIsResizing] = useState(false)

  // ── costing state ──
  const [search, setSearch] = useState('')
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null)
  const [inputMode, setInputMode] = useState<'rupee' | 'percent'>('rupee')
  const [dirty, setDirty] = useState<Record<string, number>>({})
  const [saving, setSaving] = useState(false)
  const [globalPct, setGlobalPct] = useState('')
  const [expandedParents, setExpandedParents] = useState<Set<string>>(new Set())

  useEffect(() => { setDirty({}) }, [selectedOutlet])

  // Resize handler
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return
      const newWidth = e.clientX - 260
      if (newWidth > 200 && newWidth < 600) setSidebarWidth(newWidth)
    }
    const handleMouseUp = () => setIsResizing(false)
    if (isResizing) {
      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', handleMouseUp)
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isResizing])

  // Category mapping
  const parentCategories = useMemo(() =>
    categories.filter(c => !c.parent_category),
    [categories]
  )
  const subcategoryMap = useMemo(() => {
    const map: Record<string, any[]> = {}
    categories.forEach(c => {
      if (c.parent_category) {
        if (!map[c.parent_category]) map[c.parent_category] = []
        map[c.parent_category].push(c)
      }
    })
    return map
  }, [categories])

  const filteredParentCategories = parentCategories?.filter((c: any) => {
    if (!search) return true
    const q = search.toLowerCase()
    const matchesSelf = (c.display_name || c.category_name || c.name).toLowerCase().includes(q)
    const matchesSub = (subcategoryMap[c.name] || []).some((s: any) =>
      (s.display_name || s.category_name || s.name).toLowerCase().includes(q)
    )
    return matchesSelf || matchesSub
  })

  const activeCategory = useMemo(() =>
    categories.find(c => c.category_name === selectedCategoryId),
    [categories, selectedCategoryId]
  )

  const isSubcategorySelected = useMemo(() =>
    selectedCategoryId ? !!categories.find(c => c.category_name === selectedCategoryId && c.parent_category) : false,
    [selectedCategoryId, categories]
  )

  const filteredProducts = useMemo(() => {
    let list = products
    if (selectedCategoryId) {
      list = list.filter(p => p.category === selectedCategoryId)
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(p => p.name.toLowerCase().includes(q) || (p.category || '').toLowerCase().includes(q))
    }
    return list
  }, [products, selectedCategoryId, search])

  const dirtyCount = Object.keys(dirty).length

  const liveFoodCost = (p: CostingProduct) => (p.docname in dirty ? dirty[p.docname] : p.food_cost)
  const liveMetrics = (p: CostingProduct) => {
    const fc = liveFoodCost(p)
    const has = fc > 0
    const margin = has ? p.price - fc : 0
    const marginPct = has && p.price > 0 ? (margin / p.price) * 100 : 0
    const foodCostPct = has && p.price > 0 ? (fc / p.price) * 100 : 0
    return { fc, has, margin, marginPct, foodCostPct }
  }

  const onEdit = (p: CostingProduct, raw: string) => {
    const v = parseFloat(raw)
    let food_cost = isNaN(v) ? 0 : v
    if (inputMode === 'percent') food_cost = p.price > 0 ? +(p.price * food_cost / 100).toFixed(2) : 0
    setDirty(prev => ({ ...prev, [p.docname]: food_cost }))
  }

  const inputValue = (p: CostingProduct) => {
    const fc = liveFoodCost(p)
    if (!fc) return ''
    return inputMode === 'percent'
      ? (p.price > 0 ? Math.round((fc / p.price) * 100).toString() : '')
      : Math.round(fc).toString()
  }

  const saveAll = async () => {
    if (!dirtyCount) return
    setSaving(true)
    try {
      const items = Object.entries(dirty).map(([docname, food_cost]) => ({ docname, food_cost }))
      const res = await bulkSet({ outlet_id: selectedOutlet, items: JSON.stringify(items) })
      if (res?.message?.success) {
        toast.success(`Saved cost for ${res.message.data.updated} item${res.message.data.updated === 1 ? '' : 's'}`)
        setDirty({})
        mutate()
      } else {
        toast.error(res?.message?.error?.message || 'Failed to save')
      }
    } catch { toast.error('Failed to save costs') } finally { setSaving(false) }
  }

  const applyToCategory = async (category: string, pct: number) => {
    try {
      const res = await applyCategoryPct({ outlet_id: selectedOutlet, category, pct })
      if (res?.message?.success) {
        toast.success(`Set ${pct}% item cost on ${res.message.data.updated} items in ${category}`)
        setDirty({}); mutate()
      } else toast.error(res?.message?.error?.message || 'Failed to apply')
    } catch { toast.error('Failed to apply') }
  }

  const confirmRemoveAll = async () => {
    const confirmed = await confirm({
      title: 'Reset All Item Costs',
      description: 'Are you sure you want to remove item costs from all items? This will reset your margins and break the Offer Simulator until you set them again. This action cannot be undone.',
      variant: 'destructive'
    })
    if (!confirmed) return
    try {
      const res = await applyGlobalPct({ outlet_id: selectedOutlet, pct: 0 })
      if (res?.message?.success) {
        toast.success(`Removed item costs from all ${res.message.data.updated} items`)
        setDirty({}); mutate()
      } else toast.error(res?.message?.error?.message || 'Failed to remove costs')
    } catch { toast.error('Failed to remove costs') }
  }

  const applyToAll = async () => {
    const pct = parseFloat(globalPct)
    if (isNaN(pct) || pct <= 0 || pct >= 100) { toast.error('Enter a % between 1 and 99'); return }
    try {
      const res = await applyGlobalPct({ outlet_id: selectedOutlet, pct })
      if (res?.message?.success) {
        toast.success(`Set ${pct}% item cost across ${res.message.data.updated} items`)
        setGlobalPct(''); setDirty({}); mutate()
      } else toast.error(res?.message?.error?.message || 'Failed to apply')
    } catch { toast.error('Failed to apply') }
  }

  const toggleParentExpand = (parentName: string) => {
    setExpandedParents(prev => {
      const next = new Set(prev)
      if (next.has(parentName)) next.delete(parentName)
      else next.add(parentName)
      return next
    })
  }

  return (
    <div className="flex flex-col h-[calc(100vh-100px)] -m-4 sm:-m-6 overflow-hidden">
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden bg-muted/30 dark:bg-background">
        {/* Resizable Sidebar */}
        <div
          className="flex flex-col bg-card border-b md:border-b-0 md:border-r relative w-full md:w-[var(--menu-sw)] shrink-0 max-h-[45vh] md:max-h-none"
          style={{ ['--menu-sw' as any]: `${sidebarWidth}px` }}
        >
          <div className="p-4 border-b space-y-4 bg-muted/20">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search category and product"
                className="pl-9 bg-background shadow-sm"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
            {isLoading ? (
              Array(6).fill(0).map((_, i) => <Skeleton key={i} className="h-12 w-full rounded-lg" />)
            ) : (
              <>
                <div
                  className={cn(
                    "group flex items-center gap-2 p-3 cursor-pointer rounded-lg transition-all border border-transparent",
                    !selectedCategoryId && !search
                      ? "bg-accent text-accent-foreground shadow-md border-accent"
                      : "hover:bg-muted text-muted-foreground hover:text-foreground"
                  )}
                  onClick={() => { setSelectedCategoryId(null); setSearch('') }}
                >
                  <LayoutGrid className={cn("h-4 w-4 shrink-0 opacity-80", !selectedCategoryId && "opacity-100")} />
                  <p className={cn("text-sm font-medium truncate flex-1", !selectedCategoryId && !search ? "text-accent-foreground" : "text-foreground")}>All Items</p>
                </div>

                {!search && filteredParentCategories?.map((category: any) => {
                  const subs = subcategoryMap[category.name] || []
                  const isParentExpanded = expandedParents.has(category.name) || subs.length === 0
                  const isActive = selectedCategoryId === category.category_name

                  return (
                    <div key={category.name}>
                      <div
                        className={cn(
                          "group flex items-center gap-2 p-3 cursor-pointer rounded-lg transition-all border border-transparent",
                          isActive
                            ? "bg-accent text-accent-foreground shadow-md border-accent"
                            : "hover:bg-muted text-muted-foreground hover:text-foreground"
                        )}
                        onClick={() => setSelectedCategoryId(category.category_name)}
                      >
                        {subs.length > 0 && (
                          <button
                            onClick={(e) => { e.stopPropagation(); toggleParentExpand(category.name) }}
                            className="p-0.5 rounded hover:bg-background/30 transition-colors"
                          >
                            <ChevronRight className={cn("h-3.5 w-3.5 transition-transform duration-200", isParentExpanded && "rotate-90")} />
                          </button>
                        )}
                        {!subs.length && <div className="w-4" />}
                        <p className={cn("text-sm font-medium truncate flex-1", isActive ? "text-accent-foreground" : "text-foreground")}>
                          {category.display_name || category.category_name}
                        </p>
                      </div>

                      {subs.length > 0 && isParentExpanded && (
                        <div className="mt-0.5 space-y-0.5 ml-4 pl-3 border-l-2 border-l-primary/30">
                          {subs.map((sub: any) => {
                            const isSubActive = selectedCategoryId === sub.category_name
                            return (
                              <div
                                key={sub.name}
                                className={cn(
                                  "group flex items-center gap-2 px-2.5 py-1.5 cursor-pointer rounded-md transition-all",
                                  isSubActive
                                    ? "bg-primary/15 text-primary border border-primary/30"
                                    : "hover:bg-muted/60 text-muted-foreground hover:text-foreground border border-transparent"
                                )}
                                onClick={() => setSelectedCategoryId(sub.category_name)}
                              >
                                <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", isSubActive ? "bg-primary" : "bg-muted-foreground/40 group-hover:bg-muted-foreground/70")} />
                                <p className={cn("text-xs font-medium truncate flex-1", isSubActive ? "text-primary" : "text-foreground/80")}>
                                  {sub.display_name || sub.category_name}
                                </p>
                              </div>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  )
                })}
              </>
            )}
          </div>

          {/* Resize Handle — desktop only */}
          <div
            className={cn(
              "hidden md:block absolute top-0 -right-1 w-2 h-full cursor-col-resize hover:bg-primary/20 transition-colors z-20",
              isResizing && "bg-primary/40"
            )}
            onMouseDown={() => setIsResizing(true)}
          />
        </div>

        {/* Main Content */}
        <main className="flex-1 flex flex-col overflow-hidden">
          <header className="p-4 sm:p-6 bg-card border-b flex flex-col gap-4 sticky top-0 z-[5]">
            <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4">
              <div>
                <h2 className="text-xl font-bold text-foreground uppercase tracking-tight">
                  {search ? `Results for "${search}"` : (activeCategory?.display_name || activeCategory?.category_name || 'All Items')}
                </h2>
                {!search && isSubcategorySelected && (() => {
                  const parent = categories.find(c => c.name === activeCategory?.parent_category)
                  return parent ? (
                    <p className="text-xs text-muted-foreground mt-0.5">
                      <button className="hover:underline" onClick={() => setSelectedCategoryId(parent.category_name)}>
                        {parent.display_name || parent.category_name}
                      </button>
                      {' › '}
                      <span>{activeCategory?.display_name || activeCategory?.category_name}</span>
                    </p>
                  ) : null
                })()}
              </div>

              <div className="flex items-center gap-3">
                {selectedCategoryId && !search && (
                  <CategoryQuickSet
                    onApply={(pct) => applyToCategory(activeCategory?.category_name || '', pct)}
                  />
                )}
                <div className="flex items-center rounded-lg border p-0.5 bg-muted/50 shrink-0">
                  <button
                    onClick={() => setInputMode('rupee')}
                    className={cn('px-3 py-1.5 rounded-md text-xs font-bold flex items-center gap-1 transition-all', inputMode === 'rupee' ? 'bg-card shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground')}
                  >
                    <IndianRupee className="h-3.5 w-3.5" /> Set Cost
                  </button>
                  <button
                    onClick={() => setInputMode('percent')}
                    className={cn('px-3 py-1.5 rounded-md text-xs font-bold flex items-center gap-1 transition-all', inputMode === 'percent' ? 'bg-card shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground')}
                  >
                    <Percent className="h-3.5 w-3.5" /> Set Percent
                  </button>
                </div>
                {dirtyCount > 0 && (
                  <Button
                    className="bg-[#ea580c] hover:bg-[#c2410c] text-white gap-2 shadow-sm shrink-0"
                    onClick={saveAll}
                    disabled={saving}
                  >
                    <Save className={cn('h-4 w-4', saving && 'animate-spin')} />
                    {saving ? 'Saving…' : `Save ${dirtyCount}`}
                  </Button>
                )}
              </div>
            </div>

            {/* Summary metrics — All Items only */}
            {!selectedCategoryId && !search && (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 animate-in fade-in slide-in-from-top-2 duration-300">
                <SummaryCard icon={<PieChart className="h-4 w-4" />} label="Items costed" value={summary ? `${summary.itemsWithCost}/${summary.totalItems}` : '—'} sub={summary ? `${summary.coveragePct}% coverage` : ''} loading={isLoading} />
                <SummaryCard icon={<IndianRupee className="h-4 w-4" />} label="Avg item cost" value={summary ? `${summary.avgFoodCostPct}%` : '—'} sub="of selling price" loading={isLoading} tone={summary && summary.avgFoodCostPct > 40 ? 'red' : summary && summary.avgFoodCostPct > 30 ? 'amber' : 'green'} />
                <SummaryCard icon={<TrendingUp className="h-4 w-4" />} label="Avg margin" value={summary ? `${summary.avgMarginPct}%` : '—'} sub="gross, before overheads" loading={isLoading} tone={summary && summary.avgMarginPct < 50 ? 'red' : summary && summary.avgMarginPct < 60 ? 'amber' : 'green'} />
                <SummaryCard icon={<AlertTriangle className="h-4 w-4" />} label="Missing cost" value={summary ? `${summary.itemsWithoutCost}` : '—'} sub="items need a cost" loading={isLoading} tone={summary && summary.itemsWithoutCost > 0 ? 'amber' : 'green'} />
              </div>
            )}

            {/* Global Setup — All Items only */}
            {!selectedCategoryId && !search && (
              <div className="rounded-xl border border-orange-200 dark:border-orange-900/50 overflow-hidden">
                {/* Header strip */}
                <div className="flex items-center gap-2 px-4 py-2 bg-orange-100/70 dark:bg-orange-900/25 border-b border-orange-200/80 dark:border-orange-900/40">
                  <span className="text-[11px] font-black uppercase tracking-widest text-orange-700 dark:text-orange-400">Global Setup</span>
                  <span className="hidden sm:block text-[11px] text-orange-500/80 dark:text-orange-500/60">— set one item cost % across every item instantly</span>
                </div>
                {/* Controls row */}
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 px-4 py-3 bg-orange-50/60 dark:bg-orange-950/10">
                  {/* Input + apply */}
                  <div className="flex items-center gap-2 flex-1">
                    <div className="relative">
                      <NumberInput
                        allowNegative={false}
                        min={0}
                        value={globalPct}
                        onChange={e => setGlobalPct(e.target.value)}
                        placeholder="e.g. 30"
                        className="h-9 text-sm w-28 pr-7"
                      />
                      <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-xs font-semibold text-muted-foreground">%</span>
                    </div>
                    <Button
                      size="sm"
                      className="bg-[#ea580c] hover:bg-[#c2410c] text-white h-9 gap-1.5 text-xs font-semibold shrink-0"
                      onClick={applyToAll}
                    >
                      Apply to All Items
                    </Button>
                  </div>
                  {/* Divider */}
                  <div className="hidden sm:block w-px h-7 bg-orange-200 dark:bg-orange-900/60 shrink-0" />
                  {/* Reset */}
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-9 shrink-0 text-xs font-semibold text-red-600 hover:text-red-700 hover:bg-red-100 dark:text-red-400 dark:hover:bg-red-950/40 gap-1.5"
                    onClick={confirmRemoveAll}
                  >
                    <Trash2 className="h-3.5 w-3.5" /> Reset All Costs
                  </Button>
                </div>
              </div>
            )}
          </header>

          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 custom-scrollbar pb-32">
            {summary?.migrationPending && (
              <div className="mb-6 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 rounded-xl p-4 flex items-start gap-3 text-sm text-amber-700 dark:text-amber-400">
                <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold">Finishing setup</p>
                  <p>Your items are listed below, but saving costs needs one last step on the server. Please run <code className="font-mono text-xs bg-amber-100 dark:bg-amber-900/40 px-1 rounded">bench migrate</code>.</p>
                </div>
              </div>
            )}

            {isLoading ? (
              <div className="space-y-3">{Array(6).fill(0).map((_, i) => <Skeleton key={i} className="h-16 w-full rounded-xl" />)}</div>
            ) : filteredProducts.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-10">
                <Calculator className="h-10 w-10 text-muted-foreground/40 mb-3" />
                <p className="text-muted-foreground italic">No items found.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3">
                {filteredProducts.map(p => {
                  const m = liveMetrics(p)
                  const tone = costTone(m.foodCostPct, m.has)
                  return (
                    <div
                      key={p.docname}
                      className={cn(
                        'flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 bg-card border rounded-xl p-3 sm:px-4 transition-all hover:border-muted-foreground/30 hover:shadow-sm',
                        p.docname in dirty && 'ring-1 ring-[#ea580c]/50 bg-orange-50/10 dark:bg-orange-950/10'
                      )}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="font-bold text-sm text-foreground truncate">{p.name}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-xs font-medium text-muted-foreground">Price: {rupee(p.price)}</span>
                          {!p.is_active && <span className="text-[9px] bg-muted text-muted-foreground px-1.5 py-0.5 rounded font-bold uppercase tracking-wider">Inactive</span>}
                        </div>
                      </div>
                      <div className="flex items-center justify-between sm:justify-end gap-4">
                        <div className="relative w-28 shrink-0">
                          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground font-medium">{inputMode === 'rupee' ? '₹' : ''}</span>
                          <NumberInput
                            allowNegative={false} min={0} inputMode="decimal"
                            value={inputValue(p)}
                            onChange={e => onEdit(p, e.target.value)}
                            placeholder={inputMode === 'rupee' ? 'cost' : '%'}
                            className={cn('text-right tabular-nums h-9 border-muted-foreground/30 focus-visible:ring-[#ea580c]/50 font-medium bg-background', inputMode === 'rupee' ? 'pl-6 pr-3' : 'pr-6')}
                          />
                          {inputMode === 'percent' && <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground font-medium">%</span>}
                        </div>
                        <div className={cn('shrink-0 w-28 text-center rounded-lg border px-2 py-1.5', tone.bg, tone.ring)}>
                          {m.has ? (
                            <>
                              <p className={cn('text-sm font-black tabular-nums tracking-tight', tone.text)}>{m.marginPct.toFixed(0)}% Margin</p>
                              <p className="text-[10px] text-muted-foreground tabular-nums font-medium mt-0.5">{rupee(m.margin)} profit</p>
                            </>
                          ) : (
                            <p className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground mt-1">Set Cost</p>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </main>
      </div>

      {ConfirmDialogComponent}

      <style>{`
        .custom-scrollbar::-webkit-scrollbar { width: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #e2e8f0; border-radius: 10px; }
        .dark .custom-scrollbar::-webkit-scrollbar-thumb { background: #334155; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #cbd5e1; }
        .dark .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #475569; }
      `}</style>
    </div>
  )
}

// ── sub-components ──────────────────────────────────────────────────────────
function SummaryCard({ icon, label, value, sub, loading, tone }: {
  icon: React.ReactNode; label: string; value: string; sub?: string; loading?: boolean
  tone?: 'green' | 'amber' | 'red'
}) {
  const toneText = tone === 'red' ? 'text-red-600 dark:text-red-400'
    : tone === 'amber' ? 'text-amber-600 dark:text-amber-400'
    : tone === 'green' ? 'text-green-600 dark:text-green-400' : 'text-foreground'
  return (
    <div className="bg-card border rounded-xl p-3 sm:p-4 hover:shadow-sm transition-shadow">
      <div className="flex items-center gap-1.5 text-muted-foreground text-[10px] font-bold uppercase tracking-wider">{icon}{label}</div>
      {loading ? <Skeleton className="h-7 w-16 mt-2" /> : <p className={cn('text-2xl font-black mt-1 tabular-nums', toneText)}>{value}</p>}
      {sub && <p className="text-[11px] text-muted-foreground mt-0.5 truncate">{sub}</p>}
    </div>
  )
}

function CategoryQuickSet({ onApply }: { onApply: (pct: number) => void }) {
  const [val, setVal] = useState('')
  return (
    <div className="flex items-center gap-2 bg-muted/50 p-1 rounded-lg border border-border/50">
      <span className="hidden xl:inline text-[10px] uppercase font-bold tracking-widest text-muted-foreground ml-2">Quick Set</span>
      <div className="relative w-14">
        <NumberInput allowNegative={false} min={0} value={val} onChange={e => setVal(e.target.value)} placeholder="%" className="h-7 text-xs pr-4 text-right bg-background border-muted-foreground/30" />
      </div>
      <Button size="sm" variant="outline" className="h-7 text-xs px-2.5 bg-background"
        onClick={() => { const p = parseFloat(val); if (!isNaN(p) && p > 0 && p < 100) { onApply(p); setVal('') } }}>
        Apply to Category
      </Button>
    </div>
  )
}
