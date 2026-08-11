import { useFrappeGetDocList } from '@/lib/frappe'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Eye, Plus, Edit } from 'lucide-react'
import { Link } from 'react-router-dom'
import { usePermissions } from '@/lib/permissions'
import DynamicForm from './DynamicForm'
import { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { toast } from 'sonner'

interface OutletDataListProps {
  doctype: string
  outletId: string
  titleField: string
}

export default function OutletDataList({ doctype, outletId, titleField }: OutletDataListProps) {
  const { permissions } = usePermissions(doctype)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showEditDialog, setShowEditDialog] = useState(false)
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null)

  const { data: docs, isLoading, mutate } = useFrappeGetDocList(
    doctype,
    {
      fields: ['name', titleField, 'creation', 'modified'],
      filters: [['restaurant', '=', outletId]],
      orderBy: { field: 'modified', order: 'desc' },
      limit: 100
    },
    outletId ? `${doctype}-${outletId}` : null
  )

  if (isLoading) {
    return (
      <div className="text-center py-8 text-muted-foreground">Loading...</div>
    )
  }

  const items = docs || []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">All {doctype.replace(/_/g, ' ')}</h3>
          <p className="text-sm text-muted-foreground">
            {items.length} item{items.length !== 1 ? 's' : ''} found
          </p>
        </div>
        {permissions.create && (
          <Button onClick={() => setShowCreateDialog(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Add New
          </Button>
        )}
      </div>

      {items.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground border rounded-md">
          <p>No {doctype.replace(/_/g, ' ')} found for this outlet.</p>
          {permissions.create && (
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => setShowCreateDialog(true)}
            >
              <Plus className="mr-2 h-4 w-4" />
              Create First {doctype.replace(/_/g, ' ')}
            </Button>
          )}
        </div>
      ) : (
        <div className="border rounded-md overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Modified</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item: any) => (
                <TableRow key={item.name}>
                  <TableCell className="font-medium">
                    {item[titleField] || item.name}
                  </TableCell>
                  <TableCell>
                    {item.creation ? new Date(item.creation).toLocaleDateString() : 'N/A'}
                  </TableCell>
                  <TableCell>
                    {item.modified ? new Date(item.modified).toLocaleDateString() : 'N/A'}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Link to={`/${doctype}/${item.name}`}>
                        <Button variant="ghost" size="sm">
                          <Eye className="h-4 w-4" />
                        </Button>
                      </Link>
                      {permissions.write && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setSelectedDoc(item.name)
                            setShowEditDialog(true)
                          }}
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {showCreateDialog && (
        <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
          <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Create {doctype.replace(/_/g, ' ')}</DialogTitle>
              <DialogDescription>Fill in the details to create a new {doctype.replace(/_/g, ' ')} for this outlet.</DialogDescription>
            </DialogHeader>
            <DynamicForm
              doctype={doctype}
              mode="create"
              initialData={{ restaurant: outletId }}
              onSave={() => {
                setShowCreateDialog(false)
                mutate()
                toast.success(`${doctype} created successfully`)
              }}
              onCancel={() => setShowCreateDialog(false)}
            />
          </DialogContent>
        </Dialog>
      )}

      {showEditDialog && selectedDoc && (
        <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
          <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Edit {doctype.replace(/_/g, ' ')}</DialogTitle>
              <DialogDescription>Modify the existing details of the selected {doctype.replace(/_/g, ' ')}.</DialogDescription>
            </DialogHeader>
            <DynamicForm
              doctype={doctype}
              docname={selectedDoc}
              mode="edit"
              onSave={() => {
                setShowEditDialog(false)
                setSelectedDoc(null)
                mutate()
                toast.success(`${doctype} updated successfully`)
              }}
              onCancel={() => {
                setShowEditDialog(false)
                setSelectedDoc(null)
              }}
            />
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}

