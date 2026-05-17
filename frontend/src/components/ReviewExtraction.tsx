import { useFrappeGetDocList, useFrappeGetDoc, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Loader2, CheckCircle, XCircle, Clock, FileText } from 'lucide-react'
import { toast } from 'sonner'
import { useState, useEffect } from 'react'

interface ReviewExtractionProps {
  restaurantId: string
}

export default function ReviewExtraction({ restaurantId }: ReviewExtractionProps) {
  const [processing, setProcessing] = useState(false)

  // Get latest extraction for this restaurant
  const { data: extractions, isLoading } = useFrappeGetDocList(
    'Menu Image Extractor',
    {
      fields: ['name', 'restaurant', 'extraction_status', 'extraction_log', 'total_batches', 'completed_batches', 'creation', 'modified'],
      filters: restaurantId ? [['restaurant', '=', restaurantId]] : undefined,
      orderBy: { field: 'creation', order: 'desc' },
      limit: 1
    },
    restaurantId ? `menu-extraction-${restaurantId}` : null
  )

  const latestExtraction = extractions?.[0]

  // Get extraction document with full data
  const { data: extractionDoc, mutate: refreshExtraction } = useFrappeGetDoc(
    'Menu Image Extractor',
    latestExtraction?.name || '',
    {
      enabled: !!latestExtraction?.name
    }
  )

  // Auto-refresh if processing
  useEffect(() => {
    if (latestExtraction?.extraction_status === 'Processing') {
      const interval = setInterval(() => {
        refreshExtraction()
      }, 5000) // Refresh every 5 seconds
      return () => clearInterval(interval)
    }
  }, [latestExtraction?.extraction_status, refreshExtraction])

  const { call: approveExtraction } = useFrappePostCall(
    'flamezo_backend.flamezo.doctype.menu_image_extractor.menu_image_extractor.approve_extracted_data'
  )

  const handleApprove = async () => {
    if (!latestExtraction?.name) return

    setProcessing(true)
    try {
      const result = await approveExtraction({ docname: latestExtraction.name })
      // Handle different response formats
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
      // Refresh data reactively
      refreshExtraction()
    } catch (error: any) {
      const errorMessage = error?.message || error?.data?.message || 'Failed to approve extraction'
      toast.error(typeof errorMessage === 'string' ? errorMessage : 'Failed to approve extraction')
    } finally {
      setProcessing(false)
    }
  }

  if (isLoading) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
        Loading extraction data...
      </div>
    )
  }

  if (!latestExtraction) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground mb-4">
            No extraction found for this restaurant.
          </p>
          <p className="text-sm text-muted-foreground">
            Please go back to the "Extract Menu from Images" step to upload menu images.
          </p>
        </CardContent>
      </Card>
    )
  }

  const status = latestExtraction.extraction_status || extractionDoc?.extraction_status
  const isCompleted = status === 'Completed'
  const isPendingApproval = status === 'Pending Approval'
  const isProcessing = status === 'Processing'
  const hasError = status === 'Failed'
  const canApprove = isPendingApproval || isCompleted

  // Parse extracted data from raw_response or child tables
  let categories: any[] = []
  let dishes: any[] = []
  
  if (extractionDoc) {
    try {
      // First, try to get dishes from child table (most reliable)
      if (extractionDoc.extracted_dishes && Array.isArray(extractionDoc.extracted_dishes) && extractionDoc.extracted_dishes.length > 0) {
        dishes = extractionDoc.extracted_dishes.map((d: any) => ({
          name: d.dish_name || d.product_name || d.name,
          product_name: d.dish_name || d.product_name || d.name,
          description: d.description,
          price: d.price,
          category: d.category || d.main_category
        }))
      }
      
      // Parse raw_response for categories and dishes (if child table is empty)
      if (extractionDoc.raw_response) {
        const rawData = typeof extractionDoc.raw_response === 'string' 
          ? JSON.parse(extractionDoc.raw_response) 
          : extractionDoc.raw_response
        
        // Handle different response structures
        let data = rawData
        if (rawData?.data) {
          data = rawData.data
        } else if (rawData?.success && rawData?.data) {
          data = rawData.data
        }
        
        // Extract categories
        if (data?.categories) {
          let cats = data.categories
          if (!Array.isArray(cats)) {
            // Convert dict to array
            if (typeof cats === 'object') {
              cats = Object.values(cats)
            } else {
              cats = []
            }
          }
          categories = cats.filter((c: any) => c && typeof c === 'object')
        }
        
        // Extract dishes if not already from child table
        if (dishes.length === 0 && data?.dishes) {
          let dishesData = data.dishes
          if (!Array.isArray(dishesData)) {
            // Convert dict to array
            if (typeof dishesData === 'object') {
              dishesData = Object.values(dishesData)
            } else {
              dishesData = []
            }
          }
          dishes = dishesData.map((d: any) => ({
            name: d.name || d.product_name || d.dish_name,
            product_name: d.name || d.product_name || d.dish_name,
            description: d.description,
            price: d.price,
            category: d.category || d.mainCategory
          }))
        }
      }
      
      // Extract unique categories from dishes if no categories found
      if (categories.length === 0 && dishes.length > 0) {
        const uniqueCategories = new Set<string>()
        dishes.forEach((dish: any) => {
          if (dish.category) {
            uniqueCategories.add(dish.category)
          }
        })
        categories = Array.from(uniqueCategories).map(cat => ({ name: cat, category_name: cat }))
      }
    } catch (e) {
      console.error('Error parsing extraction data:', e)
      console.error('ExtractionDoc:', extractionDoc)
    }
  }

  return (
    <div className="space-y-6">
      {/* Extraction Status */}
      <Card className="border-2">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Extraction Status</CardTitle>
              <CardDescription>
                Latest extraction for this restaurant
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
              {status || 'Pending'}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          {isProcessing && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Processing batches: {latestExtraction.completed_batches || 0} / {latestExtraction.total_batches || 0}</span>
              </div>
              <Progress 
                value={latestExtraction.total_batches ? ((latestExtraction.completed_batches || 0) / latestExtraction.total_batches) * 100 : 0} 
                className="h-2"
              />
            </div>
          )}
          {latestExtraction.extraction_log && (
            <div className="mt-4 p-3 bg-muted rounded text-sm">
              {latestExtraction.extraction_log}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Extracted Data Preview */}
      {(canApprove || dishes.length > 0 || categories.length > 0) && (
        <>
          <Card className="border-2">
            <CardHeader>
              <CardTitle>Extracted Categories</CardTitle>
              <CardDescription>
                {categories.length} categor{categories.length !== 1 ? 'ies' : 'y'} found
              </CardDescription>
            </CardHeader>
            <CardContent>
              {categories.length > 0 ? (
                <div className="space-y-2">
                  {categories.slice(0, 10).map((cat: any, idx: number) => (
                    <div key={idx} className="p-3 border rounded-md">
                      <div className="font-medium">{cat.name || cat.category_name}</div>
                      {cat.description && (
                        <div className="text-sm text-muted-foreground mt-1">{cat.description}</div>
                      )}
                    </div>
                  ))}
                  {categories.length > 10 && (
                    <p className="text-sm text-muted-foreground text-center">
                      + {categories.length - 10} more categories
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-muted-foreground text-center py-4">No categories extracted</p>
              )}
            </CardContent>
          </Card>

          <Card className="border-2">
            <CardHeader>
              <CardTitle>Extracted Products</CardTitle>
              <CardDescription>
                {dishes.length} product{dishes.length !== 1 ? 's' : ''} found
              </CardDescription>
            </CardHeader>
            <CardContent>
              {dishes.length > 0 ? (
                <div className="space-y-2">
                  {dishes.slice(0, 10).map((dish: any, idx: number) => (
                    <div key={idx} className="p-3 border rounded-md">
                      <div className="font-medium">{dish.name || dish.product_name}</div>
                      {dish.description && (
                        <div className="text-sm text-muted-foreground mt-1">{dish.description}</div>
                      )}
                      {dish.price && (
                        <div className="text-sm font-medium mt-1">${dish.price}</div>
                      )}
                    </div>
                  ))}
                  {dishes.length > 10 && (
                    <p className="text-sm text-muted-foreground text-center">
                      + {dishes.length - 10} more products
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-muted-foreground text-center py-4">No products extracted</p>
              )}
            </CardContent>
          </Card>

          {/* Approve Button - Show for Pending Approval or Completed status */}
          {canApprove && (
            <Card className="border-2 border-primary/20">
              <CardContent className="py-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold mb-1">Ready to Create Categories & Products?</h3>
                    <p className="text-sm text-muted-foreground">
                      Approve the extracted data to automatically create menu categories and products.
                    </p>
                  </div>
                  <Button 
                    onClick={handleApprove}
                    disabled={processing || isCompleted}
                    size="lg"
                  >
                    {processing ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Processing...
                      </>
                    ) : isCompleted ? (
                      <>
                        <CheckCircle className="mr-2 h-4 w-4" />
                        Already Approved
                      </>
                    ) : (
                      <>
                        <CheckCircle className="mr-2 h-4 w-4" />
                        Approve & Create Menu Items
                      </>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

