import { useState, useEffect, useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useFrappeGetDocList, useFrappePostCall, useFrappeGetDoc } from 'frappe-react-sdk'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { toast } from 'sonner'
import { getFrappeError } from '@/lib/utils'
import {
  Sparkles, Loader2, Image as ImageIcon, Plus, Eye, Download,
  LayoutGrid, ChevronLeft, ChevronRight, Coins, AlertTriangle, Camera, ShieldCheck
} from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import { Link } from 'react-router-dom'
import {
  Dialog,
  DialogContent,
} from '@/components/ui/dialog'
import { AiRechargeModal } from '@/components/AiRechargeModal'




// ─── Main Page ────────────────────────────────────────────────────────────────
export default function AIEnhancementPage() {
  const { selectedRestaurant, restaurants } = useRestaurant()
  const [aiMode, setAiMode] = useState<'enhance' | 'generate'>('enhance')
  const [includeBranding, setIncludeBranding] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)

  // Coin state
  const [coinBalance, setCoinBalance] = useState(0)
  const [coinLoading, setCoinLoading] = useState(false)
  const [showRechargeModal, setShowRechargeModal] = useState(false)

  // Product Selection
  const [selectedProduct, setSelectedProduct] = useState<string>('')
  const { data: products } = useFrappeGetDocList('Menu Product', {
    fields: ['name', 'product_name'],
    filters: [['restaurant', '=', selectedRestaurant]],
    limit: 1000
  }, `ai-products-${selectedRestaurant}`)

  const { data: productDoc, mutate: mutateProduct, isLoading: isProductLoading } = useFrappeGetDoc('Menu Product', selectedProduct, {
    enabled: !!selectedProduct,
    fields: ['*']
  })

  // API Calls
  const { call: enqueueEnhancement } = useFrappePostCall('flamezo_backend.flamezo.api.ai_media.enqueue_enhancement')
  const { call: getStatus } = useFrappePostCall('flamezo_backend.flamezo.api.ai_media.get_enhancement_status')
  const { call: applyToProduct } = useFrappePostCall('flamezo_backend.flamezo.api.ai_media.apply_to_product')
  const { call: uploadFile } = useFrappePostCall('flamezo_backend.flamezo.api.ai_media.upload_base64_image')
  const { call: getBillingInfo } = useFrappePostCall('flamezo_backend.flamezo.api.coin_billing.get_coin_billing_info')

  const [variantCount, setVariantCount] = useState<string>('1')
  const [generationIds, setGenerationIds] = useState<string[]>([])
  const [generationStatuses, setGenerationStatuses] = useState<Record<string, { status: string, url: string | null }>>({})
  const [activeSlide, setActiveSlide] = useState(0)
  const [isPolling, setIsPolling] = useState(false)

  const BASE_COINS = aiMode === 'generate' ? 10 : 5
  const COINS_PER_VARIANT = BASE_COINS
  const numVariants = parseInt(variantCount, 10)
  const [isApplying, setIsApplying] = useState(false)
  const [showPreviewModal, setShowPreviewModal] = useState(false)

  // Fetch coin balance
  const fetchCoins = useCallback(async () => {
    if (!selectedRestaurant) return
    setCoinLoading(true)
    try {
      const res = await getBillingInfo({ restaurant: selectedRestaurant })
      if (res.message) {
        const balance = res.message.coins_balance ?? 0
        setCoinBalance(balance)
        // Notify other components (like Layout) that balance has been updated
        window.dispatchEvent(new CustomEvent('coins-updated', { detail: { balance } }))
      }
    } catch (err) {
      console.error('Failed to load coins:', err)
    } finally {
      setCoinLoading(false)
    }
  }, [selectedRestaurant])

  // Sync coins when updated from other components (like global recharge)
  useEffect(() => {
    const handleCoinsUpdate = (e: any) => {
      if (typeof e.detail?.balance === 'number') {
        setCoinBalance(e.detail.balance)
      }
    }
    window.addEventListener('coins-updated', handleCoinsUpdate)
    return () => window.removeEventListener('coins-updated', handleCoinsUpdate)
  }, [])

  useEffect(() => {
    fetchCoins()
  }, [fetchCoins])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const selected = e.target.files[0]
      setFile(selected)
      setPreview(URL.createObjectURL(selected))
      setGenerationIds([])
      setGenerationStatuses({})
      setActiveSlide(0)
    }
  }

  const handleEnhanceClick = () => {
    if (aiMode === 'enhance' && !file) {
      toast.error('Please select an image first')
      return
    }
    if (!selectedProduct) {
      toast.error('Please select a Menu Product to associate with')
      return
    }

    const coinsRequired = numVariants * COINS_PER_VARIANT
    if (coinBalance < coinsRequired) {
      toast.error('Insufficient Coins!', {
        description: `You need ${coinsRequired} coins but have ${coinBalance}.`,
        action: { label: 'Recharge', onClick: () => setShowRechargeModal(true) }
      })
      return
    }
    handleEnhance()
  }

  // Actual enhancement/generation after confirmation
  const handleEnhance = async () => {
    setIsUploading(true)
    setGenerationIds([])
    setGenerationStatuses({})

    const newGenIds: string[] = []
    const initialStatus: Record<string, any> = {}

    try {
      if (aiMode === 'generate') {
        // Generate mode: no file upload needed, just pass product + mode to backend
        for (let i = 0; i < numVariants; i++) {
          try {
            const res = await enqueueEnhancement({
              restaurant: selectedRestaurant,
              owner_doctype: 'Menu Product',
              owner_name: selectedProduct,
              mode: 'generate',
              include_branding: includeBranding
            })
            if (res.message?.generation_id) {
              newGenIds.push(res.message.generation_id)
              initialStatus[res.message.generation_id] = { status: 'Pending_Upload', url: null }
            }
          } catch (err: any) {
            const errorMsg = getFrappeError(err)
            if (errorMsg.toLowerCase().includes('insufficient')) {
              toast.error('Insufficient Coins!', {
                description: 'Please recharge your Flamezo coin wallet.',
                action: { label: 'Recharge', onClick: () => setShowRechargeModal(true) }
              })
              break
            }
            toast.error(`Variant ${i + 1} failed to start`, { description: errorMsg })
          }
        }
      } else {
        // Enhance mode: upload file first, then queue
        const reader = new FileReader()
        reader.readAsDataURL(file!)
        await new Promise<void>((resolve, reject) => {
          reader.onload = async () => {
            try {
              const base64Data = (reader.result as string).split(',')[1]
              const timestamp = new Date().getTime()
              const sanitizedName = selectedProduct.toLowerCase().replace(/[^a-z0-9]/g, '-')
              const productionFileName = `raw_${sanitizedName}_${timestamp}.${file!.name.split('.').pop()}`

              const uploadRes = await uploadFile({ filename: productionFileName, filedata: base64Data })
              if (!uploadRes.message?.file_url) throw new Error('File upload failed')

              const fileUrl = uploadRes.message.file_url
              for (let i = 0; i < numVariants; i++) {
                try {
                  const res = await enqueueEnhancement({
                    restaurant: selectedRestaurant,
                    owner_doctype: 'Menu Product',
                    owner_name: selectedProduct,
                    original_image_url: fileUrl,
                    mode: 'enhance',
                    include_branding: includeBranding
                  })
                  if (res.message?.generation_id) {
                    newGenIds.push(res.message.generation_id)
                    initialStatus[res.message.generation_id] = { status: 'Pending_Upload', url: null }
                  }
                } catch (err: any) {
                  const errorMsg = getFrappeError(err)
                  if (errorMsg.toLowerCase().includes('insufficient')) {
                    toast.error('Insufficient credits!', {
                      description: 'Please recharge your AI credit wallet.',
                      action: { label: 'Recharge', onClick: () => setShowRechargeModal(true) }
                    })
                    break
                  }
                  toast.error(`Variant ${i + 1} failed to start`, { description: errorMsg })
                }
              }
              resolve()
            } catch (err) { reject(err) }
          }
          reader.onerror = reject
        })
      }
    } catch (err: any) {
      toast.error('Failed to start AI job', { description: getFrappeError(err) })
    } finally {
      // Refresh balance after deduction
      fetchCoins()
      if (newGenIds.length > 0) {
        setGenerationIds(newGenIds)
        setGenerationStatuses(initialStatus)
        setActiveSlide(0)
        toast.success(`${aiMode === 'generate' ? 'Generation' : 'Enhancement'} started for ${newGenIds.length} variant(s)!`)
      }
      setIsUploading(false)
    }
  }


  useEffect(() => {
    if (generationIds.length === 0) return

    const allDone = generationIds.every(id => {
      const s = generationStatuses[id]?.status
      return s === 'Completed' || s === 'Failed'
    })

    if (allDone) {
      if (isPolling) setIsPolling(false)
      return
    }

    setIsPolling(true)
    const interval = setInterval(async () => {
      const newStatuses = { ...generationStatuses }
      let hasChanges = false
      let justCompleted = 0
      let justFailed = 0

      for (const genId of generationIds) {
        if (newStatuses[genId]?.status === 'Completed' || newStatuses[genId]?.status === 'Failed') continue;

        try {
          const res = await getStatus({ generation_id: genId })
          if (res.message) {
            const status = res.message.status
            if (status !== newStatuses[genId]?.status) {
              newStatuses[genId] = {
                status: status,
                url: res.message.enhanced_image_url || null
              }
              hasChanges = true
              if (status === 'Completed') justCompleted++;
              if (status === 'Failed') justFailed++;
            }
          }
        } catch (err) {
          console.error('Polling error for', genId, err)
        }
      }

      if (hasChanges) {
        setGenerationStatuses(newStatuses)
        if (justCompleted > 0) {
          toast.success(`${justCompleted} variant(s) completed!`)
          fetchCoins() // Refresh balance after successful deduction
        }
        if (justFailed > 0) {
          toast.error(`${justFailed} variant(s) failed`)
          fetchCoins() // Refresh balance to ensure accuracy
        }
      }
    }, 3000)

    return () => clearInterval(interval)
  }, [generationIds, generationStatuses])

  const activeGenerations = generationIds.filter(id => generationStatuses[id]?.status !== 'Failed')
  const completedUrls = activeGenerations.map(id => generationStatuses[id]?.url).filter(Boolean) as string[]
  const currentEnhancedUrl = completedUrls[activeSlide] || null
  const currentGenId = activeGenerations[activeSlide] || null

  const isAnyProcessing = generationIds.some(id => {
    const s = generationStatuses[id]?.status
    return s === 'Pending_Upload' || s === 'Processing'
  })

  const allFailed = generationIds.length > 0 && generationIds.every(id => generationStatuses[id]?.status === 'Failed')

  const [optimisticMedia, setOptimisticMedia] = useState<any[] | null>(null)

  const handleApply = async (replaceIndex?: number) => {
    if (!currentGenId || !currentEnhancedUrl) return

    setIsApplying(true)

    const currentMedia = productDoc?.product_media || []
    let newMedia = [...currentMedia]

    if (replaceIndex !== undefined && replaceIndex !== -1 && replaceIndex < newMedia.length) {
      newMedia[replaceIndex] = { ...newMedia[replaceIndex], media_url: currentEnhancedUrl }
    } else {
      newMedia.push({ media_url: currentEnhancedUrl, media_type: 'image' })
    }
    setOptimisticMedia(newMedia)

    try {
      await applyToProduct({
        generation_id: currentGenId,
        replace_index: replaceIndex ?? null
      })
      toast.success('Successfully applied enhanced image to product!')
      await mutateProduct()
      setOptimisticMedia(null)
    } catch (err: any) {
      toast.error('Failed to apply', { description: getFrappeError(err) })
      setOptimisticMedia(null)
    } finally {
      setIsApplying(false)
    }
  }

  const handleDownload = async () => {
    if (!currentEnhancedUrl) return
    const proxyUrl = `/api/method/flamezo_backend.flamezo.api.ai_media.download_proxy?file_url=${encodeURIComponent(currentEnhancedUrl)}&filename=enhanced-${selectedProduct}.png`
    const link = document.createElement('a')
    link.href = proxyUrl
    link.download = `enhanced-${selectedProduct}.png`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    toast.success('Download started!')
  }



  if (!selectedRestaurant) {
    return <div className="p-8 text-center text-muted-foreground">Please select a restaurant</div>
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">AI Image Enhancement</h1>
          <p className="text-muted-foreground mt-2">
            Transform raw food photos into stunning, studio-quality images for your menu.
          </p>
        </div>
        <Link to="/ai-gallery">
          <Button variant="outline" className="gap-2 border-primary/20 hover:bg-primary/5 hover:text-primary transition-all shadow-sm">
            <LayoutGrid className="h-4 w-4" />
            My Generative Gallery
          </Button>
        </Link>
      </div>

      {/* ── Low balance warning banner ── */}
      {!coinLoading && coinBalance < COINS_PER_VARIANT && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 dark:bg-red-950/20 px-4 py-3">
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-red-500 shrink-0" />
            <p className="text-sm text-red-700 dark:text-red-400">
              <strong>Coin balance too low!</strong> You need at least {COINS_PER_VARIANT} coins to run this operation.
            </p>
          </div>
          <Button size="sm" className="bg-red-500 hover:bg-red-600 text-white shrink-0" onClick={() => setShowRechargeModal(true)}>
            Recharge Now
          </Button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* ── Upload & Setup Section ── */}
        <Card className="shadow-xs border-muted/60">
          <CardHeader>
            <CardTitle>1. Upload & Setup</CardTitle>
            <CardDescription>Select a product and the raw photo</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* AI Mode Selector */}
            <div className="space-y-2">
              <Label>What do you want to do?</Label>
              <Select
                value={aiMode}
                onValueChange={(v) => { setAiMode(v as 'enhance' | 'generate'); setGenerationIds([]); setGenerationStatuses({}); setFile(null); setPreview(null) }}
                disabled={generationIds.length > 0 && !allFailed}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="enhance">
                    <div className="flex items-center gap-2">
                       <Sparkles className="h-4 w-4 text-primary" />
                       Enhance my Photo <span className="text-muted-foreground text-xs ml-1">(5 coins)</span>
                     </div>
                   </SelectItem>
                   <SelectItem value="generate">
                     <div className="flex items-center gap-2">
                       <Camera className="h-4 w-4 text-primary" />
                       Generate Photo for my Food <span className="text-muted-foreground text-xs ml-1">(10 coins)</span>
                     </div>
                   </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Target Menu Product</Label>
              <Select value={selectedProduct} onValueChange={setSelectedProduct} disabled={generationIds.length > 0}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a product to associate" />
                </SelectTrigger>
                <SelectContent>
                  {products?.map((p: any) => (
                    <SelectItem key={p.name} value={p.name}>{p.product_name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Variants to Generate</Label>
              <Select value={variantCount} onValueChange={setVariantCount} disabled={generationIds.length > 0}>
                <SelectTrigger>
                  <SelectValue placeholder="Select variant count" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">1 Variant</SelectItem>
                  <SelectItem value="2">2 Variants</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Branding Toggle */}
            <div className="flex items-center space-x-2 p-3 rounded-lg border bg-muted/20 border-border/50">
              <Checkbox
                id="branding"
                checked={includeBranding}
                onCheckedChange={(checked) => setIncludeBranding(!!checked)}
              />
              <div className="grid gap-1.5 leading-none">
                <label
                  htmlFor="branding"
                  className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 flex items-center gap-1.5"
                >
                  <ShieldCheck className="h-3.5 w-3.5 text-primary" />
                  Include {restaurants.find(r => r.restaurant_id === selectedRestaurant)?.restaurant_name || 'Restaurant'} branding
                </label>
                <p className="text-[10px] text-muted-foreground">
                   Included free.
                </p>
              </div>
            </div>

            {/* Raw Food Photo — only shown in enhance mode */}
            {aiMode === 'enhance' && (
              <div className="space-y-2">
                <Label>Raw Food Photo</Label>
                <div className="border-2 border-dashed rounded-lg p-4 flex flex-col items-center justify-center space-y-4 bg-muted/20 hover:bg-muted/40 transition-colors">
                  {preview ? (
                    <div className="relative w-full aspect-video rounded-md overflow-hidden bg-black/5">
                      <img src={preview} alt="Preview" className="w-full h-full object-contain" />
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-4 text-muted-foreground space-y-2">
                      <div className="p-3 rounded-full bg-primary/10">
                        <ImageIcon className="h-6 w-6 text-primary" />
                      </div>
                      <span>Drag &amp; drop or click to upload</span>
                    </div>
                  )}
                  <Input
                    type="file"
                    accept="image/*"
                    onChange={handleFileChange}
                    disabled={generationIds.length > 0 && !allFailed}
                    className="max-w-[250px]"
                  />
                </div>
              </div>
            )}

            {/* Generate mode info banner */}
            {aiMode === 'generate' && (
              <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 flex items-start gap-3">
                <Camera className="h-5 w-5 text-primary shrink-0 mt-0.5" />
                <div className="text-sm text-muted-foreground">
                  <p className="font-medium text-foreground mb-1">AI will generate a brand-new photo</p>
                  <p>No upload needed. We'll use your product's name and description to create a professional food photo from scratch.</p>
                </div>
              </div>
            )}


            {/* Action Button with coin cost hint */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
                <span className="flex items-center gap-1">
                  <Coins className="h-3 w-3" /> Cost: <strong>{numVariants * COINS_PER_VARIANT} coins</strong>
                </span>
                <span>Balance: <strong>{coinBalance}</strong></span>
              </div>
              <Button
                onClick={handleEnhanceClick}
                disabled={(aiMode === 'enhance' && !file) || !selectedProduct || isUploading || isPolling}
                className="w-full"
              >
                {isUploading ? (
                  <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Processing...</>
                ) : isPolling ? (
                  <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> {aiMode === 'generate' ? 'Generating...' : 'Enhancing...'}</>
                ) : aiMode === 'generate' ? (
                  <><Camera className="h-4 w-4 mr-2" /> {generationIds.length > 0 ? 'Regenerate Photo' : 'Generate Photo'}</>
                ) : (
                  <><Sparkles className="h-4 w-4 mr-2" /> {generationIds.length > 0 ? 'Re-enhance Image' : 'Enhance Image'}</>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* ── Results Section ── */}
        <Card className="shadow-xs border-muted/60">
          <CardHeader>
            <CardTitle>2. AI Results</CardTitle>
            <CardDescription>Preview and apply your enhanced image</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col h-[calc(100%-5rem)]">
            <div className="flex-1 border rounded-lg bg-muted/10 flex flex-col items-center justify-center p-4 min-h-[300px] mb-6">
              {generationIds.length === 0 ? (
                <div className="text-muted-foreground flex flex-col items-center">
                  <Sparkles className="h-10 w-10 mb-2 opacity-20" />
                  Upload an image to start
                </div>
              ) : isAnyProcessing ? (
                <div className="flex flex-col items-center space-y-4 text-primary">
                  <div className="relative">
                    <div className="absolute inset-0 bg-primary/20 blur-xl rounded-full"></div>
                    <Loader2 className="h-12 w-12 animate-spin relative z-10" />
                  </div>
                  <div className="font-medium animate-pulse">Running AI pipeline...</div>
                  <p className="text-xs text-muted-foreground">This normally takes 10-15 seconds.</p>
                </div>
              ) : allFailed ? (
                <div className="text-destructive font-medium flex items-center">
                  Failed during AI execution. Check console/logs.
                </div>
              ) : completedUrls.length > 0 && currentEnhancedUrl ? (
                <div className="relative w-full h-full group flex flex-col items-center justify-center">
                  <div className="relative w-full aspect-square md:aspect-[4/3] rounded-md overflow-hidden bg-black/5 flex items-center justify-center">
                    <img
                      src={currentEnhancedUrl}
                      alt="Enhanced Result"
                      draggable
                      onDragStart={(e) => {
                        e.dataTransfer.setData('text/plain', 'enhanced-image')
                      }}
                      className="max-w-full max-h-full object-contain rounded-md shadow-sm cursor-grab active:cursor-grabbing hover:scale-[1.01] transition-transform"
                    />
                  </div>

                  {/* Floating Actions */}
                  <div className="absolute top-2 right-2 flex flex-col gap-2 z-10 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      size="icon"
                      variant="secondary"
                      className="rounded-full shadow-lg bg-white/90 hover:bg-white"
                      onClick={() => setShowPreviewModal(true)}
                    >
                      <Eye className="h-4 w-4" />
                    </Button>
                    <Button
                      size="icon"
                      variant="secondary"
                      className="rounded-full shadow-lg bg-white/90 hover:bg-white"
                      onClick={handleDownload}
                    >
                      <Download className="h-4 w-4" />
                    </Button>
                  </div>

                  {/* Carousel Controls */}
                  {completedUrls.length > 1 && (
                    <div className="absolute top-1/2 -translate-y-1/2 left-2 right-2 flex justify-between z-10 pointer-events-none">
                      <Button
                        variant="secondary"
                        size="icon"
                        className="rounded-full h-8 w-8 shadow-md pointer-events-auto opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-0"
                        disabled={activeSlide === 0}
                        onClick={(e) => { e.preventDefault(); setActiveSlide(prev => Math.max(0, prev - 1)); }}
                      >
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="secondary"
                        size="icon"
                        className="rounded-full h-8 w-8 shadow-md pointer-events-auto opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-0"
                        disabled={activeSlide === completedUrls.length - 1}
                        onClick={(e) => { e.preventDefault(); setActiveSlide(prev => Math.min(completedUrls.length - 1, prev + 1)); }}
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  )}

                  {completedUrls.length > 1 && (
                    <div className="flex items-center gap-1.5 mt-3 mb-1">
                      {completedUrls.map((_, idx) => (
                        <button
                          key={idx}
                          onClick={() => setActiveSlide(idx)}
                          className={cn("w-2 h-2 rounded-full transition-all", activeSlide === idx ? "bg-primary w-4" : "bg-primary/20 hover:bg-primary/40")}
                        />
                      ))}
                    </div>
                  )}

                  <div className="absolute bottom-6 left-1/2 -translate-x-1/2 bg-black/60 text-white text-[10px] px-3 py-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 z-10 pointer-events-none">
                    <ImageIcon className="h-3 w-3" /> Drag me to a slot below
                  </div>
                </div>
              ) : null}
            </div>

            {/* Target Media Slots */}
            {selectedProduct && generationIds.length > 0 && (
              <div className="w-full space-y-2">
                <Label className="text-xs uppercase tracking-wider opacity-60">Target Media Slots (Images Only)</Label>
                <div className="grid grid-cols-2 gap-3 max-w-[300px] mx-auto">
                  {(isProductLoading || (!productDoc && !optimisticMedia)) ? (
                    <div className="col-span-2 flex flex-col items-center justify-center py-8 text-muted-foreground space-y-2">
                      <Loader2 className="h-5 w-5 animate-spin text-primary/40" />
                      <span className="text-[10px] uppercase tracking-tighter">Loading current media...</span>
                    </div>
                  ) : [0, 1].map((idx) => {
                    const baseMedia = optimisticMedia || productDoc?.product_media || []
                    const imageSlots = baseMedia.filter((m: any) => m.media_type === 'image')
                    const currentMedia = imageSlots[idx]

                    return (
                      <div
                        key={idx}
                        onDragOver={(e) => {
                          e.preventDefault()
                          e.currentTarget.classList.add('border-primary', 'bg-primary/5')
                        }}
                        onDragLeave={(e) => {
                          e.currentTarget.classList.remove('border-primary', 'bg-primary/5')
                        }}
                        onDrop={(e) => {
                          e.preventDefault()
                          e.currentTarget.classList.remove('border-primary', 'bg-primary/5')
                          const actualMedia = productDoc?.product_media || []
                          const originalIdx = actualMedia.findIndex((m: any) => m.name === currentMedia?.name)
                          handleApply(originalIdx !== -1 ? originalIdx : undefined)
                        }}
                        onClick={() => {
                          const actualMedia = productDoc?.product_media || []
                          const originalIdx = actualMedia.findIndex((m: any) => m.name === currentMedia?.name)
                          handleApply(originalIdx !== -1 ? originalIdx : undefined)
                        }}
                        className={cn(
                          "relative aspect-square rounded-md border-2 border-dashed flex flex-col items-center justify-center transition-all cursor-pointer group overflow-hidden",
                          currentMedia ? "border-transparent" : "border-muted-foreground/30 hover:border-primary",
                          isApplying && "opacity-50 pointer-events-none"
                        )}
                      >
                        {currentMedia ? (
                          <>
                            <img src={currentMedia.media_url} className="w-full h-full object-cover group-hover:opacity-40 transition-opacity" alt={`Slot ${idx + 1}`} />
                            <div className="absolute inset-0 flex flex-col items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                              <div className="bg-primary text-white text-[10px] font-bold px-2 py-1 rounded shadow-sm">REPLACE</div>
                            </div>
                          </>
                        ) : (
                          <>
                            <Plus className="h-5 w-5 text-muted-foreground/50 group-hover:text-primary transition-colors" />
                            <span className="text-[9px] text-muted-foreground/60 mt-1 font-medium group-hover:text-primary">ADD NEW</span>
                          </>
                        )}
                        {isApplying && (
                          <div className="absolute inset-0 bg-background/40 flex items-center justify-center">
                            <Loader2 className="h-4 w-4 animate-spin text-primary" />
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {generationIds.length > 0 && !isAnyProcessing && !allFailed && (
              <p className="text-[10px] text-muted-foreground text-center italic mt-4">
                Tip: Drag {completedUrls.length > 1 ? "an" : "the"} enhanced photo or click a slot to replace/add to your menu image slots.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Modals ── */}


      {/* Recharge Modal */}
      <AiRechargeModal
        open={showRechargeModal}
        onClose={() => setShowRechargeModal(false)}
        restaurant={selectedRestaurant}
        onSuccess={fetchCoins}
      />

      {/* Preview Modal */}
      <Dialog open={showPreviewModal} onOpenChange={setShowPreviewModal}>
        <DialogContent className="max-w-3xl p-0 border-none bg-transparent shadow-none overflow-visible">
          <div className="relative group overflow-hidden rounded-xl shadow-2xl ring-1 ring-white/20">
            {currentEnhancedUrl && (
              <img
                src={currentEnhancedUrl}
                alt="Premium AI Enhancement"
                className="w-full h-auto max-h-[85vh] object-contain rounded-xl"
              />
            )}

            {/* High-End Label */}
            <div className="absolute top-4 left-4 flex items-center gap-2 bg-primary/90 text-white text-[10px] px-3 py-1.5 rounded-full font-bold shadow-lg backdrop-blur-md">
              <Sparkles className="h-3 w-3" />
              STUDIO PREVIEW
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
