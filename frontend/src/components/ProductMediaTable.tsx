import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from "@/components/ui/input"
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Trash2, Upload, Image as ImageIcon, Video, GripVertical } from 'lucide-react'
import { toast } from 'sonner'
import { cn, getFrappeError } from '@/lib/utils'
import { uploadToR2, getMediaType } from '@/lib/r2Upload'
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
  verticalListSortingStrategy,
  useSortable
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

interface ProductMediaItem {
  name?: string
  media_asset?: string
  media_url?: string
  media_type?: 'image' | 'video'
  display_order?: number
  alt_text?: string
  caption?: string
}

interface ProductMediaTableProps {
  value?: ProductMediaItem[]
  onChange?: (items: ProductMediaItem[]) => void
  required?: boolean
  disabled?: boolean
  productName?: string
}

interface SortableMediaRowProps {
  item: ProductMediaItem
  index: number
  disabled?: boolean
  onRemove: () => void
  getMediaUrl: (url?: string) => string
}

function SortableMediaRow({ item, index, disabled, onRemove, getMediaUrl }: SortableMediaRowProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: item.media_asset || item.name || `item-${index}` })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 50 : 0,
    position: 'relative' as const,
  }

  const mediaUrl = getMediaUrl(item.media_url)
  const isVideo = item.media_type === 'video'

  return (
    <TableRow 
      ref={setNodeRef} 
      style={style}
      className={cn(isDragging && "bg-accent opacity-50 shadow-lg")}
    >
      <TableCell>
        <div 
          {...attributes} 
          {...listeners} 
          className="cursor-grab active:cursor-grabbing p-1 hover:bg-muted rounded"
        >
          <GripVertical className="h-4 w-4 text-muted-foreground" />
        </div>
      </TableCell>
      <TableCell>
        {mediaUrl ? (
          <div className="relative group">
            {isVideo ? (
              <div className="relative w-16 h-16 bg-muted rounded border flex items-center justify-center overflow-hidden">
                <Video className="h-6 w-6 text-muted-foreground absolute z-10" />
                <video
                  src={mediaUrl}
                  className="absolute inset-0 w-full h-full object-cover rounded"
                  muted
                  playsInline
                />
                <div className="absolute top-0 right-0 bg-blue-600 text-white text-[10px] px-1 py-0.5 rounded-bl font-bold z-20">
                  VIDEO
                </div>
              </div>
            ) : (
              <div className="relative w-16 h-16">
                <img
                  src={mediaUrl}
                  alt={item.alt_text || `Media ${index + 1}`}
                  className="w-16 h-16 object-cover rounded border"
                />
              </div>
            )}
          </div>
        ) : (
          <span className="text-muted-foreground text-sm">No media</span>
        )}
      </TableCell>
      <TableCell className="text-center">
        <span className={cn(
          "px-2 py-1 rounded text-xs font-medium uppercase tracking-wider",
          isVideo ? "bg-blue-100 text-blue-800" : "bg-green-100 text-green-800"
        )}>
          {isVideo ? 'Video' : 'Image'}
        </span>
      </TableCell>
      {!disabled && (
        <TableCell className="text-right">
          <Button
            variant="ghost"
            size="sm"
            onClick={onRemove}
            className="text-destructive hover:text-destructive hover:bg-destructive/10"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </TableCell>
      )}
    </TableRow>
  )
}

export default function ProductMediaTable({ value = [], onChange, required, disabled, productName }: ProductMediaTableProps) {
  const [uploading, setUploading] = useState(false)

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  const currentValue = Array.isArray(value) ? value : []

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    // Validate file count (max 3 media items)
    if (currentValue.length + files.length > 3) {
      toast.error('Maximum 3 media items allowed per product')
      return
    }

    // Check video count (max 1 video)
    const existingVideoCount = currentValue.filter(item => item.media_type === 'video').length
    const newVideoCount = Array.from(files).filter(file => 
      file.type.startsWith('video/') || 
      ['.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv', '.flv', '.wmv'].some(ext => 
        file.name.toLowerCase().endsWith(ext)
      )
    ).length

    if (existingVideoCount + newVideoCount > 1) {
      toast.error('Maximum 1 video allowed per product')
      return
    }

    if (!productName) {
      toast.error('Product must be saved before uploading media')
      return
    }

    setUploading(true)

    try {
      // Sequential upload for mobile reliability (Promise.all overwhelms mobile bandwidth)
      const uploadedItems = []
      let failedCount = 0

      for (let index = 0; index < files.length; index++) {
        const file = files[index]
        const mediaType = getMediaType(file)
        const mediaRole = mediaType === 'video' ? 'product_video' : 'product_image'

        try {
          // Upload to R2 (compression handled inside uploadToR2 for images)
          const result = await uploadToR2({
            ownerDoctype: 'Menu Product',
            ownerName: productName,
            mediaRole,
            file,
            displayOrder: currentValue.length + index + 1,
          })

          uploadedItems.push({
            media_asset: result.name,
            media_url: result.primary_url || '',
            media_type: mediaType,
            display_order: currentValue.length + index + 1,
            alt_text: '',
            caption: ''
          })
        } catch (fileError: any) {
          console.error(`Upload failed for ${file.name}:`, fileError)
          failedCount++
        }
      }

      if (uploadedItems.length > 0) {
        const newItems = [...currentValue, ...uploadedItems]
        onChange?.(newItems)
        toast.success(`${uploadedItems.length} media file(s) uploaded successfully`)
      }
      if (failedCount > 0) {
        toast.error(`${failedCount} file(s) failed to upload. Please try again.`)
      }
    } catch (error: any) {
      toast.error('Failed to upload media files', { description: getFrappeError(error) })
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleRemove = (index: number) => {
    const newItems = currentValue.filter((_, i) => i !== index)
    // Reorder display_order
    const reorderedItems = newItems.map((item, idx) => ({
      ...item,
      display_order: idx + 1
    }))
    onChange?.(reorderedItems)
  }

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (over && active.id !== over.id) {
      const oldIndex = currentValue.findIndex(item => (item.media_asset || item.name) === active.id)
      const newIndex = currentValue.findIndex(item => (item.media_asset || item.name) === over.id)
      const newItems = arrayMove(currentValue, oldIndex, newIndex)
      
      // Update display_order based on new position
      const reorderedItems = newItems.map((item, idx) => ({
        ...item,
        display_order: idx + 1
      }))
      
      onChange?.(reorderedItems)
    }
  }

  const getMediaUrl = (url?: string) => {
    if (!url) return ''
    if (url.startsWith('http')) return url
    if (url.startsWith('/files/')) {
      const baseUrl = window.location.origin
      return `${baseUrl}${url}`
    }
    return url
  }

  const canAddMore = currentValue.length < 3
  const videoCount = currentValue.filter(item => item.media_type === 'video').length

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Label>
          Product Media
          {required && <span className="text-destructive">*</span>}
        </Label>
        <div className="text-sm text-muted-foreground">
          {currentValue.length} / 3 items ({videoCount} video{videoCount !== 1 ? 's' : ''})
        </div>
      </div>

      {!disabled && canAddMore && (
        <div className="flex items-center gap-2">
          <Input
            type="file"
            accept="image/*,video/*"
            multiple={canAddMore}
            onChange={handleFileSelect}
            disabled={disabled || uploading || !canAddMore}
            className="hidden"
            id="product-media-upload"
          />
          <Label
            htmlFor="product-media-upload"
            className={cn(
              "flex items-center gap-2 px-4 py-2 border rounded-md transition-colors",
              (disabled || uploading || !canAddMore)
                ? "opacity-50 cursor-not-allowed"
                : "cursor-pointer hover:bg-accent"
            )}
          >
            <Upload className="h-4 w-4" />
            {uploading ? 'Uploading...' : 'Upload Media'}
          </Label>
          {!canAddMore && (
            <span className="text-sm text-muted-foreground">Maximum 3 media items reached</span>
          )}
        </div>
      )}

      {/* Media List */}
      {currentValue.length > 0 && (
        <div className="border rounded-md overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10"></TableHead>
                <TableHead className="w-24">Preview</TableHead>
                <TableHead className="text-center">Media Type</TableHead>
                {!disabled && <TableHead className="w-24 text-right">Actions</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={handleDragEnd}
              >
                <SortableContext
                  items={currentValue.map(item => item.media_asset || item.name || '')}
                  strategy={verticalListSortingStrategy}
                >
                  {currentValue.map((item, index) => (
                    <SortableMediaRow
                      key={item.media_asset || item.name || index}
                      item={item}
                      index={index}
                      disabled={disabled}
                      onRemove={() => handleRemove(index)}
                      getMediaUrl={getMediaUrl}
                    />
                  ))}
                </SortableContext>
              </DndContext>
            </TableBody>
          </Table>
        </div>
      )}

      {currentValue.length === 0 && (
        <div className="text-center py-8 text-muted-foreground border rounded-md">
          <ImageIcon className="h-12 w-12 mx-auto mb-2 opacity-50" />
          <p>No media uploaded yet</p>
          <p className="text-sm mt-1">Upload images or videos (max 3 items, max 1 video)</p>
        </div>
      )}
    </div>
  )
}

