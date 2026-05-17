import { useState, useEffect } from 'react'
import { useFrappeGetDocList, useFrappeGetDoc, useFrappePostCall } from '@/lib/frappe'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Loader2, CheckCircle, XCircle, Clock, Play, Check } from 'lucide-react'
import DynamicForm from './DynamicForm'
import EditableExtractedDishesTable from './EditableExtractedDishesTable'
import { useConfirm } from '@/hooks/useConfirm'

interface MenuExtractionProps {
  restaurantId: string
  onExtractionComplete?: (data: any) => void
  onNavigateToReview?: () => void
}

export default function MenuExtraction({ restaurantId, onExtractionComplete, onNavigateToReview }: MenuExtractionProps) {
  const { confirm, ConfirmDialogComponent } = useConfirm()
  // Get selected document from localStorage or use latest
  const [selectedDocName, setSelectedDocName] = useState<string | null>(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(`menu-extraction-${restaurantId}`)
      return stored || null
    }
    return null
  })

  // Get all extractions for this restaurant
  const { data: extractions, isLoading: isLoadingList } = useFrappeGetDocList(
    'Menu Image Extractor',
    {
      fields: ['name', 'restaurant', 'extraction_status', 'creation', 'modified'],
      filters: { restaurant: restaurantId },
      orderBy: { field: 'creation', order: 'desc' },
      limit: 100
    },
    restaurantId ? `menu-extractions-list-${restaurantId}` : null
  )

  // Get the selected extraction document
  const { data: extractionDoc, mutate: refreshExtraction } = useFrappeGetDoc(
    'Menu Image Extractor',
    selectedDocName || '',
    {
      enabled: !!selectedDocName
    }
  )

  const { call: extractMenuData } = useFrappePostCall(
    'flamezo_backend.flamezo.doctype.menu_image_extractor.menu_image_extractor.extract_menu_data'
  )

  const { call: approveExtraction } = useFrappePostCall(
    'flamezo_backend.flamezo.doctype.menu_image_extractor.menu_image_extractor.approve_extracted_data'
  )

  // Auto-select latest extraction if none selected
  useEffect(() => {
    if (!selectedDocName && extractions && extractions.length > 0) {
      const latest = extractions[0]
      setSelectedDocName(latest.name)
      localStorage.setItem(`menu-extraction-${restaurantId}`, latest.name)
    }
  }, [extractions, selectedDocName, restaurantId])

  // Auto-refresh if processing or pending approval (to catch when extraction completes)
  useEffect(() => {
    if (extractionDoc?.extraction_status === 'Processing' || extractionDoc?.extraction_status === 'Pending Approval') {
      const interval = setInterval(() => {
        refreshExtraction()
      }, 5000)
      return () => clearInterval(interval)
    }
  }, [extractionDoc?.extraction_status, refreshExtraction])

  const handleSelectDocument = (docName: string) => {
    setSelectedDocName(docName)
    localStorage.setItem(`menu-extraction-${restaurantId}`, docName)
  }

  const handleExtract = async () => {
    if (!selectedDocName) {
      toast.error('Please select or create a Menu Image Extractor document first')
      return
    }

    // Ensure document is loaded
    if (!extractionDoc) {
      toast.error('Please wait for document to load')
      return
    }

    if (!extractionDoc.menu_images || extractionDoc.menu_images.length === 0) {
      toast.error('Please upload at least one menu image before extraction')
      return
    }

    if (extractionDoc.menu_images.length > 20) {
      toast.error(`Maximum 20 images allowed. Currently ${extractionDoc.menu_images.length} images uploaded.`)
      return
    }

    const confirmed = await confirm({
      title: 'Extract Menu Data',
      description: `This will extract menu data from ${extractionDoc.menu_images.length} image(s). Continue?`,
      variant: 'info',
      confirmText: 'Continue',
      cancelText: 'Cancel'
    })

    if (!confirmed) {
      return
    }

    try {
      // Call the API with docname as a parameter object
      // The backend function expects: extract_menu_data(docname)
      const result = await extractMenuData({ docname: selectedDocName })
      let message = 'Extraction started in the background'
      if (result) {
        if (typeof result === 'string') {
          message = result
        } else if (result.message) {
          message = String(result.message)
        } else if (result.data?.message) {
          message = String(result.data.message)
        }
      }
      toast.success(message)
      // Refresh immediately to show Processing status
      refreshExtraction()
    } catch (error: any) {
      console.error('Extraction error:', error)
      // Better error handling for 417 and other errors
      let errorMessage = 'Failed to start extraction'
      if (error?.exc) {
        try {
          const excData = typeof error.exc === 'string' ? JSON.parse(error.exc) : error.exc
          errorMessage = Array.isArray(excData) ? excData[0] : (excData?.message || String(excData))
        } catch {
          errorMessage = String(error.exc)
        }
      } else if (error?.message) {
        errorMessage = String(error.message)
      } else if (error?.data?.message) {
        errorMessage = String(error.data.message)
      } else if (error?.response?.data?.message) {
        errorMessage = String(error.response.data.message)
      }
      toast.error(errorMessage)
    }
  }

  const handleApprove = async () => {
    if (!selectedDocName) {
      toast.error('Document not found')
      return
    }

    const confirmed = await confirm({
      title: 'Approve Extraction',
      description: 'This will create/update menu categories and products in the database. Continue?',
      variant: 'warning',
      confirmText: 'Approve',
      cancelText: 'Cancel'
    })

    if (!confirmed) {
      return
    }

    try {
      const result = await approveExtraction({ docname: selectedDocName })
      let message = 'Extracted data approved and categories/products created successfully'
      if (result) {
        if (typeof result === 'string') {
          message = result
        } else if (result.message) {
          message = String(result.message)
        } else if (result.data?.message) {
          message = String(result.data.message)
        }
      }
      toast.success(message)
      refreshExtraction()
      onExtractionComplete?.(extractionDoc)
    } catch (error: any) {
      const errorMessage = error?.message || error?.data?.message || 'Failed to approve extraction'
      toast.error(typeof errorMessage === 'string' ? errorMessage : 'Failed to approve extraction')
    }
  }

  if (isLoadingList) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
        Loading...
      </div>
    )
  }

  const status = extractionDoc?.extraction_status || 'Draft'
  const isCompleted = status === 'Completed'
  const isProcessing = status === 'Processing'
  const isPendingApproval = status === 'Pending Approval'
  const hasError = status === 'Failed'
  const isDraft = status === 'Draft'

  return (
    <div className="space-y-6">
      {/* Document Selector */}
      <Card>
        <CardHeader>
          <CardTitle>Select Menu Image Extractor</CardTitle>
          <CardDescription>
            Choose an existing extraction or create a new one
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4 items-end">
            <div className="flex-1">
              <label className="text-sm font-medium mb-2 block">Select Document</label>
              <Select
                value={selectedDocName || ''}
                onValueChange={(value) => {
                  if (value === 'new') {
                    setSelectedDocName(null)
                    localStorage.removeItem(`menu-extraction-${restaurantId}`)
                  } else {
                    handleSelectDocument(value)
                  }
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select or create a document" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="new">+ Create New Extraction</SelectItem>
                  {extractions?.map((ext: any) => (
                    <SelectItem key={ext.name} value={ext.name}>
                      {ext.name} - {ext.extraction_status || 'Draft'} ({new Date(ext.creation).toLocaleDateString()})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Main Form - Just like the doctype */}
      <Card className="border-2">
        <CardHeader>
          <CardTitle>Menu Image Extractor</CardTitle>
          <CardDescription>
            Upload menu images and extract categories and products automatically
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DynamicForm
            doctype="Menu Image Extractor"
            docname={selectedDocName || undefined}
            mode={selectedDocName ? 'edit' : 'create'}
            initialData={{ restaurant: restaurantId }}
            onSave={(data) => {
              setSelectedDocName(data.name)
              localStorage.setItem(`menu-extraction-${restaurantId}`, data.name)
              refreshExtraction()
              toast.success('Document saved successfully')
            }}
          />
        </CardContent>
      </Card>

      {/* Extraction Status and Actions */}
      {selectedDocName && extractionDoc && (
        <Card className="border-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Extraction Status</CardTitle>
                <CardDescription>
                  Current status of menu extraction
                </CardDescription>
              </div>
              <Badge 
                variant={
                  isCompleted ? 'default' : 
                  isPendingApproval ? 'secondary' :
                  isProcessing ? 'secondary' : 
                  hasError ? 'destructive' : 
                  'outline'
                }
              >
                {isCompleted && <CheckCircle className="mr-1 h-3 w-3" />}
                {isPendingApproval && <Clock className="mr-1 h-3 w-3" />}
                {isProcessing && <Clock className="mr-1 h-3 w-3" />}
                {hasError && <XCircle className="mr-1 h-3 w-3" />}
                {status}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Processing Progress */}
            {isProcessing && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span>Processing batches...</span>
                  <span>
                    {extractionDoc.completed_batches || 0} / {extractionDoc.total_batches || 0}
                  </span>
                </div>
                <Progress 
                  value={
                    extractionDoc.total_batches 
                      ? ((extractionDoc.completed_batches || 0) / extractionDoc.total_batches) * 100 
                      : 0
                  } 
                  className="h-2"
                />
              </div>
            )}

            {/* Extraction Log */}
            {extractionDoc.extraction_log && (
              <div className="p-3 bg-muted rounded text-sm">
                {extractionDoc.extraction_log}
              </div>
            )}

            {/* Extract Button */}
            {!isProcessing && (
              <Button 
                onClick={handleExtract} 
                disabled={
                  !selectedDocName || 
                  !extractionDoc || 
                  !extractionDoc.menu_images || 
                  extractionDoc.menu_images.length === 0 || 
                  isPendingApproval
                }
                size="lg"
                className="w-full"
                title={
                  !selectedDocName 
                    ? 'Please select or create a document first'
                    : !extractionDoc 
                    ? 'Please wait for document to load'
                    : !extractionDoc.menu_images || extractionDoc.menu_images.length === 0
                    ? 'Please upload at least one menu image'
                    : isPendingApproval
                    ? 'Extraction is pending approval. Please approve or extract again.'
                    : 'Click to extract menu data from uploaded images'
                }
              >
                <Play className="mr-2 h-4 w-4" />
                {isCompleted || hasError ? 'Extract Again' : 'Extract Menu Data'}
              </Button>
            )}

            {/* Extraction Results Stats */}
            {(isCompleted || isPendingApproval) && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-muted rounded-md">
                <div>
                  <div className="text-sm text-muted-foreground">Categories</div>
                  <div className="text-2xl font-bold">{extractionDoc.categories_created || 0}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">Items Created</div>
                  <div className="text-2xl font-bold">{extractionDoc.items_created || 0}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">Items Updated</div>
                  <div className="text-2xl font-bold">{extractionDoc.items_updated || 0}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">Items Skipped</div>
                  <div className="text-2xl font-bold">{extractionDoc.items_skipped || 0}</div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Extracted Dishes - Review and Edit - Only show when status is Pending Approval (fresh from API) */}
      {isPendingApproval && extractionDoc?.extracted_dishes && Array.isArray(extractionDoc.extracted_dishes) && extractionDoc.extracted_dishes.length > 0 && (
        <Card className="border-2 border-primary/20">
          <CardHeader>
            <CardTitle>Extracted Dishes - Review and Edit</CardTitle>
            <CardDescription>
              {extractionDoc.extracted_dishes.length} dish{extractionDoc.extracted_dishes.length !== 1 ? 'es' : ''} extracted from API processing. 
              Review and edit before approval. Changes will be saved automatically.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <EditableExtractedDishesTable
              dishes={extractionDoc.extracted_dishes}
              docname={selectedDocName!}
              onUpdate={refreshExtraction}
            />
          </CardContent>
        </Card>
      )}

      {/* Show message when extraction is completed (old data hidden) */}
      {isCompleted && (!extractionDoc?.extracted_dishes || extractionDoc.extracted_dishes.length === 0) && (
        <Card className="border-2">
          <CardContent className="py-6">
            <p className="text-sm text-muted-foreground text-center">
              Extraction completed and data approved. Click "Extract Again" to process new images.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Approve Button */}
      {isPendingApproval && (
        <Card className="border-2 border-green-200 bg-green-50/50">
          <CardContent className="py-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold mb-1">Ready to Create Categories & Products?</h3>
                <p className="text-sm text-muted-foreground">
                  Approve the extracted data to automatically create menu categories and products in the database.
                </p>
              </div>
              <Button 
                onClick={handleApprove}
                size="lg"
                className="bg-green-600 hover:bg-green-700"
              >
                <Check className="mr-2 h-4 w-4" />
                Approve & Create Menu Items
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
      {ConfirmDialogComponent}
    </div>
  )
}
