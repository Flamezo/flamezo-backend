/**
 * ProductAddonGroupLinker — Links & manages addon groups on a product.
 * Matches the exact UX pattern from CustomizationQuestionsTable:
 *  - Template cards (Quantity, Size, Prep, Base, Rice, Custom)
 *  - Copy from Item dialog
 *  - Inline group editing with expand/collapse
 *  - Options table with inline editing
 *
 * Creates Addon Groups via API (new system) instead of legacy customization_questions.
 */
import { useState, useMemo } from 'react'
import { useFrappeGetCall } from 'frappe-react-sdk'
import { useRestaurant } from '../contexts/RestaurantContext'
import { useCurrency } from '../hooks/useCurrency'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Badge } from './ui/badge'
import { Switch } from './ui/switch'
import { Card, CardContent, CardHeader } from './ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog'
import {
  Plus, Trash2, ChevronDown, GripVertical, Layers,
  Copy, Search, Loader2, Link2, ExternalLink, MousePointer2, Eye
} from 'lucide-react'


// ─── Types ──────────────────────────────────────────────────────────────────

interface AddonItem {
  item_id?: string
  item_name?: string
  name?: string
  label?: string
  price?: number
  is_default?: boolean | number
  is_vegetarian?: boolean | number
  isVegetarian?: boolean | number
  in_stock?: boolean | number
  inStock?: boolean | number
  display_order?: number
}

interface AddonGroupLink {
  addon_group?: string
  addon_group_name?: string
  addon_group_type?: string
  is_enabled?: boolean | number
  display_order?: number
}

interface Props {
  value?: AddonGroupLink[]
  onChange?: (links: AddonGroupLink[]) => void
  disabled?: boolean
  restaurantId?: string  // Pass explicitly from product form when context may not be ready
}


// ─── Main Component ─────────────────────────────────────────────────────────

export default function ProductAddonGroupLinker({ value = [], onChange, disabled, restaurantId: propRestaurantId }: Props) {
  const { selectedRestaurant } = useRestaurant()
  const restaurantId = propRestaurantId || selectedRestaurant
  const { formatAmountNoDecimals } = useCurrency()



  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set())
  const [isCopyDialogOpen, setIsCopyDialogOpen] = useState(false)
  const [isLinkDialogOpen, setIsLinkDialogOpen] = useState(false)
  const [copySearchQuery, setCopySearchQuery] = useState('')
  const [linkSearchQuery, setLinkSearchQuery] = useState('')
  const [previewGroupId, setPreviewGroupId] = useState<string | null>(null)

  // Fetch all products for copy dialog
  const { data: allProductsData, isLoading: productsLoading } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.products.get_products',
    { restaurant_id: restaurantId, include_inactive: 1, limit: 500 },
    isCopyDialogOpen && restaurantId ? `copy-ag-products-${restaurantId}` : null
  )

  // Fetch all addon groups (with items) — needed for expanded preview AND link dialog
  const hasLinkedGroups = (Array.isArray(value) ? value : []).length > 0
  const { data: allGroupsData, isLoading: groupsLoading } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.addon_groups.get_addon_groups',
    restaurantId ? { restaurant_id: restaurantId, include_items: 1 } : undefined,
    (isLinkDialogOpen || hasLinkedGroups) && restaurantId ? `link-ag-groups-${restaurantId}` : null
  )

  // Build a lookup of group details by ID for inline preview
  const groupDetailsMap = useMemo(() => {
    const groups = allGroupsData?.message?.data || allGroupsData?.data || []
    const map: Record<string, any> = {}
    for (const g of groups) {
      map[g.id] = g
    }
    return map
  }, [allGroupsData])

  const productsWithAddons = useMemo(() => {
    const products = allProductsData?.message?.data?.products || []
    return products.filter((p: any) =>
      (p.addonGroups && p.addonGroups.length > 0) ||
      (p.customizationQuestions && p.customizationQuestions.length > 0)
    )
  }, [allProductsData])

  const filteredCopyProducts = useMemo(() => {
    if (!copySearchQuery.trim()) return productsWithAddons
    const q = copySearchQuery.toLowerCase()
    return productsWithAddons.filter((p: any) =>
      (p.name || '').toLowerCase().includes(q) || (p.category || '').toLowerCase().includes(q)
    )
  }, [productsWithAddons, copySearchQuery])

  const currentValue = Array.isArray(value) ? value : []

  const linkedGroupNames = useMemo(() =>
    new Set(currentValue.map(l => l.addon_group)),
    [currentValue]
  )

  const availableGroups = useMemo(() => {
    const groups = allGroupsData?.message?.data || allGroupsData?.data || []
    let filtered = groups.filter((g: any) => !linkedGroupNames.has(g.id))
    if (linkSearchQuery) {
      const q = linkSearchQuery.toLowerCase()
      filtered = filtered.filter((g: any) => g.groupName?.toLowerCase().includes(q))
    }
    return filtered
  }, [allGroupsData, linkedGroupNames, linkSearchQuery])

  // ─── Helpers ────────────────────────────────────────────────────────────

  const generateId = () => `id_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`

  const toggleGroup = (index: number) => {
    const next = new Set(expandedGroups)
    if (next.has(index)) next.delete(index)
    else next.add(index)
    setExpandedGroups(next)
  }

  // ─── Link Existing Group ───────────────────────────────────────────────

  const handleLinkExisting = (group: any) => {
    // Only send fields that Frappe needs — addon_group_name/type are fetch_from (auto-populated)
    const newLink: AddonGroupLink = {
      addon_group: group.id,
      is_enabled: 1,
      display_order: currentValue.length,
      // Keep these for UI display only (not saved to DB — they're fetch_from fields)
      addon_group_name: group.groupName,
      addon_group_type: group.groupType || group.type,
    }
    emitChange([...currentValue, newLink])
    setIsLinkDialogOpen(false)
    toast.success(`Linked "${group.groupName}"`)
  }

  // ─── Copy (Link) from Product ───────────────────────────────────────────
  // Since groups are reusable, "copy" = link the same groups to this product

  const handleCopyFromProduct = (product: any) => {
    const sourceGroups = product.addonGroups || []
    if (sourceGroups.length === 0) {
      toast.error('No addon groups found on this item')
      return
    }

    let linked = 0
    const updated = [...currentValue]
    for (const g of sourceGroups) {
      const groupId = g.id || g.groupId
      if (!groupId) continue
      // Skip if already linked
      if (updated.some(l => l.addon_group === groupId)) continue

      updated.push({
        addon_group: groupId,
        addon_group_name: g.groupName || g.name || '',
        addon_group_type: g.groupType || g.type || 'addon',
        is_enabled: 1,
        display_order: updated.length,
      })
      linked++
    }

    if (linked > 0) {
      emitChange(updated)
      toast.success(`Linked ${linked} group${linked > 1 ? 's' : ''} from "${product.name}"`)
    } else {
      toast.info('All groups from this item are already linked')
    }
    setIsCopyDialogOpen(false)
    setCopySearchQuery('')
  }

  // ─── Remove Group ──────────────────────────────────────────────────────

  // Normalize any link format to Frappe child table format before emitting onChange
  const toFrappeFormat = (raw: any): AddonGroupLink => ({
    addon_group: raw.addon_group || raw.id || '',
    addon_group_name: raw.addon_group_name || raw.groupName || raw.name || '',
    addon_group_type: raw.addon_group_type || raw.groupType || raw.type || 'addon',
    is_enabled: raw.is_enabled !== undefined ? raw.is_enabled : 1,
    display_order: raw.display_order ?? raw.displayOrder ?? 0,
  })

  const emitChange = (links: any[]) => {
    onChange?.(links.map((l, idx) => ({ ...toFrappeFormat(l), display_order: idx })))
  }

  const handleRemoveGroup = (index: number) => {
    const updated = currentValue.filter((_, i) => i !== index)
    emitChange(updated)
    expandedGroups.delete(index)
    setExpandedGroups(new Set(expandedGroups))
  }

  // ─── Toggle Enable/Disable ───────────────────────────────────────────

  const handleToggleEnabled = (index: number) => {
    const updated = [...currentValue]
    const normalized = toFrappeFormat(updated[index])
    normalized.is_enabled = normalized.is_enabled ? 0 : 1
    updated[index] = normalized
    emitChange(updated)
  }

  // ─── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header with action buttons */}
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-foreground/80 uppercase tracking-tight">Addons & Variations</h3>
            <p className="text-xs text-muted-foreground mt-1">Link reusable addon & variation groups to this product.</p>
          </div>
          {!disabled && (
            <div className="flex gap-2">
              <Button type="button" variant="outline" size="sm"
                onClick={() => setIsLinkDialogOpen(true)}
                className="shrink-0 gap-1.5 border-primary/30 text-primary hover:bg-primary/5 hover:border-primary/50"
              >
                <Link2 className="h-3.5 w-3.5" /> Link Existing
              </Button>
              <Button type="button" size="sm" asChild
                className="shrink-0 gap-1.5"
              >
                <a href="/flamezo_backend/addon-groups" target="_blank" rel="noopener">
                  <Plus className="h-3.5 w-3.5" /> Create New
                </a>
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Groups List */}
      <div className="space-y-3">
        {currentValue.length === 0 ? (
          <div className="p-10 border border-dashed rounded-xl bg-muted/10 flex flex-col items-center justify-center text-center gap-3">
            <Layers className="h-6 w-6 text-muted-foreground/30" />
            <p className="text-xs text-muted-foreground">No addon groups linked yet.</p>
            {!disabled && (
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setIsLinkDialogOpen(true)}>
                  <Link2 className="h-3.5 w-3.5 mr-1" /> Link Existing Group
                </Button>
                <Button size="sm" asChild>
                  <a href="/flamezo_backend/addon-groups" target="_blank" rel="noopener">
                    <Plus className="h-3.5 w-3.5 mr-1" /> Create in Addon Groups
                  </a>
                </Button>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {currentValue.map((rawLink, groupIndex) => {
              // Normalize: handle both Frappe child table format AND API response format
              const link = {
                addon_group: rawLink.addon_group || (rawLink as any).id || '',
                addon_group_name: rawLink.addon_group_name || (rawLink as any).groupName || (rawLink as any).name || '',
                addon_group_type: rawLink.addon_group_type || (rawLink as any).groupType || (rawLink as any).type || 'addon',
                is_enabled: rawLink.is_enabled !== undefined ? rawLink.is_enabled : 1,
                display_order: rawLink.display_order ?? (rawLink as any).displayOrder ?? groupIndex,
              }
              const isExpanded = expandedGroups.has(groupIndex)
              const gName = link.addon_group_name || link.addon_group || 'Unnamed Group'
              const gType = link.addon_group_type || 'addon'
              const isVariation = gType === 'variation'
              const enabled = !!link.is_enabled
              const groupDetail = groupDetailsMap[link.addon_group || '']
              // Also check if rawLink itself has items (API format)
              const itemCount = groupDetail?.items?.length || (rawLink as any).items?.length || 0

              return (
                <Card key={link.addon_group || groupIndex} className={cn(
                  "overflow-hidden border-border/40 transition-all duration-300 shadow-none",
                  isExpanded && "border-border shadow-md",
                  enabled ? "bg-card/20" : "bg-muted/30 opacity-60"
                )}>
                  <CardHeader className="p-3 cursor-pointer select-none" onClick={() => toggleGroup(groupIndex)}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        <GripVertical className="h-4 w-4 text-muted-foreground/20" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <h4 className={cn("text-sm font-bold", enabled ? "text-foreground/80" : "text-muted-foreground line-through")}>{gName}</h4>
                            <Badge variant={isVariation ? 'default' : 'secondary'} className="text-[8px] h-3.5 px-1">
                              {isVariation ? 'VARIATION' : 'ADDON'}
                            </Badge>
                            {groupDetail?.isRequired && (
                              <Badge variant="default" className="text-[8px] h-3.5 bg-orange-500/10 text-orange-500 border-none px-1">REQUIRED</Badge>
                            )}
                          </div>
                          <span className="text-[10px] text-muted-foreground">{itemCount} items</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
                        <Switch
                          checked={enabled}
                          onCheckedChange={() => !disabled && handleToggleEnabled(groupIndex)}
                          className="scale-75"
                        />
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive/60 hover:text-destructive hover:bg-destructive/10"
                          onClick={() => !disabled && handleRemoveGroup(groupIndex)}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                        <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", isExpanded && "rotate-180")} />
                      </div>
                    </div>
                  </CardHeader>

                  {isExpanded && (() => {
                  const groupDetail2 = groupDetailsMap[link.addon_group || '']
                  const groupItems = groupDetail2?.items || (rawLink as any).items || []
                  const isReq = groupDetail2?.isRequired || (rawLink as any).isRequired
                  const maxSel = groupDetail2?.maxSelections || (rawLink as any).maxSelections || 0
                  const minSel = groupDetail2?.minSelections || (rawLink as any).minSelections || 0

                  return (
                    <CardContent className="p-4 pt-0 border-t border-border/40 bg-muted/5">
                      {/* Group meta */}
                      <div className="flex items-center gap-4 py-3 mb-3 border-b border-border/30 text-[10px] text-muted-foreground">
                        {isReq && <span className="text-orange-500 font-bold uppercase">Required</span>}
                        {minSel > 0 && <span>Min: {minSel}</span>}
                        {maxSel > 0 && <span>Max: {maxSel}</span>}
                        <span className="ml-auto">
                          <Button variant="ghost" size="sm" className="h-6 text-[10px] text-primary" asChild>
                            <a href="/flamezo_backend/addon-groups" target="_blank" rel="noopener">
                              <ExternalLink className="h-3 w-3 mr-1" /> Edit Group
                            </a>
                          </Button>
                        </span>
                      </div>

                      {/* Items table */}
                      {groupItems.length === 0 ? (
                        <p className="text-xs text-muted-foreground text-center py-4">No items in this group yet.</p>
                      ) : (
                        <div className="rounded-lg border border-border/40 overflow-hidden bg-background/30">
                          <Table>
                            <TableHeader className="bg-muted/30">
                              <TableRow className="hover:bg-transparent border-none h-8">
                                <TableHead className="text-[9px] font-bold uppercase h-8">Name</TableHead>
                                <TableHead className="text-[9px] font-bold uppercase h-8 text-right">Price</TableHead>
                                <TableHead className="text-[9px] font-bold uppercase h-8 text-center">Veg</TableHead>
                                <TableHead className="text-[9px] font-bold uppercase h-8 text-center">Stock</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {groupItems.map((item: any, idx: number) => (
                                <TableRow key={idx} className="hover:bg-muted/20 border-border/20 h-9">
                                  <TableCell className="py-1.5">
                                    <div className="flex items-center gap-2">
                                      <div className={`h-1.5 w-1.5 rounded-full ${item.isVegetarian !== false ? 'bg-green-500' : 'bg-red-500'}`} />
                                      <span className="text-xs font-medium">{item.itemName || item.name || '-'}</span>
                                      {item.isDefault && <Badge variant="outline" className="text-[8px] h-3.5 px-1">Default</Badge>}
                                    </div>
                                  </TableCell>
                                  <TableCell className="py-1.5 text-right">
                                    <span className="text-xs font-mono text-muted-foreground">
                                      {item.price ? formatAmountNoDecimals(item.price) : 'FREE'}
                                    </span>
                                  </TableCell>
                                  <TableCell className="py-1.5 text-center">
                                    <div className={`h-2 w-2 rounded-full mx-auto ${item.isVegetarian !== false ? 'bg-green-500' : 'bg-red-500'}`} />
                                  </TableCell>
                                  <TableCell className="py-1.5 text-center">
                                    <span className={`text-[10px] font-medium ${item.inStock !== false ? 'text-green-600' : 'text-red-500'}`}>
                                      {item.inStock !== false ? 'In Stock' : 'Out'}
                                    </span>
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      )}
                    </CardContent>
                  )
                })()}
                </Card>
              )
            })}
          </div>
        )}
      </div>

      {/* Copy from Item Dialog */}
      <Dialog open={isCopyDialogOpen} onOpenChange={(open) => { setIsCopyDialogOpen(open); if (!open) setCopySearchQuery('') }}>
        <DialogContent className="sm:max-w-lg max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">Copy Addon Groups from Item</DialogTitle>
            <p className="text-xs text-muted-foreground">Select an item to copy all its addon groups and options.</p>
          </DialogHeader>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input placeholder="Search items..." value={copySearchQuery} onChange={e => setCopySearchQuery(e.target.value)} className="pl-9" autoFocus />
          </div>
          <div className="flex-1 overflow-y-auto min-h-0 -mx-6 px-6">
            {productsLoading ? (
              <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /><span className="text-sm">Loading items...</span>
              </div>
            ) : filteredCopyProducts.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center gap-2">
                <MousePointer2 className="h-6 w-6 text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">{copySearchQuery ? 'No matching items found.' : 'No items with addon groups yet.'}</p>
              </div>
            ) : (
              <div className="space-y-2 py-2">
                {filteredCopyProducts.map((product: any) => {
                  const groups = product.addonGroups || product.customizationQuestions || []
                  const totalItems = groups.reduce((sum: number, g: any) => sum + ((g.items || g.options || []).length), 0)
                  return (
                    <button key={product.docname || product.id}
                      className="w-full text-left p-3 rounded-lg border border-border/40 hover:border-primary/50 hover:bg-primary/5 transition-all group"
                      onClick={() => handleCopyFromProduct(product)}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <div className={`h-2 w-2 rounded-full shrink-0 ${product.is_vegetarian ? 'bg-green-500' : 'bg-red-500'}`} />
                            <h4 className="text-sm font-semibold text-foreground truncate">{product.name}</h4>
                          </div>
                          <p className="text-[10px] text-muted-foreground mt-0.5 ml-4">{product.category}</p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <Badge variant="outline" className="text-[9px] h-5 border-border/60 text-muted-foreground">
                            {groups.length} group{groups.length !== 1 ? 's' : ''} · {totalItems} item{totalItems !== 1 ? 's' : ''}
                          </Badge>
                          <Copy className="h-3.5 w-3.5 text-muted-foreground/40 group-hover:text-primary transition-colors" />
                        </div>
                      </div>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Link Existing Group Dialog */}
      <Dialog open={isLinkDialogOpen} onOpenChange={(open) => { setIsLinkDialogOpen(open); if (!open) { setLinkSearchQuery(''); setPreviewGroupId(null) } }}>
        <DialogContent className="sm:max-w-lg max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">Link Existing Addon Group</DialogTitle>
            <p className="text-xs text-muted-foreground">Select an existing group to reuse on this product.</p>
          </DialogHeader>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input placeholder="Search groups..." value={linkSearchQuery} onChange={e => setLinkSearchQuery(e.target.value)} className="pl-9" autoFocus />
          </div>
          <div className="flex-1 overflow-y-auto min-h-0 -mx-6 px-6">
            {groupsLoading ? (
              <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /><span className="text-sm">Loading groups...</span>
              </div>
            ) : availableGroups.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center gap-2">
                <MousePointer2 className="h-6 w-6 text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">{linkedGroupNames.size > 0 ? 'All groups already linked.' : 'No addon groups exist yet.'}</p>
                <Button variant="outline" size="sm" asChild>
                  <a href="/flamezo_backend/addon-groups" target="_blank" rel="noopener">
                    <Plus className="h-3.5 w-3.5 mr-1" /> Create New Group
                  </a>
                </Button>
              </div>
            ) : (
              <div className="space-y-2 py-2">
                {availableGroups.map((group: any) => {
                  const isVariation = group.groupType === 'variation'
                  const isPreviewing = previewGroupId === group.id
                  const items = group.items || []

                  return (
                    <div key={group.id} className="rounded-lg border border-border/40 overflow-hidden transition-all hover:border-primary/30">
                      {/* Header row */}
                      <div className="flex items-center p-3 gap-2">
                        <div className="flex-1 min-w-0 cursor-pointer hover:bg-primary/5 rounded -m-1 p-1 transition-colors"
                          onClick={() => handleLinkExisting(group)}>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold">{group.groupName}</span>
                            <Badge variant={isVariation ? 'default' : 'secondary'} className="text-[9px]">
                              {isVariation ? 'Variation' : 'Addon'}
                            </Badge>
                            {group.isRequired && <Badge variant="destructive" className="text-[9px]">Required</Badge>}
                          </div>
                          <p className="text-[10px] text-muted-foreground mt-0.5">
                            {items.length} items
                            {group.linkedProductCount ? ` · ${group.linkedProductCount} products` : ''}
                          </p>
                        </div>
                        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0"
                          onClick={(e) => { e.stopPropagation(); setPreviewGroupId(isPreviewing ? null : group.id) }}>
                          <Eye className={cn("h-3.5 w-3.5 transition-colors", isPreviewing ? "text-primary" : "text-muted-foreground/50")} />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0 text-primary"
                          onClick={() => handleLinkExisting(group)}>
                          <Link2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>

                      {/* Preview panel */}
                      {isPreviewing && items.length > 0 && (
                        <div className="border-t border-border/30 bg-muted/5 px-3 py-2">
                          <Table>
                            <TableHeader className="bg-muted/20">
                              <TableRow className="hover:bg-transparent border-none h-7">
                                <TableHead className="text-[9px] font-bold uppercase h-7">Name</TableHead>
                                <TableHead className="text-[9px] font-bold uppercase h-7 text-right">Price</TableHead>
                                <TableHead className="text-[9px] font-bold uppercase h-7 text-center">Veg</TableHead>
                                <TableHead className="text-[9px] font-bold uppercase h-7 text-center">Stock</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {items.map((item: any, idx: number) => (
                                <TableRow key={idx} className="hover:bg-muted/10 border-border/10 h-8">
                                  <TableCell className="py-1 text-xs">{item.itemName || item.name || '-'}</TableCell>
                                  <TableCell className="py-1 text-xs text-right font-mono text-muted-foreground">
                                    {item.price ? formatAmountNoDecimals(item.price) : 'FREE'}
                                  </TableCell>
                                  <TableCell className="py-1 text-center">
                                    <div className={`h-2 w-2 rounded-full mx-auto ${item.isVegetarian !== false ? 'bg-green-500' : 'bg-red-500'}`} />
                                  </TableCell>
                                  <TableCell className="py-1 text-center">
                                    <span className={`text-[10px] ${item.inStock !== false ? 'text-green-600' : 'text-red-500'}`}>
                                      {item.inStock !== false ? 'In Stock' : 'Out'}
                                    </span>
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
