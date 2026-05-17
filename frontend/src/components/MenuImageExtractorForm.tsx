import { useState, useEffect } from 'react'
import { useFrappeGetDoc, useFrappePostCall } from '@/lib/frappe'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { 
  Loader2, CheckCircle, Check, 
  Settings, Image as ImageIcon, Sparkles, ChevronRight,
  ArrowLeft, AlertTriangle, X, ShieldCheck, Zap
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
  extraction_log: string
  items_created: number
  categories_created: number
}

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
            toast.success(`AI Extraction complete! Found ${newStatus.items_created} dishes in ${newStatus.categories_created} categories.`)
            await refreshExtraction()
            setActiveStep('review')
          }, 800)
        } else if (newStatus.status === 'Failed') {
          clearInterval(interval)
          setIsPolling(false)
          toast.error('Extraction failed. Please check the error log and retry.')
        }
      } catch (err) {
        console.error('Extraction status poll error:', err)
      }
    }, 2000)

    return () => clearInterval(interval)
  }, [extractionDocName, activeStep, liveStatus?.status])

  const [magicStatusIdx, setMagicStatusIdx] = useState(0)
  const magicStatuses = [
    'Deep scanning menu images...',
    'Identifying food categories...',
    'Extracting product names & prices...',
    'Generating professional descriptions...',
    'Refining menu structure...',
    'Organizing dish metadata...',
  ]

  useEffect(() => {
    if (activeStep === 'processing') {
      const interval = setInterval(() => {
        setMagicStatusIdx(prev => (prev + 1) % magicStatuses.length)
      }, 2500)
      return () => clearInterval(interval)
    }
  }, [activeStep])

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
        toast.success('Onboarding session started')
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
      toast.success('AI extraction started!')
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
      title: 'Final Approval',
      description: 'Create menu categories and products now?',
      confirmText: 'Approve',
      cancelText: 'Wait'
    })
    if (!confirmed) return

    setIsSaving(true)
    try {
      await approveExtraction({ docname: extractionDocName })
      toast.success('Extraction approved! Menu generated.')
      refreshExtraction()
      onComplete?.(extractionDoc)
    } catch (err: any) {
      toast.error(err?.message || 'Approval failed')
    } finally {
      setIsSaving(false)
    }
  }

  const renderStepIndicator = () => (
    <div className="flex items-center gap-4 px-2">
      {[
        { id: 'setup', label: 'Setup', icon: Settings },
        { id: 'images', label: 'Images', icon: ImageIcon },
        { id: 'processing', label: 'Magic', icon: Sparkles },
        { id: 'review', label: 'Review', icon: CheckCircle }
      ].map((step, idx) => {
        const Icon = step.icon
        const isActive = activeStep === step.id
        const isPast = ['setup', 'images', 'processing', 'review'].indexOf(activeStep) > idx
        
        return (
          <div key={step.id} className="flex items-center gap-3 shrink-0">
            <div className={cn(
              "flex flex-col items-center gap-1.5 transition-all duration-500",
              isActive ? "scale-105" : "opacity-40"
            )}>
              <div className={cn(
                "h-8 w-8 rounded-lg flex items-center justify-center transition-all duration-500 relative",
                isActive 
                  ? "bg-primary text-white shadow-lg ring-2 ring-primary/20" 
                  : isPast 
                    ? "bg-emerald-500/10 text-emerald-600 border border-emerald-500/20" 
                    : "bg-muted text-muted-foreground border border-border"
              )}>
                {isPast ? <Check className="h-4 w-4" /> : <Icon className={cn("h-4 w-4", isActive && "animate-pulse")} />}
              </div>
              <span className={cn(
                "text-[9px] font-black uppercase tracking-widest",
                isActive ? "text-primary" : isPast ? "text-emerald-600" : "text-muted-foreground"
              )}>
                {step.label}
              </span>
            </div>
            {idx < 3 && (
              <ChevronRight className={cn(
                "h-4 w-4 opacity-10",
                isPast && "text-emerald-500 opacity-30"
              )} />
            )}
          </div>
        )
      })}
    </div>
  )

  if (isDocLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-32 animate-pulse bg-background min-h-[500px]">
        <Loader2 className="h-12 w-12 animate-spin text-primary/20 mb-6" />
        <p className="text-muted-foreground text-[10px] font-black uppercase tracking-[0.3em]">Neural Interface Layering...</p>
      </div>
    )
  }

  const isFinalState = activeStep === 'review' || extractionDoc?.extraction_status === 'Pending Approval' || extractionDoc?.extraction_status === 'Completed'
  const currentStatus = (isFinalState ? extractionDoc?.extraction_status : liveStatus?.status) || extractionDoc?.extraction_status
  const totalBatches = (isFinalState ? extractionDoc?.total_batches : (liveStatus?.total_batches || extractionDoc?.total_batches)) || 0
  const completedBatches = (isFinalState ? extractionDoc?.completed_batches : (liveStatus?.completed_batches || extractionDoc?.completed_batches)) || 0
  
  const itemsFound = Math.max(liveStatus?.items_created || 0, extractionDoc?.items_created || 0)
  const categoriesFound = Math.max(liveStatus?.categories_created || 0, extractionDoc?.categories_created || 0)

  return (
    <div className="flex flex-col h-full bg-background relative selection:bg-primary selection:text-white">
      {/* Premium Sticky Header */}
      <div className="sticky top-0 z-50 bg-background/80 backdrop-blur-xl border-b p-6 pb-6 shadow-sm">
        <button 
          onClick={onClose}
          className="absolute right-6 top-6 p-2 rounded-full hover:bg-muted/80 transition-colors z-30"
          aria-label="Close"
        >
          <X className="h-4 w-4 text-muted-foreground" />
        </button>
        
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 pr-12">
          <DialogHeader>
            <div className="flex items-center gap-2 mb-1">
                <Badge variant="outline" className="px-2 py-0.5 text-[10px] font-bold tracking-widest uppercase border-primary/30 text-primary">AI Workforce</Badge>
                {extractionDocName && (
                  <Badge variant="secondary" className="px-2 py-0.5 text-[10px] font-bold font-mono bg-muted/50 border-none">{extractionDocName}</Badge>
                )}
            </div>
            <DialogTitle className="text-3xl font-black tracking-tight flex items-center gap-2">
                Menu Transformation Hub
            </DialogTitle>
            <DialogDescription className="text-base font-medium">
                Converting physical menus into digital intelligence for <span className="text-foreground">{restaurantName || 'your restaurant'}</span>.
            </DialogDescription>
          </DialogHeader>

          {renderStepIndicator()}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto min-h-[400px]">
        {/* STEP 1: SETUP */}
        {activeStep === 'setup' && (
          <div className="p-8 max-w-2xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-700">
            <div className="space-y-12 py-6">
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                   <div className="h-10 w-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
                      <Settings className="h-5 w-5" />
                   </div>
                   <h2 className="text-xl font-black tracking-tight uppercase">Environmental Context</h2>
                </div>
                <div className="space-y-4">
                  <div className="space-y-2.5">
                    <Label className="text-[10px] lowercase font-black tracking-[0.2em] text-muted-foreground/80 pl-1 uppercase">Restaurant Brand Name</Label>
                    <Input 
                      placeholder="e.g. The Gourmet Yard"
                      value={restaurantName}
                      onChange={(e) => setRestaurantName(e.target.value)}
                      className="h-14 text-lg font-bold bg-muted/30 border-none focus-visible:ring-2 focus-visible:ring-primary/20 transition-all rounded-2xl px-6"
                    />
                    <p className="text-[10px] text-muted-foreground/60 leading-relaxed font-medium mt-2 px-1 italic">
                      Vision models use the brand context to resolve ambiguous text and optimize dish metadata.
                    </p>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                 <div className="p-6 rounded-[2rem] border bg-card/50 space-y-3 hover:border-primary/20 transition-all group">
                    <div className="h-10 w-10 rounded-xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center group-hover:scale-110 transition-transform">
                       <Sparkles className="h-5 w-5" />
                    </div>
                    <h3 className="text-sm font-black uppercase tracking-tight">AI Copywriting</h3>
                    <p className="text-xs text-muted-foreground font-medium leading-relaxed">
                      Models will generate professional, appetizing descriptions based on dish names.
                    </p>
                 </div>
                 <div className="p-6 rounded-[2rem] border bg-card/50 space-y-3 hover:border-emerald/20 transition-all group">
                    <div className="h-10 w-10 rounded-xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center group-hover:scale-110 transition-transform">
                       <CheckCircle className="h-5 w-5" />
                    </div>
                    <h3 className="text-sm font-black uppercase tracking-tight">Clustering</h3>
                    <p className="text-xs text-muted-foreground font-medium leading-relaxed">
                      Automatically maps items to logical menu categories found in the source images.
                    </p>
                 </div>
              </div>
            </div>
          </div>
        )}

        {/* STEP 2: IMAGES */}
        {activeStep === 'images' && (
          <div className="p-8 max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-700">
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
          <div className="p-8 max-w-2xl mx-auto flex flex-col items-center justify-center min-h-[400px] animate-in zoom-in-95 duration-1000">
            <div className="relative w-40 h-40 mb-12">
               {/* Pulsing Aura */}
               <div className="absolute inset-0 bg-primary/20 rounded-full blur-[60px] animate-pulse" />
               <div className="relative w-full h-full bg-gradient-to-br from-primary via-indigo-600 to-purple-700 rounded-[2.5rem] flex items-center justify-center shadow-2xl border border-white/20">
                  <Sparkles className="h-16 w-16 text-white animate-bounce" />
               </div>
               <div className="absolute -inset-4 border-2 border-primary/10 rounded-[3rem] animate-[spin_10s_linear_infinite]" />
            </div>

            <div className="text-center space-y-6 max-w-sm">
               <h2 className="text-3xl font-black tracking-tight bg-gradient-to-r from-primary to-indigo-600 bg-clip-text text-transparent">Neural Core Active</h2>
               <div className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary/5 text-primary border border-primary/10">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span className="text-[10px] font-black uppercase tracking-[0.2em]">{magicStatuses[magicStatusIdx]}</span>
               </div>
               
               <div className="pt-8 space-y-3">
                  <div className="relative h-2.5 w-full bg-muted rounded-full overflow-hidden">
                     <div 
                        className="absolute inset-0 bg-gradient-to-r from-primary via-indigo-500 to-primary transition-all duration-1000 ease-out"
                        style={{ width: `${totalBatches > 0 ? (completedBatches / totalBatches) * 100 : 15}%` }}
                     >
                        <div className="absolute inset-0 bg-[linear-gradient(45deg,rgba(255,255,255,0.2)_25%,transparent_25%,transparent_50%,rgba(255,255,255,0.2)_50%,rgba(255,255,255,0.2)_75%,transparent_75%,transparent)] bg-[length:40px_40px] animate-[shimmer_2s_linear_infinite]" />
                     </div>
                  </div>
                  <div className="flex justify-between text-[10px] font-black text-muted-foreground/60 uppercase tracking-[0.1em]">
                     <span>Extraction Process</span>
                     <span>{totalBatches > 0 ? Math.round((completedBatches / totalBatches) * 100) : 15}%</span>
                  </div>
               </div>
            </div>

            <div className="grid grid-cols-2 gap-8 w-full mt-16">
               <div className="p-6 rounded-3xl bg-muted/30 border border-border/50 text-center space-y-1">
                  <p className="text-3xl font-black text-primary">{itemsFound}</p>
                  <p className="text-[10px] font-black text-muted-foreground uppercase tracking-widest opacity-60">Items Mapped</p>
               </div>
               <div className="p-6 rounded-3xl bg-muted/30 border border-border/50 text-center space-y-1">
                  <p className="text-3xl font-black text-primary">{categoriesFound}</p>
                  <p className="text-[10px] font-black text-muted-foreground uppercase tracking-widest opacity-60">Categories</p>
               </div>
            </div>

            {currentStatus === 'Failed' && (
              <div className="mt-12 p-6 rounded-2xl bg-destructive/5 border border-destructive/20 text-destructive flex gap-4 items-start animate-in shake duration-500">
                <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
                <div className="space-y-2">
                  <p className="font-bold text-sm">Extraction Halted</p>
                  <p className="text-xs opacity-80 leading-relaxed font-medium">{liveStatus?.extraction_log || extractionDoc?.extraction_log || 'A neural processing exception occurred.'}</p>
                   <Button variant="ghost" size="sm" className="h-8 text-xs font-bold px-4 rounded-lg bg-white/50 border-destructive/10 border mt-2" onClick={() => setActiveStep('images')}>
                    Back to Images
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* STEP 4: REVIEW */}
        {activeStep === 'review' && (
          <div className="p-8 max-w-5xl mx-auto space-y-12 animate-in fade-in duration-1000">
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
              {[
                { label: 'Cloud Categories', val: categoriesFound, icon: ImageIcon, color: 'text-primary' },
                { label: 'Neural Dishes', val: itemsFound, icon: Sparkles, color: 'text-indigo-600' },
                { label: 'Doc Updates', val: extractionDoc?.items_updated, icon: CheckCircle, color: 'text-emerald-600' },
                { label: 'Neural Skips', val: extractionDoc?.items_skipped, icon: X, color: 'text-rose-600' }
              ].map((stat, i) => (
                <div key={i} className="flex flex-col bg-card border p-6 rounded-3xl shadow-sm hover:shadow-xl hover:border-primary/20 transition-all group">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-[9px] text-muted-foreground uppercase font-black tracking-widest opacity-60">{stat.label}</span>
                    <stat.icon className={cn("h-4 w-4 opacity-20", stat.color)} />
                  </div>
                  <span className={cn("text-3xl font-black", stat.color)}>{stat.val || 0}</span>
                </div>
              ))}
            </div>

            {extractionDoc?.extracted_dishes?.length > 0 && (
              <div className="space-y-6">
                <div className="flex items-center gap-3">
                  <div className="h-8 w-1.5 bg-primary rounded-full" />
                  <h3 className="text-lg font-black tracking-wide uppercase">Refine & Verify Intelligence</h3>
                </div>
                <div className="border rounded-3xl overflow-hidden bg-white shadow-2xl shadow-black/5">
                  <EditableExtractedDishesTable
                    dishes={extractionDoc.extracted_dishes}
                    docname={extractionDocName!}
                    onUpdate={refreshExtraction}
                  />
                </div>
              </div>
            )}

            {isFinalState && currentStatus === 'Completed' && (
              <div className="p-12 text-center bg-muted/30 rounded-[3rem] border-2 border-dashed border-border/50">
                <div className="h-16 w-16 bg-emerald-500/10 text-emerald-500 rounded-2xl flex items-center justify-center mx-auto mb-6 transform rotate-12">
                   <CheckCircle className="h-8 w-8" />
                </div>
                <h4 className="text-2xl font-black tracking-tight mb-2">Transformation Successful</h4>
                <p className="text-muted-foreground font-medium max-w-xs mx-auto text-sm leading-relaxed italic">
                  The menu data has been successfully synchronized and mapped to your restaurant ecosystem.
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* STICKY ACTION FOOTER */}
      <div className="sticky bottom-0 z-50 bg-background/95 backdrop-blur-md border-t p-6 px-8 flex items-center justify-between shadow-[0_-4px_10px_rgba(0,0,0,0.03)]">
         <div className="flex items-center gap-6 text-[10px] text-muted-foreground font-black uppercase tracking-widest">
            {activeStep !== 'setup' ? (
               <button 
                onClick={() => {
                  if (activeStep === 'images') setActiveStep('setup')
                  else if (activeStep === 'processing' || activeStep === 'review') setActiveStep('images')
                }}
                className="hover:text-primary transition-colors flex items-center gap-2 group border-r pr-6 border-muted-foreground/20 h-10"
                disabled={isSaving || isPolling}
               >
                 <ArrowLeft className="h-3.5 w-3.5 group-hover:-translate-x-1 transition-transform" />
                 Navigate Back
               </button>
            ) : (
                <div className="flex items-center gap-4 border-r pr-6 border-muted-foreground/20 h-10">
                    <span className="flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5 text-emerald-500" /> Neural Safety</span>
                    <span className="flex items-center gap-1.5"><Zap className="h-3.5 w-3.5 text-amber-500" /> High Precision</span>
                </div>
            )}
            
            <div className="hidden md:flex items-center gap-4 opacity-70">
                <span className="italic normal-case font-medium">99.2% Accuracy SLA</span>
            </div>
         </div>

         <div className="flex items-center gap-3">
            {activeStep === 'setup' && (
              <Button 
                onClick={handleStart}
                disabled={isSaving || !restaurantName}
                className="h-12 w-48 rounded-xl bg-primary text-white font-black shadow-lg shadow-primary/20 hover:scale-[1.02] active:scale-[0.98] transition-all"
              >
                {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Start Session'}
              </Button>
            )}

            {activeStep === 'images' && (
              <Button 
                onClick={handleExtract}
                disabled={isSaving || (!hasUploadedImages && (!extractionDoc?.menu_images || extractionDoc.menu_images.length === 0))}
                className="h-12 w-64 rounded-xl bg-primary text-white font-black shadow-lg shadow-primary/20 hover:scale-[1.02] active:scale-[0.98] transition-all gap-2"
              >
                {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : (
                  <>
                    <Sparkles className="h-4 w-4" />
                    Transform Images
                  </>
                )}
              </Button>
            )}

            {activeStep === 'review' && currentStatus !== 'Completed' && (
              <Button 
                onClick={handleApprove}
                disabled={isSaving}
                className="h-12 w-64 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-black shadow-lg shadow-emerald-500/20 hover:scale-[1.02] active:scale-[0.98] transition-all gap-2"
              >
                {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : (
                  <>
                    <Check className="h-4 w-4" />
                    Finalize Sync
                  </>
                )}
              </Button>
            )}

            {(currentStatus === 'Completed' || activeStep === 'review') && (
              <Button variant="ghost" className="h-12 rounded-xl text-muted-foreground font-bold" onClick={onClose}>
                Close Interface
              </Button>
            )}
         </div>
      </div>

      {ConfirmDialogComponent}
    </div>
  )
}
