import { useState, useEffect } from 'react'
import { Plus, Search, Trash2, Edit2, AlertCircle, FolderPlus, Package, Scissors, Dumbbell,
  ShoppingBag, Gamepad2, ChevronDown, ChevronRight, Star, Layers, X, Link2, Loader2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useFrappePostCall } from '@/lib/frappe'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from 'sonner'
import { useConfirm } from '@/hooks/useConfirm'
import { getCatalogueLabel } from '@/lib/industryConfig'
import { cn } from '@/lib/utils'
import { CatalogueSkeleton } from '@/components/PageSkeletons'

// ── Interfaces ────────────────────────────────────────────────────────────────

interface CatalogueCategory {
  name: string
  category_name: string
  is_active: number
  sort_order: number
}

interface CatalogueItem {
  name: string
  item_name: string
  category: string
  category_name: string
  price: number
  price_prefix: string
  original_price: number | null
  description: string
  is_popular: number
  badge: string
  sort_order: number
  is_active: number
  thumbnail?: string
}

interface AddonOption {
  id: string
  name: string
  price: number
  is_default: boolean
  in_stock: boolean
}

interface ItemAddon {
  id: string            // Addon Group doc name
  addon_group_id: string // Catalogue Item Addon child row name
  group_name: string
  group_type: 'addon' | 'variation'
  is_required: boolean
  min_selections: number
  max_selections: number
  is_enabled: boolean
  display_order: number
  options: AddonOption[]
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function CatalogueManagement() {
  const { selectedRestaurant, outletType } = useRestaurant()
  const { confirm, ConfirmDialogComponent } = useConfirm()
  const labels = getCatalogueLabel(outletType)

  const isDining = !outletType || outletType === 'dining' || outletType === 'cafe'

  const PageIcon =
    outletType === 'wellness' ? Scissors :
    outletType === 'fitness' ? Dumbbell :
    outletType === 'fashion' ? ShoppingBag :
    outletType === 'sports_venue' ? Gamepad2 :
    Package

  // ── State ────────────────────────────────────────────────────────────────
  const [categories, setCategories] = useState<CatalogueCategory[]>([])
  const [items, setItems] = useState<CatalogueItem[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set())

  // Category form
  const [catFormOpen, setCatFormOpen] = useState(false)
  const [editingCat, setEditingCat] = useState<CatalogueCategory | null>(null)
  const [catName, setCatName] = useState('')
  const [catSaving, setCatSaving] = useState(false)

  // Item form
  const [itemFormOpen, setItemFormOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<CatalogueItem | null>(null)
  const [activeTab, setActiveTab] = useState<'details' | 'addons'>('details')
  const [itemData, setItemData] = useState({
    item_name: '',
    category: '',
    price: '',
    price_prefix: '',
    original_price: '',
    description: '',
    is_popular: false,
    badge: '',
    is_active: true,
  })
  const [itemSaving, setItemSaving] = useState(false)

  // Addon state
  const [itemAddons, setItemAddons] = useState<ItemAddon[]>([])
  const [allAddonGroups, setAllAddonGroups] = useState<any[]>([])
  const [loadingAddons, setLoadingAddons] = useState(false)
  const [linkDialogOpen, setLinkDialogOpen] = useState(false)
  const [linkSearch, setLinkSearch] = useState('')
  const [linkingGroupId, setLinkingGroupId] = useState<string | null>(null)

  // ── API calls ────────────────────────────────────────────────────────────
  const { call: fetchCategories } = useFrappePostCall('flamezo_backend.flamezo.api.catalogue.get_catalogue_categories')
  const { call: fetchCatalogue } = useFrappePostCall('flamezo_backend.flamezo.api.catalogue.get_catalogue')
  const { call: saveCategory } = useFrappePostCall('flamezo_backend.flamezo.api.catalogue.save_catalogue_category')
  const { call: deleteCategory } = useFrappePostCall('flamezo_backend.flamezo.api.catalogue.delete_catalogue_category')
  const { call: saveItem } = useFrappePostCall('flamezo_backend.flamezo.api.catalogue.save_catalogue_item')
  const { call: deleteItem } = useFrappePostCall('flamezo_backend.flamezo.api.catalogue.delete_catalogue_item')
  const { call: fetchItemAddonsApi } = useFrappePostCall('flamezo_backend.flamezo.api.catalogue_addons.get_item_addons')
  const { call: linkAddonApi } = useFrappePostCall('flamezo_backend.flamezo.api.catalogue_addons.link_addon_to_item')
  const { call: unlinkAddonApi } = useFrappePostCall('flamezo_backend.flamezo.api.catalogue_addons.unlink_addon_from_item')
  const { call: toggleAddonApi } = useFrappePostCall('flamezo_backend.flamezo.api.catalogue_addons.toggle_item_addon_enabled')
  const { call: fetchAddonGroupsApi } = useFrappePostCall('flamezo_backend.flamezo.api.addon_groups.get_addon_groups')

  useEffect(() => {
    if (selectedRestaurant) loadData()
  }, [selectedRestaurant])

  const loadData = async () => {
    if (!selectedRestaurant) return
    try {
      setLoading(true)
      const [catRes, catRes2] = await Promise.all([
        fetchCategories({ restaurant_id: selectedRestaurant }),
        fetchCatalogue({ restaurant_id: selectedRestaurant }),
      ])
      const cats: CatalogueCategory[] = catRes?.message?.data || catRes?.data || []
      setCategories(cats)
      if (cats.length > 0) {
        const allExpanded = new Set(cats.map((c) => c.name))
        setExpandedCategories(allExpanded)
      }

      const catalogueData = catRes2?.message?.data || catRes2?.data
      const allItems: CatalogueItem[] = []
      if (catalogueData?.categories) {
        catalogueData.categories.forEach((cat: any) => {
          ;(cat.items || []).forEach((item: any) => {
            allItems.push({
              name: item.id,
              item_name: item.name,
              category: cat.id || cat.name,
              category_name: cat.category_name,
              price: item.price,
              price_prefix: item.price_prefix || '',
              original_price: item.original_price || null,
              description: item.description || '',
              is_popular: item.is_popular ? 1 : 0,
              badge: item.badge || '',
              sort_order: item.sort_order || 0,
              is_active: item.is_active !== false ? 1 : 0,
              thumbnail: item.thumbnail || item.item_media?.[0]?.media_url,
            })
          })
        })
      }
      setItems(allItems)
    } catch {
      toast.error('Failed to load catalogue')
    } finally {
      setLoading(false)
    }
  }

  // ── Category actions ─────────────────────────────────────────────────────
  const openCatForm = (cat?: CatalogueCategory) => {
    setEditingCat(cat || null)
    setCatName(cat?.category_name || '')
    setCatFormOpen(true)
  }

  const handleSaveCategory = async () => {
    if (!catName.trim()) { toast.error('Category name is required'); return }
    try {
      setCatSaving(true)
      const res = await saveCategory({
        restaurant_id: selectedRestaurant,
        name: editingCat?.name || null,
        category_name: catName.trim(),
      })
      const ok = res?.message?.success ?? res?.success ?? (res?.message?.data || res?.data)
      if (ok) {
        toast.success(editingCat ? 'Category updated' : 'Category added')
        setCatFormOpen(false)
        await loadData()
      } else {
        toast.error(res?.message?.error?.message || 'Failed to save category')
      }
    } catch {
      toast.error('Failed to save category')
    } finally {
      setCatSaving(false)
    }
  }

  const handleDeleteCategory = async (cat: CatalogueCategory) => {
    const ok = await confirm({
      title: `Delete "${cat.category_name}"?`,
      description: 'Items in this category will become uncategorised.',
      confirmLabel: 'Delete',
      confirmVariant: 'destructive',
    })
    if (!ok) return
    try {
      const res = await deleteCategory({ restaurant_id: selectedRestaurant, name: cat.name })
      const success = res?.message?.success ?? res?.success
      if (success) {
        toast.success('Category deleted')
        await loadData()
      } else {
        toast.error(res?.message?.error?.message || 'Failed to delete category')
      }
    } catch {
      toast.error('Failed to delete category')
    }
  }

  // ── Item actions ─────────────────────────────────────────────────────────
  const openItemForm = async (item?: CatalogueItem, defaultCategory?: string) => {
    setEditingItem(item || null)
    setItemData({
      item_name: item?.item_name || '',
      category: item?.category || defaultCategory || categories[0]?.name || '',
      price: item?.price?.toString() || '',
      price_prefix: item?.price_prefix || '',
      original_price: item?.original_price?.toString() || '',
      description: item?.description || '',
      is_popular: !!item?.is_popular,
      badge: item?.badge || '',
      is_active: item ? !!item.is_active : true,
    })
    setActiveTab('details')
    setItemAddons([])
    setAllAddonGroups([])
    setItemFormOpen(true)

    if (item) {
      setLoadingAddons(true)
      try {
        const [addonsRes, groupsRes] = await Promise.all([
          fetchItemAddonsApi({ restaurant_id: selectedRestaurant, item_id: item.name }),
          fetchAddonGroupsApi({ restaurant_id: selectedRestaurant, include_items: 1 }),
        ])
        setItemAddons(addonsRes?.message?.data || addonsRes?.data || [])
        setAllAddonGroups(groupsRes?.message?.data || groupsRes?.data || [])
      } catch {
        // addons load failure is non-critical
      } finally {
        setLoadingAddons(false)
      }
    }
  }

  const handleSaveItem = async () => {
    if (!itemData.item_name.trim() || !itemData.category || !itemData.price) {
      toast.error('Name, category, and price are required')
      return
    }
    try {
      setItemSaving(true)
      const payload = {
        item_name: itemData.item_name.trim(),
        category: itemData.category,
        price: parseFloat(itemData.price) || 0,
        price_prefix: itemData.price_prefix || '',
        original_price: itemData.original_price ? parseFloat(itemData.original_price) : null,
        description: itemData.description || '',
        is_popular: itemData.is_popular ? 1 : 0,
        badge: itemData.badge || '',
        is_active: itemData.is_active ? 1 : 0,
      }
      const res = await saveItem({
        restaurant_id: selectedRestaurant,
        name: editingItem?.name || null,
        item_data: JSON.stringify(payload),
      })
      const ok = res?.message?.success ?? res?.success ?? (res?.message?.data || res?.data)
      if (ok) {
        toast.success(editingItem ? `${labels.singular} updated` : `${labels.singular} added`)
        setItemFormOpen(false)
        await loadData()
      } else {
        toast.error(res?.message?.error?.message || `Failed to save ${labels.singular.toLowerCase()}`)
      }
    } catch {
      toast.error(`Failed to save ${labels.singular.toLowerCase()}`)
    } finally {
      setItemSaving(false)
    }
  }

  const handleDeleteItem = async (item: CatalogueItem) => {
    const ok = await confirm({
      title: `Delete "${item.item_name}"?`,
      description: `This ${labels.singular.toLowerCase()} will be permanently removed.`,
      confirmLabel: 'Delete',
      confirmVariant: 'destructive',
    })
    if (!ok) return
    try {
      const res = await deleteItem({ restaurant_id: selectedRestaurant, name: item.name })
      const success = res?.message?.success ?? res?.success
      if (success) {
        toast.success(`${labels.singular} deleted`)
        await loadData()
      } else {
        toast.error(res?.message?.error?.message || 'Failed to delete')
      }
    } catch {
      toast.error('Failed to delete')
    }
  }

  // ── Addon actions ─────────────────────────────────────────────────────────
  const handleLinkAddon = async (groupId: string) => {
    if (!editingItem) return
    setLinkingGroupId(groupId)
    try {
      const res = await linkAddonApi({
        restaurant_id: selectedRestaurant,
        item_id: editingItem.name,
        addon_group_id: groupId,
      })
      const ok = res?.message?.success ?? res?.success
      if (ok) {
        const data = res?.message?.data || res?.data || []
        setItemAddons(data)
        setLinkDialogOpen(false)
        toast.success('Add-on group linked')
      } else {
        toast.error(res?.message?.error?.message || 'Failed to link group')
      }
    } catch {
      toast.error('Failed to link group')
    } finally {
      setLinkingGroupId(null)
    }
  }

  const handleUnlinkAddon = async (addon: ItemAddon) => {
    if (!editingItem) return
    try {
      const res = await unlinkAddonApi({
        restaurant_id: selectedRestaurant,
        item_id: editingItem.name,
        addon_group_id: addon.id,
      })
      const ok = res?.message?.success ?? res?.success
      if (ok) {
        setItemAddons(prev => prev.filter(a => a.id !== addon.id))
        toast.success('Add-on group removed')
      } else {
        toast.error(res?.message?.error?.message || 'Failed to remove group')
      }
    } catch {
      toast.error('Failed to remove group')
    }
  }

  const handleToggleAddon = async (addon: ItemAddon, enabled: boolean) => {
    if (!editingItem) return
    try {
      await toggleAddonApi({
        restaurant_id: selectedRestaurant,
        item_id: editingItem.name,
        addon_group_id: addon.id,
        is_enabled: enabled ? 1 : 0,
      })
      setItemAddons(prev => prev.map(a => a.id === addon.id ? { ...a, is_enabled: enabled } : a))
    } catch {
      toast.error('Failed to toggle add-on')
    }
  }

  // ── Derived ───────────────────────────────────────────────────────────────
  const filteredItems = items.filter((item) => {
    const matchesSearch = !searchQuery ||
      item.item_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.description?.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesCat = !selectedCategory || item.category === selectedCategory
    return matchesSearch && matchesCat
  })

  const itemsByCategory = categories.reduce<Record<string, CatalogueItem[]>>((acc, cat) => {
    acc[cat.name] = filteredItems.filter((i) => i.category === cat.name)
    return acc
  }, {})

  const toggleExpand = (catName: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(catName)) next.delete(catName)
      else next.add(catName)
      return next
    })
  }

  // Groups not yet linked to the editing item
  const linkedGroupIds = new Set(itemAddons.map(a => a.id))
  const availableGroupsToLink = allAddonGroups.filter((g: any) => {
    const gId = g.id || g.name
    const matchesSearch = !linkSearch || (g.groupName || g.group_name || '').toLowerCase().includes(linkSearch.toLowerCase())
    return !linkedGroupIds.has(gId) && matchesSearch && (g.status === 'Active' || !g.status)
  })

  if (!selectedRestaurant) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground">Please select an outlet to manage your catalogue</p>
        </div>
      </div>
    )
  }

  if (loading && !items.length) return <CatalogueSkeleton />

  return (
    <div className="space-y-6">
      {ConfirmDialogComponent}

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">{labels.plural} Catalogue</h1>
          <p className="text-muted-foreground mt-1">
            Manage your {labels.plural.toLowerCase()}, pricing and categories
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => openCatForm()} className="gap-2">
            <FolderPlus className="w-4 h-4" />
            Add Category
          </Button>
          <Button onClick={() => openItemForm()} className="gap-2" disabled={categories.length === 0}>
            <Plus className="w-4 h-4" />
            Add {labels.singular}
          </Button>
        </div>
      </div>

      {/* Search + category filter */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder={`Search ${labels.plural.toLowerCase()}...`}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button
            variant={!selectedCategory ? 'default' : 'outline'}
            size="sm"
            onClick={() => setSelectedCategory(null)}
          >
            All
          </Button>
          {categories.map((cat) => (
            <Button
              key={cat.name}
              variant={selectedCategory === cat.name ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedCategory(cat.name === selectedCategory ? null : cat.name)}
            >
              {cat.category_name}
              <span className="ml-1.5 text-xs opacity-70">
                ({items.filter((i) => i.category === cat.name).length})
              </span>
            </Button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary" />
        </div>
      ) : categories.length === 0 ? (
        <div className="bg-card rounded-lg border p-12 text-center">
          <PageIcon className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground text-lg">No categories yet</p>
          <p className="text-sm text-muted-foreground mt-2 mb-4">
            Start by creating a category, then add your {labels.plural.toLowerCase()} to it
          </p>
          <Button onClick={() => openCatForm()} className="gap-2">
            <FolderPlus className="w-4 h-4" />
            Create First Category
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          {categories.map((cat) => {
            const catItems = itemsByCategory[cat.name] || []
            const isExpanded = expandedCategories.has(cat.name)
            return (
              <div key={cat.name} className="bg-card rounded-lg border overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/30">
                  <button
                    className="flex items-center gap-2 font-semibold text-foreground hover:text-primary transition-colors"
                    onClick={() => toggleExpand(cat.name)}
                  >
                    {isExpanded ? (
                      <ChevronDown className="w-4 h-4 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-muted-foreground" />
                    )}
                    {cat.category_name}
                    <span className="text-xs font-normal text-muted-foreground ml-1">
                      ({catItems.length} {catItems.length === 1 ? labels.singular : labels.plural})
                    </span>
                  </button>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="gap-1.5 text-primary"
                      onClick={() => openItemForm(undefined, cat.name)}
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Add {labels.singular}
                    </Button>
                    <Button variant="ghost" size="icon" className="w-8 h-8" onClick={() => openCatForm(cat)}>
                      <Edit2 className="w-3.5 h-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="w-8 h-8 text-destructive hover:text-destructive"
                      onClick={() => handleDeleteCategory(cat)}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>

                {isExpanded && (
                  <div>
                    {catItems.length === 0 ? (
                      <div className="px-4 py-6 text-center">
                        <p className="text-sm text-muted-foreground">
                          No {labels.plural.toLowerCase()} in this category yet
                        </p>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="mt-2 gap-1.5 text-primary"
                          onClick={() => openItemForm(undefined, cat.name)}
                        >
                          <Plus className="w-3.5 h-3.5" />
                          Add first {labels.singular}
                        </Button>
                      </div>
                    ) : (
                      <div className="divide-y divide-border">
                        {catItems.map((item) => (
                          <div
                            key={item.name}
                            className="flex items-center gap-4 px-4 py-3 hover:bg-muted/20 transition-colors"
                          >
                            {item.thumbnail ? (
                              <img
                                src={item.thumbnail}
                                alt={item.item_name}
                                className="w-12 h-12 rounded-lg object-cover flex-shrink-0"
                              />
                            ) : (
                              <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center flex-shrink-0">
                                <PageIcon className="w-5 h-5 text-muted-foreground" />
                              </div>
                            )}

                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="font-medium text-foreground truncate">{item.item_name}</p>
                                {item.is_popular ? (
                                  <Star className="w-3.5 h-3.5 text-yellow-500 fill-yellow-500 flex-shrink-0" />
                                ) : null}
                                {item.badge && (
                                  <Badge variant="secondary" className="text-[10px] py-0 px-1.5">
                                    {item.badge}
                                  </Badge>
                                )}
                                {!item.is_active && (
                                  <Badge variant="outline" className="text-[10px] py-0 px-1.5 text-muted-foreground">
                                    Hidden
                                  </Badge>
                                )}
                              </div>
                              {item.description && (
                                <p className="text-xs text-muted-foreground truncate mt-0.5">{item.description}</p>
                              )}
                            </div>

                            <div className="text-right flex-shrink-0">
                              <p className="font-semibold text-foreground">
                                {item.price_prefix && <span className="text-xs text-muted-foreground mr-1">{item.price_prefix}</span>}
                                ₹{item.price}
                              </p>
                              {item.original_price ? (
                                <p className="text-xs text-muted-foreground line-through">₹{item.original_price}</p>
                              ) : null}
                            </div>

                            <div className="flex gap-1 flex-shrink-0">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="w-8 h-8"
                                onClick={() => openItemForm(item)}
                              >
                                <Edit2 className="w-3.5 h-3.5" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="w-8 h-8 text-destructive hover:text-destructive"
                                onClick={() => handleDeleteItem(item)}
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* ── Category Form Modal ──────────────────────────────────────────── */}
      <Dialog open={catFormOpen} onOpenChange={(open) => !open && setCatFormOpen(false)}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>{editingCat ? 'Edit Category' : 'Add Category'}</DialogTitle>
          </DialogHeader>
          <div className="py-2 space-y-3">
            <div className="space-y-1.5">
              <Label>Category Name *</Label>
              <Input
                placeholder={`e.g. ${outletType === 'wellness' ? 'Hair Services' : outletType === 'fitness' ? 'Yoga Classes' : outletType === 'fashion' ? "Men's Clothing" : 'Activities'}`}
                value={catName}
                onChange={(e) => setCatName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSaveCategory()}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCatFormOpen(false)}>Cancel</Button>
            <Button onClick={handleSaveCategory} disabled={catSaving}>
              {catSaving ? 'Saving...' : editingCat ? 'Update' : 'Add Category'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Item Form Modal ──────────────────────────────────────────────── */}
      <Dialog open={itemFormOpen} onOpenChange={(open) => !open && setItemFormOpen(false)}>
        <DialogContent className="sm:max-w-[540px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingItem ? `Edit ${labels.singular}` : `Add ${labels.singular}`}
            </DialogTitle>
          </DialogHeader>

          {/* Tabs — only for edit mode */}
          {editingItem && (
            <div className="flex border-b -mx-6 px-6">
              <button
                className={cn(
                  'px-4 py-2 text-sm font-medium border-b-2 transition-colors',
                  activeTab === 'details'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                )}
                onClick={() => setActiveTab('details')}
              >
                Details
              </button>
              <button
                className={cn(
                  'px-4 py-2 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5',
                  activeTab === 'addons'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                )}
                onClick={() => setActiveTab('addons')}
              >
                Add-ons & Options
                {itemAddons.length > 0 && (
                  <span className="text-[10px] bg-primary/10 text-primary rounded px-1.5 py-0.5 font-bold">
                    {itemAddons.length}
                  </span>
                )}
              </button>
            </div>
          )}

          {/* ── Details Tab ──────────────────────────────────────────────── */}
          {activeTab === 'details' && (
            <div className="py-2 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2 space-y-1.5">
                  <Label>{labels.singular} Name *</Label>
                  <Input
                    placeholder={
                      outletType === 'wellness' ? 'e.g. Full Body Massage' :
                      outletType === 'fitness' ? 'e.g. Morning Yoga Flow' :
                      outletType === 'fashion' ? 'e.g. Silk Kurta' :
                      'e.g. Go-Kart Race (5 laps)'
                    }
                    value={itemData.item_name}
                    onChange={(e) => setItemData({ ...itemData, item_name: e.target.value })}
                  />
                </div>

                <div className="space-y-1.5">
                  <Label>Category *</Label>
                  <Select
                    value={itemData.category}
                    onValueChange={(v) => setItemData({ ...itemData, category: v })}
                  >
                    <SelectTrigger><SelectValue placeholder="Select category" /></SelectTrigger>
                    <SelectContent>
                      {categories.map((c) => (
                        <SelectItem key={c.name} value={c.name}>{c.category_name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label>Price (₹) *</Label>
                  <Input
                    type="number"
                    min={0}
                    placeholder="0"
                    value={itemData.price}
                    onChange={(e) => setItemData({ ...itemData, price: e.target.value })}
                  />
                </div>

                <div className="space-y-1.5">
                  <Label>Price Prefix</Label>
                  <Input
                    placeholder="e.g. Starting from, From"
                    value={itemData.price_prefix}
                    onChange={(e) => setItemData({ ...itemData, price_prefix: e.target.value })}
                  />
                </div>

                <div className="space-y-1.5">
                  <Label>Original Price (₹)</Label>
                  <Input
                    type="number"
                    min={0}
                    placeholder="Strikethrough price"
                    value={itemData.original_price}
                    onChange={(e) => setItemData({ ...itemData, original_price: e.target.value })}
                  />
                </div>

                <div className="col-span-2 space-y-1.5">
                  <Label>Description</Label>
                  <Textarea
                    placeholder={
                      outletType === 'wellness' ? "Duration, what's included, technique used..." :
                      outletType === 'fitness' ? 'Intensity level, equipment needed, instructor...' :
                      'Brief description visible to customers'
                    }
                    rows={3}
                    value={itemData.description}
                    onChange={(e) => setItemData({ ...itemData, description: e.target.value })}
                  />
                </div>

                <div className="space-y-1.5">
                  <Label>Badge</Label>
                  <Select
                    value={itemData.badge || '__none__'}
                    onValueChange={(v) => setItemData({ ...itemData, badge: v === '__none__' ? '' : v })}
                  >
                    <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">None</SelectItem>
                      <SelectItem value="Best Value">Best Value</SelectItem>
                      <SelectItem value="New">New</SelectItem>
                      <SelectItem value="Sale">Sale</SelectItem>
                      <SelectItem value="Limited">Limited</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex flex-col gap-3 justify-end pb-1">
                  <div className="flex items-center justify-between">
                    <Label className="text-sm font-medium">Mark as Popular</Label>
                    <Switch
                      checked={itemData.is_popular}
                      onCheckedChange={(v) => setItemData({ ...itemData, is_popular: v })}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label className="text-sm font-medium">Visible to Customers</Label>
                    <Switch
                      checked={itemData.is_active}
                      onCheckedChange={(v) => setItemData({ ...itemData, is_active: v })}
                    />
                  </div>
                </div>
              </div>

              {!editingItem && (
                <p className="text-xs text-muted-foreground flex items-center gap-1.5 pt-1">
                  <Layers className="w-3.5 h-3.5" />
                  Add-on options (duration, intensity, extras) can be linked after saving.
                </p>
              )}
            </div>
          )}

          {/* ── Add-ons Tab ───────────────────────────────────────────────── */}
          {activeTab === 'addons' && editingItem && (
            <div className="py-3 space-y-3">
              {loadingAddons ? (
                <div className="flex justify-center py-10">
                  <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                </div>
              ) : itemAddons.length === 0 ? (
                <div className="text-center py-8 border border-dashed rounded-lg">
                  <Layers className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                  <p className="text-sm font-medium text-foreground mb-1">No add-on groups linked</p>
                  <p className="text-xs text-muted-foreground max-w-[260px] mx-auto">
                    {outletType === 'wellness'
                      ? 'Let customers choose duration (30/60/90 min), intensity, or add extras like aromatherapy.'
                      : outletType === 'fitness'
                      ? 'Let customers choose session length, difficulty level, or add equipment.'
                      : outletType === 'fashion'
                      ? 'Let customers choose size, colour, or add gift wrap.'
                      : 'Let customers choose options or add extras to this item.'}
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {itemAddons.map((addon) => (
                    <div
                      key={addon.id}
                      className={cn(
                        'border rounded-lg p-3 space-y-2 transition-opacity',
                        !addon.is_enabled && 'opacity-50'
                      )}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="font-medium text-sm truncate">{addon.group_name}</span>
                          <span className={cn(
                            'text-[9px] font-bold px-1.5 py-0.5 rounded uppercase flex-shrink-0',
                            addon.group_type === 'variation'
                              ? 'bg-primary/10 text-primary'
                              : 'bg-muted text-muted-foreground'
                          )}>
                            {addon.group_type === 'variation' ? 'Pick One' : 'Optional'}
                          </span>
                          {addon.is_required && (
                            <span className="text-[9px] text-orange-500 font-bold flex-shrink-0">REQUIRED</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <Switch
                            checked={addon.is_enabled}
                            onCheckedChange={(v) => handleToggleAddon(addon, v)}
                            className="scale-75"
                          />
                          <button
                            onClick={() => handleUnlinkAddon(addon)}
                            className="text-muted-foreground hover:text-destructive transition-colors"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                      {addon.options.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {addon.options.map((opt) => (
                            <span
                              key={opt.id}
                              className="text-[10px] bg-muted px-2 py-0.5 rounded text-muted-foreground"
                            >
                              {opt.name}
                              {opt.price > 0 ? ` +₹${opt.price}` : ''}
                              {!opt.in_stock && ' (out of stock)'}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              <Button
                variant="outline"
                size="sm"
                className="w-full gap-1.5"
                onClick={() => { setLinkSearch(''); setLinkDialogOpen(true) }}
              >
                <Link2 className="w-3.5 h-3.5" />
                Link Add-on Group
              </Button>

              <p className="text-[11px] text-muted-foreground text-center">
                Create & manage templates in{' '}
                <Link to="/addon-groups" className="text-primary underline" onClick={() => setItemFormOpen(false)}>
                  Add-on Groups
                </Link>
              </p>
            </div>
          )}

          <DialogFooter className="mt-2">
            <Button variant="outline" onClick={() => setItemFormOpen(false)}>
              {activeTab === 'addons' ? 'Close' : 'Cancel'}
            </Button>
            {activeTab === 'details' && (
              <Button onClick={handleSaveItem} disabled={itemSaving}>
                {itemSaving ? 'Saving...' : editingItem ? `Update ${labels.singular}` : `Add ${labels.singular}`}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Link Addon Group Dialog ──────────────────────────────────────── */}
      <Dialog open={linkDialogOpen} onOpenChange={setLinkDialogOpen}>
        <DialogContent className="sm:max-w-[460px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Link2 className="w-4 h-4" />
              Link Add-on Group
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
              <Input
                placeholder="Search groups..."
                value={linkSearch}
                onChange={(e) => setLinkSearch(e.target.value)}
                className="pl-9 h-8 text-sm"
              />
            </div>

            {availableGroupsToLink.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Layers className="w-6 h-6 mx-auto mb-2 opacity-40" />
                <p className="text-sm">
                  {allAddonGroups.length === 0
                    ? 'No add-on groups created yet'
                    : 'All groups are already linked'}
                </p>
                <Link
                  to="/addon-groups"
                  className="text-xs text-primary underline mt-1 block"
                  onClick={() => { setLinkDialogOpen(false); setItemFormOpen(false) }}
                >
                  Go to Add-on Groups to create one
                </Link>
              </div>
            ) : (
              <div className="space-y-1.5 max-h-64 overflow-y-auto">
                {availableGroupsToLink.map((group: any) => {
                  const gId = group.id || group.name
                  const gName = group.groupName || group.group_name || ''
                  const gType = group.groupType || group.group_type || 'addon'
                  const gItems: any[] = group.items || []
                  const isLinking = linkingGroupId === gId

                  return (
                    <div
                      key={gId}
                      className="flex items-center justify-between border rounded-lg px-3 py-2.5 hover:bg-muted/30 cursor-pointer transition-colors"
                      onClick={() => !isLinking && handleLinkAddon(gId)}
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium truncate">{gName}</span>
                          <span className={cn(
                            'text-[9px] font-bold px-1.5 py-0.5 rounded uppercase flex-shrink-0',
                            gType === 'variation' ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'
                          )}>
                            {gType === 'variation' ? 'Pick One' : 'Optional'}
                          </span>
                        </div>
                        {gItems.length > 0 && (
                          <p className="text-[10px] text-muted-foreground mt-0.5 truncate">
                            {gItems.slice(0, 4).map((i: any) => i.itemName || i.name || i.item_name).join(' · ')}
                            {gItems.length > 4 ? ` +${gItems.length - 4} more` : ''}
                          </p>
                        )}
                      </div>
                      {isLinking ? (
                        <Loader2 className="w-4 h-4 animate-spin text-muted-foreground flex-shrink-0" />
                      ) : (
                        <Plus className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setLinkDialogOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
