import { useState } from 'react'
import { useFrappeGetDocList, useFrappePostCall, useFrappeUpdateDoc, useFrappeDeleteDoc } from '@/lib/frappe'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Plus, Edit2, Trash2, Star } from 'lucide-react'
import { toast } from 'sonner'
import { useOutlet } from '@/contexts/OutletContext'

export default function LegacySignatureDishPage() {
  const { selectedOutlet } = useOutlet()
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<any>(null)

  // Get signature dishes data
  const { data: signatureDishes } = useFrappeGetDocList('Legacy Signature Dish', {
    filters: [['parent', '=', selectedOutlet]],
    fields: ['name', 'dish', 'display_order', 'dish_name'],
    orderBy: { field: 'display_order', order: 'asc' }
  })

  // Get menu products for signature dishes selection
  const { data: menuProducts } = useFrappeGetDocList('Menu Product', {
    filters: [['outlet', '=', selectedOutlet]],
    fields: ['name', 'product_name', 'image']
  })

  const { call: createDoc, loading: isCreating } = useFrappePostCall('frappe.client.insert')
  const { updateDoc, loading: isUpdating } = useFrappeUpdateDoc()
  const { deleteDoc, loading: isDeleting } = useFrappeDeleteDoc()

  const handleSave = async (data: any) => {
    try {
      if (editingItem?.name) {
        await updateDoc('Legacy Signature Dish', editingItem.name, data)
        toast.success('Featured item updated successfully')
      } else {
        await createDoc({
          ...data,
          doctype: 'Legacy Signature Dish',
          parent: selectedOutlet,
          parenttype: 'Legacy Content',
          parentfield: 'signature_dishes'
        })
        toast.success('Featured item added successfully')
      }
      
      setIsDialogOpen(false)
      setEditingItem(null)
      window.location.reload()
    } catch (error) {
      toast.error('Failed to save featured item')
    }
  }

  const handleDelete = async (name: string) => {
    try {
      await deleteDoc('Legacy Signature Dish', name)
      toast.success('Featured item deleted successfully')
      window.location.reload()
    } catch (error) {
      toast.error('Failed to delete featured item')
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const formData = new FormData(e.target as HTMLFormElement)
    const data: any = {
      dish: formData.get('dish'),
      display_order: parseInt(formData.get('display_order') as string) || 0
    }
    handleSave(data)
  }

  if (!selectedOutlet) {
    return (
      <div className="text-center py-8">
        <p>Please select an outlet to manage featured items.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Signature Dishes</h1>
        <p className="text-muted-foreground">Manage your outlet's featured items (max 3)</p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Star className="h-5 w-5" />
              Signature Dishes
              <Badge variant="secondary">{signatureDishes?.length || 0}</Badge>
            </CardTitle>
            <Dialog open={isDialogOpen} onOpenChange={(open) => {
              setIsDialogOpen(open)
              if (!open) setEditingItem(null)
            }}>
              <DialogTrigger asChild>
                <Button size="sm" onClick={() => setEditingItem({})}>
                  <Plus className="h-4 w-4 mr-1" />
                  Add Featured Item
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl">
                <DialogHeader>
                  <DialogTitle>
                    {editingItem?.name ? 'Edit Featured Item' : 'Add Featured Item'}
                  </DialogTitle>
                </DialogHeader>
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div>
                    <Label htmlFor="dish">Item</Label>
                    <Select name="dish" defaultValue={editingItem?.dish} required>
                      <SelectTrigger>
                        <SelectValue placeholder="Select an item" />
                      </SelectTrigger>
                      <SelectContent>
                        {menuProducts?.map((product: any) => (
                          <SelectItem key={product.name} value={product.name}>
                            {product.product_name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label htmlFor="display_order">Display Order</Label>
                    <NumberInput  name="display_order" defaultValue={editingItem?.display_order || 0} />
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>
                      Cancel
                    </Button>
                    <Button type="submit" disabled={isCreating || isUpdating}>
                      {editingItem?.name ? 'Update' : 'Create'}
                    </Button>
                  </div>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        </CardHeader>
        <CardContent>
          {(!signatureDishes || signatureDishes.length === 0) ? (
            <div className="text-center py-8 text-muted-foreground">
              No featured items yet. Click "Add Featured Item" to get started.
            </div>
          ) : (
            <div className="space-y-4">
              {signatureDishes.map((item: any) => (
                <div key={item.name} className="flex items-center justify-between p-4 border rounded-lg">
                  <div>
                    <h4 className="font-semibold">{item.dish_name || item.dish}</h4>
                    <p className="text-sm text-muted-foreground">Order: {item.display_order}</p>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => setEditingItem(item)}>
                      <Edit2 className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => handleDelete(item.name)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
