import { useState, useMemo } from 'react'
import { useFrappePostCall, useFrappeGetCall } from 'frappe-react-sdk'
import { useRestaurant } from '../contexts/RestaurantContext'
import { useCurrency } from '../hooks/useCurrency'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { NumberInput } from '../components/ui/number-input'
import { Badge } from '../components/ui/badge'
import { Switch } from '../components/ui/switch'
import { Label } from '../components/ui/label'
import { Card, CardContent, CardHeader } from '../components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter
} from '../components/ui/dialog'
import {
  Plus, Pencil, Trash2, Search, Layers, ChevronDown, GripVertical,
  Scale, Maximize2, Utensils, Pizza, Soup, MousePointer2, Edit2, Check,
  Link2
} from 'lucide-react'
import json from 'superjson'


// ─── Types ──────────────────────────────────────────────────────────────────

interface AddonItem {
  id?: string
  itemId?: string
  name?: string
  itemName?: string
  price?: number
  isDefault?: boolean
  isVegetarian?: boolean
  inStock?: boolean
  displayOrder?: number
}

interface AddonGroup {
  id: string
  groupId: string
  groupName: string
  groupType: 'addon' | 'variation'
  type?: string
  status: string
  isRequired: boolean
  minSelections: number
  maxSelections: number
  displayOrder: number
  items: AddonItem[]
  linkedProductCount?: number
}


// ─── Templates ──────────────────────────────────────────────────────────────

const TEMPLATES = [
  { id: 'quantity', title: 'Quantity', subtitle: 'Quantity variations like - Small, medium, large, etc', icon: Scale, groupType: 'variation' as const },
  { id: 'size', title: 'Size', subtitle: 'Different sizes of an item, eg - bread size, pizza size - 6", 12", etc', icon: Maximize2, groupType: 'variation' as const },
  { id: 'prep', title: 'Preparation type', subtitle: 'Item preparation style, eg - Halal, non-Halal, etc', icon: Utensils, groupType: 'addon' as const },
  { id: 'base', title: 'Base', subtitle: 'Item Base types, eg - wheat bread, multi-grain bread, etc', icon: Pizza, groupType: 'addon' as const },
  { id: 'rice', title: 'Rice', subtitle: "Choice of item's rice selection.", icon: Soup, groupType: 'addon' as const },
  { id: 'custom', title: 'Make your own', subtitle: "Define your own addon or variation group from scratch.", icon: Plus, groupType: 'addon' as const, highlight: true },
]


// ─── Main Page ──────────────────────────────────────────────────────────────

export default function AddonGroupManagement() {
  const { selectedRestaurant } = useRestaurant()
  const restaurantId = selectedRestaurant
  const { formatAmountNoDecimals } = useCurrency()

  const [search, setSearch] = useState('')
  const [filterType, setFilterType] = useState<string>('all')
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  const [editingGroup, setEditingGroup] = useState<string | null>(null)
  const [editingOption, setEditingOption] = useState<{ groupId: string; optionIndex: number } | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteGroupId, setDeleteGroupId] = useState<string | null>(null)

  // API
  const { data: groupsData, mutate: mutateGroups } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.addon_groups.get_addon_groups',
    restaurantId ? { restaurant_id: restaurantId, include_items: 1 } : undefined,
    restaurantId ? `addon-groups-${restaurantId}` : null
  )
  const { call: createGroup } = useFrappePostCall('flamezo_backend.flamezo.api.addon_groups.create_addon_group')
  const { call: updateGroup } = useFrappePostCall('flamezo_backend.flamezo.api.addon_groups.update_addon_group')
  const { call: deleteGroupApi } = useFrappePostCall('flamezo_backend.flamezo.api.addon_groups.delete_addon_group')
  const { call: toggleStock } = useFrappePostCall('flamezo_backend.flamezo.api.addon_groups.toggle_addon_item_stock')

  const groups: AddonGroup[] = useMemo(() => {
    const raw = groupsData?.message?.data || groupsData?.data || []
    let filtered = raw
    if (search) {
      const q = search.toLowerCase()
      filtered = filtered.filter((g: AddonGroup) =>
        g.groupName?.toLowerCase().includes(q) ||
        g.items?.some((i: AddonItem) => (i.name || i.itemName || '').toLowerCase().includes(q))
      )
    }
    if (filterType !== 'all') {
      filtered = filtered.filter((g: AddonGroup) => (g.groupType || g.type) === filterType)
    }
    return filtered
  }, [groupsData, search, filterType])

  // ─── Template Create ────────────────────────────────────────────────────

  const handleAddFromTemplate = async (templateId: string) => {
    if (!restaurantId) {
      toast.error('No restaurant selected')
      return
    }
    const template = TEMPLATES.find(t => t.id === templateId)
    const isCustom = templateId === 'custom'

    try {
      const result = await createGroup({
        restaurant_id: restaurantId,
        group_name: isCustom ? '' : (template?.title || 'New Group'),
        group_type: template?.groupType || 'addon',
        is_required: 0,
        min_selections: 0,
        max_selections: template?.groupType === 'variation' ? 1 : 0,
        items: JSON.stringify([{ name: 'Option 1', price: 0 }])
      })

      const data = result?.message?.data || result?.data
      if (data) {
        await mutateGroups()
        setEditingGroup(data.id)
        setExpandedGroups(new Set([...expandedGroups, data.id]))
        toast.success(isCustom ? 'New group created' : `Created "${data.groupName}" group`)
      }
    } catch (e: any) {
      toast.error(e?.message || 'Failed to create group')
    }
  }

  // ─── Toggle / Edit Helpers ──────────────────────────────────────────────

  const toggleExpand = (id: string) => {
    const next = new Set(expandedGroups)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setExpandedGroups(next)
  }

  const handleSaveGroup = async (group: AddonGroup) => {
    try {
      await updateGroup({
        restaurant_id: restaurantId,
        group_id: group.groupId || group.id,
        group_name: group.groupName,
        group_type: group.groupType,
        is_required: group.isRequired ? 1 : 0,
        min_selections: group.minSelections || 0,
        max_selections: group.maxSelections || 0,
        items: JSON.stringify((group.items || []).map((item, idx) => ({
          name: item.itemName || item.name || '',
          id: item.itemId || item.id || '',
          price: item.price || 0,
          isDefault: item.isDefault || false,
          isVegetarian: item.isVegetarian !== false,
          inStock: item.inStock !== false,
          displayOrder: idx,
        })))
      })
      setEditingGroup(null)
      mutateGroups()
      toast.success('Group saved')
    } catch (e: any) {
      toast.error(e?.message || 'Failed to save')
    }
  }

  const handleDelete = async () => {
    if (!deleteGroupId) return
    try {
      const group = groups.find(g => g.id === deleteGroupId)
      await deleteGroupApi({
        restaurant_id: restaurantId,
        group_id: group?.groupId || deleteGroupId
      })
      setDeleteDialogOpen(false)
      mutateGroups()
      toast.success('Addon group deleted')
    } catch (e: any) {
      toast.error(e?.message || 'Failed to delete')
    }
  }

  const handleToggleStock = async (group: AddonGroup, itemId: string, currentStock: boolean) => {
    try {
      await toggleStock({
        restaurant_id: restaurantId,
        group_id: group.groupId || group.id,
        item_id: itemId,
        in_stock: currentStock ? 0 : 1
      })
      mutateGroups()
    } catch (e: any) {
      toast.error(e?.message || 'Failed to toggle stock')
    }
  }

  // ─── Local Editing State (for inline editing before save) ───────────────

  const [localEdits, setLocalEdits] = useState<Record<string, AddonGroup>>({})

  const getEditableGroup = (group: AddonGroup): AddonGroup => {
    return localEdits[group.id] || group
  }

  const updateLocal = (groupId: string, updates: Partial<AddonGroup>) => {
    setLocalEdits(prev => ({
      ...prev,
      [groupId]: { ...(prev[groupId] || groups.find(g => g.id === groupId)!), ...updates }
    }))
  }

  const updateLocalItem = (groupId: string, itemIndex: number, field: string, value: any) => {
    const group = getEditableGroup(groups.find(g => g.id === groupId)!)
    const items = [...(group.items || [])]
    items[itemIndex] = { ...items[itemIndex], [field]: value }
    updateLocal(groupId, { items })
  }

  const addLocalItem = (groupId: string) => {
    const group = getEditableGroup(groups.find(g => g.id === groupId)!)
    const items = [...(group.items || []), { name: '', itemName: '', price: 0, isVegetarian: true, inStock: true }]
    updateLocal(groupId, { items })
    setEditingOption({ groupId, optionIndex: items.length - 1 })
  }

  const removeLocalItem = (groupId: string, itemIndex: number) => {
    const group = getEditableGroup(groups.find(g => g.id === groupId)!)
    const items = (group.items || []).filter((_, i) => i !== itemIndex)
    updateLocal(groupId, { items })
  }

  const handleToggleStatus = async (rawGroup: AddonGroup) => {
    const newStatus = rawGroup.status === 'Active' ? 'Inactive' : 'Active'
    try {
      await updateGroup({
        restaurant_id: restaurantId,
        group_id: rawGroup.groupId || rawGroup.id,
        status: newStatus
      })
      mutateGroups()
      toast.success(`Group ${newStatus === 'Active' ? 'enabled' : 'disabled'}`)
    } catch (e: any) {
      toast.error(e?.message || 'Failed to toggle status')
    }
  }

  const handleSaveEditing = async (groupId: string) => {
    const group = getEditableGroup(groups.find(g => g.id === groupId)!)
    await handleSaveGroup(group)
    setLocalEdits(prev => {
      const next = { ...prev }
      delete next[groupId]
      return next
    })
  }

  // ─── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Addon Groups</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Manage reusable addon & variation groups. Link them to multiple products.
        </p>
      </div>

      {/* Templates */}
      <div className="space-y-4">
        <div>
          <h3 className="text-sm font-bold text-foreground/80 uppercase tracking-tight">Create New Group</h3>
          <p className="text-xs text-muted-foreground mt-1">Pick a template or start from scratch.</p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
          {TEMPLATES.map((template) => (
            <Card key={template.id} className={cn(
              "group transition-all duration-300 border-border/40 bg-card/30 cursor-pointer hover:border-primary/50",
              template.highlight && "border-primary/20"
            )} onClick={() => handleAddFromTemplate(template.id)}>
              <CardContent className="p-3 flex flex-col gap-2">
                <div className="p-2 rounded-lg bg-muted text-muted-foreground group-hover:text-primary transition-colors w-fit">
                  <template.icon className="h-4 w-4" />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-foreground/90">{template.title}</h4>
                  <p className="text-[10px] text-muted-foreground leading-relaxed mt-1 line-clamp-2">{template.subtitle}</p>
                </div>
                <span className="text-[10px] font-bold text-primary opacity-0 group-hover:opacity-100 transition-opacity uppercase tracking-widest">
                  + Create
                </span>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 items-center pt-4 border-t border-border/40">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input placeholder="Search groups or items..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9" />
        </div>
        <Select value={filterType} onValueChange={setFilterType}>
          <SelectTrigger className="w-[160px]"><SelectValue placeholder="All types" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            <SelectItem value="addon">Addons</SelectItem>
            <SelectItem value="variation">Variations</SelectItem>
          </SelectContent>
        </Select>
        <Badge variant="outline" className="text-[10px] h-5 border-border/60 text-muted-foreground ml-auto">
          {groups.length} GROUPS
        </Badge>
      </div>

      {/* Groups List */}
      {groups.length === 0 ? (
        <div className="p-12 border border-dashed rounded-xl bg-muted/10 flex flex-col items-center justify-center text-center gap-3">
          <MousePointer2 className="h-6 w-6 text-muted-foreground/30" />
          <p className="text-xs text-muted-foreground font-medium uppercase tracking-widest">No addon groups yet</p>
          <p className="text-sm text-muted-foreground">Use the templates above to create your first group.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {groups.map((rawGroup) => {
            const group = getEditableGroup(rawGroup)
            const isExpanded = expandedGroups.has(rawGroup.id)
            const isEditing = editingGroup === rawGroup.id
            const isVariation = (group.groupType || group.type) === 'variation'
            const groupItems = group.items || []

            const isActive = rawGroup.status === 'Active'

            return (
              <Card key={rawGroup.id} className={cn(
                "overflow-hidden border-border/40 transition-all duration-300 shadow-none",
                isExpanded && "border-border shadow-md",
                isActive ? "bg-card/20" : "bg-muted/30 opacity-60"
              )}>
                {/* Header */}
                <CardHeader className="p-3 cursor-pointer select-none" onClick={() => !isEditing && toggleExpand(rawGroup.id)}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <GripVertical className="h-4 w-4 text-muted-foreground/20" />
                      <div className="flex-1 min-w-0">
                        {isEditing ? (
                          <Input value={group.groupName || ''} onClick={e => e.stopPropagation()}
                            onChange={e => updateLocal(rawGroup.id, { groupName: e.target.value })}
                            placeholder="Group name (e.g., Choice of Bread)" className="h-8 text-sm font-bold bg-background/50" autoFocus />
                        ) : (
                          <div>
                            <div className="flex items-center gap-2">
                              <h4 className={cn("text-sm font-bold", isActive ? "text-foreground/80" : "text-muted-foreground line-through")}>{group.groupName || 'Untitled Group'}</h4>
                              <Badge variant={isVariation ? 'default' : 'secondary'} className="text-[8px] h-3.5 px-1">
                                {isVariation ? 'VARIATION' : 'ADDON'}
                              </Badge>
                              {group.isRequired && <Badge variant="default" className="text-[8px] h-3.5 bg-orange-500/10 text-orange-500 border-none px-1">REQUIRED</Badge>}
                              {!isActive && <Badge variant="outline" className="text-[8px] h-3.5 px-1">DISABLED</Badge>}
                            </div>
                            <div className="flex items-center gap-3 text-[10px] text-muted-foreground mt-0.5">
                              <span>{groupItems.length} items</span>
                              {rawGroup.linkedProductCount ? <span className="flex items-center gap-1"><Link2 className="w-3 h-3" />{rawGroup.linkedProductCount} products</span> : null}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
                      <Switch
                        checked={isActive}
                        onCheckedChange={() => handleToggleStatus(rawGroup)}
                        className="scale-75"
                      />
                      {isEditing ? (
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-green-500 hover:bg-green-500/10"
                          onClick={() => handleSaveEditing(rawGroup.id)}>
                          <Check className="h-4 w-4" />
                        </Button>
                      ) : (
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-foreground"
                          onClick={() => { setEditingGroup(rawGroup.id); if (!isExpanded) toggleExpand(rawGroup.id) }}>
                          <Edit2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive/60 hover:text-destructive hover:bg-destructive/10"
                        onClick={() => { setDeleteGroupId(rawGroup.id); setDeleteDialogOpen(true) }}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                      <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform ml-1", isExpanded && "rotate-180")} />
                    </div>
                  </div>
                </CardHeader>

                {/* Expanded Content */}
                {isExpanded && (
                  <CardContent className="p-4 pt-0 border-t border-border/40 bg-muted/5">
                    {/* Selection Type & Required */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-4 mb-4 border-b border-border/40">
                      <div className="space-y-1">
                        <Label className="text-[10px] font-bold text-muted-foreground/80 uppercase">Type</Label>
                        <Select value={group.groupType || 'addon'}
                          onValueChange={val => updateLocal(rawGroup.id, { groupType: val as any, maxSelections: val === 'variation' ? 1 : group.maxSelections })}
                          disabled={!isEditing}>
                          <SelectTrigger className="h-8 text-xs bg-background/50 border-border/60"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="addon">Addon (multi-select extras)</SelectItem>
                            <SelectItem value="variation">Variation (single-select, replaces price)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex items-end gap-4 pb-1.5">
                        <div className="flex items-center space-x-2">
                          <input type="checkbox" id={`req-${rawGroup.id}`} checked={!!group.isRequired}
                            onChange={e => updateLocal(rawGroup.id, { isRequired: e.target.checked })}
                            className="h-4 w-4 rounded border-border/60 text-primary" disabled={!isEditing} />
                          <Label htmlFor={`req-${rawGroup.id}`} className="text-xs font-medium cursor-pointer">Selection Mandatory?</Label>
                        </div>
                      </div>
                    </div>

                    {/* Items Table */}
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60">Options & Pricing</span>
                        {isEditing && (
                          <Button type="button" variant="outline" size="sm" onClick={() => addLocalItem(rawGroup.id)}
                            className="h-6 text-[10px] border-primary/20 text-primary hover:bg-primary/5">
                            <Plus className="h-3 w-3 mr-1" /> ADD OPTION
                          </Button>
                        )}
                      </div>

                      <div className="rounded-lg border border-border/40 overflow-hidden bg-background/30">
                        <Table>
                          <TableHeader className="bg-muted/30">
                            <TableRow className="hover:bg-transparent border-none h-8">
                              <TableHead className="text-[9px] font-bold uppercase h-8">Name</TableHead>
                              <TableHead className="text-[9px] font-bold uppercase h-8 text-right">Price</TableHead>
                              <TableHead className="text-[9px] font-bold uppercase h-8 text-center">Veg</TableHead>
                              <TableHead className="text-[9px] font-bold uppercase h-8 text-center">Stock</TableHead>
                              <TableHead className="text-[9px] font-bold uppercase h-8 text-right">Action</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {groupItems.length === 0 && (
                              <TableRow>
                                <TableCell colSpan={5} className="text-center text-xs text-muted-foreground py-6">
                                  No items yet. {isEditing ? 'Click "ADD OPTION" above.' : 'Click edit to add items.'}
                                </TableCell>
                              </TableRow>
                            )}
                            {groupItems.map((item, optIdx) => {
                              const itemId = item.itemId || item.id || ''
                              const itemName = item.itemName || item.name || ''
                              const isEditingOpt = editingOption?.groupId === rawGroup.id && editingOption?.optionIndex === optIdx

                              return (
                                <TableRow key={optIdx} className="hover:bg-muted/20 border-border/20 h-10 group/row">
                                  <TableCell className="py-2">
                                    {isEditing || isEditingOpt ? (
                                      <Input value={itemName}
                                        onChange={e => updateLocalItem(rawGroup.id, optIdx, 'itemName', e.target.value)}
                                        className="h-7 text-xs bg-background" autoFocus={isEditingOpt} placeholder="Item name" />
                                    ) : (
                                      <div className="flex items-center gap-2">
                                        <div className={`h-1.5 w-1.5 rounded-full ${item.isVegetarian !== false ? 'bg-green-500' : 'bg-red-500'}`} />
                                        <span className="text-xs font-medium">{itemName || '-'}</span>
                                      </div>
                                    )}
                                  </TableCell>
                                  <TableCell className="py-2 text-right">
                                    {isEditing || isEditingOpt ? (
                                      <NumberInput value={item.price ?? 0}
                                        onChange={e => updateLocalItem(rawGroup.id, optIdx, 'price', parseFloat(e.target.value) || 0)}
                                        className="h-7 text-xs text-right w-20 ml-auto bg-background" />
                                    ) : (
                                      <span className="text-xs font-mono text-muted-foreground">
                                        {item.price ? formatAmountNoDecimals(item.price) : 'FREE'}
                                      </span>
                                    )}
                                  </TableCell>
                                  <TableCell className="py-2 text-center">
                                    <input type="checkbox" checked={item.isVegetarian !== false}
                                      onChange={e => updateLocalItem(rawGroup.id, optIdx, 'isVegetarian', e.target.checked)}
                                      className="h-3.5 w-3.5 rounded border-border/40" disabled={!isEditing} />
                                  </TableCell>
                                  <TableCell className="py-2 text-center">
                                    <Switch checked={item.inStock !== false} className="scale-75"
                                      onCheckedChange={() => {
                                        if (isEditing) {
                                          updateLocalItem(rawGroup.id, optIdx, 'inStock', !(item.inStock !== false))
                                        } else {
                                          handleToggleStock(rawGroup, itemId, item.inStock !== false)
                                        }
                                      }} />
                                  </TableCell>
                                  <TableCell className="py-2 text-right">
                                    {isEditing && (
                                      <Button variant="ghost" size="icon"
                                        className="h-6 w-6 text-destructive/60 hover:text-destructive"
                                        onClick={() => removeLocalItem(rawGroup.id, optIdx)}>
                                        <Trash2 className="h-3 w-3" />
                                      </Button>
                                    )}
                                  </TableCell>
                                </TableRow>
                              )
                            })}
                          </TableBody>
                        </Table>
                      </div>
                    </div>
                  </CardContent>
                )}
              </Card>
            )
          })}
        </div>
      )}

      {/* Delete Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Addon Group</DialogTitle>
            <DialogDescription>This will unlink the group from all products and permanently delete it.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
