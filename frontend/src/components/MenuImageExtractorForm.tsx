import { useState, useEffect } from 'react'
import { useFrappeGetDoc, useFrappePostCall } from '@/lib/frappe'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Stepper } from '@/components/ui/stepper'
import {
  Loader2, CheckCircle, Check,
  Settings, Image as ImageIcon, Sparkles,
  ArrowLeft, AlertTriangle, X, FileText, LayoutGrid
} from 'lucide-react'
import { toast } from 'sonner'
import MenuImagesTable from './MenuImagesTable'
import EditableExtractedDishesTable from './EditableExtractedDishesTable'
import { useConfirm } from '@/hooks/useConfirm'
import { cn } from '@/lib/utils'
import {
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'

interface MenuImageExtractorFormProps {
  docname?: string
  restaurantId?: string
  restaurantName?: string
  onComplete?: (data: any) => void
  onClose?: () => void
}

type Step = 'setup' | 'images' | 'processing' | 'review'

interface ExtractionStatus {
  status: string
  total_batches: number
  completed_batches: number
  progress_pct: number
  extraction_log: string
  items_created: number
  categories_created: number
  modified: string | null
}

const STEP_ORDER: Step[] = ['setup', 'images', 'processing', 'review']

const STEPPER_STEPS = [
  { id: 'setup', title: 'Setup' },
  { id: 'images', title: 'Upload Images' },
  { id: 'processing', title: 'Processing' },
  { id: 'review', title: 'Review & Approve' },
]

export default function MenuImageExtractorForm({
  docname,
  restaurantId,
  restaurantName: initialRestaurantName,
  onComplete,
  onClose
}: MenuImageExtractorFormProps) {
  const { confirm, ConfirmDialogComponent } = useConfirm()
  const [extractionDocName, setExtractionDocName] = useState<string | undefined>(docname)
  const [activeStep, setActiveStep] = useState<Step>('setup')
  const [isSaving, setIsSaving] = useState(false)
  const [hasUploadedImages, setHasUploadedImages] = useState(false)

  const [restaurantName, setRestaurantName] = useState(initialRestaurantName || '')
  const autoDescriptions = true

  const [liveStatus, setLiveStatus] = useState<ExtractionStatus | null>(null)
  const [isPolling, setIsPolling] = useState(false)

  const { data: extractionDoc, mutate: refreshExtraction, isLoading: isDocLoading } = useFrappeGetDoc(
    'Menu Image Extractor',
    extractionDocName || '',
    {
      enabled: !!extractionDocName
    }
  )

  const { call: insertDoc } = useFrappePostCall('flamezo_backend.flamezo.api.documents.create_document')
  const { call: updateDocument } = useFrappePostCall('flamezo_backend.flamezo.api.documents.update_document')

  const { call: extractMenuData } = useFrappePostCall(
    'flamezo_backend.flamezo.doctype.menu_image_extractor.menu_image_extractor.extract_menu_data'
  )

  const { call: getExtractionStatus } = useFrappePostCall(
    'flamezo_backend.flamezo.doctype.menu_image_extractor.menu_image_extractor.get_extraction_status'
  )

  const { call: approveExtraction } = useFrappePostCall(
    'flamezo_backend.flamezo.doctype.menu_image_extractor.menu_image_extractor.approve_extracted_data'
  )

  const { call: recoverExtraction } = useFrappePostCall(
    'flamezo_backend.flamezo.doctype.menu_image_extractor.menu_image_extractor.recover_extraction'
  )

  useEffect(() => {
    if (extractionDoc?.menu_images?.length) {
      setHasUploadedImages(true)
    }
  }, [extractionDoc?.menu_images?.length])

  useEffect(() => {
    if (extractionDoc && !isPolling) {
      const status = extractionDoc.extraction_status
      if (status === 'Pending Approval' || status === 'Completed') {
        setActiveStep('review')
      } else if (status === 'Processing') {
        if (extractionDocName && activeStep !== 'processing') {
          setActiveStep('processing')
        }
      } else if (extractionDocName) {
        setActiveStep('images')
      }
      if (extractionDoc.restaurant_name && !restaurantName) setRestaurantName(extractionDoc.restaurant_name)
    }
  }, [extractionDoc?.name])

  useEffect(() => {
    if (!extractionDocName || activeStep !== 'processing') return
    if (liveStatus?.status === 'Pending Approval' || liveStatus?.status === 'Completed' || liveStatus?.status === 'Failed') {
      setIsPolling(false)
      return
    }

    setIsPolling(true)
    // Self-heal: if the backend modified timestamp doesn't change for ~30s
    // consecutive polls, ask the backend to recover (re-aggregate if all batches
    // are actually done, or mark Failed if truly stuck >5min on server side).
    let lastModified: string | null = null
    let stalePolls = 0
    let recovering = false

    const interval = setInterval(async () => {
      try {
        const res = await getExtractionStatus({ docname: extractionDocName })
        if (!res?.message) return

        const newStatus: ExtractionStatus = res.message
        setLiveStatus(newStatus)

        if (newStatus.status === 'Pending Approval' || newStatus.status === 'Completed') {
          clearInterval(interval)
          setIsPolling(false)
          setTimeout(async () => {
            toast.success(`Extraction complete — found ${newStatus.items_created} dishes in ${newStatus.categories_created} categories.`)
            await refreshExtraction()
            setActiveStep('review')
          }, 800)
          return
        }

        if (newStatus.status === 'Failed') {
          clearInterval(interval)
          setIsPolling(false)
          toast.error('Extraction failed. Please check the error log and retry.')
          return
        }

        // Stall detection
        if (newStatus.modified && newStatus.modified === lastModified) {
          stalePolls += 1
        } else {
          stalePolls = 0
          lastModified = newStatus.modified
        }

        // After ~15 consecutive 2s polls with no doc updates (~30s), nudge backend.
        if (stalePolls >= 15 && !recovering) {
          recovering = true
          try {
            const r = await recoverExtraction({ docname: extractionDocName })
            if (r?.message?.recovered) {
              stalePolls = 0
              lastModified = null
            }
          } catch (e) {
            console.error('recover_extraction failed:', e)
          } finally {
            recovering = false
          }
        }
      } catch (err) {
        console.error('Extraction status poll error:', err)
      }
    }, 2000)

    return () => clearInterval(interval)
  }, [extractionDocName, activeStep, liveStatus?.status])

  const handleStart = async () => {
    if (!restaurantId) return
    setIsSaving(true)
    try {
      const result = await insertDoc({
        doctype: 'Menu Image Extractor',
        doc_data: {
          restaurant: restaurantId,
          restaurant_name: restaurantName,
          generate_descriptions: autoDescriptions ? 1 : 0
        }
      })
      if (result?.message?.name) {
        setExtractionDocName(result.message.name)
        setActiveStep('images')
        toast.success('Session started')
      }
    } catch (err: any) {
      toast.error(err?.message || 'Failed to start session')
    } finally {
      setIsSaving(false)
    }
  }

  const handleExtract = async () => {
    if (!extractionDocName || isSaving) return
    const hasImages = hasUploadedImages || (extractionDoc?.menu_images && extractionDoc.menu_images.length > 0)
    if (!hasImages) {
      toast.error('Please upload at least one menu image')
      return
    }

    setIsSaving(true)
    try {
      await extractMenuData({ docname: extractionDocName })
      toast.success('Extraction started')
      setLiveStatus(null)
      setActiveStep('processing')
    } catch (err: any) {
      toast.error(err?.message || 'Failed to start extraction')
    } finally {
      setIsSaving(false)
    }
  }

  const handleApprove = async () => {
    if (!extractionDocName || isSaving) return
    const confirmed = await confirm({
      title: 'Approve & generate menu?',
      description: 'This will create menu categories and products from the extracted data.',
      confirmText: 'Approve',
      cancelText: 'Cancel'
    })
    if (!confirmed) return

    setIsSaving(true)
    try {
      await approveExtraction({ docname: extractionDocName })
      toast.success('Menu generated successfully')
      refreshExtraction()
      onComplete?.(extractionDoc)
    } catch (err: any) {
      toast.error(err?.message || 'Approval failed')
    } finally {
      setIsSaving(false)
    }
  }

  if (isDocLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-32 bg-background min-h-[500px]">
        <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
        <p className="text-sm text-muted-foreground">Loading session…</p>
      </div>
    )
  }

  const isFinalState = activeStep === 'review' || extractionDoc?.extraction_status === 'Pending Approval' || extractionDoc?.extraction_status === 'Completed'
  const currentStatus = (isFinalState ? extractionDoc?.extraction_status : liveStatus?.status) || extractionDoc?.extraction_status
  const totalBatches = (isFinalState ? extractionDoc?.total_batches : (liveStatus?.total_batches || extractionDoc?.total_batches)) || 0
  const completedBatches = (isFinalState ? extractionDoc?.completed_batches : (liveStatus?.completed_batches || extractionDoc?.completed_batches)) || 0

  const itemsFound = Math.max(liveStatus?.items_created || 0, extractionDoc?.items_created || 0)
  const categoriesFound = Math.max(liveStatus?.categories_created || 0, extractionDoc?.categories_created || 0)

  const progressPct = liveStatus?.progress_pct
    ?? (totalBatches > 0 ? Math.round((completedBatches / totalBatches) * 100) : 0)
  const liveLogText = (liveStatus?.extraction_log || extractionDoc?.extraction_log || '').trim()
  const firstLineOfLog = liveLogText.split('\n')[0] || 'Initializing…'

  const currentStepIndex = STEP_ORDER.indexOf(activeStep)

  const handleStepClick = (idx: number) => {
    const target = STEP_ORDER[idx]
    if (!target) return
    if (idx > currentStepIndex) return
    // Don't allow jumping back to setup once a session exists
    if (target === 'setup' && extractionDocName) return
    if (target === 'processing' && !extractionDocName) return
    setActiveStep(target)
  }

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Sticky Header — matches dashboard pattern */}
      <div className="sticky top-0 z-20 bg-background/95 backdrop-blur-sm border-b px-6 py-5">
        <button
          onClick={onClose}
          className="absolute right-5 top-5 p-1.5 rounded-md hover:bg-muted transition-colors"
          aria-label="Close"
        >
          <X className="h-4 w-4 text-muted-foreground" />
        </button>

        <DialogHeader className="pr-10 mb-5">
          <div className="flex items-center gap-2 mb-1">
            <Badge variant="secondary" className="gap-1.5 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider">
              <Sparkles className="h-3 w-3 text-primary" />
              AI Menu Import
            </Badge>
            {extractionDocName && (
              <Badge variant="outline" className="px-2 py-0.5 text-[10px] font-mono">
                {extractionDocName}
              </Badge>
            )}
          </div>
          <DialogTitle className="text-xl font-semibold tracking-tight">
            Import menu from images
          </DialogTitle>
          <DialogDescription className="text-sm">
            Upload photos of your physical menu — we'll extract categories, dishes, and prices
            {restaurantName ? <> for <span className="text-foreground font-medium">{restaurantName}</span></> : ''}.
          </DialogDescription>
        </DialogHeader>

        <Stepper
          steps={STEPPER_STEPS}
          currentStep={currentStepIndex}
          onStepClick={handleStepClick}
        />
      </div>

      <div className="flex-1 overflow-y-auto min-h-[400px]">
        {/* STEP 1: SETUP */}
        {activeStep === 'setup' && (
          <div className="p-6 max-w-2xl mx-auto space-y-6">
            <Card className="shadow-xs">
              <CardHeader>
                <div className="flex items-center gap-3">
                  <div className="h-9 w-9 rounded-md bg-primary/10 text-primary flex items-center justify-center">
                    <Settings className="h-4 w-4" />
                  </div>
                  <div>
                    <CardTitle>Restaurant details</CardTitle>
                    <CardDescription>Provide the brand name to improve extraction accuracy</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="restaurant-name" className="text-sm font-medium">
                    Restaurant brand name
                  </Label>
                  <Input
                    id="restaurant-name"
                    placeholder="e.g. The Gourmet Yard"
                    value={restaurantName}
                    onChange={(e) => setRestaurantName(e.target.value)}
                    className="h-10"
                  />
                  <p className="text-xs text-muted-foreground">
                    Used as context when reading menu images — helps resolve ambiguous text and item names.
                  </p>
                </div>
              </CardContent>
            </Card>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card className="shadow-xs">
                <CardHeader className="pb-3">
                  <div className="h-9 w-9 rounded-md bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 flex items-center justify-center mb-2">
                    <FileText className="h-4 w-4" />
                  </div>
                  <CardTitle className="text-sm">Auto descriptions</CardTitle>
                  <CardDescription className="text-xs">
                    Generates short, professional descriptions for each dish based on its name.
                  </CardDescription>
                </CardHeader>
              </Card>

              <Card className="shadow-xs">
                <CardHeader className="pb-3">
                  <div className="h-9 w-9 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mb-2">
                    <LayoutGrid className="h-4 w-4" />
                  </div>
                  <CardTitle className="text-sm">Smart categorization</CardTitle>
                  <CardDescription className="text-xs">
                    Maps items to logical menu sections detected in the source images.
                  </CardDescription>
                </CardHeader>
              </Card>
            </div>
          </div>
        )}

        {/* STEP 2: IMAGES */}
        {activeStep === 'images' && (
          <div className="p-6 max-w-4xl mx-auto">
            <MenuImagesTable
              ownerDoctype="Menu Image Extractor"
              ownerName={extractionDocName}
              value={extractionDoc?.menu_images || []}
              onChange={async (newImages) => {
                if (newImages.length > 0) setHasUploadedImages(true)
                if (extractionDocName) {
                  try {
                    await updateDocument({
                      doctype: 'Menu Image Extractor',
                      name: extractionDocName,
                      doc_data: { menu_images: newImages }
                    })
                    refreshExtraction()
                  } catch (err: any) {
                    console.error('Failed to update extraction doc:', err)
                    toast.error(err?.message || 'Failed to sync image list')
                  }
                }
              }}
            />
          </div>
        )}

        {/* STEP 3: PROCESSING */}
        {activeStep === 'processing' && (
          <div className="p-6 max-w-2xl mx-auto">
            <Card className="shadow-xs">
              <CardHeader className="text-center pb-4">
                <div className="mx-auto h-14 w-14 rounded-xl bg-primary/10 text-primary flex items-center justify-center mb-3">
                  <Loader2 className="h-6 w-6 animate-spin" />
                </div>
                <CardTitle className="text-lg">Processing your menu</CardTitle>
                <CardDescription>
                  This usually takes 1–3 minutes depending on the number of images.
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-6">
                {/* Status line */}
                <div className="flex items-center justify-center gap-2 px-3 py-2 rounded-md bg-muted/40 border border-border/60">
                  <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                  <span className="text-xs font-medium text-muted-foreground truncate">
                    {firstLineOfLog}
                  </span>
                </div>

                {/* Progress */}
                <div className="space-y-2">
                  <Progress value={Math.max(progressPct, 3)} className="h-2" />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>
                      {totalBatches > 0 ? `Batch ${completedBatches} of ${totalBatches}` : 'Starting…'}
                    </span>
                    <span className="font-semibold text-foreground">{progressPct}%</span>
                  </div>
                </div>

                {/* Live counters */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-md border bg-card p-4">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        Items found
                      </span>
                      <Sparkles className="h-3.5 w-3.5 text-primary/60" />
                    </div>
                    <p className="text-2xl font-bold tracking-tight">{itemsFound}</p>
                  </div>
                  <div className="rounded-md border bg-card p-4">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        Categories
                      </span>
                      <LayoutGrid className="h-3.5 w-3.5 text-primary/60" />
                    </div>
                    <p className="text-2xl font-bold tracking-tight">{categoriesFound}</p>
                  </div>
                </div>

                {currentStatus === 'Failed' && (
                  <div className="rounded-md border border-destructive/30 bg-destructive/5 p-4 flex gap-3 items-start">
                    <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-destructive" />
                    <div className="space-y-2 flex-1">
                      <p className="font-semibold text-sm text-destructive">Extraction failed</p>
                      <p className="text-xs text-muted-foreground leading-relaxed">
                        {liveStatus?.extraction_log || extractionDoc?.extraction_log || 'Something went wrong while processing the images.'}
                      </p>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => setActiveStep('images')}
                      >
                        Back to images
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* STEP 4: REVIEW */}
        {activeStep === 'review' && (
          <div className="p-6 max-w-5xl mx-auto space-y-6">
            {/* Summary stats */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                { label: 'Categories', val: categoriesFound, icon: LayoutGrid, color: 'text-primary' },
                { label: 'Dishes Found', val: itemsFound, icon: Sparkles, color: 'text-indigo-600 dark:text-indigo-400' },
                { label: 'Updated', val: extractionDoc?.items_updated || 0, icon: CheckCircle, color: 'text-emerald-600 dark:text-emerald-400' },
                { label: 'Skipped', val: extractionDoc?.items_skipped || 0, icon: X, color: 'text-rose-600 dark:text-rose-400' }
              ].map((stat, i) => (
                <Card key={i} className="shadow-xs">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-muted-foreground uppercase font-semibold tracking-wider">
                        {stat.label}
                      </span>
                      <stat.icon className={cn("h-3.5 w-3.5", stat.color)} />
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className={cn("text-2xl font-bold tracking-tight", stat.color)}>
                      {stat.val}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>

            {extractionDoc?.extracted_dishes?.length > 0 && (
              <Card className="shadow-xs overflow-hidden">
                <CardHeader>
                  <CardTitle className="text-base">Review extracted dishes</CardTitle>
                  <CardDescription>
                    Edit names, prices, or remove items before approving. Approved items will be added to your menu.
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  <EditableExtractedDishesTable
                    dishes={extractionDoc.extracted_dishes}
                    docname={extractionDocName!}
                    onUpdate={refreshExtraction}
                  />
                </CardContent>
              </Card>
            )}

            {isFinalState && currentStatus === 'Completed' && (
              <Card className="shadow-xs border-emerald-500/30 bg-emerald-50/50 dark:bg-emerald-950/20">
                <CardContent className="py-8 text-center">
                  <div className="h-12 w-12 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-full flex items-center justify-center mx-auto mb-3">
                    <Check className="h-6 w-6" />
                  </div>
                  <h4 className="text-base font-semibold mb-1">Menu generated successfully</h4>
                  <p className="text-sm text-muted-foreground max-w-sm mx-auto">
                    Your categories and products are now live. You can manage them from Menu Management.
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </div>

      {/* Sticky Action Footer */}
      <div className="sticky bottom-0 z-20 bg-background/95 backdrop-blur-sm border-t px-6 py-3.5 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {activeStep !== 'setup' && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                if (activeStep === 'images') setActiveStep('setup')
                else if (activeStep === 'processing' || activeStep === 'review') setActiveStep('images')
              }}
              disabled={isSaving || isPolling}
              className="gap-1.5 text-muted-foreground"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Back
            </Button>
          )}
        </div>

        <div className="flex items-center gap-2">
          {activeStep === 'setup' && (
            <Button
              onClick={handleStart}
              disabled={isSaving || !restaurantName}
              className="min-w-[140px]"
            >
              {isSaving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  Continue
                </>
              )}
            </Button>
          )}

          {activeStep === 'images' && (
            <Button
              onClick={handleExtract}
              disabled={isSaving || (!hasUploadedImages && (!extractionDoc?.menu_images || extractionDoc.menu_images.length === 0))}
              className="min-w-[180px] gap-2"
            >
              {isSaving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Extract menu
                </>
              )}
            </Button>
          )}

          {activeStep === 'review' && currentStatus !== 'Completed' && (
            <Button
              onClick={handleApprove}
              disabled={isSaving}
              className="min-w-[180px] gap-2 bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              {isSaving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <Check className="h-4 w-4" />
                  Approve & generate menu
                </>
              )}
            </Button>
          )}

          {(currentStatus === 'Completed' || activeStep === 'review') && (
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
          )}
        </div>
      </div>

      {ConfirmDialogComponent}
    </div>
  )
}
