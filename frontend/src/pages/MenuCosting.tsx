import { useState, useMemo, useEffect } from 'react'
import { useFrappeGetCall, useFrappePostCall } from '@/lib/frappe'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Search, Save, Calculator, TrendingUp, PieChart, IndianRupee, Percent,
  Sparkles, AlertTriangle, CheckCircle2, XCircle, Info,
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

/** Healthiness color by food-cost %. Lower cost % = healthier margin. */
function costTone(foodCostPct: number, hasCost: boolean) {
  if (!hasCost) return { text: 'text-muted-foreground', bg: 'bg-muted', ring: 'border-dashed border-muted-foreground/30' }
  if (foodCostPct <= 30) return { text: 'text-green-600 dark:text-green-400', bg: 'bg-green-50 dark:bg-green-950/30', ring: 'border-green-200 dark:border-green-900/50' }
  if (foodCostPct <= 40) return { text: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-950/30', ring: 'border-amber-200 dark:border-amber-900/50' }
  return { text: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-950/30', ring: 'border-red-200 dark:border-red-900/50' }
}

export default function MenuCosting() {
  const { selectedRestaurant } = useRestaurant()

  const { data, isLoading, mutate } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.costing.get_menu_costing',
    { restaurant_id: selectedRestaurant },
    selectedRestaurant ? `menu-costing-${selectedRestaurant}` : null,
  )

  const products: CostingProduct[] = data?.message?.data?.products || []
  const categories: { name: string; category_name: string; display_name?: string }[] =
    data?.message?.data?.categories || []
  const summary: Summary | undefined = data?.message?.data?.summary

  const { call: bulkSet } = useFrappePostCall('flamezo_backend.flamezo.api.costing.bulk_set_costs')
  const { call: applyCategoryPct } = useFrappePostCall('flamezo_backend.flamezo.api.costing.apply_category_cost_pct')
  const { call: applyGlobalPct } = useFrappePostCall('flamezo_backend.flamezo.api.costing.apply_global_cost_pct')

  // ── set-costs tab state ──
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [inputMode, setInputMode] = useState<'rupee' | 'percent'>('rupee')
  const [dirty, setDirty] = useState<Record<string, number>>({}) // docname -> new food_cost (₹)
  const [saving, setSaving] = useState(false)
  const [globalPct, setGlobalPct] = useState('')

  useEffect(() => { setDirty({}) }, [selectedRestaurant])

  const filtered = useMemo(() => {
    let list = products
    if (categoryFilter !== 'all') list = list.filter(p => p.category === categoryFilter)
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(p => p.name.toLowerCase().includes(q) || (p.category || '').toLowerCase().includes(q))
    }
    return list
  }, [products, categoryFilter, search])

  // group filtered products by category for display
  const grouped = useMemo(() => {
    const map: Record<string, CostingProduct[]> = {}
    filtered.forEach(p => {
      const key = p.category || 'Uncategorised'
      ;(map[key] = map[key] || []).push(p)
    })
    return Object.entries(map)
  }, [filtered])

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
      const res = await bulkSet({ restaurant_id: selectedRestaurant, items: JSON.stringify(items) })
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
      const res = await applyCategoryPct({ restaurant_id: selectedRestaurant, category, pct })
      if (res?.message?.success) {
        toast.success(`Set ${pct}% food cost on ${res.message.data.updated} items in ${category}`)
        setDirty({}); mutate()
      } else toast.error(res?.message?.error?.message || 'Failed to apply')
    } catch { toast.error('Failed to apply') }
  }

  const applyToAll = async () => {
    const pct = parseFloat(globalPct)
    if (isNaN(pct) || pct <= 0 || pct >= 100) { toast.error('Enter a % between 1 and 99'); return }
    try {
      const res = await applyGlobalPct({ restaurant_id: selectedRestaurant, pct })
      if (res?.message?.success) {
        toast.success(`Set ${pct}% food cost across ${res.message.data.updated} items`)
        setGlobalPct(''); setDirty({}); mutate()
      } else toast.error(res?.message?.error?.message || 'Failed to apply')
    } catch { toast.error('Failed to apply') }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-100px)] -m-4 sm:-m-6 overflow-hidden">


      <Tabs defaultValue="costs" className="flex-1 flex flex-col overflow-hidden">
        <div className="bg-card border-b px-4 sm:px-6">
          <TabsList className="bg-transparent h-12 p-0 gap-6">
            <TabsTrigger value="costs" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-[#ea580c] data-[state=active]:text-[#ea580c] rounded-none h-12 px-0 font-bold uppercase text-xs tracking-wider">
              <Calculator className="h-4 w-4 mr-2" /> Set Costs
            </TabsTrigger>
            <TabsTrigger value="simulator" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-[#ea580c] data-[state=active]:text-[#ea580c] rounded-none h-12 px-0 font-bold uppercase text-xs tracking-wider">
              <Sparkles className="h-4 w-4 mr-2" /> Offer Simulator
            </TabsTrigger>
          </TabsList>
        </div>

        {/* ───────────────────────── SET COSTS ───────────────────────── */}
        <TabsContent value="costs" className="flex-1 overflow-y-auto custom-scrollbar p-4 sm:p-6 space-y-6 mt-0">
          {summary?.migrationPending && (
            <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 rounded-xl p-4 flex items-start gap-3 text-sm text-amber-700 dark:text-amber-400">
              <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Finishing setup</p>
                <p>Your items are listed below, but saving costs needs one last step on the server (<code className="font-mono text-xs bg-amber-100 dark:bg-amber-900/40 px-1 rounded">bench migrate</code>). Once done, costs you enter here will save.</p>
              </div>
            </div>
          )}
          {/* Summary cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <SummaryCard icon={<PieChart className="h-4 w-4" />} label="Items costed"
              value={summary ? `${summary.itemsWithCost}/${summary.totalItems}` : '—'}
              sub={summary ? `${summary.coveragePct}% coverage` : ''} loading={isLoading} />
            <SummaryCard icon={<IndianRupee className="h-4 w-4" />} label="Avg food cost"
              value={summary ? `${summary.avgFoodCostPct}%` : '—'} sub="of selling price" loading={isLoading}
              tone={summary && summary.avgFoodCostPct > 40 ? 'red' : summary && summary.avgFoodCostPct > 30 ? 'amber' : 'green'} />
            <SummaryCard icon={<TrendingUp className="h-4 w-4" />} label="Avg margin"
              value={summary ? `${summary.avgMarginPct}%` : '—'} sub="gross, before overheads" loading={isLoading}
              tone={summary && summary.avgMarginPct < 50 ? 'red' : summary && summary.avgMarginPct < 60 ? 'amber' : 'green'} />
            <SummaryCard icon={<AlertTriangle className="h-4 w-4" />} label="Missing cost"
              value={summary ? `${summary.itemsWithoutCost}` : '—'} sub="items need a cost" loading={isLoading}
              tone={summary && summary.itemsWithoutCost > 0 ? 'amber' : 'green'} />
          </div>

          {/* Quick tools */}
          <div className="bg-card border rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-2 text-sm font-bold text-foreground">
              <Sparkles className="h-4 w-4 text-[#ea580c]" /> Quick set-up for big menus
            </div>
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="flex items-center gap-2 flex-1">
                <span className="text-xs text-muted-foreground whitespace-nowrap">Set whole menu to</span>
                <div className="relative w-24">
                  <Input value={globalPct} onChange={e => setGlobalPct(e.target.value)} type="number"
                    placeholder="30" className="pr-7" />
                  <Percent className="absolute right-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                </div>
                <span className="text-xs text-muted-foreground whitespace-nowrap">food cost</span>
                <Button size="sm" className="bg-[#ea580c] hover:bg-[#c2410c]" onClick={applyToAll}>Apply to all</Button>
              </div>
              <p className="text-[11px] text-muted-foreground flex items-center gap-1.5 sm:max-w-xs">
                <Info className="h-3.5 w-3.5 shrink-0" />
                A fast baseline. Beverages are usually ~18%, food ~30–35%. Fine-tune per item below.
              </p>
            </div>
          </div>

          {/* Filters + input mode */}
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input placeholder="Search items…" className="pl-9" value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            <Select value={categoryFilter} onValueChange={setCategoryFilter}>
              <SelectTrigger className="w-full sm:w-52"><SelectValue placeholder="All categories" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {categories.map(c => (
                  <SelectItem key={c.name} value={c.category_name}>{c.display_name || c.category_name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex items-center rounded-lg border p-0.5 bg-muted/50">
              <button onClick={() => setInputMode('rupee')}
                className={cn('px-3 py-1.5 rounded-md text-xs font-bold flex items-center gap-1', inputMode === 'rupee' ? 'bg-card shadow-sm text-foreground' : 'text-muted-foreground')}>
                <IndianRupee className="h-3.5 w-3.5" /> ₹
              </button>
              <button onClick={() => setInputMode('percent')}
                className={cn('px-3 py-1.5 rounded-md text-xs font-bold flex items-center gap-1', inputMode === 'percent' ? 'bg-card shadow-sm text-foreground' : 'text-muted-foreground')}>
                <Percent className="h-3.5 w-3.5" /> %
              </button>
            </div>
          </div>

          {/* Product list grouped by category */}
          {isLoading ? (
            <div className="space-y-3">{Array(6).fill(0).map((_, i) => <Skeleton key={i} className="h-16 w-full rounded-xl" />)}</div>
          ) : grouped.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground italic">No items found.</div>
          ) : (
            <div className="space-y-6 pb-24">
              {grouped.map(([cat, items]) => (
                <div key={cat} className="space-y-2">
                  <div className="flex items-center justify-between sticky top-0 bg-background/95 backdrop-blur py-1 z-[2]">
                    <h3 className="text-sm font-black uppercase tracking-wider text-foreground">{cat}
                      <span className="ml-2 text-xs font-normal text-muted-foreground">{items.length} items</span>
                    </h3>
                    <CategoryQuickSet onApply={(pct) => applyToCategory(cat, pct)} />
                  </div>
                  <div className="space-y-2">
                    {items.map(p => {
                      const m = liveMetrics(p)
                      const tone = costTone(m.foodCostPct, m.has)
                      return (
                        <div key={p.docname} className={cn('flex items-center gap-3 sm:gap-4 bg-card border rounded-xl p-3', p.docname in dirty && 'ring-1 ring-[#ea580c]/40')}>
                          <div className="flex-1 min-w-0">
                            <p className="font-semibold text-sm text-foreground truncate">{p.name}</p>
                            <p className="text-xs text-muted-foreground">Sells at {rupee(p.price)}{p.is_active ? '' : ' · inactive'}</p>
                          </div>
                          <div className="relative w-24 sm:w-28 shrink-0">
                            <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">{inputMode === 'rupee' ? '₹' : ''}</span>
                            <Input type="number" inputMode="decimal" value={inputValue(p)} onChange={e => onEdit(p, e.target.value)}
                              placeholder={inputMode === 'rupee' ? 'cost' : '%'}
                              className={cn('text-right tabular-nums', inputMode === 'rupee' ? 'pl-6 pr-2' : 'pr-6')} />
                            {inputMode === 'percent' && <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">%</span>}
                          </div>
                          <div className={cn('shrink-0 w-24 sm:w-28 text-center rounded-lg border px-2 py-1.5', tone.bg, tone.ring)}>
                            {m.has ? (
                              <>
                                <p className={cn('text-sm font-bold tabular-nums', tone.text)}>{m.marginPct.toFixed(0)}% margin</p>
                                <p className="text-[10px] text-muted-foreground tabular-nums">{rupee(m.margin)} · {m.foodCostPct.toFixed(0)}% cost</p>
                              </>
                            ) : <p className="text-xs text-muted-foreground">set cost</p>}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        {/* ───────────────────────── SIMULATOR ───────────────────────── */}
        <TabsContent value="simulator" className="flex-1 overflow-y-auto custom-scrollbar p-4 sm:p-6 mt-0">
          <OfferSimulator products={products.filter(p => p.hasCost)} avgFoodCostPct={summary?.avgFoodCostPct || 30} />
        </TabsContent>
      </Tabs>

      {/* Sticky save bar */}
      {dirtyCount > 0 && (
        <div className="absolute bottom-0 inset-x-0 bg-card border-t shadow-2xl p-3 flex items-center justify-between gap-3 animate-in slide-in-from-bottom-2 z-20">
          <div className="flex items-center gap-2 text-sm">
            <span className="h-6 w-6 bg-[#ea580c] text-white rounded-full flex items-center justify-center text-[11px] font-bold">{dirtyCount}</span>
            <span className="font-semibold text-foreground">unsaved cost{dirtyCount === 1 ? '' : 's'}</span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setDirty({})}>Discard</Button>
            <Button size="sm" className="bg-[#ea580c] hover:bg-[#c2410c] gap-2" onClick={saveAll} disabled={saving}>
              <Save className="h-4 w-4" /> {saving ? 'Saving…' : 'Save all'}
            </Button>
          </div>
        </div>
      )}

      <style>{`
        .custom-scrollbar::-webkit-scrollbar { width: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #e2e8f0; border-radius: 10px; }
        .dark .custom-scrollbar::-webkit-scrollbar-thumb { background: #334155; }
      `}</style>
    </div>
  )
}

// ── sub-components ─────────────────────────────────────────────────────────
function SummaryCard({ icon, label, value, sub, loading, tone }: {
  icon: React.ReactNode; label: string; value: string; sub?: string; loading?: boolean
  tone?: 'green' | 'amber' | 'red'
}) {
  const toneText = tone === 'red' ? 'text-red-600 dark:text-red-400'
    : tone === 'amber' ? 'text-amber-600 dark:text-amber-400'
    : tone === 'green' ? 'text-green-600 dark:text-green-400' : 'text-foreground'
  return (
    <div className="bg-card border rounded-xl p-3 sm:p-4">
      <div className="flex items-center gap-1.5 text-muted-foreground text-[10px] font-bold uppercase tracking-wider">{icon}{label}</div>
      {loading ? <Skeleton className="h-7 w-16 mt-2" /> : <p className={cn('text-2xl font-black mt-1 tabular-nums', toneText)}>{value}</p>}
      {sub && <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  )
}

function CategoryQuickSet({ onApply }: { onApply: (pct: number) => void }) {
  const [val, setVal] = useState('')
  return (
    <div className="flex items-center gap-1.5">
      <div className="relative w-16">
        <Input value={val} onChange={e => setVal(e.target.value)} type="number" placeholder="%" className="h-8 text-xs pr-5 text-right" />
        <Percent className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
      </div>
      <Button size="sm" variant="outline" className="h-8 text-xs"
        onClick={() => { const p = parseFloat(val); if (!isNaN(p) && p > 0 && p < 100) { onApply(p); setVal('') } }}>
        Set all
      </Button>
    </div>
  )
}

// ── offer simulator ─────────────────────────────────────────────────────────
type OfferType = 'bogo' | 'combo' | 'flat'

function OfferSimulator({ products, avgFoodCostPct }: { products: CostingProduct[]; avgFoodCostPct: number }) {
  const [type, setType] = useState<OfferType>('bogo')
  const [itemA, setItemA] = useState<string>('')
  const [itemB, setItemB] = useState<string>('')
  const [comboPrice, setComboPrice] = useState('')
  const [bill, setBill] = useState('1000')
  const [flatPct, setFlatPct] = useState('15')

  const A = products.find(p => p.docname === itemA)
  const B = products.find(p => p.docname === itemB)

  useEffect(() => { if (!itemA && products.length) setItemA(products[0].docname) }, [products, itemA])

  // ── compute ──
  let feel = 0, burn = 0, perceivedPct = 0, profit = 0, marginPct = 0, arbitrage = 0
  let revenue = 0, valid = false, note = ''

  if (type === 'bogo' && A) {
    valid = true
    revenue = A.price
    feel = A.price                 // one item free
    burn = A.food_cost             // merchant only pays COGS of the free item
    perceivedPct = 50
    profit = A.price - 2 * A.food_cost
    marginPct = revenue > 0 ? (profit / revenue) * 100 : 0
    arbitrage = burn > 0 ? feel / burn : 0
    note = `Customer pays ${rupee(A.price)} for two. The free one costs you only its ingredients (${rupee(A.food_cost)}).`
  } else if (type === 'combo' && A && B) {
    const cp = parseFloat(comboPrice)
    if (!isNaN(cp) && cp > 0) {
      valid = true
      const normal = A.price + B.price
      revenue = cp
      feel = normal - cp
      perceivedPct = normal > 0 ? (feel / normal) * 100 : 0
      const cogs = A.food_cost + B.food_cost
      profit = cp - cogs
      marginPct = cp > 0 ? (profit / cp) * 100 : 0
      burn = cogs                 // delivered cost
      arbitrage = cogs > 0 ? feel / cogs : 0
      note = `Normally ${rupee(normal)}. At ${rupee(cp)} you still make ${rupee(profit)} profit (${marginPct.toFixed(0)}% margin) if it brings an extra cover.`
    }
  } else if (type === 'flat') {
    const b = parseFloat(bill), pct = parseFloat(flatPct)
    if (!isNaN(b) && !isNaN(pct) && b > 0) {
      valid = true
      revenue = b - (b * pct / 100)
      feel = b * pct / 100
      burn = feel                 // real cash off the top line
      perceivedPct = pct
      const cogs = b * avgFoodCostPct / 100
      profit = revenue - cogs
      marginPct = b > 0 ? (profit / b) * 100 : 0
      arbitrage = 1
      note = `A flat discount is real money off profit — every ₹1 the customer saves costs you ₹1. Burns ${rupee(feel)} on a ${rupee(b)} bill.`
    }
  }

  const verdict = !valid ? null
    : marginPct >= 35 ? { tone: 'green', icon: <CheckCircle2 className="h-5 w-5" />, label: 'Profit-safe' }
    : marginPct >= 15 ? { tone: 'amber', icon: <AlertTriangle className="h-5 w-5" />, label: 'Thin margin' }
    : { tone: 'red', icon: <XCircle className="h-5 w-5" />, label: 'Eats your profit' }

  const vbg = verdict?.tone === 'green' ? 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-900/50 text-green-700 dark:text-green-400'
    : verdict?.tone === 'amber' ? 'bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400'
    : 'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-900/50 text-red-700 dark:text-red-400'

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      {products.length === 0 && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 rounded-xl p-4 flex items-center gap-3 text-sm text-amber-700 dark:text-amber-400">
          <AlertTriangle className="h-5 w-5 shrink-0" /> Set food cost on a few items first — then the simulator can show real profit.
        </div>
      )}

      {/* offer type */}
      <div className="grid grid-cols-3 gap-2">
        {([['bogo', 'Buy 1 Get 1'], ['combo', 'Combo deal'], ['flat', 'Flat % off']] as [OfferType, string][]).map(([t, label]) => (
          <button key={t} onClick={() => setType(t)}
            className={cn('rounded-xl border p-3 text-sm font-bold transition-colors', type === t ? 'border-[#ea580c] bg-[#ea580c]/5 text-[#ea580c]' : 'bg-card text-muted-foreground hover:border-muted-foreground/30')}>
            {label}
          </button>
        ))}
      </div>

      {/* inputs */}
      <div className="bg-card border rounded-xl p-4 space-y-3">
        {(type === 'bogo' || type === 'combo') && (
          <ItemSelect label={type === 'combo' ? 'First item' : 'Item'} value={itemA} onChange={setItemA} products={products} />
        )}
        {type === 'combo' && (
          <>
            <ItemSelect label="Second item" value={itemB} onChange={setItemB} products={products} />
            <LabeledInput label="Combo price (₹)" value={comboPrice} onChange={setComboPrice} placeholder="e.g. 300" />
          </>
        )}
        {type === 'flat' && (
          <div className="grid grid-cols-2 gap-3">
            <LabeledInput label="Bill amount (₹)" value={bill} onChange={setBill} />
            <LabeledInput label="Discount (%)" value={flatPct} onChange={setFlatPct} />
          </div>
        )}
      </div>

      {/* result */}
      {valid && verdict && (
        <div className="space-y-4">
          <div className={cn('rounded-xl border p-4 flex items-center justify-between', vbg)}>
            <div className="flex items-center gap-3">{verdict.icon}<span className="font-black text-lg">{verdict.label}</span></div>
            <div className="text-right"><p className="text-xs opacity-70">Your margin after offer</p><p className="text-2xl font-black tabular-nums">{marginPct.toFixed(0)}%</p></div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <ResultCard label="Customer feels they saved" value={rupee(feel)} sub={`${perceivedPct.toFixed(0)}% off`} accent="green" />
            <ResultCard label="You actually burn" value={rupee(burn)} sub={type === 'flat' ? 'real cash, off profit' : 'just ingredient cost'} accent="orange" />
            <ResultCard label="You still collect" value={rupee(revenue)} sub="revenue on this deal" />
            <ResultCard label="Profit kept" value={rupee(profit)} sub={profit < 0 ? 'LOSS — reprice it' : 'after food cost'} accent={profit < 0 ? 'red' : undefined} />
          </div>

          {type !== 'flat' && arbitrage > 1 && (
            <div className="bg-[#ea580c]/5 border border-[#ea580c]/20 rounded-xl p-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-[#ea580c] text-white flex items-center justify-center font-black">{arbitrage.toFixed(1)}×</div>
              <p className="text-sm text-foreground"><strong>{arbitrage.toFixed(1)}× perception arbitrage.</strong> The customer feels a {rupee(feel)} gift; it costs you {rupee(burn)}. That gap is free marketing a flat discount can never give you.</p>
            </div>
          )}

          <p className="text-xs text-muted-foreground flex items-start gap-2"><Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />{note}</p>
        </div>
      )}
    </div>
  )
}

function ItemSelect({ label, value, onChange, products }: { label: string; value: string; onChange: (v: string) => void; products: CostingProduct[] }) {
  return (
    <div>
      <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">{label}</label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="mt-1"><SelectValue placeholder="Choose an item" /></SelectTrigger>
        <SelectContent>
          {products.map(p => <SelectItem key={p.docname} value={p.docname}>{p.name} — {rupee(p.price)} ({p.foodCostPct.toFixed(0)}% cost)</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  )
}

function LabeledInput({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <div>
      <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">{label}</label>
      <Input type="number" value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} className="mt-1" />
    </div>
  )
}

function ResultCard({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: 'green' | 'orange' | 'red' }) {
  const t = accent === 'green' ? 'text-green-600 dark:text-green-400'
    : accent === 'orange' ? 'text-[#ea580c]'
    : accent === 'red' ? 'text-red-600 dark:text-red-400' : 'text-foreground'
  return (
    <div className="bg-card border rounded-xl p-3">
      <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={cn('text-xl font-black mt-1 tabular-nums', t)}>{value}</p>
      {sub && <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  )
}
