import { useState, useMemo, useEffect } from 'react'
import { useFrappeGetDocList, useFrappePostCall } from 'frappe-react-sdk'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Search, Plus, HelpCircle, ArrowRightLeft, Trash2, RefreshCw, Info } from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'

import { MenuCategoryItem } from '@/components/MenuCategoryItem'
import { MenuProductCard } from '@/components/MenuProductCard'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from 'sonner'
import { useConfirm } from '@/hooks/useConfirm'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import DynamicForm from '@/components/DynamicForm'
import { useFrappeGetCall } from '@/lib/frappe'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy
} from '@dnd-kit/sortable'

export default function MenuManagement() {
  const { selectedRestaurant } = useRestaurant()
  const { confirm, ConfirmDialogComponent } = useConfirm()

  const { data: restaurantDocList } = useFrappeGetDocList('Restaurant', {
    fields: ['name', 'pos_enabled', 'pos_provider', 'pos_menu_sync_enabled'],
    filters: selectedRestaurant ? [['name', '=', selectedRestaurant]] : [],
    limit: 1,
  })
  const restaurantDoc = restaurantDocList?.[0] || null
  const isPOSManaged = !!(restaurantDoc?.pos_enabled && restaurantDoc?.pos_provider && restaurantDoc?.pos_menu_sync_enabled !== 0)
  const posProvider = restaurantDoc?.pos_provider || ''

  const [isSyncingMenu, setIsSyncingMenu] = useState(false)
  const { call: syncMenuCall } = useFrappePostCall('flamezo_backend.flamezo.api.pos.sync_menu')

  const handleSyncMenu = async () => {
    if (!selectedRestaurant) return
    // Petpooja is push-only (fetch API deprecated) — direct owner to their POS tablet
    if (posProvider === 'Petpooja') {
      toast.info('Go to your Petpooja dashboard → Menu Management → Push Menu to sync.', { duration: 6000 })
      return
    }
    setIsSyncingMenu(true)
    try {
      await syncMenuCall({ restaurant_id: selectedRestaurant })
      toast.success(`Menu sync requested from ${posProvider}. This may take a few seconds.`)
      setTimeout(() => { mutateCategories(); mutateProducts() }, 3000)
    } catch {
      toast.error('Menu sync failed')
    } finally {
      setIsSyncingMenu(false)
    }
  }

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  // UI State
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null)
  const [isHelpOpen, setIsHelpOpen] = useState(false)

  // Sidebar resize
  const [sidebarWidth, setSidebarWidth] = useState(320)
  const [isResizing, setIsResizing] = useState(false)

  // Track which parent categories are expanded in the sidebar
  const [expandedParents, setExpandedParents] = useState<Set<string>>(new Set())

  // Form handling
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [formConfig, setFormConfig] = useState<{
    doctype: string
    docname?: string
    mode: 'create' | 'edit'
    title: string
    initialData?: Record<string, any>
  } | null>(null)
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([])

  // API Hooks
  const { call: updateDoc } = useFrappePostCall('flamezo_backend.flamezo.api.documents.update_document')
  const { call: deleteDoc } = useFrappePostCall('flamezo_backend.flamezo.api.documents.delete_multiple_docs')
  const { call: updateOrder } = useFrappePostCall('flamezo_backend.flamezo.api.categories.update_category_order')
  const { call: updateProductOrder } = useFrappePostCall('flamezo_backend.flamezo.api.products.update_product_order')

  // Fetch ALL categories (flat list including sub-categories)
  const {
    data: categories,
    isLoading: categoriesLoading,
    mutate: mutateCategories
  } = useFrappeGetDocList('Menu Category', {
    fields: ['name', 'category_name', 'display_name', 'display_order', 'is_special', 'is_active', 'parent_category'],
    filters: selectedRestaurant ? [['restaurant', '=', selectedRestaurant]] : [],
    orderBy: { field: 'display_order', order: 'asc' },
    limit: 200
  })

  // Derived: top-level and sub-category maps
  const parentCategories = useMemo(() =>
    (categories || []).filter((c: any) => !c.parent_category),
    [categories]
  )

  // subcategoryMap: parent name → [children]
  const subcategoryMap = useMemo(() => {
    const map: Record<string, any[]> = {}
    ;(categories || []).forEach((c: any) => {
      if (c.parent_category) {
        if (!map[c.parent_category]) map[c.parent_category] = []
        map[c.parent_category].push(c)
      }
    })
    return map
  }, [categories])

  // Set initial category selection
  useMemo(() => {
    if (!selectedCategoryId && parentCategories && parentCategories.length > 0) {
      setSelectedCategoryId(parentCategories[0].name)
    }
  }, [parentCategories, selectedCategoryId])

  const activeCategory = useMemo(() =>
    (categories || []).find((c: any) => c.name === selectedCategoryId),
    [categories, selectedCategoryId]
  )

  // Hierarchical categories for selection menus (parents -> children)

  // Fetch Products
  const {
    data: productsData,
    isLoading: productsLoading,
    mutate: mutateProducts
  } = useFrappeGetCall('flamezo_backend.flamezo.api.products.get_products', {
    restaurant_id: selectedRestaurant,
    category: searchQuery ? undefined : activeCategory?.category_name,
    search: searchQuery || undefined,
    include_inactive: 1,
    limit: 500
  }, (selectedRestaurant && (activeCategory || searchQuery)) ? `menu-products-${activeCategory?.name || 'search'}-${searchQuery}` : null)
  
  // Hierarchical categories for selection menus (parents -> children)
  const hierarchicalCategories = useMemo(() => {
    if (!categories) return []
    const records = [...categories]
    const sorted: any[] = []
    const parents = records.filter(r => !r.parent_category)
    const children = records.filter(r => r.parent_category)

    // Sort parents by display_order, then display_name
    parents.sort((a, b) => {
      if ((a.display_order || 0) !== (b.display_order || 0)) {
        return (a.display_order || 0) - (b.display_order || 0)
      }
      return (a.display_name || a.category_name || '').localeCompare(b.display_name || b.category_name || '')
    })

    parents.forEach(p => {
      sorted.push(p)
      const subs = children.filter(c => c.parent_category === p.name)
      // Sort children by display_order, then display_name
      subs.sort((a, b) => {
        if ((a.display_order || 0) !== (b.display_order || 0)) {
          return (a.display_order || 0) - (b.display_order || 0)
        }
        return (a.display_name || a.category_name || '').localeCompare(b.display_name || b.category_name || '')
      })
      sorted.push(...subs)
    })

    // Orphans
    const orphans = children.filter(c => !parents.some(p => p.name === c.parent_category))
    if (orphans.length > 0) sorted.push(...orphans)

    return sorted
  }, [categories])

  const products = productsData?.message?.data?.products || []

  const editingProduct = useMemo(() => {
    if (formConfig?.doctype === 'Menu Product' && formConfig?.docname && products) {
      return products.find((p: any) => p.docname === formConfig.docname || p.id === formConfig.docname)
    }
    return null
  }, [formConfig, products])

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

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event
    if (over && active.id !== over.id && parentCategories) {
      const oldIndex = parentCategories.findIndex((c: any) => c.name === active.id)
      const newIndex = parentCategories.findIndex((c: any) => c.name === over.id)
      const newOrder = arrayMove(parentCategories, oldIndex, newIndex)
      mutateCategories(newOrder, false)
      try {
        const updates = newOrder.map((c: any, index: number) => ({ name: c.name, display_order: index + 1 }))
        await updateOrder({ category_orders: updates })
        toast.success('Category order updated')
      } catch {
        toast.error('Failed to update order')
        mutateCategories()
      }
    }
  }

  const handleProductDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event
    if (over && active.id !== over.id && products) {
      const oldIndex = products.findIndex((p: any) => p.docname === active.id)
      const newIndex = products.findIndex((p: any) => p.docname === over.id)
      const newOrder = arrayMove(products, oldIndex, newIndex)
      mutateProducts({
        message: { ...productsData.message, data: { ...productsData.message.data, products: newOrder } }
      }, false)
      try {
        const updates = newOrder.map((p: any, index: number) => ({ name: p.docname, display_order: index + 1 }))
        await updateProductOrder({ product_orders: updates })
        toast.success('Product order updated')
      } catch {
        toast.error('Failed to update product order')
        mutateProducts()
      }
    }
  }

  const handleToggleProductStatus = async (product: any, status: boolean) => {
    try {
      await updateDoc({ doctype: 'Menu Product', name: product.docname, doc_data: { is_active: status ? 1 : 0 } })
      mutateProducts()
      toast.success(`${product.name} status updated`)
    } catch { toast.error('Failed to update status') }
  }

  const handleToggleCategoryStatus = async (category: any, status: boolean) => {
    try {
      await updateDoc({ doctype: 'Menu Category', name: category.name, doc_data: { is_active: status ? 1 : 0 } })
      toast.success(`${category.display_name || category.category_name} status updated`)
      mutateCategories()
    } catch { toast.error('Failed to update status') }
  }

  const handleDeleteCategory = async (category: any) => {
    const subs = subcategoryMap[category.name] || []
    const description = subs.length > 0
      ? `Are you sure you want to delete "${category.display_name || category.category_name}"? This will permanently delete its ${subs.length} sub-categor${subs.length > 1 ? 'ies' : 'y'} and ALL products within. This action cannot be undone.`
      : `Are you sure you want to delete "${category.display_name || category.category_name}"? This will permanently delete ALL products within this category and all their data. This action cannot be undone.`

    const confirmed = await confirm({ title: 'Delete Category', description, variant: 'destructive' })
    if (confirmed) {
      try {
        const response = await deleteDoc({ doctype: 'Menu Category', names: [category.name] })
        if (response.message?.success) {
          toast.success('Category deleted')
          mutateCategories()
          if (selectedCategoryId === category.name) setSelectedCategoryId(null)
        } else {
          toast.error(response.message?.errors?.[0] || 'Failed to delete category')
        }
      } catch { toast.error('Failed to delete category') }
    }
  }

  const handleDeleteProduct = async (product: any) => {
    const confirmed = await confirm({
      title: 'Delete Product',
      description: `Are you sure you want to delete "${product.name}"?`,
      variant: 'destructive'
    })
    if (!confirmed) return
    try {
      const response = await deleteDoc({ doctype: 'Menu Product', names: [product.docname], force: true })
      if (response.message?.success) {
        mutateProducts()
        toast.success('Product deleted')
      } else {
        toast.error(response.message?.errors?.[0] || 'Failed to delete product')
      }
    } catch { toast.error('Failed to delete product') }
  }

  const handleMoveProduct = async (productDocname: string, targetCategory: string) => {
    try {
      await updateDoc({ doctype: 'Menu Product', name: productDocname, doc_data: { category: targetCategory } })
      toast.success('Product moved successfully')
      mutateProducts()
    } catch { toast.error('Failed to move product') }
  }

  const handleBulkMove = async (targetCategory: string) => {
    const confirmed = await confirm({
      title: 'Bulk Move Products',
      description: `Are you sure you want to move ${selectedProductIds.length} products to another category?`,
    })
    if (!confirmed) return
    try {
      await Promise.all(selectedProductIds.map(id =>
        updateDoc({ doctype: 'Menu Product', name: id, doc_data: { category: targetCategory } })
      ))
      toast.success(`${selectedProductIds.length} products moved successfully`)
      setSelectedProductIds([])
      mutateProducts()
    } catch { toast.error('Failed to move products') }
  }

  const handleBulkDelete = async () => {
    const confirmed = await confirm({
      title: 'Bulk Delete Products',
      description: `Are you sure you want to delete ${selectedProductIds.length} products? This action cannot be undone.`,
      variant: 'destructive'
    })
    if (!confirmed) return
    try {
      const response = await deleteDoc({ doctype: 'Menu Product', names: selectedProductIds, force: true })
      if (response.message?.success) {
        toast.success(`${selectedProductIds.length} products deleted`)
        setSelectedProductIds([])
        mutateProducts()
      } else {
        toast.error(response.message?.errors?.[0] || 'Failed to delete products')
      }
    } catch { toast.error('Failed to delete products') }
  }

  const toggleSelectProduct = (id: string, checked: boolean) => {
    if (checked) setSelectedProductIds(prev => [...prev, id])
    else setSelectedProductIds(prev => prev.filter(pId => pId !== id))
  }

  const toggleSelectAll = (checked: boolean) => {
    if (checked) setSelectedProductIds(products.map((p: any) => p.docname))
    else setSelectedProductIds([])
  }

  const openForm = (
    doctype: string,
    mode: 'create' | 'edit',
    docname?: string,
    initialData?: Record<string, any>
  ) => {
    setFormConfig({
      doctype,
      docname,
      mode,
      title: `${mode === 'create' ? 'Add' : 'Edit'} ${doctype === 'Menu Category' ? 'Category' : 'Item'}`,
      initialData,
    })
    setIsFormOpen(true)
  }

  const handleFormSave = () => {
    setIsFormOpen(false)
    if (formConfig?.doctype === 'Menu Category') mutateCategories()
    else mutateProducts()
  }

  const toggleParentExpand = (parentName: string) => {
    setExpandedParents(prev => {
      const next = new Set(prev)
      if (next.has(parentName)) next.delete(parentName)
      else next.add(parentName)
      return next
    })
  }

  // Filter: when searching, show all top-level categories whose name or any sub name matches
  const filteredParentCategories = parentCategories?.filter((c: any) => {
    if (!searchQuery) return true
    const matchesSelf = (c.display_name || c.category_name || c.name).toLowerCase().includes(searchQuery.toLowerCase())
    const matchesSub = (subcategoryMap[c.name] || []).some((s: any) =>
      (s.display_name || s.category_name || s.name).toLowerCase().includes(searchQuery.toLowerCase())
    )
    return matchesSelf || matchesSub
  })

  const isSubcategorySelected = useMemo(() =>
    selectedCategoryId ? !!(categories || []).find((c: any) => c.name === selectedCategoryId && c.parent_category) : false,
    [selectedCategoryId, categories]
  )

  return (
    <div className="flex flex-col h-[calc(100vh-100px)] -m-4 sm:-m-6 overflow-hidden">
      <header className="bg-[#1e2433] dark:bg-card text-white dark:text-foreground p-4 flex items-center justify-between shadow-lg z-10 border-b dark:border-border">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-lg font-bold tracking-tight uppercase">Menu Management</h1>
            <p className="text-[10px] text-slate-400 dark:text-muted-foreground uppercase tracking-widest">
              {isPOSManaged ? `Synced from ${posProvider}` : 'Centralized Menu Control'}
            </p>
          </div>
          <Badge variant="outline" className="bg-slate-700/50 dark:bg-muted border-slate-600 dark:border-border text-slate-300 dark:text-muted-foreground gap-1.5 px-2 py-0.5">
            <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
            Live
          </Badge>
          {isPOSManaged && (
            <Badge variant="outline" className="bg-blue-900/40 border-blue-600/50 text-blue-300 gap-1.5 px-2 py-0.5">
              <Info className="h-3 w-3" />
              {posProvider} Managed
            </Badge>
          )}
        </div>
        {isPOSManaged && (
          <Button
            variant="outline" size="sm"
            className="bg-slate-700/50 border-slate-600 text-slate-200 hover:bg-slate-600 hover:text-white gap-2"
            onClick={handleSyncMenu}
            disabled={isSyncingMenu}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isSyncingMenu ? 'animate-spin' : ''}`} />
            {isSyncingMenu ? 'Syncing...' : 'Sync Menu Now'}
          </Button>
        )}
      </header>

      {isPOSManaged && (
        <div className="bg-blue-50 dark:bg-blue-950/30 border-b border-blue-200 dark:border-blue-900/50 px-6 py-2.5 flex items-center gap-3">
          <Info className="h-4 w-4 text-blue-500 shrink-0" />
          <p className="text-sm text-blue-700 dark:text-blue-300">
            This menu is managed by <strong>{posProvider}</strong>. Prices, items, and categories sync automatically from your POS.
            You can only update <strong>photos</strong> here — everything else is controlled from your {posProvider} tablet.
          </p>
        </div>
      )}

      <div className="flex-1 flex overflow-hidden bg-muted/30 dark:bg-background">
        {/* Resizable Sidebar */}
        <div
          className="flex flex-col bg-card border-r relative"
          style={{ width: `${sidebarWidth}px` }}
        >
          <div className="p-4 border-b space-y-4 bg-muted/20">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search category and product"
                className="pl-9 bg-background shadow-sm"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            {!isPOSManaged && (
              <Button
                className="w-full bg-[#ea580c] hover:bg-[#c2410c] text-white shadow-md"
                onClick={() => openForm('Menu Category', 'create', undefined, { restaurant: selectedRestaurant, is_active: 1 })}
              >
                <Plus className="h-4 w-4 mr-2" />
                ADD NEW CATEGORY
              </Button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
            {categoriesLoading ? (
              Array(6).fill(0).map((_, i) => <Skeleton key={i} className="h-14 w-full rounded-lg" />)
            ) : (
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={handleDragEnd}
              >
                <SortableContext
                  items={filteredParentCategories?.map((c: any) => c.name) || []}
                  strategy={verticalListSortingStrategy}
                  disabled={!!searchQuery || isPOSManaged}
                >
                  {filteredParentCategories?.map((category: any) => {
                    const subs = subcategoryMap[category.name] || []
                    const isParentExpanded = expandedParents.has(category.name) || subs.length === 0
                    return (
                      <MenuCategoryItem
                        key={category.name}
                        category={category}
                        isActive={selectedCategoryId === category.name}
                        onClick={() => setSelectedCategoryId(category.name)}
                        onToggleStatus={(status) => handleToggleCategoryStatus(category, status)}
                        onEdit={() => openForm('Menu Category', 'edit', category.name)}
                        onDelete={() => handleDeleteCategory(category)}
                        posManaged={isPOSManaged}
                        subcategories={subs}
                        activeSubcategoryId={selectedCategoryId}
                        isExpanded={subs.length > 0 ? isParentExpanded : undefined}
                        onToggleExpand={() => toggleParentExpand(category.name)}
                        onAddSubcategory={!isPOSManaged ? () => openForm('Menu Category', 'create', undefined, {
                          restaurant: selectedRestaurant,
                          is_active: 1,
                          parent_category: category.name,
                        }) : undefined}
                        onSubcategoryClick={(sub) => setSelectedCategoryId(sub.name)}
                        onSubcategoryEdit={(sub) => openForm('Menu Category', 'edit', sub.name)}
                        onSubcategoryDelete={(sub) => handleDeleteCategory(sub)}
                        onSubcategoryToggleStatus={(sub, status) => handleToggleCategoryStatus(sub, status)}
                      />
                    )
                  })}
                </SortableContext>
              </DndContext>
            )}
          </div>

          {/* Resize Handle */}
          <div
            className={cn(
              "absolute top-0 -right-1 w-2 h-full cursor-col-resize hover:bg-primary/20 transition-colors z-20",
              isResizing && "bg-primary/40"
            )}
            onMouseDown={() => setIsResizing(true)}
          />
        </div>

        {/* Main Product List */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {activeCategory || searchQuery ? (
            <>
              <header className="p-4 sm:p-6 bg-card border-b flex flex-col gap-4 sticky top-0 z-[5]">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div>
                      <h2 className="text-xl font-bold text-foreground uppercase tracking-tight">
                        {searchQuery
                          ? `Results for "${searchQuery}"`
                          : (activeCategory?.display_name || activeCategory?.category_name)}
                      </h2>
                      {/* Breadcrumb for subcategories */}
                      {!searchQuery && isSubcategorySelected && (() => {
                        const parent = (categories || []).find(
                          (c: any) => c.name === activeCategory?.parent_category
                        )
                        return parent ? (
                          <p className="text-xs text-muted-foreground mt-0.5">
                            <button
                              className="hover:underline"
                              onClick={() => setSelectedCategoryId(parent.name)}
                            >
                              {parent.display_name || parent.category_name}
                            </button>
                            {' › '}
                            <span>{activeCategory?.display_name || activeCategory?.category_name}</span>
                          </p>
                        ) : null
                      })()}
                    </div>
                    {!isPOSManaged && products.length > 0 && (
                      <div className="flex items-center gap-2 px-3 py-1 bg-muted rounded-full border">
                        <Checkbox
                          checked={selectedProductIds.length === products.length && products.length > 0}
                          onCheckedChange={(checked) => toggleSelectAll(!!checked)}
                          className="h-4 w-4 rounded-sm border-muted-foreground/30 data-[state=checked]:bg-orange-500 data-[state=checked]:border-orange-500"
                        />
                        <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">Select All</span>
                      </div>
                    )}
                  </div>
                  {!isPOSManaged && (
                    <Button
                      className="bg-[#ea580c] hover:bg-[#c2410c]"
                      onClick={() => openForm('Menu Product', 'create')}
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      ADD NEW ITEM
                    </Button>
                  )}
                </div>

                {!isPOSManaged && selectedProductIds.length > 0 && (
                  <div className="flex items-center justify-between bg-orange-50 dark:bg-orange-950/20 border border-orange-200 dark:border-orange-900/50 p-3 rounded-xl animate-in fade-in slide-in-from-top-2 duration-300">
                    <div className="flex items-center gap-3">
                      <div className="h-6 w-6 bg-orange-500 text-white rounded-full flex items-center justify-center text-[10px] font-bold">
                        {selectedProductIds.length}
                      </div>
                      <span className="text-sm font-semibold text-orange-700 dark:text-orange-400">Products Selected</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="outline" size="sm" className="h-9 gap-2 border-orange-200 dark:border-orange-900/50 hover:bg-orange-100 dark:hover:bg-orange-950/30 text-orange-700 dark:text-orange-400">
                            <ArrowRightLeft className="h-4 w-4" />
                            Move To
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-56 max-h-60 overflow-y-auto custom-scrollbar">
                          <DropdownMenuLabel>Move to Category</DropdownMenuLabel>
                          <DropdownMenuSeparator />
                          {hierarchicalCategories?.filter((c: any) => c.name !== selectedCategoryId).map((cat: any) => (
                            <DropdownMenuItem key={cat.name} onClick={() => handleBulkMove(cat.name)}>
                              <span className={cn(
                                "flex items-center gap-1",
                                cat.parent_category && "pl-4 text-muted-foreground"
                              )}>
                                {cat.parent_category && <span className="opacity-50">↳</span>}
                                {cat.display_name || cat.category_name}
                              </span>
                            </DropdownMenuItem>
                          ))}
                        </DropdownMenuContent>
                      </DropdownMenu>
                      <Button variant="destructive" size="sm" className="h-9 gap-2" onClick={handleBulkDelete}>
                        <Trash2 className="h-4 w-4" />
                        Delete
                      </Button>
                      <Button variant="ghost" size="sm" className="h-9 text-muted-foreground hover:text-foreground" onClick={() => setSelectedProductIds([])}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </header>

              <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 custom-scrollbar">
                {productsLoading ? (
                  Array(4).fill(0).map((_, i) => <Skeleton key={i} className="h-28 w-full rounded-xl" />)
                ) : products.length > 0 ? (
                  <DndContext
                    sensors={sensors}
                    collisionDetection={closestCenter}
                    onDragEnd={handleProductDragEnd}
                  >
                    <SortableContext
                      items={products.map((p: any) => p.docname)}
                      strategy={verticalListSortingStrategy}
                      disabled={!!searchQuery || isPOSManaged}
                    >
                      <div className="grid grid-cols-1 gap-4">
                        {products.map((product: any) => (
                          <MenuProductCard
                            key={product.docname}
                            product={product}
                            onEdit={() => openForm('Menu Product', 'edit', product.docname)}
                            onDelete={() => handleDeleteProduct(product)}
                            onToggleStatus={(status) => handleToggleProductStatus(product, status)}
                            isSelected={selectedProductIds.includes(product.docname)}
                            onSelect={(checked) => toggleSelectProduct(product.docname, checked)}
                            categories={hierarchicalCategories}
                            onMove={(targetCategory) => handleMoveProduct(product.docname, targetCategory)}
                            posManaged={isPOSManaged}
                          />
                        ))}
                      </div>
                    </SortableContext>
                  </DndContext>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center text-center p-10">
                    <p className="text-muted-foreground italic">No products found.</p>
                    {!isPOSManaged && (
                      <Button
                        className="mt-4 bg-[#ea580c] hover:bg-[#c2410c]"
                        onClick={() => openForm('Menu Product', 'create')}
                      >
                        <Plus className="h-4 w-4 mr-2" />
                        Add First Item
                      </Button>
                    )}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-10">
              <h3 className="text-xl font-bold text-foreground">Select a Category</h3>
              <p className="text-muted-foreground mt-2">Choose a category to start managing items.</p>
            </div>
          )}
        </main>
      </div>

      {/* Slide-over Form */}
      <Sheet open={isFormOpen} onOpenChange={setIsFormOpen}>
        <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
          <SheetHeader className="mb-6">
            <SheetTitle className="text-2xl font-bold">
              {isPOSManaged && formConfig?.doctype === 'Menu Product' ? 'Update Photo' : formConfig?.title}
            </SheetTitle>
            {isPOSManaged && formConfig?.doctype === 'Menu Product' && (
              <p className="text-sm text-muted-foreground">
                Prices, names, and descriptions are managed by {posProvider}. Only the photo can be updated here.
              </p>
            )}
            {formConfig?.doctype === 'Menu Category' && formConfig?.initialData?.parent_category && (
              <p className="text-sm text-muted-foreground">
                Creating sub-category under <strong>
                  {(categories || []).find((c: any) => c.name === formConfig.initialData?.parent_category)?.display_name || formConfig.initialData?.parent_category}
                </strong>
              </p>
            )}
          </SheetHeader>
          {formConfig && (
            <DynamicForm
              doctype={formConfig.doctype}
              docname={formConfig.docname}
              mode={formConfig.mode}
              onSave={handleFormSave}
              onCancel={() => setIsFormOpen(false)}
              hideFields={
                formConfig.doctype === 'Menu Category'
                  ? ['category_id', 'restaurant', 'display_name', 'display_order']
                  : isPOSManaged
                    ? ['product_id', 'seo_slug', 'category_name', 'restaurant', 'main_category',
                       'has_no_media', 'display_order', 'product_name', 'price', 'original_price',
                       'description', 'is_vegetarian', 'is_active', 'category', 'calories']
                    : ['product_id', 'seo_slug', 'category_name', 'restaurant', 'main_category', 'has_no_media', 'display_order']
              }
              readOnlyFields={['restaurant']}
              initialData={
                formConfig.mode === 'create'
                  ? {
                      restaurant: selectedRestaurant,
                      category: formConfig.doctype === 'Menu Product' ? selectedCategoryId : undefined,
                      is_active: 1,
                      ...(formConfig.initialData || {})
                    }
                  : (editingProduct || formConfig.initialData || {})
              }
            />
          )}
        </SheetContent>
      </Sheet>

      {ConfirmDialogComponent}

      {/* Help Trigger */}
      <div className="fixed bottom-6 right-6 z-50">
        <Button
          variant="secondary" size="icon" className="h-12 w-12 rounded-full shadow-2xl bg-card border-2 border-border hover:scale-110 transition-all"
          onClick={() => setIsHelpOpen(true)}
        >
          <HelpCircle className="h-6 w-6 text-foreground" />
        </Button>
      </div>

      <Dialog open={isHelpOpen} onOpenChange={setIsHelpOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Management Guide</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="p-4 bg-muted/50 rounded-xl space-y-2">
              <h4 className="font-bold text-sm">Sub-Categories</h4>
              <p className="text-xs text-muted-foreground">Click the <strong>+</strong> icon on any category to add a sub-category inside it. Products can be assigned to either a parent or sub-category. Max 2 levels deep.</p>
            </div>
            <div className="p-4 bg-muted/50 rounded-xl space-y-2">
              <h4 className="font-bold text-sm">Resize Sidebar</h4>
              <p className="text-xs text-muted-foreground">Drag the right edge of the category list to adjust width if names are long.</p>
            </div>
            <div className="p-4 bg-muted/50 rounded-xl space-y-2">
              <h4 className="font-bold text-sm">Category Deletion</h4>
              <p className="text-xs text-muted-foreground">Deleting a parent category also deletes all its sub-categories and ALL products inside. This is permanent.</p>
            </div>
          </div>
        </DialogContent>
      </Dialog>

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
