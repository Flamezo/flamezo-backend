import { useState, useEffect } from 'react'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useFrappePostCall } from '@/lib/frappe'
import { toast } from 'sonner'
import { Save, X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ExtractedDish {
  name?: string
  dish_id?: string
  dish_name?: string
  product_name?: string
  price?: number
  category?: string
  description?: string
  calories?: number
  is_vegetarian?: boolean
  estimated_time?: number
  serving_size?: string
  main_category?: string
  original_price?: number
  has_no_media?: boolean
  media_json?: string
  customizations_json?: string
}

interface EditableExtractedDishesTableProps {
  dishes: ExtractedDish[]
  docname: string
  onUpdate?: () => void
}

export default function EditableExtractedDishesTable({ 
  dishes, 
  docname,
  onUpdate 
}: EditableExtractedDishesTableProps) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [editedDishes, setEditedDishes] = useState<ExtractedDish[]>(dishes || [])
  const [saving, setSaving] = useState(false)

  const { call: updateDoc } = useFrappePostCall('flamezo_backend.flamezo.api.documents.update_document')

  useEffect(() => {
    setEditedDishes(dishes || [])
  }, [dishes])

  const handleEdit = (index: number) => {
    setEditingIndex(index)
  }

  const handleCancel = () => {
    setEditingIndex(null)
    setEditedDishes(dishes || [])
  }

  const handleFieldChange = (index: number, field: string, value: any) => {
    const updated = [...editedDishes]
    updated[index] = { ...updated[index], [field]: value }
    setEditedDishes(updated)
  }

  const handleSave = async (_index: number) => {
    setSaving(true)
    try {
      // Update the entire extracted_dishes child table with all dishes
      const updatedDishes = editedDishes.map((dish: ExtractedDish, idx: number) => ({
        doctype: 'Extracted Dish',
        dish_id: dish.dish_id || dish.dish_name || `dish-${idx}`,
        dish_name: dish.dish_name || dish.product_name || dish.name || '',
        price: dish.price || 0,
        category: dish.category || '',
        description: dish.description || '',
        calories: dish.calories,
        is_vegetarian: dish.is_vegetarian ? 1 : 0,
        estimated_time: dish.estimated_time,
        serving_size: dish.serving_size,
        main_category: dish.main_category || '',
        original_price: dish.original_price,
        has_no_media: dish.has_no_media ? 1 : 0,
        media_json: dish.media_json || null,
        customizations_json: dish.customizations_json || null
      }))
      
      await updateDoc({
        doctype: 'Menu Image Extractor',
        name: docname,
        doc_data: {
          extracted_dishes: updatedDishes
        }
      })
      
      toast.success('Dish updated successfully')
      setEditingIndex(null)
      onUpdate?.()
    } catch (error: any) {
      const errorMessage = error?.message || error?.data?.message || 'Failed to update dish'
      toast.error(typeof errorMessage === 'string' ? errorMessage : 'Failed to update dish')
      console.error('Error updating dish:', error)
    } finally {
      setSaving(false)
    }
  }

  if (!dishes || dishes.length === 0) {
    return (
      <Card className="border-2">
        <CardHeader>
          <CardTitle>Extracted Dishes</CardTitle>
          <CardDescription>No dishes extracted yet. Start extraction to see results.</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <div className="bg-card">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader className="bg-muted/30">
            <TableRow className="hover:bg-transparent border-none">
              <TableHead className="text-[10px] font-black uppercase tracking-[0.2em] py-5">Product Identity</TableHead>
              <TableHead className="text-[10px] font-black uppercase tracking-[0.2em] py-5">Classification</TableHead>
              <TableHead className="text-[10px] font-black uppercase tracking-[0.2em] py-5 text-right">Pricing (₹)</TableHead>
              <TableHead className="text-[10px] font-black uppercase tracking-[0.2em] py-5">Neural Description</TableHead>
              <TableHead className="text-[10px] font-black uppercase tracking-[0.2em] py-5 text-right">Control</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {editedDishes.map((dish, index) => {
              const isEditing = editingIndex === index
              const dishName = dish?.dish_name || dish?.product_name || dish?.name || 'Unknown Item'
              const category = dish?.category || ''
              const price = dish?.price || 0
              const description = dish?.description || ''

              return (
                <TableRow 
                  key={dish?.dish_id || `dish-${index}`} 
                  className={cn(
                    "group transition-all duration-300",
                    isEditing ? 'bg-primary/5 hover:bg-primary/5' : 'hover:bg-muted/20'
                  )}
                >
                  <TableCell className="py-4">
                    {isEditing ? (
                      <Input
                        value={dishName}
                        onChange={(e) => handleFieldChange(index, 'dish_name', e.target.value)}
                        className="h-10 text-sm font-bold bg-background/50 border-primary/20 focus-visible:ring-primary/30 rounded-xl"
                      />
                    ) : (
                      <div className="flex flex-col">
                         <span className="font-black text-sm tracking-tight text-foreground">{String(dishName)}</span>
                         {dish.is_vegetarian && (
                           <span className="text-[8px] font-black uppercase text-green-600 mt-0.5 tracking-tighter flex items-center gap-1">
                             <div className="w-1.5 h-1.5 rounded-full bg-green-500" /> Plant-Based
                           </span>
                         )}
                      </div>
                    )}
                  </TableCell>
                  <TableCell>
                    {isEditing ? (
                      <Input
                        value={category}
                        onChange={(e) => handleFieldChange(index, 'category', e.target.value)}
                        className="h-10 text-xs font-medium bg-background/50 border-primary/20 focus-visible:ring-primary/30 rounded-xl"
                        placeholder="Category"
                      />
                    ) : (
                      category ? (
                        <Badge variant="outline" className="text-[9px] font-black uppercase tracking-widest bg-primary/5 text-primary border-primary/20 px-2 py-0.5">
                          {String(category)}
                        </Badge>
                      ) : (
                        <span className="text-[10px] font-black text-muted-foreground/30 uppercase">Unclassified</span>
                      )
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {isEditing ? (
                      <NumberInput
                        
                        value={price}
                        onChange={(e) => handleFieldChange(index, 'price', parseFloat(e.target.value) || 0)}
                        className="h-10 text-sm font-black text-right bg-background/50 border-primary/20 focus-visible:ring-primary/30 rounded-xl"
                        step="0.01"
                      />
                    ) : (
                      <div className="flex flex-col items-end gap-1">
                        <span className="font-black text-sm text-foreground">₹{Number(price).toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                        {dish.customizations_json && (
                          <div className="text-[8px] font-black text-primary uppercase tracking-tighter opacity-70">
                            + Dynamic Add-ons
                          </div>
                        )}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="max-w-md">
                    {isEditing ? (
                      <Textarea
                        value={description}
                        onChange={(e) => handleFieldChange(index, 'description', e.target.value)}
                        className="text-xs font-medium bg-background/50 border-primary/20 focus-visible:ring-primary/30 rounded-xl min-h-[80px]"
                        rows={3}
                      />
                    ) : (
                      <div className="line-clamp-2 text-xs text-muted-foreground font-medium leading-relaxed group-hover:text-foreground/80 transition-colors">
                        {String(description) || <span className="italic opacity-30">No description generated</span>}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {isEditing ? (
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          onClick={() => handleSave(index)}
                          disabled={saving}
                          className="h-9 w-9 rounded-xl bg-primary hover:bg-primary/90 shadow-lg shadow-primary/20"
                        >
                          <Save className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={handleCancel}
                          disabled={saving}
                          className="h-9 w-9 rounded-xl text-muted-foreground hover:text-foreground"
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleEdit(index)}
                        className="h-9 text-[10px] font-black uppercase tracking-widest text-primary hover:bg-primary/10 rounded-xl px-4 opacity-0 group-hover:opacity-100 transition-all transform translate-x-2 group-hover:translate-x-0"
                      >
                        Edit Entry
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
  )
}

