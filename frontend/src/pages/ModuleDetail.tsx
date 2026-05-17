import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useFrappeGetDoc, useFrappePostCall } from '@/lib/frappe'
import { usePermissions } from '@/lib/permissions'
import DynamicForm from '@/components/DynamicForm'
import { Button } from '@/components/ui/button'
import { ArrowLeft, Edit, Trash2, QrCode, Download, Eye } from 'lucide-react'
import { toast } from 'sonner'
import { Card, CardContent } from '@/components/ui/card'
import { useConfirm } from '@/hooks/useConfirm'
import { useRestaurant } from '@/contexts/RestaurantContext'

export default function ModuleDetail() {
  const { confirm, ConfirmDialogComponent } = useConfirm()
  const { doctype, docname } = useParams<{ doctype: string; docname: string }>()
  const navigate = useNavigate()
  const { permissions } = usePermissions(doctype || '')
  const { data: doc, isLoading } = useFrappeGetDoc(doctype || '', docname || '')
  const [mode, setMode] = useState<'view' | 'edit'>('view')
  const [qrCodeUrl, setQrCodeUrl] = useState<string | null>(null)
  const { selectedRestaurant } = useRestaurant()
  const { call: getQrCodeUrl } = useFrappePostCall('flamezo_backend.flamezo.doctype.restaurant.restaurant.get_qr_codes_pdf_url')
  const { call: generateQrCodes } = useFrappePostCall('flamezo_backend.flamezo.doctype.restaurant.restaurant.generate_qr_codes_pdf')

  // Load QR code URL for Restaurant doctype
  useEffect(() => {
    if (doctype === 'Restaurant' && docname && doc?.tables && doc.tables > 0) {
      getQrCodeUrl({ restaurant: docname })
        .then((response: any) => {
          if (response?.message) {
            setQrCodeUrl(response.message)
          }
        })
        .catch(() => {
          // QR codes not generated yet
          setQrCodeUrl(null)
        })
    }
  }, [doctype, docname, doc?.tables])

  const { call: deleteDocApi } = useFrappePostCall('flamezo_backend.flamezo.api.documents.delete_multiple_docs')

  const handleDelete = async () => {
    const confirmed = await confirm({
      title: `Force Delete ${doctype}`,
      description: `Are you sure you want to delete this ${doctype}? If it is linked to other records, force deleting will remove it regardless. This action cannot be undone.`,
      variant: 'destructive',
      confirmText: 'Force Delete',
      cancelText: 'Cancel'
    })

    if (!confirmed) return

    try {
      const result = await deleteDocApi({
        doctype: doctype || '',
        names: [docname],
        force: true
      })

      if (result.success && result.deleted_count > 0) {
        toast.success(`${doctype} deleted successfully`)
        navigate(`/${doctype}`)
      } else if (result.errors && result.errors.length > 0) {
        toast.error(`Failed to delete ${doctype}`, { description: result.errors[0] })
      } else {
        throw new Error(result.error || 'Delete failed')
      }
    } catch (error: any) {
      toast.error(error?.message || `Failed to delete ${doctype}`)
    }
  }

  const handleGenerateQrCodes = async () => {
    if (!docname) return
    
    try {
      const response: any = await generateQrCodes({ restaurant: docname })
      if (response?.message) {
        setQrCodeUrl(response.message)
        toast.success('QR codes PDF generated successfully')
        // Reload document to refresh
        window.location.reload()
      }
    } catch (error: any) {
      toast.error(error?.message || 'Failed to generate QR codes')
    }
  }

  const handleViewQrCodes = () => {
    if (qrCodeUrl) {
      window.open(qrCodeUrl, '_blank')
    }
  }

  const handleDownloadQrCodes = () => {
    if (qrCodeUrl) {
      const link = document.createElement('a')
      link.href = qrCodeUrl
      link.download = `${doc?.restaurant_id || docname}_table_qr_codes.pdf`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    }
  }

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <div className="text-muted-foreground">Loading...</div>
        </CardContent>
      </Card>
    )
  }

  if (!doc) {
    return (
      <Card>
        <CardContent className="py-8">
          <p className="text-center text-muted-foreground mb-4">
            {doctype} not found
          </p>
          <Link to={`/${doctype}`}>
            <Button>Back to List</Button>
          </Link>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to={`/${doctype}`}>
            <Button variant="ghost" size="sm">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back
            </Button>
          </Link>
          <div>
            <h2 className="text-3xl font-bold tracking-tight capitalize">
              {doctype?.replace(/_/g, ' ')}: {docname}
            </h2>
          </div>
        </div>
        <div className="flex gap-2">
          {/* QR Code buttons for Restaurant */}
          {doctype === 'Restaurant' && doc?.tables && doc.tables > 0 && mode === 'view' && (
            <>
              {qrCodeUrl ? (
                <>
                  <Button variant="outline" onClick={handleViewQrCodes}>
                    <Eye className="mr-2 h-4 w-4" />
                    View QR Codes
                  </Button>
                  <Button variant="outline" onClick={handleDownloadQrCodes}>
                    <Download className="mr-2 h-4 w-4" />
                    Download QR Codes
                  </Button>
                </>
              ) : (
                <Button variant="outline" onClick={handleGenerateQrCodes}>
                  <QrCode className="mr-2 h-4 w-4" />
                  Generate QR Codes
                </Button>
              )}
            </>
          )}
          {permissions.write && mode === 'view' && (
            <Button onClick={() => setMode('edit')}>
              <Edit className="mr-2 h-4 w-4" />
              Edit
            </Button>
          )}
          {permissions.delete && (
            <Button variant="destructive" onClick={handleDelete}>
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </Button>
          )}
        </div>
      </div>

      <DynamicForm
        doctype={doctype || ''}
        docname={docname}
        mode={mode}
        initialData={selectedRestaurant ? { restaurant: selectedRestaurant } : {}}
        readOnlyFields={['restaurant']}
        onSave={() => {
          setMode('view')
          toast.success(`${doctype} updated successfully`)
        }}
        onCancel={() => setMode('view')}
      />
      {ConfirmDialogComponent}
    </div>
  )
}

