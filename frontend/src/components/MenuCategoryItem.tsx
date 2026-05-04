import React from 'react'
import { cn } from '@/lib/utils'
import { Pencil, Trash2, GripVertical } from 'lucide-react'
import { Switch } from '@/components/ui/switch'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

interface MenuCategoryItemProps {
  category: any
  isActive: boolean
  onClick: () => void
  onToggleStatus: (status: boolean) => void
  onEdit: () => void
  onDelete: () => void
}

export const MenuCategoryItem: React.FC<MenuCategoryItemProps> = ({
  category,
  isActive,
  onClick,
  onToggleStatus,
  onEdit,
  onDelete,
}) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: category.name })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 100 : undefined,
    opacity: isDragging ? 0.5 : 1,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "group flex items-center gap-2 p-3 cursor-pointer rounded-lg transition-all border border-transparent",
        isActive 
          ? "bg-accent text-accent-foreground shadow-md border-accent" 
          : "hover:bg-muted text-muted-foreground hover:text-foreground"
      )}

      onClick={onClick}
    >
      <div {...attributes} {...listeners} className="flex items-center">
        <GripVertical className={cn(
          "h-4 w-4 shrink-0 opacity-40 group-hover:opacity-100 transition-opacity cursor-grab active:cursor-grabbing",
          isActive && "opacity-60"
        )} />
      </div>
      
      <div className="flex-1 min-w-0">
        <p className={cn(
          "text-sm font-medium truncate",
          isActive ? "text-accent-foreground" : "text-foreground"
        )}>
          {category.display_name || category.category_name || category.name}
        </p>

        {category.item_count !== undefined && (
          <p className="text-[10px] opacity-70">
            {category.item_count} {category.item_count === 1 ? 'item' : 'items'}
          </p>
        )}
      </div>

      <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
        <Switch 
          checked={category.is_active !== 0} 
          onCheckedChange={onToggleStatus}
          className="scale-75"
        />
        <button 
          onClick={onEdit}
          className="p-1 rounded-md hover:bg-background/20 dark:hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        <button 
          onClick={onDelete}
          className="p-1 rounded-md hover:bg-destructive/20 text-destructive/70 hover:text-destructive transition-colors"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>


    </div>
  )
}
