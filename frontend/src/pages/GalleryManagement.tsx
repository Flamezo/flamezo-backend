import { useState, useMemo, useEffect } from 'react'
import { useFrappePostCall, useFrappeUpdateDoc, useFrappeDeleteDoc, useFrappeGetCall } from '@/lib/frappe'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { 
  Plus, 
  Edit, 
  Trash2, 
  Image as ImageIcon, 
  Search, 
  Loader2,
  CheckCircle2,
  AlertCircle,
  Layers,
  LayoutGrid,
  Folder,
  ChevronRight,
  FolderOpen,
  ArrowLeft,
  Utensils,
  Calendar,
  Zap,
  Crown
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Progress } from '@/components/ui/progress'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { toast } from 'sonner'
import { cn, getFrappeError } from '@/lib/utils'
import { useDataTable } from '@/hooks/useDataTable'
import { uploadToR2, getMediaType } from '@/lib/r2Upload'
import SilverMediaUpload from '@/components/SilverMediaUpload'

export default function GalleryManagement() {
  const navigate = useNavigate()
  const { selectedRestaurant } = useRestaurant()
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<any>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [itemToDelete, setItemToDelete] = useState<any>(null)
  const [activeTab, setActiveTab] = useState(() => {
    return localStorage.getItem('gallery-management-active-tab') || 'selection'
  })
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null)
  const [uploadCategory, setUploadCategory] = useState<string>('Gallery Uploads')

  const CATEGORIES = ['Branding', 'Food & Menu', 'Events', 'Gallery Uploads']

  // Persist tab selection
  useEffect(() => {
    localStorage.setItem('gallery-management-active-tab', activeTab)
  }, [activeTab])

  // Fetch Media Pool
  const { data: poolData, isLoading: isPoolLoading, mutate: mutatePool } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.restaurant.get_restaurant_media_pool',
    { restaurant_id: selectedRestaurant },
    selectedRestaurant ? `media-pool-${selectedRestaurant}` : null
  )

  const mediaPool = useMemo(() => {
    const response = (poolData as any)?.message || poolData;
    return response?.data?.media || [];
  }, [poolData])

  const initialFilters = useMemo(() => {
    if (!selectedRestaurant) return []
    return [
        { fieldname: 'restaurant', operator: '=', value: selectedRestaurant },
        { fieldname: 'is_selected', operator: '=', value: 1 }
    ]
  }, [selectedRestaurant])

  const {
    data: selectedItems,
    isLoading: isSelectedLoading,
    mutate: mutateSelected,
    totalCount: selectedCount,
    searchQuery,
    setSearchQuery
  } = useDataTable({
    doctype: 'Restaurant Gallery Item',
    fields: ['name', 'restaurant', 'media_type', 'url', 'title', 'sort_order', 'is_selected'],
    initialFilters,
    searchFields: ['title'],
    orderBy: { field: 'sort_order', order: 'asc' },
    initialPageSize: 100, // Show all selected items
    debugId: `selected-gallery-${selectedRestaurant}`
  })

  const { call: createGalleryItem } = useFrappePostCall('frappe.client.insert')
  const { updateDoc: updateGalleryItem } = useFrappeUpdateDoc()
  const { deleteDoc: deleteGalleryItem } = useFrappeDeleteDoc()

  const handleUpload = async (files: File[]) => {
    if (!selectedRestaurant) return
    if (selectedCount + files.length > 25) {
        toast.error('Gallery limit reached', { description: 'You can only have up to 25 items in your gallery.' })
        return
    }

    try {
      for (const file of files) {
        const mediaType = getMediaType(file)
        const activeRole = uploadCategory === 'Events' ? 'event_image' : 'restaurant_gallery_image'

        const uploadResult = await uploadToR2({
          ownerDoctype: 'Restaurant',
          ownerName: selectedRestaurant,
          mediaRole: activeRole,
          file,
        })

        await createGalleryItem({
          doc: {
            doctype: 'Restaurant Gallery Item',
            restaurant: selectedRestaurant,
            media_type: mediaType === 'video' ? 'Video' : 'Image',
            url: uploadResult.primary_url,
            title: file.name.split('.')[0],
            sort_order: selectedCount + 1,
            is_selected: 1,
            source: uploadCategory // Use the selected upload category as source/category
          }
        })
      }
      
      toast.success(`${files.length} items added to ${uploadCategory}`)
      mutateSelected()
      mutatePool()
      setIsUploadDialogOpen(false)
    } catch (error: any) {
      toast.error('Failed to upload', { description: getFrappeError(error) })
    }
  }

  const handleToggleSelection = async (media: any) => {
    if (!selectedRestaurant) return

    try {
        if (media.is_in_gallery && media.gallery_item_name) {
            const newStatus = media.is_selected ? 0 : 1
            
            if (newStatus === 1 && selectedCount >= 25) {
                toast.error('Gallery is full', { description: 'Remove some items before adding new ones.' })
                return
            }

            await updateGalleryItem('Restaurant Gallery Item', media.gallery_item_name, {
                is_selected: newStatus
            })
            toast.success(newStatus ? 'Added to gallery' : 'Removed from gallery')
        } else {
            if (selectedCount >= 25) {
                toast.error('Gallery is full', { description: 'Remove some items before adding new ones.' })
                return
            }

            // Create new record from pool
            await createGalleryItem({
                doc: {
                    doctype: 'Restaurant Gallery Item',
                    restaurant: selectedRestaurant,
                    media_type: media.type === 'video' ? 'Video' : 'Image',
                    url: media.url,
                    title: media.source_title || 'Imported Asset',
                    sort_order: selectedCount + 1,
                    is_selected: 1,
                    source: media.source_type || 'Import'
                }
            })
            toast.success('Added to gallery')
        }
        mutateSelected()
        mutatePool()
    } catch (error: any) {
        toast.error('Action failed', { description: getFrappeError(error) })
    }
  }

  const handleUpdateItem = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingItem) return

    try {
      const itemName = editingItem.name || editingItem.gallery_item_name;
      
      if (itemName) {
        await updateGalleryItem('Restaurant Gallery Item', itemName, {
          title: editingItem.title,
          sort_order: parseInt(editingItem.sort_order) || 0,
          media_type: editingItem.media_type
        })
      } else {
        // Create new from Discovery Pool
        await createGalleryItem({
            doc: {
                doctype: 'Restaurant Gallery Item',
                restaurant: selectedRestaurant,
                media_type: editingItem.media_type,
                url: editingItem.url,
                title: editingItem.title,
                sort_order: parseInt(editingItem.sort_order) || 0,
                is_selected: 1,
                source: editingItem.source_type || 'Pool'
            }
        })
      }
      
      toast.success('Gallery updated')
      mutateSelected()
      mutatePool()
      setEditingItem(null)
    } catch (error: any) {
      toast.error('Failed to update', { description: getFrappeError(error) })
    }
  }

  const handleDeleteItem = async () => {
    if (!itemToDelete) return
    try {
      await deleteGalleryItem('Restaurant Gallery Item', itemToDelete.name)
      toast.success('Permanently removed')
      mutateSelected()
      mutatePool()
      setDeleteDialogOpen(false)
      setItemToDelete(null)
    } catch (error: any) {
      toast.error('Delete failed', { description: getFrappeError(error) })
    }
  }

  if (!selectedRestaurant) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-center p-8">
        <ImageIcon className="h-16 w-16 text-muted-foreground/20 mb-4" />
        <h3 className="text-xl font-semibold mb-2">Restaurant Required</h3>
        <p className="text-muted-foreground max-w-sm">Please select a restaurant to manage its media assets.</p>
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-8 space-y-8 max-w-7xl mx-auto pb-24 transition-all duration-300">
      {/* Professional Header Section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 border-b border-border pb-8">
        <div className="flex items-start gap-4">
          <div className="w-14 h-14 rounded-xl bg-primary/10 flex items-center justify-center text-primary shrink-0 border border-primary/20">
            <LayoutGrid className="h-7 w-7" />
          </div>
          <div className="space-y-1">
            <h2 className="text-2xl font-bold tracking-tight text-foreground">Gallery Management</h2>
            <p className="text-muted-foreground text-sm font-medium">
              Curate and manage your restaurant's visual showcase for the consumer application.
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
            <div className={cn(
                "px-4 py-2 rounded-lg flex items-center gap-2 border bg-background transition-all",
                selectedCount >= 25 
                    ? "border-destructive/30 text-destructive" 
                    : "border-primary/20 text-primary"
            )}>
                <div className={cn(
                    "w-1.5 h-1.5 rounded-full",
                    selectedCount >= 25 ? "bg-destructive animate-pulse" : "bg-primary"
                )} />
                <span className="text-xs font-bold uppercase tracking-wider">
                    {selectedCount} / 25 Selected
                </span>
            </div>
            
            <Button 
                onClick={() => setIsUploadDialogOpen(true)} 
                className="rounded-lg h-11 px-6 bg-primary hover:bg-primary/90 text-primary-foreground font-bold shadow-sm"
            >
                <Plus className="h-4 w-4 mr-2" />
                Upload Asset
            </Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => { setActiveTab(v); setSelectedFolder(null); }} className="w-full">
        <div className="flex justify-center mb-8">
            <TabsList className="bg-muted/30 p-1.5 rounded-xl border border-border inline-flex h-14 items-center">
                <TabsTrigger 
                    value="selection" 
                    className="rounded-lg px-8 py-2.5 data-[state=active]:bg-background data-[state=active]:text-primary data-[state=active]:shadow-sm font-bold text-xs transition-all h-full"
                >
                    <CheckCircle2 className="h-3.5 w-3.5 mr-2" />
                    Active Showcase
                </TabsTrigger>
                <TabsTrigger 
                    value="pool" 
                    className="rounded-lg px-8 py-2.5 data-[state=active]:bg-background data-[state=active]:text-primary data-[state=active]:shadow-sm font-bold text-xs transition-all h-full"
                >
                    <Layers className="h-3.5 w-3.5 mr-2" />
                    Media Library
                </TabsTrigger>
            </TabsList>
        </div>

        <TabsContent value="selection" className="space-y-6 outline-none">
          <Card className="border border-border shadow-sm bg-card rounded-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-border bg-muted/5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h3 className="font-bold text-base">Curated Showcase</h3>
                <p className="text-xs text-muted-foreground font-medium">Items currently visible in your public gallery.</p>
              </div>
              <div className="relative w-full sm:w-72">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input 
                      placeholder="Search items..." 
                      className="pl-9 h-10 rounded-lg bg-background border-border"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                  />
              </div>
            </div>
            
            <CardContent className="p-6">
              {isSelectedLoading ? (
                <div className="py-24 flex flex-col items-center justify-center gap-3">
                  <Loader2 className="h-8 w-8 animate-spin text-primary/40" />
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-widest">Syncing items...</p>
                </div>
              ) : selectedItems.length === 0 ? (
                <div className="py-32 text-center flex flex-col items-center">
                  <div className="w-16 h-16 rounded-full bg-muted/20 flex items-center justify-center mb-6 border border-border/50">
                    <AlertCircle className="h-8 w-8 text-muted-foreground/30" />
                  </div>
                  <h3 className="text-lg font-bold">No Items Selected</h3>
                  <p className="text-muted-foreground max-w-sm mx-auto mt-2 text-sm font-medium">Your public gallery is empty. Head to the <span className="text-primary font-bold">Media Library</span> to add assets.</p>
                </div>
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
                  {selectedItems.map((item: any, idx: number) => (
                    <div key={item.name} className="group relative flex flex-col rounded-xl border border-border bg-background shadow-sm hover:shadow-md transition-all overflow-hidden">
                      <div className="aspect-[4/5] overflow-hidden relative bg-muted/10">
                        {item.media_type === 'Video' ? (
                          <video src={encodeURI(item.url)} className="w-full h-full object-cover" muted loop onMouseOver={e => e.currentTarget.play()} onMouseOut={e => {e.currentTarget.pause(); e.currentTarget.currentTime = 0}} />
                        ) : (
                          <img src={encodeURI(item.url)} className="w-full h-full object-cover" alt={item.title} />
                        )}
                        <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-3">
                           <Button 
                                size="icon" 
                                variant="secondary" 
                                className="h-9 w-9 rounded-lg" 
                                onClick={() => setEditingItem(item)}
                           >
                             <Edit className="h-4 w-4" />
                           </Button>
                           <Button 
                                size="icon" 
                                variant="destructive" 
                                className="h-9 w-9 rounded-lg shadow-lg" 
                                onClick={() => handleToggleSelection({...item, is_in_gallery: true, gallery_item_name: item.name})}
                           >
                             <Trash2 className="h-4 w-4" />
                           </Button>
                        </div>
                        <div className="absolute top-3 left-3">
                           <div className="bg-background/90 backdrop-blur-sm border border-border px-2.5 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider shadow-sm">
                              #{item.sort_order || idx + 1}
                           </div>
                        </div>
                      </div>
                      <div className="p-4 space-y-1 bg-background border-t border-border/50">
                        <p className="font-bold text-sm truncate text-foreground">{item.title || 'Untitled'}</p>
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] text-muted-foreground font-bold uppercase">{item.media_type}</span>
                            <span className="text-[10px] text-primary font-bold uppercase">• Live</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="pool" className="space-y-6 outline-none">
           <Card className="border border-border shadow-sm bg-card rounded-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-border bg-muted/5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h3 className="font-bold text-base">Discovery Pool</h3>
                <p className="text-xs text-muted-foreground font-medium">Assets detected in your menu, events, and branding.</p>
              </div>
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => mutatePool()} 
                className="font-bold text-xs h-9"
              >
                <Plus className="h-3.5 w-3.5 mr-2" /> Sync Library
              </Button>
            </div>
            
            <CardContent className="p-6 min-h-[400px]">
              {isPoolLoading ? (
                <div className="py-24 flex flex-col items-center justify-center gap-3">
                  <Loader2 className="h-8 w-8 animate-spin text-primary/40" />
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-widest text-center">Identifying Media Assets...</p>
                </div>
              ) : mediaPool.length === 0 ? (
                <div className="py-24 text-center">
                    <div className="w-12 h-12 rounded-full bg-muted/30 flex items-center justify-center mx-auto mb-4">
                        <Layers className="h-6 w-6 text-muted-foreground/30" />
                    </div>
                    <p className="text-sm font-bold text-muted-foreground">No media detected in the application.</p>
                    <p className="text-xs text-muted-foreground/60 mt-1 max-w-xs mx-auto">Upload new photos directly using the button above.</p>
                </div>
              ) : !selectedFolder ? (
                /* Professional Folder Grid */
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                    {CATEGORIES.map((category: string) => {
                        const count = mediaPool.filter((m: any) => (m.category || 'General') === category).length;
                        let Icon = Folder;
                        let colorClass = "text-blue-500 bg-blue-500/10 fill-blue-500/5";
                        
                        if (category === 'Food & Menu') {
                            Icon = Utensils;
                            colorClass = "text-orange-500 bg-orange-500/10 fill-orange-500/5";
                        }
                        if (category === 'Events') {
                            Icon = Calendar;
                            colorClass = "text-purple-500 bg-purple-500/10 fill-purple-500/5";
                        }
                        if (category === 'Branding') {
                            Icon = Zap;
                            colorClass = "text-amber-500 bg-amber-500/10 fill-amber-500/5";
                        }
                        if (category === 'Gallery Uploads') {
                            Icon = ImageIcon;
                            colorClass = "text-emerald-500 bg-emerald-500/10 fill-emerald-500/5";
                        }

                        return (
                            <button 
                                key={category}
                                onClick={() => setSelectedFolder(category)}
                                className="group flex items-center gap-4 p-4 rounded-xl border border-border hover:border-primary/30 hover:bg-primary/[0.02] hover:shadow-sm transition-all text-left"
                            >
                                <div className={cn("w-12 h-12 rounded-lg flex items-center justify-center shrink-0 transition-transform group-hover:scale-110", colorClass)}>
                                    <Icon className="h-6 w-6" strokeWidth={2} />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-bold truncate group-hover:text-primary transition-colors">{category}</p>
                                    <p className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">{count} Assets</p>
                                </div>
                                <ChevronRight className="h-4 w-4 text-muted-foreground/40 group-hover:text-primary/60 transition-colors" />
                            </button>
                        );
                    })}
                </div>
              ) : (
                /* Folder Content View */
                <div className="space-y-6">
                    <div className="flex items-center justify-between border-b border-border pb-4 mb-6">
                        <Button 
                            variant="ghost" 
                            size="sm" 
                            onClick={() => setSelectedFolder(null)}
                            className="font-bold text-xs"
                        >
                            <ArrowLeft className="h-3.5 w-3.5 mr-2" />
                            Back to Library
                        </Button>
                        <div className="flex items-center gap-2">
                            <FolderOpen className="h-4 w-4 text-primary" />
                            <span className="font-bold text-sm text-foreground">{selectedFolder}</span>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                        {mediaPool
                            .filter((m: any) => (m.category || 'General') === selectedFolder)
                            .map((media: any) => {
                                const isSelected = !!media.is_selected && !!media.is_in_gallery;
                                return (
                                    <div 
                                        key={media.url} 
                                        className={cn(
                                            "group relative aspect-square rounded-xl overflow-hidden border transition-all cursor-pointer shadow-sm hover:shadow-md",
                                            isSelected 
                                                ? "border-primary ring-4 ring-primary/10 shadow-sm" 
                                                : "border-border hover:border-primary/40"
                                        )}
                                        onClick={() => setEditingItem({ 
                                            ...media, 
                                            name: media.gallery_item_name,
                                            title: media.source_title || '', 
                                            sort_order: media.sort_order || 0,
                                            media_type: (media.type || 'image').charAt(0).toUpperCase() + (media.type || 'image').slice(1)
                                        })}
                                    >
                                        {media.type === 'video' ? (
                                            <video src={encodeURI(media.url)} className="w-full h-full object-cover" muted />
                                        ) : (
                                            <img src={encodeURI(media.url)} className="w-full h-full object-cover" alt="" />
                                        )}
                                        
                                        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity p-4 flex flex-col justify-end gap-3">
                                            <div className="space-y-0.5 text-left">
                                                <p className="text-[10px] font-bold text-white/60 uppercase">{media.source_type}</p>
                                                <p className="text-xs font-bold text-white truncate">{media.source_title}</p>
                                            </div>
                                            <div className="flex w-full">
                                                <Button 
                                                    size="sm" 
                                                    variant={isSelected ? "secondary" : "default"} 
                                                    className={cn(
                                                        "w-full h-8 text-[10px] font-bold uppercase rounded-md shadow-lg px-2", 
                                                        isSelected ? "bg-white text-black hover:bg-white" : "bg-primary text-white"
                                                    )}
                                                    onClick={(e) => { e.stopPropagation(); handleToggleSelection(media); }}
                                                >
                                                    {isSelected ? "Selected" : "Add to Gallery"}
                                                </Button>
                                            </div>
                                        </div>

                                        <div className="absolute top-3 right-3 z-10 flex flex-col gap-2 items-end">
                                            {isSelected && (
                                                <div className="bg-primary text-white p-1 rounded-full shadow-lg">
                                                    <CheckCircle2 className="h-3 w-3" />
                                                </div>
                                            )}
                                            <Button 
                                                size="icon" 
                                                variant="secondary" 
                                                className="h-8 w-8 rounded-full bg-white/90 hover:bg-white shadow-lg text-black border-none opacity-0 group-hover:opacity-100 transition-all scale-75 group-hover:scale-100"
                                                onClick={(e) => { 
                                                    e.stopPropagation(); 
                                                    setEditingItem({ 
                                                        ...media, 
                                                        name: media.gallery_item_name,
                                                        title: media.source_title || '', 
                                                        sort_order: media.sort_order || 0,
                                                        media_type: (media.type || 'image').charAt(0).toUpperCase() + (media.type || 'image').slice(1)
                                                    });
                                                }}
                                            >
                                                <Edit className="h-3.5 w-3.5" />
                                            </Button>
                                        </div>
                                    </div>
                                );
                            })}
                    </div>
                </div>
              )}
            </CardContent>
           </Card>
        </TabsContent>
      </Tabs>      {/* Upload Dialog */}
      <Dialog open={isUploadDialogOpen} onOpenChange={setIsUploadDialogOpen}>
        <DialogContent className="sm:max-w-[700px] rounded-2xl border border-border shadow-2xl p-0 overflow-hidden">
          <div className="flex h-full min-h-[450px]">
            {/* Sidebar */}
            <div className="w-[220px] bg-muted/30 border-r border-border p-6 flex flex-col justify-between">
              <div className="space-y-6">
                <div className="space-y-1">
                  <DialogTitle className="text-lg font-bold">Upload Assets</DialogTitle>
                  <p className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">Storage & Categorization</p>
                </div>

                <div className="space-y-3">
                  <Label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Target Folder</Label>
                  <div className="flex flex-col gap-1.5">
                    {CATEGORIES.map((cat) => {
                      let Icon = Folder;
                      if (cat === 'Food & Menu') Icon = Utensils;
                      if (cat === 'Events') Icon = Calendar;
                      if (cat === 'Branding') Icon = Zap;
                      if (cat === 'Gallery Uploads') Icon = ImageIcon;

                      return (
                        <button
                          key={cat}
                          onClick={() => setUploadCategory(cat)}
                          className={cn(
                            "flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-bold transition-all text-left border",
                            uploadCategory === cat 
                              ? "bg-primary text-white border-primary shadow-sm" 
                              : "text-muted-foreground bg-transparent border-transparent hover:bg-muted hover:text-foreground"
                          )}
                        >
                          <Icon className={cn("h-3.5 w-3.5", uploadCategory === cat ? "text-white" : "text-muted-foreground")} />
                          {cat}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Sidebar Footer: Usage */}
              <div className="space-y-4 pt-6 border-t border-border/50">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-tight">
                    <span className="text-muted-foreground">Gallery Usage</span>
                    <span className="text-primary">{selectedCount}/25</span>
                  </div>
                  <Progress value={(selectedCount / 25) * 100} className="h-1.5" />
                </div>
                
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="w-full h-8 text-[10px] font-bold uppercase bg-background hover:bg-primary/5 hover:text-primary hover:border-primary/30"
                  onClick={() => {
                    setIsUploadDialogOpen(false);
                    navigate('/autopay-setup');
                  }}
                >
                  <Crown className="h-3 w-3 mr-2 text-yellow-500" />
                  Upgrade to Gold
                </Button>
              </div>
            </div>

            {/* Main Content Area */}
            <div className="flex-1 flex flex-col">
              <div className="p-8 flex-1 flex flex-col justify-center">
                <SilverMediaUpload 
                  variant="compact"
                  onUpload={handleUpload}
                  onUpgrade={() => {
                    setIsUploadDialogOpen(false);
                    navigate('/autopay-setup');
                  }}
                  currentImageCount={selectedCount}
                  maxImages={25}
                  className="border-2 border-dashed border-border/60 hover:border-primary/30 transition-all p-8 rounded-2xl bg-muted/5"
                />
              </div>
              
              <div className="px-8 py-4 bg-muted/5 border-t border-border flex items-center justify-between">
                <p className="text-[10px] text-muted-foreground font-medium italic">
                  Categorized as <span className="text-primary font-bold">{uploadCategory}</span>
                </p>
                <Button variant="ghost" size="sm" onClick={() => setIsUploadDialogOpen(false)} className="font-bold text-xs">
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingItem} onOpenChange={(open) => !open && setEditingItem(null)}>
        <DialogContent className="sm:max-w-[400px] rounded-2xl border border-border shadow-2xl p-0 overflow-hidden">
          <div className="px-6 py-4 border-b border-border bg-muted/5">
            <DialogTitle className="text-lg font-bold">Edit Media Info</DialogTitle>
          </div>
          {editingItem && (
                <form onSubmit={handleUpdateItem} className="p-6 space-y-5">
                <div className="space-y-4">
                    <div className="space-y-1.5">
                        <Label className="text-xs font-bold text-muted-foreground uppercase">Asset Title</Label>
                        <Input
                        value={editingItem.title}
                        onChange={(e) => setEditingItem({ ...editingItem, title: e.target.value })}
                        className="h-10 rounded-lg border-border font-medium px-4"
                        placeholder="e.g. Main Dining Area"
                        />
                    </div>
                    <div className="space-y-1.5">
                        <Label className="text-xs font-bold text-muted-foreground uppercase">Display Priority</Label>
                        <Input
                        type="number"
                        value={editingItem.sort_order}
                        onChange={(e) => setEditingItem({ ...editingItem, sort_order: e.target.value })}
                        className="h-10 rounded-lg border-border font-medium px-4"
                        />
                    </div>
                </div>
                
                <div className="aspect-video rounded-lg overflow-hidden bg-muted border border-border relative">
                    {editingItem.media_type === 'Video' ? (
                    <video src={encodeURI(editingItem.url)} className="w-full h-full object-cover" controls />
                    ) : (
                    <img src={encodeURI(editingItem.url)} className="w-full h-full object-cover" alt="Preview" />
                    )}
                </div>

                <div className="flex items-center gap-3 pt-2">
                    <Button type="button" variant="ghost" onClick={() => setEditingItem(null)} className="flex-1 font-bold">Cancel</Button>
                    <Button type="submit" className="flex-[2] font-bold shadow-sm">Save Changes</Button>
                </div>
                </form>
            )}
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent className="rounded-2xl border border-border shadow-2xl p-6">
          <AlertDialogHeader className="space-y-3">
            <AlertDialogTitle className="text-lg font-bold">Delete permanently?</AlertDialogTitle>
            <AlertDialogDescription className="text-sm font-medium">
              This will remove <span className="font-bold text-foreground">"{itemToDelete?.title}"</span>. 
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="mt-6">
            <AlertDialogCancel className="rounded-lg font-bold text-sm">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteItem}
              className="rounded-lg font-bold text-sm bg-destructive text-white hover:bg-destructive/90"
            >
              Delete Forever
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
