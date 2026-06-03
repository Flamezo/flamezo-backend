import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall, useFrappeGetCall, useFrappeGetDoc } from '@/lib/frappe'
import { useEffect, useState, useMemo, useCallback, useRef } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import {
  CheckCircle2, XCircle, Sparkles, RefreshCw, Zap, ChevronLeft, ChevronRight,
  DollarSign, Eye, CreditCard, ImagePlus, Upload, X, Loader2, Heart, MessageCircle,
  Send as SendIcon, Bookmark, MoreHorizontal, Copy, Calendar, MapPin, Clock
} from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { uploadToR2 } from '@/lib/r2Upload'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import BoostRadiusMap from '@/components/BoostRadiusMap'

// ─── Types & Constants ──────────────────────────────────────────

const FOOD_PLACEHOLDERS = [
  'https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?auto=format&fit=crop&w=600&q=80', // Pizza
  'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=600&q=80', // Salad bowl
  'https://images.unsplash.com/photo-1567620905732-2d1ec7ab7445?auto=format&fit=crop&w=600&q=80', // Pancakes
  'https://images.unsplash.com/photo-1484723091739-30a097e8f929?auto=format&fit=crop&w=600&q=80', // Toast
  'https://images.unsplash.com/photo-1482049016688-2d3e1b311543?auto=format&fit=crop&w=600&q=80', // Sandwich
]

const AVG_BILL = 600

const STEPS = [
  { id: 'prereqs', label: 'Prerequisites', icon: CheckCircle2 },
  { id: 'package', label: 'Package', icon: DollarSign },
  { id: 'template', label: 'Template & Offer', icon: Sparkles },
  { id: 'preview', label: 'Preview & Image', icon: Eye },
  { id: 'payment', label: 'Payment', icon: CreditCard },
] as const

const PACKAGES = [
  { tier: 'Growth', price: 2000, est: { A: [15, 25], B: [12, 20], C: [9, 15] }, popular: false },
  { tier: 'Boost', price: 5000, est: { A: [40, 60], B: [32, 48], C: [24, 36] }, popular: true },
  { tier: 'Scale', price: 10000, est: { A: [85, 130], B: [68, 104], C: [51, 78] }, popular: false },
]

interface Template {
  template_id: string; template_name: string; hook_formula: string
  best_for: string; requires_hero_dish: boolean
  expected_ctr_low: number; expected_ctr_high: number
}

interface Campaign {
  campaign_id: string; ad_primary_text: string; ad_headline: string
  offer_description: string; coupon_code: string; budget_total: number
  ad_spend_allocated: number; flamezo_fee: number; gst_on_fee: number
  guaranteed_redemptions: number; is_first_campaign: boolean; location_grade: string
}

// ─── Ad Preview Mockup Sub-component ─────────────────────────────────

interface AdPreviewMockupProps {
  restaurantName: string
  imageUrl?: string
  primaryText: string
  headline: string
  onClearImage?: () => void
  placeholderTitle?: string
  placeholderDesc?: string
  processing?: boolean
  processingLabel?: string
  isCreative?: boolean
}

function AdPreviewMockup({
  restaurantName,
  imageUrl,
  primaryText,
  headline,
  onClearImage,
  placeholderTitle,
  placeholderDesc,
  processing,
  processingLabel,
  isCreative
}: AdPreviewMockupProps) {
  return (
    <div className="w-[300px] sm:w-[320px] bg-card border border-border/80 rounded-[2.5rem] p-3 shadow-xl shadow-orange-500/5 mx-auto shrink-0 select-none">
      {/* Phone notch */}
      <div className="w-24 h-1.5 bg-muted rounded-full mx-auto mb-2" />
      {/* Screen */}
      <div className="rounded-2xl overflow-hidden border bg-background">
        {/* IG Header */}
        <div className="flex items-center gap-2 px-3 py-2 border-b">
          <div className="h-7 w-7 rounded-full bg-gradient-to-br from-orange-500 to-amber-600 flex items-center justify-center">
            <Zap className="h-3.5 w-3.5 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-semibold truncate">{restaurantName}</p>
            <p className="text-[9px] text-muted-foreground">Sponsored</p>
          </div>
          <MoreHorizontal className="h-4 w-4 text-muted-foreground" />
        </div>
        {/* Image */}
        {imageUrl ? (
          <div className="relative aspect-square bg-muted">
            <img src={imageUrl} alt="Ad" className="w-full h-full object-cover" />
            {isCreative && (
              <div className="absolute bottom-2 left-2 bg-black/70 backdrop-blur-sm text-white text-[9px] px-2 py-1 rounded-full flex items-center gap-1">
                <Sparkles className="h-3 w-3" /> AI Creative
              </div>
            )}
            {onClearImage && !processing && (
              <button onClick={onClearImage}
                className="absolute top-2 right-2 p-1 bg-black/60 rounded-full text-white hover:bg-black/80 transition-colors pointer-events-auto">
                <X className="h-3 w-3" />
              </button>
            )}
            {processing && (
              <div className="absolute inset-0 bg-black/55 backdrop-blur-[2px] flex flex-col items-center justify-center gap-2 text-white">
                <Loader2 className="h-7 w-7 animate-spin" />
                <p className="text-[11px] font-semibold">{processingLabel || 'Generating final version…'}</p>
                <p className="text-[9px] text-white/70 px-6 text-center">Checking the photo, then adding offer, location & branding</p>
              </div>
            )}
          </div>
        ) : (
          <div className="aspect-square bg-gradient-to-br from-orange-50 to-amber-50 dark:from-orange-950/20 dark:to-amber-950/20 flex flex-col items-center justify-center gap-2">
            <div className="h-12 w-12 rounded-full bg-orange-100 dark:bg-orange-900/40 flex items-center justify-center animate-pulse">
              <ImagePlus className="h-6 w-6 text-orange-500" />
            </div>
            <p className="text-xs font-medium text-muted-foreground">{placeholderTitle || 'Ad Photo Placeholder'}</p>
            <p className="text-[10px] text-muted-foreground">{placeholderDesc || 'Photo chosen in next step'}</p>
          </div>
        )}
        {/* IG Actions */}
        <div className="flex items-center justify-between px-3 py-2">
          <div className="flex gap-3">
            <Heart className="h-4 w-4" /><MessageCircle className="h-4 w-4" /><SendIcon className="h-4 w-4" />
          </div>
          <Bookmark className="h-4 w-4" />
        </div>
        {/* Copy */}
        <div className="px-3 pb-3">
          <p className="text-[11px] leading-snug break-words min-h-[50px] line-clamp-4">{primaryText}</p>
          <p className="text-[11px] font-bold mt-1.5 truncate">{headline}</p>
          <div className="flex items-center gap-1.5 mt-2.5 p-1.5 bg-orange-50 dark:bg-orange-950/20 rounded-md border border-orange-200 dark:border-orange-800">
            <Zap className="h-3 w-3 text-orange-500" />
            <span className="text-[10px] font-semibold text-orange-600 flex-1">Get Offer</span>
            <ChevronRight className="h-3 w-3 text-orange-400" />
          </div>
        </div>
      </div>
      {/* Phone bottom bar */}
      <div className="w-20 h-1 bg-muted rounded-full mx-auto mt-2" />
    </div>
  )
}

// ─── Component ──────────────────────────────────────────────────

export default function BoostNewCampaign() {
  const { selectedRestaurant } = useRestaurant()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  // Get restaurant name
  const { data: restaurantDoc } = useFrappeGetDoc('Restaurant', selectedRestaurant || '', selectedRestaurant ? undefined : null)
  const restaurantName = (restaurantDoc as any)?.restaurant_name || selectedRestaurant || '{restaurantName}'

  // Read initial state from URL params (persists across refreshes)
  const urlCampaignId = searchParams.get('id') || ''
  const urlStep = parseInt(searchParams.get('step') || '0', 10)

  const [stepIndex, setStepIndexRaw] = useState(urlStep)
  const [prereqs, setPrereqs] = useState<any>(null)
  const [templates, setTemplates] = useState<Template[]>([])
  const filteredTemplates = useMemo(() => {
    const allowedNames = [
      'the hero dish',
      'the bogo',
      'the first timer',
      'the weekend pull',
      'the lunch steal',
      'the comeback'
    ]
    return templates.filter(t => allowedNames.includes(t.template_name.toLowerCase()))
  }, [templates])

  const randomPlaceholderImage = useMemo(() => {
    const idx = Math.floor(Math.random() * FOOD_PLACEHOLDERS.length)
    return FOOD_PLACEHOLDERS[idx]
  }, [])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Form state
  const [pkg, setPkg] = useState('Growth')
  const [duration, setDuration] = useState(14)
  const [radius, setRadius] = useState(5)
  const [templateId, setTemplateId] = useState('')
  const [offer, setOffer] = useState(100)
  const [heroDish, setHeroDish] = useState('')
  const [campaign, setCampaign] = useState<Campaign | null>(null)

  const mockPreviewCopy = useMemo(() => {
    const selectedTemplate = filteredTemplates.find(t => t.template_id === templateId)
    if (!selectedTemplate) {
      return {
        primaryText: 'Select a template above to preview your Instagram & Facebook campaign ad copy here...',
        headline: `Flat ₹${offer} OFF at ${restaurantName}`
      }
    }

    let hook = selectedTemplate.hook_formula || ''
    const dishPlaceholder = heroDish.trim() || '[Hero Dish]'
    hook = hook.replace(/{dish}/gi, dishPlaceholder)
    hook = hook.replace(/{restaurant}/gi, restaurantName)

    return {
      primaryText: `✨ ${hook}\n\nGet FLAT ₹${offer} OFF on your next visit! Click 'Get Offer' to claim your exclusive voucher coupon now. Valid for a limited time.`,
      headline: `Flat ₹${offer} OFF at ${restaurantName}!`
    }
  }, [templateId, heroDish, offer, restaurantName, filteredTemplates])

  // Image state
  const [adImageUrl, setAdImageUrl] = useState('')          // final processed creative URL
  const [imagePreview, setImagePreview] = useState('')      // what the mockup shows
  const [sourceImageUrl, setSourceImageUrl] = useState('')  // raw photo chosen from gallery
  const [creativeStatus, setCreativeStatus] = useState<'idle' | 'processing' | 'ready' | 'failed'>('idle')
  const [uploadingImage, setUploadingImage] = useState(false)
  const creativePollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Sync step changes to URL (so refresh preserves position)
  const setStepIndex = useCallback((step: number) => {
    setStepIndexRaw(step)
    const params = new URLSearchParams(searchParams)
    params.set('step', String(step))
    if (campaign?.campaign_id) params.set('id', campaign.campaign_id)
    setSearchParams(params, { replace: true })
  }, [searchParams, setSearchParams, campaign])

  // Success state
  const [success, setSuccess] = useState(false)
  const [razorpayLoaded, setRazorpayLoaded] = useState(false)



  // Load Razorpay script
  useEffect(() => {
    if ((window as any).Razorpay) { setRazorpayLoaded(true); return }
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.onload = () => setRazorpayLoaded(true)
    script.onerror = () => toast.error('Failed to load payment gateway')
    document.body.appendChild(script)
  }, [])

  // API calls
  const { call: fetchPrereqs } = useFrappePostCall('flamezo_backend.flamezo.api.boost.check_prerequisites')
  const { call: fetchTemplates } = useFrappePostCall('flamezo_backend.flamezo.api.boost.get_boost_templates')
  const { call: createCampaign } = useFrappePostCall('flamezo_backend.flamezo.api.boost.create_boost_campaign')
  const { call: approveCreative } = useFrappePostCall('flamezo_backend.flamezo.api.boost.approve_creative')
  const { call: createPayment } = useFrappePostCall('flamezo_backend.flamezo.api.boost.create_boost_payment')
  const { call: verifyPayment } = useFrappePostCall('flamezo_backend.flamezo.api.boost.verify_boost_payment')
  const { call: regenCreative } = useFrappePostCall('flamezo_backend.flamezo.api.boost.regenerate_creative')
  const { call: generateCreativeImage } = useFrappePostCall('flamezo_backend.flamezo.api.boost.generate_boost_creative')
  const { call: getCreativeStatus } = useFrappePostCall('flamezo_backend.flamezo.api.boost.get_boost_creative_status')

  // Gallery — same API as Gallery Management page
  const { data: poolData } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.restaurant.get_restaurant_media_pool',
    { restaurant_id: selectedRestaurant },
    selectedRestaurant ? `boost-media-pool-${selectedRestaurant}` : null
  )
  const existingMedia = useMemo(() => {
    const response = (poolData as any)?.message || poolData
    const allMedia = response?.data?.media || []
    // Media pool returns: { url, type, source_title, source_type, category }
    // Filter to images only (no videos), exclude branding assets
    return allMedia
      .filter((m: any) => m.type === 'image' && m.url && m.category !== 'Branding')
      .map((m: any) => ({ ...m, primary_url: m.url, alt_text: m.source_title || '' }))
  }, [poolData])

  const { call: fetchCampaignPerf } = useFrappePostCall('flamezo_backend.flamezo.api.boost.get_boost_performance')

  useEffect(() => {
    if (!selectedRestaurant) return
    setLoading(true)

    const promises: Promise<any>[] = [
      fetchPrereqs({ restaurant_id: selectedRestaurant }).then((r: any) => r?.message?.data || r?.data).catch(() => null),
      fetchTemplates({}).then((r: any) => r?.message?.data || r?.data).catch(() => []),
    ]

    // If we have a campaign ID from URL, reload it
    if (urlCampaignId) {
      promises.push(
        fetchCampaignPerf({ campaign_id: urlCampaignId })
          .then((r: any) => r?.message?.data || r?.data)
          .catch(() => null)
      )
    }

    Promise.all(promises).then(([pr, t, existingCampaign]) => {
      setPrereqs(pr)
      setTemplates(t || [])

      // Restore campaign state from DB if reloading
      if (existingCampaign && urlCampaignId) {
        setCampaign({
          campaign_id: existingCampaign.campaign_id,
          ad_primary_text: existingCampaign.ad_primary_text || '',
          ad_headline: existingCampaign.ad_headline || '',
          offer_description: existingCampaign.offer_description || '',
          coupon_code: existingCampaign.coupon_code || '',
          budget_total: existingCampaign.budget_total || 0,
          ad_spend_allocated: existingCampaign.ad_spend_allocated || 0,
          flamezo_fee: existingCampaign.flamezo_fee || 0,
          gst_on_fee: existingCampaign.gst_on_fee || 0,
          guaranteed_redemptions: existingCampaign.guaranteed_redemptions || 0,
          is_first_campaign: existingCampaign.is_first_campaign || false,
          location_grade: existingCampaign.location_grade || 'A',
        })
        setPkg(existingCampaign.package_tier || 'Growth')
        setOffer(existingCampaign.offer_amount || 100)
        setTemplateId(existingCampaign.template_id || '')
        if (existingCampaign.ad_image_url) {
          setAdImageUrl(existingCampaign.ad_image_url)
          setImagePreview(existingCampaign.ad_image_url)
        }
        // Stay on the URL step
        setStepIndexRaw(urlStep)
      } else if (pr?.passed && !urlCampaignId) {
        // New campaign — skip to package step
        setStepIndexRaw(1)
        const params = new URLSearchParams(searchParams)
        params.set('step', '1')
        setSearchParams(params, { replace: true })
      }

      setLoading(false)
    })
  }, [selectedRestaurant])

  const grade = (prereqs?.location_grade || 'A') as 'A' | 'B' | 'C'

  // ─── Handlers ─────────────────────────────────────────────────

  const handleCreateCampaign = async () => {
    if (!selectedRestaurant || !templateId) return
    setSubmitting(true); setError(null)
    try {
      const res: any = await createCampaign({
        restaurant_id: selectedRestaurant, template_id: templateId,
        package_tier: pkg, campaign_duration: duration,
        geo_radius_km: radius, offer_amount: offer,
        hero_dish_name: heroDish.trim() || undefined,
        ad_image_url: adImageUrl || undefined,
      })
      const newCampaign = res?.message?.data || res?.data
      setCampaign(newCampaign)
      // Save campaign ID to URL so refresh preserves state
      setStepIndexRaw(3)
      const params = new URLSearchParams(searchParams)
      params.set('step', '3')
      params.set('id', newCampaign.campaign_id)
      setSearchParams(params, { replace: true })
    } catch (e: any) {
      setError(e.message || 'Failed to create campaign')
    } finally { setSubmitting(false) }
  }

  const handlePay = async () => {
    if (!campaign) return
    if (!razorpayLoaded) { toast.error('Payment gateway is loading. Please wait.'); return }
    setSubmitting(true); setError(null)
    try {
      await approveCreative({ campaign_id: campaign.campaign_id })
      const payRes: any = await createPayment({ campaign_id: campaign.campaign_id })
      const payment = payRes?.message?.data || payRes?.data

      const rzp = new (window as any).Razorpay({
        key: payment.key_id, amount: payment.amount, currency: payment.currency,
        name: 'Flamezo Boost', description: `Boost - ${pkg}`,
        order_id: payment.razorpay_order_id,
        handler: async (resp: any) => {
          try {
            await verifyPayment({
              campaign_id: campaign.campaign_id,
              razorpay_order_id: resp.razorpay_order_id,
              razorpay_payment_id: resp.razorpay_payment_id,
              razorpay_signature: resp.razorpay_signature,
            })
            setSuccess(true)
          } catch { setError('Payment verification failed. Contact support if charged.') }
          finally { setSubmitting(false) }
        },
        modal: { ondismiss: () => setSubmitting(false) },
        theme: { color: '#f97316' },
      })
      rzp.open()
    } catch (e: any) {
      setError(e.message || 'Payment failed')
      setSubmitting(false)
    }
  }

  const handleRegen = async () => {
    if (!campaign) return
    setSubmitting(true)
    try {
      const r: any = await regenCreative({ campaign_id: campaign.campaign_id })
      const d = r?.message?.data || r?.data
      setCampaign({ ...campaign, ad_primary_text: d.ad_primary_text, ad_headline: d.ad_headline })
      toast.success('Copy regenerated')
    } catch { toast.error('Failed to regenerate') }
    finally { setSubmitting(false) }
  }

  // ─── AI Creative refinement ───────────────────────────────────
  const stopCreativePolling = useCallback(() => {
    if (creativePollRef.current) { clearInterval(creativePollRef.current); creativePollRef.current = null }
  }, [])

  // Clean up the poller on unmount
  useEffect(() => () => stopCreativePolling(), [stopCreativePolling])

  // Restore the processed creative when an existing campaign is reloaded
  const restoredCreativeFor = useRef<string | null>(null)
  useEffect(() => {
    const id = campaign?.campaign_id
    if (!id || restoredCreativeFor.current === id) return
    restoredCreativeFor.current = id
    getCreativeStatus({ campaign_id: id }).then((r: any) => {
      const d = r?.message?.data || r?.data
      if (d?.status === 'Ready' && d?.processed_url) {
        setAdImageUrl(d.processed_url)
        setImagePreview(prev => prev || d.processed_url)
        setCreativeStatus('ready')
      } else if (d?.status === 'Processing') {
        setCreativeStatus('processing')
        startCreativePolling(id)  // resume polling an in-flight job (no re-enqueue)
      }
    }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaign?.campaign_id])

  // Pick a raw photo — shown immediately; AI creative generated on demand
  const handleSelectSource = (url: string) => {
    stopCreativePolling()
    setSourceImageUrl(url)
    setImagePreview(url)
    setAdImageUrl('')
    setCreativeStatus('idle')
  }

  // Upload a photo from the user's computer, then treat it as the source
  const handleUploadFromComputer = async (file: File) => {
    if (!file || !selectedRestaurant) return
    setUploadingImage(true)
    try {
      const result = await uploadToR2({
        ownerDoctype: 'Boost Campaign',
        ownerName: campaign?.campaign_id || selectedRestaurant,
        mediaRole: 'boost_ad_source',
        file,
      })
      const url = result.primary_url || ''
      if (url) { handleSelectSource(url); toast.success('Photo uploaded') }
    } catch (e: any) {
      toast.error(e.message || 'Upload failed')
    } finally {
      setUploadingImage(false)
    }
  }

  // Poll the background job until the creative is Ready/Failed
  const startCreativePolling = (campaignId: string) => {
    stopCreativePolling()
    creativePollRef.current = setInterval(async () => {
      try {
        const r: any = await getCreativeStatus({ campaign_id: campaignId })
        const d = r?.message?.data || r?.data
        if (d?.status === 'Ready' && d?.processed_url) {
          stopCreativePolling()
          setAdImageUrl(d.processed_url)
          setImagePreview(d.processed_url)
          setCreativeStatus('ready')
          toast.success('AI creative ready')
        } else if (d?.status === 'Failed') {
          stopCreativePolling()
          setCreativeStatus('failed')
          toast.error(d?.error ? `Creative failed: ${d.error}` : 'Creative generation failed')
        }
      } catch { /* keep polling; transient errors are fine */ }
    }, 2500)
  }

  const handleGenerateCreative = async (url?: string) => {
    const source = url || sourceImageUrl
    if (!campaign || !source) return
    stopCreativePolling()
    setCreativeStatus('processing')
    setError(null)
    try {
      await generateCreativeImage({ campaign_id: campaign.campaign_id, source_image_url: source })
      startCreativePolling(campaign.campaign_id)
    } catch (e: any) {
      stopCreativePolling()
      setCreativeStatus('failed')
      toast.error(e.message || 'Failed to start creative generation')
    }
  }

  const canProceed = () => {
    if (stepIndex === 0) return prereqs?.passed
    if (stepIndex === 1) return true
    if (stepIndex === 2) return !!templateId && offer > 0
    if (stepIndex === 3) return !!campaign
    return false
  }

  // ─── Loading ──────────────────────────────────────────────────

  if (loading) return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-48" />
      <Skeleton className="h-16 rounded-xl" />
      <Skeleton className="h-96 rounded-xl" />
    </div>
  )

  // ─── Success ──────────────────────────────────────────────────

  if (success) return (
    <div className="max-w-6xl">
      <div className="text-center py-16">
        <div className="h-20 w-20 rounded-full bg-emerald-100 dark:bg-emerald-950/40 flex items-center justify-center mx-auto mb-6 animate-in zoom-in-50 duration-500">
          <CheckCircle2 className="h-10 w-10 text-emerald-600" />
        </div>
        <h1 className="text-2xl font-bold mb-2 animate-in fade-in-0 slide-in-from-bottom-4 duration-500 delay-200">Campaign Launched!</h1>
        <p className="text-muted-foreground max-w-sm mx-auto mb-8 animate-in fade-in-0 duration-500 delay-300">
          Your ad is being reviewed by Meta and will go live within 1–2 hours. We'll notify you when it starts running.
        </p>
        <div className="flex gap-3 justify-center animate-in fade-in-0 duration-500 delay-500">
          <Button variant="outline" onClick={() => navigate('/boost')}>View Campaigns</Button>
          <Button onClick={() => { setSuccess(false); setStepIndex(1); setCampaign(null) }}
            className="bg-gradient-to-r from-orange-500 to-amber-600 text-white">
            Create Another
          </Button>
        </div>
      </div>
    </div>
  )  // ─── Navigation Buttons ───────────────────────────────────────
  const navigationButtons = !success && (
    <div className="flex items-center justify-between py-3 border-t border-b border-border/40 my-2">
      <Button variant="ghost" onClick={() => stepIndex > 0 ? setStepIndex(stepIndex - 1) : navigate('/boost')} className="gap-1">
        <ChevronLeft className="h-4 w-4" /> {stepIndex === 0 ? 'Cancel' : 'Back'}
      </Button>
      {stepIndex < 3 && (
        <Button onClick={() => stepIndex === 2 ? handleCreateCampaign() : setStepIndex(stepIndex + 1)}
          disabled={!canProceed() || submitting}
          className="gap-2 bg-gradient-to-r from-orange-500 to-amber-600 text-white">
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {stepIndex === 2 ? (submitting ? 'Generating...' : 'Generate Preview') : 'Next'}
          {!submitting && <ChevronRight className="h-4 w-4" />}
        </Button>
      )}
      {stepIndex === 3 && (
        <Button onClick={() => setStepIndex(4)}
          disabled={creativeStatus !== 'ready' || !adImageUrl}
          title={creativeStatus !== 'ready' ? 'Generate your AI creative first' : undefined}
          className="gap-2 bg-gradient-to-r from-orange-500 to-amber-600 text-white">
          {creativeStatus === 'processing' ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Continue to Payment <ChevronRight className="h-4 w-4" />
        </Button>
      )}
      {stepIndex === 4 && (
        <Button onClick={handlePay} disabled={submitting}
          className="gap-2 bg-gradient-to-r from-orange-500 to-amber-600 text-white shadow-lg shadow-orange-500/20">
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
          {submitting ? 'Processing...' : 'Approve & Pay'}
        </Button>
      )}
    </div>
  )

  // ─── Render ───────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1.5 text-[11px] font-bold tracking-widest uppercase text-muted-foreground/60 mb-2">
        <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
        <ChevronRight className="h-3 w-3" />
        <Link to="/boost" className="hover:text-foreground transition-colors">Boost</Link>
        <ChevronRight className="h-3 w-3" />
        <span className="text-foreground">New Campaign</span>
      </nav>

      {/* Back */}
      <Button variant="ghost" size="sm" onClick={() => navigate('/boost')} className="gap-1 -ml-2">
        <ChevronLeft className="h-4 w-4" /> Back to Boost
      </Button>

      {/* Step Bar */}
      <Card className="border-none bg-card shadow-sm">
        <div className="h-1.5 bg-gradient-to-r from-orange-500 via-amber-500 to-yellow-400 rounded-t-xl" />
        <CardContent className="pt-4 pb-3">
          <div className="flex items-center justify-between">
            {STEPS.map((step, i) => {
              const Icon = step.icon
              const isCompleted = i < stepIndex
              const isCurrent = i === stepIndex
              return (
                <div key={step.id} className="flex items-center gap-2 flex-1">
                  <div className={cn(
                    'h-8 w-8 rounded-full flex items-center justify-center shrink-0 transition-all text-xs font-bold',
                    isCompleted && 'bg-emerald-500 text-white',
                    isCurrent && 'bg-orange-500 text-white shadow-lg shadow-orange-500/30',
                    !isCompleted && !isCurrent && 'bg-muted text-muted-foreground'
                  )}>
                    {isCompleted ? <CheckCircle2 className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
                  </div>
                  <span className={cn(
                    'text-xs font-medium hidden sm:block',
                    isCurrent ? 'text-foreground' : 'text-muted-foreground'
                  )}>{step.label}</span>
                  {i < STEPS.length - 1 && <div className={cn('h-px flex-1 mx-2', isCompleted ? 'bg-emerald-500' : 'bg-border')} />}
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* Top Navigation */}
      {navigationButtons}

      {/* Error */}
      {error && (
        <Card className="border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/20">
          <CardContent className="pt-3 pb-3 flex items-center gap-2 text-sm text-red-700 dark:text-red-300">
            <XCircle className="h-4 w-4 shrink-0" /> {error}
          </CardContent>
        </Card>
      )}

      {/* Step Content */}
      <div className="animate-in fade-in-0 slide-in-from-right-4 duration-300" key={stepIndex}>

        {/* Step 0: Prerequisites */}
        {stepIndex === 0 && prereqs && (
          <Card className="border-none bg-card shadow-sm">
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="relative h-14 w-14 shrink-0">
                  <svg className="h-14 w-14 -rotate-90" viewBox="0 0 36 36">
                    <path d="M18 2.0845a 15.9155 15.9155 0 0 1 0 31.831a 15.9155 15.9155 0 0 1 0 -31.831"
                      fill="none" stroke="currentColor" strokeWidth="3" className="text-muted" />
                    <path d="M18 2.0845a 15.9155 15.9155 0 0 1 0 31.831a 15.9155 15.9155 0 0 1 0 -31.831"
                      fill="none" stroke="currentColor" strokeWidth="3"
                      className={prereqs.passed ? 'text-emerald-500' : 'text-orange-500'}
                      strokeDasharray={`${prereqs.score}, 100`} strokeLinecap="round" />
                  </svg>
                  <span className="absolute inset-0 flex items-center justify-center text-sm font-bold">{prereqs.score}%</span>
                </div>
                <div>
                  <h2 className="text-lg font-bold">Prerequisites</h2>
                  <p className="text-sm text-muted-foreground">Location Grade: <span className="font-semibold text-orange-600">{prereqs.location_grade}</span></p>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              {prereqs.checks.map((c: any) => (
                <div key={c.check} className="flex items-center gap-3 p-3 rounded-lg border">
                  {c.passed ? <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" /> : <XCircle className="h-4 w-4 text-red-500 shrink-0" />}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">{c.label}</p>
                    <p className="text-xs text-muted-foreground truncate">{c.details}</p>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Step 1: Package */}
        {stepIndex === 1 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-bold tracking-tight text-foreground">Choose Package</h2>
              <p className="text-xs text-muted-foreground mt-0.5">Select a budget tier tailored to your restaurant's volume expectations</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              {PACKAGES.map(p => {
                const [lo, hi] = p.est[grade] || p.est.A
                const revLo = lo * AVG_BILL; const revHi = hi * AVG_BILL
                const roi = Math.round((revLo / p.price) * 10) / 10
                const cost = Math.round(p.price / lo)
                const isSelected = pkg === p.tier
                return (
                  <button key={p.tier} onClick={() => setPkg(p.tier)}
                    className={cn('w-full p-6 rounded-2xl border transition-all duration-300 relative flex flex-col justify-between min-h-[250px] text-left bg-card',
                      isSelected 
                        ? 'border-orange-500 bg-orange-50/40 dark:bg-orange-950/20 shadow-md ring-1 ring-orange-500/30 scale-[1.02]' 
                        : 'border-border/60 hover:border-orange-200 hover:shadow-md hover:scale-[1.01]')}>
                    {p.popular && (
                      <span className="absolute -top-3 left-1/2 -translate-x-1/2 text-[9px] font-black uppercase tracking-widest bg-gradient-to-r from-orange-500 to-amber-600 text-white px-3 py-1 rounded-full shadow-sm whitespace-nowrap z-10 animate-pulse">
                        Most Popular
                      </span>
                    )}
                    {isSelected && (
                      <div className="absolute top-4 right-4 h-5 w-5 bg-orange-500 text-white rounded-full flex items-center justify-center shadow-sm">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                      </div>
                    )}
                    <div className="w-full">
                      <div className="flex flex-col mb-1">
                        <span className="text-[10px] font-extrabold uppercase tracking-widest text-muted-foreground">{p.tier}</span>
                        <div className="mt-1 flex items-baseline">
                          <span className="text-3xl font-black text-foreground">₹{p.price.toLocaleString()}</span>
                        </div>
                      </div>
                      <div className="bg-muted/40 dark:bg-muted/10 rounded-xl p-4 mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
                        <div>
                          <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Walk-ins</p>
                          <p className="text-sm font-bold text-foreground mt-0.5">{lo}–{hi}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Revenue</p>
                          <p className="text-sm font-bold text-emerald-600 mt-0.5">₹{(revLo / 1000).toFixed(0)}K–{(revHi / 1000).toFixed(0)}K</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">ROI</p>
                          <p className="text-sm font-bold text-emerald-600 mt-0.5">{roi}x</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Cost/Cust</p>
                          <p className="text-sm font-bold text-foreground mt-0.5">₹{cost}</p>
                        </div>
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t border-border/40">
              <div className="space-y-3">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Campaign Duration</Label>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { days: 7, label: '7 Days', desc: 'Weekend spike test', icon: Clock },
                    { days: 14, label: '14 Days', desc: 'Optimal conversions', icon: Calendar, badge: 'Recommended' }
                  ].map(d => {
                    const isSelected = duration === d.days
                    const Icon = d.icon
                    return (
                      <button key={d.days} onClick={() => setDuration(d.days)}
                        className={cn('p-4 rounded-xl border text-left transition-all duration-300 relative flex items-center gap-3 bg-card',
                          isSelected 
                            ? 'border-orange-500 bg-orange-50/40 dark:bg-orange-950/20 ring-1 ring-orange-500/30 scale-[1.01]' 
                            : 'border-border/60 hover:border-orange-200 hover:bg-muted/10')}>
                        {d.badge && (
                          <span className="absolute -top-2.5 right-3 text-[8px] font-black uppercase tracking-wider bg-orange-500 text-white px-2 py-0.5 rounded-full whitespace-nowrap shadow-sm">
                            {d.badge}
                          </span>
                        )}
                        <div className={cn('h-8 w-8 rounded-lg flex items-center justify-center shrink-0',
                          isSelected ? 'bg-orange-500 text-white shadow-sm shadow-orange-500/10' : 'bg-muted text-muted-foreground')}>
                          <Icon className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-bold text-foreground leading-tight">{d.label}</p>
                          <p className="text-[10px] text-muted-foreground truncate mt-0.5">{d.desc}</p>
                        </div>
                      </button>
                    )
                  })}
                </div>
              </div>
              <div className="space-y-3">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Targeting Radius</Label>
                <div className="flex flex-col sm:flex-row gap-4 items-center bg-card p-4 rounded-xl border border-border/40">
                  {/* Buttons Grid */}
                  <div className="grid grid-cols-1 gap-2 flex-1 w-full">
                    {[
                      { km: 5, label: '5 km Radius', desc: 'City center scale coverage' },
                      { km: 7, label: '7 km Radius', desc: 'Destination pull max range' },
                      { km: 15, label: 'Whole City', desc: 'Entire municipal & metro region' }
                    ].map(r => {
                      const isSelected = radius === r.km
                      return (
                        <button key={r.km} onClick={() => setRadius(r.km)}
                          className={cn('p-3 rounded-lg border text-left transition-all duration-300 relative flex items-center gap-3 bg-card w-full',
                            isSelected 
                              ? 'border-orange-500 bg-orange-50/40 dark:bg-orange-950/20 ring-1 ring-orange-500/30 scale-[1.01]' 
                              : 'border-border/60 hover:border-orange-200 hover:bg-muted/10')}>
                          <div className={cn('h-8 w-8 rounded-lg flex items-center justify-center shrink-0',
                            isSelected ? 'bg-orange-500 text-white shadow-sm shadow-orange-500/10' : 'bg-muted text-muted-foreground')}>
                            <MapPin className="h-4 w-4" />
                          </div>
                          <div className="min-w-0">
                            <p className="text-xs font-bold text-foreground leading-tight">{r.label}</p>
                            <p className="text-[9px] text-muted-foreground truncate mt-0.5">{r.desc}</p>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                  
                  {/* Real Geographic Map - Leaflet Circle Radius Targeting */}
                  <div className="h-56 w-full md:w-[340px] shrink-0 rounded-xl border border-border/40 overflow-hidden shadow-inner bg-muted/20 dark:bg-muted/5 relative">
                    <BoostRadiusMap
                      lat={restaurantDoc?.latitude ? parseFloat(restaurantDoc.latitude) : 21.1702}
                      lng={restaurantDoc?.longitude ? parseFloat(restaurantDoc.longitude) : 72.8311}
                      radius={radius}
                      restaurantName={restaurantName}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Step 2: Template & Offer */}
        {stepIndex === 2 && (
          <div className="flex flex-col lg:flex-row gap-6 items-start animate-in fade-in duration-300">
            {/* Left Config Panel */}
            <div className="flex-1 w-full min-w-0 space-y-6">
              <div>
                <h2 className="text-lg font-bold tracking-tight text-foreground">Choose Template & Offer</h2>
                <p className="text-xs text-muted-foreground mt-0.5">Select a pre-calibrated campaign structure optimized for conversions</p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                {filteredTemplates.map(t => {
                  const isSelected = templateId === t.template_id
                  
                  // Dynamic icon selection
                  const nameLower = t.template_name.toLowerCase()
                  let IconComp = Zap
                  if (t.requires_hero_dish) IconComp = Sparkles
                  else if (nameLower.includes('bogo')) IconComp = Copy
                  else if (nameLower.includes('weekend')) IconComp = Calendar
                  else if (nameLower.includes('lunch')) IconComp = Clock
                  else if (nameLower.includes('review')) IconComp = Heart
                  else if (nameLower.includes('festive')) IconComp = Sparkles
                  else if (nameLower.includes('first')) IconComp = Heart

                  return (
                    <button key={t.template_id} onClick={() => setTemplateId(t.template_id)}
                      className={cn('relative rounded-xl border overflow-hidden flex text-left bg-card transition-all duration-300 min-h-[115px] w-full',
                        isSelected 
                          ? 'border-orange-500 bg-orange-50/40 dark:bg-orange-950/20 ring-1 ring-orange-500/30 scale-[1.01]' 
                          : 'border-border/60 hover:border-orange-200 hover:bg-muted/10 hover:scale-[1.005]')}>
                      
                      {/* Left Stub */}
                      <div className={cn('w-12 shrink-0 flex flex-col items-center justify-center border-r border-dashed border-border/50 relative',
                        isSelected ? 'bg-gradient-to-b from-orange-500 to-amber-600 text-white' : 'bg-muted/40 dark:bg-muted/10 text-muted-foreground/75')}>
                        <IconComp className="h-5 w-5" />
                      </div>

                      {/* Ticket Notches */}
                      <div className={cn('absolute -top-1.5 left-[42px] h-3 w-3 rounded-full bg-background border border-border/40',
                        isSelected ? 'border-orange-500' : 'border-border/60')} />
                      <div className={cn('absolute -bottom-1.5 left-[42px] h-3 w-3 rounded-full bg-background border border-border/40',
                        isSelected ? 'border-orange-500' : 'border-border/60')} />

                      {/* Main Voucher Body */}
                      <div className="p-3 flex-1 flex flex-col justify-between min-w-0">
                        <div>
                          <div className="flex items-start justify-between gap-1.5 mb-1.5">
                            <span className="font-bold text-xs text-foreground truncate">{t.template_name}</span>
                            <span className="text-[9px] font-extrabold text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30 dark:text-emerald-400 px-1.5 py-0.5 rounded-full uppercase tracking-wider shrink-0">
                              CTR {t.expected_ctr_low}–{t.expected_ctr_high}%
                            </span>
                          </div>
                          <p className="text-[10px] text-muted-foreground/90 italic leading-snug">"{t.hook_formula}"</p>
                        </div>
                        <div className="w-full mt-2 pt-1.5 border-t border-border/30">
                          <span className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground/75 truncate block">Target: {t.best_for}</span>
                        </div>
                      </div>
                    </button>
                  )
                })}
              </div>
              <div className="space-y-3">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Flat Discount (₹)</Label>
                <div className="flex flex-col md:flex-row gap-4 items-center bg-card p-4 rounded-xl border border-border/40">
                  {/* Options Grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 flex-1 w-full">
                    {[
                      { value: 50, desc: 'Starter Pull' },
                      { value: 100, desc: 'Optimal Value', badge: 'Best' },
                      { value: 150, desc: 'Weekend Spike' },
                      { value: 200, desc: 'Premium Drawer' },
                      { value: 300, desc: 'Max Growth' }
                    ].map(d => {
                      const isSelected = offer === d.value
                      return (
                        <button key={d.value} onClick={() => setOffer(d.value)}
                          className={cn('p-3 rounded-lg border text-left transition-all duration-300 relative flex flex-col justify-between bg-card min-h-[72px]',
                            isSelected 
                              ? 'border-orange-500 bg-orange-50/40 dark:bg-orange-950/20 ring-1 ring-orange-500/30 scale-[1.01]' 
                              : 'border-border/60 hover:border-orange-200 hover:bg-muted/10')}>
                          {d.badge && (
                            <span className="absolute -top-2 right-2 text-[7px] font-black uppercase tracking-wider bg-orange-500 text-white px-1.5 py-0.5 rounded-full shadow-sm">
                              {d.badge}
                            </span>
                          )}
                          <span className="text-base font-black text-foreground">₹{d.value}</span>
                          <span className="text-[8px] text-muted-foreground/80 font-medium tracking-wide mt-1 truncate">{d.desc}</span>
                        </button>
                      )
                    })}
                  </div>

                  {/* Coupon Ticket Visualizer */}
                  <div className="h-[76px] w-full md:w-[260px] shrink-0 bg-card rounded-xl border border-border/40 relative overflow-hidden shadow-inner flex select-none transition-all duration-300">
                    {/* Left Stub */}
                    <div className="w-10 bg-muted/30 dark:bg-muted/10 flex items-center justify-center border-r border-dashed border-border/50 relative">
                      {/* Ticket Notches */}
                      <div className="absolute -top-1.5 -right-1.5 h-3 w-3 rounded-full bg-background border border-border/40" />
                      <div className="absolute -bottom-1.5 -right-1.5 h-3 w-3 rounded-full bg-background border border-border/40" />
                      
                      <span className="text-[7px] font-black tracking-widest text-muted-foreground uppercase rotate-90 whitespace-nowrap">
                        BOOST
                      </span>
                    </div>

                    {/* Main Voucher */}
                    <div className="flex-1 p-2.5 flex flex-col justify-between relative bg-gradient-to-br from-card via-card to-orange-50/10 dark:to-orange-950/5">
                      {/* Top Row */}
                      <div className="flex justify-between items-start gap-1">
                        <span className="text-[7px] font-black uppercase tracking-wider text-orange-600 bg-orange-100/60 dark:bg-orange-950/40 px-1 py-0.5 rounded">
                          OFFER VOUCHER
                        </span>
                        <span className="text-[8px] font-mono text-muted-foreground">
                          Code: GET{offer}
                        </span>
                      </div>

                      {/* Middle Row */}
                      <div className="flex items-baseline gap-1.5">
                        <h3 className="text-lg font-black text-foreground tracking-tight leading-none animate-in zoom-in-95 duration-200" key={offer}>
                          ₹{offer} OFF
                        </h3>
                        <p className="text-[8px] font-bold text-muted-foreground uppercase tracking-wide truncate max-w-[130px]">
                          at {restaurantName}
                        </p>
                      </div>

                      {/* Bottom Row - Barcode */}
                      <div className="flex items-center gap-1.5 opacity-60">
                        <div className="h-3.5 flex-1 flex gap-[1.5px] items-center">
                          {[2, 1, 3, 1, 2, 4, 1, 2, 3, 1, 2, 1, 4, 2].map((w, idx) => (
                            <div key={idx} className="h-full bg-foreground" style={{ width: `${w}px` }} />
                          ))}
                        </div>
                        <span className="text-[6px] font-mono text-muted-foreground tracking-wider">
                          *FLZBOOST*
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              {!!templates.find(t => t.template_id === templateId)?.requires_hero_dish && (
                <div className="space-y-1.5 pt-2">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Hero Dish Name</Label>
                  <Input value={heroDish} onChange={e => setHeroDish(e.target.value)} placeholder="e.g., Truffle Mushroom Risotto" className="mt-1.5" />
                </div>
              )}
            </div>

            {/* Sticky Right Preview Panel */}
            <div className="mx-auto lg:mx-0 lg:sticky lg:top-4 space-y-2 shrink-0">
              <h3 className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/75 text-center lg:text-left pl-1">
                Live Ad Preview
              </h3>
              <AdPreviewMockup
                restaurantName={restaurantName}
                imageUrl={imagePreview || randomPlaceholderImage}
                primaryText={mockPreviewCopy.primaryText}
                headline={mockPreviewCopy.headline}
                placeholderTitle="Ad Photo Placeholder"
                placeholderDesc="Photo chosen in next step"
              />
            </div>
          </div>
        )}

        {/* Step 3: Preview & Image */}
        {stepIndex === 3 && campaign && (
          <div className="space-y-4">
            <h2 className="text-lg font-bold">Preview Your Ad</h2>
            <p className="text-sm text-muted-foreground">Select a food photo and our AI will generate a Meta-compliant ad creative.</p>

            <div className="flex flex-col lg:flex-row gap-6 items-start">
              {/* Phone Frame — Instagram Mockup */}
              <div className="mx-auto lg:mx-0">
                <AdPreviewMockup
                  restaurantName={restaurantName}
                  imageUrl={imagePreview}
                  primaryText={campaign.ad_primary_text}
                  headline={campaign.ad_headline}
                  onClearImage={() => { stopCreativePolling(); setImagePreview(''); setAdImageUrl(''); setSourceImageUrl(''); setCreativeStatus('idle') }}
                  placeholderTitle="Select a photo below"
                  placeholderDesc="AI will generate your ad"
                  processing={creativeStatus === 'processing'}
                  isCreative={creativeStatus === 'ready'}
                />
              </div>

              {/* Right Panel — Photo Selection + Actions */}
              <div className="flex-1 space-y-4 min-w-0">
                {/* Photo Gallery Picker */}
                <Card className="border-none bg-card shadow-sm">
                  <CardHeader className="pb-2">
                    <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Choose a Photo</h3>
                    <p className="text-xs text-muted-foreground">Pick from your gallery or upload one — AI keeps the dish as-is and adds your branding, offer & address</p>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {/* Option 1 — Gallery */}
                    <div className="space-y-2">
                      <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground/70">From your gallery</p>
                      {existingMedia && existingMedia.length > 0 ? (
                        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 max-h-48 overflow-y-auto">
                          {existingMedia.map((m: any, idx: number) => (
                            <button key={m.primary_url || idx} disabled={creativeStatus === 'processing' || uploadingImage}
                              onClick={() => handleSelectSource(m.primary_url)}
                              className={cn('aspect-square rounded-lg overflow-hidden border-2 transition-all disabled:opacity-50',
                                sourceImageUrl === m.primary_url ? 'border-orange-500 ring-2 ring-orange-500/20' : 'border-transparent hover:border-orange-300')}>
                              <img src={encodeURI(m.primary_url)} alt={m.alt_text || ''} className="w-full h-full object-cover" />
                            </button>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-muted-foreground py-2">No photos in your gallery yet — upload one below.</p>
                      )}
                    </div>

                    {/* Option 2 — Upload from computer */}
                    <div className="space-y-2">
                      <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground/70">Or upload from your computer</p>
                      <label className={cn(
                        'flex flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed py-5 cursor-pointer transition-colors',
                        (creativeStatus === 'processing' || uploadingImage)
                          ? 'opacity-50 pointer-events-none border-border'
                          : 'border-orange-200 hover:border-orange-400 hover:bg-orange-50/40 dark:hover:bg-orange-950/10')}>
                        {uploadingImage
                          ? <Loader2 className="h-6 w-6 text-orange-500 animate-spin" />
                          : <Upload className="h-6 w-6 text-orange-500" />}
                        <span className="text-xs font-medium">{uploadingImage ? 'Uploading…' : 'Click to upload a photo'}</span>
                        <span className="text-[10px] text-muted-foreground">JPG / PNG / WEBP</span>
                        <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                          disabled={creativeStatus === 'processing' || uploadingImage}
                          onChange={e => { const f = e.target.files?.[0]; if (f) handleUploadFromComputer(f); e.currentTarget.value = '' }} />
                      </label>
                    </div>

                    {/* Generate the final AI creative */}
                    {sourceImageUrl && (
                      <div className="space-y-2 pt-1 border-t border-border/40">
                        <Button
                          onClick={() => handleGenerateCreative()}
                          disabled={creativeStatus === 'processing' || uploadingImage}
                          className="w-full gap-2 bg-gradient-to-r from-orange-500 to-amber-600 text-white">
                          {creativeStatus === 'processing'
                            ? <><Loader2 className="h-4 w-4 animate-spin" /> Generating final version…</>
                            : creativeStatus === 'ready'
                              ? <><RefreshCw className="h-4 w-4" /> Regenerate Final Version</>
                              : <><Sparkles className="h-4 w-4" /> Generate Final Version</>}
                        </Button>
                        {creativeStatus === 'ready' && (
                          <p className="text-[11px] text-emerald-600 flex items-center gap-1.5">
                            <CheckCircle2 className="h-3.5 w-3.5" /> Final creative ready — branding, offer & location added
                          </p>
                        )}
                        {creativeStatus === 'failed' && (
                          <p className="text-[11px] text-red-500 flex items-center gap-1.5">
                            <XCircle className="h-3.5 w-3.5" /> Generation failed — try again
                          </p>
                        )}
                        {creativeStatus === 'idle' && (
                          <p className="text-[11px] text-muted-foreground">AI checks what's already on the photo, then adds your offer, location & Flamezo branding.</p>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Ad Copy */}
                <Card className="border-none bg-card shadow-sm">
                  <CardHeader className="pb-2">
                    <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Ad Copy</h3>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="p-3 bg-muted rounded-lg">
                      <p className="text-sm">{campaign.ad_primary_text}</p>
                    </div>
                    <div className="p-3 bg-muted rounded-lg">
                      <p className="text-sm font-bold">{campaign.ad_headline}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">{campaign.offer_description}</span>
                      <span className="text-xs font-mono text-orange-600">{campaign.coupon_code}</span>
                    </div>
                    <Button variant="outline" size="sm" onClick={handleRegen} disabled={submitting} className="w-full gap-2 mt-2">
                      <RefreshCw className={cn('h-3.5 w-3.5', submitting && 'animate-spin')} /> Regenerate Copy
                    </Button>
                  </CardContent>
                </Card>

                {/* Info */}
                <div className="text-xs text-muted-foreground bg-card shadow-sm border-none rounded-xl p-4 space-y-1.5">
                  <p className="font-medium">How it works:</p>
                  <p>• Your photo + AI-generated text = final ad creative</p>
                  <p>• Meta reviews the ad (usually 1–2 hours)</p>
                  <p>• Ad runs on Instagram Feed, Stories & Reels</p>
                  <p>• Customers click → see coupon → visit your restaurant</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Step 4: Payment */}
        {stepIndex === 4 && campaign && (
          <div className="space-y-4">
            <h2 className="text-lg font-bold">Review & Pay</h2>
            <Card className="border-none bg-card shadow-sm">
              <CardContent className="pt-5 space-y-3">
                <div className="flex justify-between text-sm"><span className="text-muted-foreground">Package</span><span className="font-semibold">{pkg}</span></div>
                <div className="flex justify-between text-sm"><span className="text-muted-foreground">Duration</span><span>{duration} days</span></div>
                <div className="flex justify-between text-sm"><span className="text-muted-foreground">Radius</span><span>{radius} km</span></div>
                <div className="flex justify-between text-sm"><span className="text-muted-foreground">Offer</span><span>₹{offer} off</span></div>
                <div className="border-t my-2" />
                <div className="flex justify-between text-sm"><span className="text-muted-foreground">GST</span><span>₹{Math.round(campaign.gst_on_fee)}</span></div>
                <div className="flex justify-between font-bold text-lg pt-1">
                  <span>Total</span>
                  <span className="text-orange-600">₹{Math.round(campaign.budget_total + campaign.gst_on_fee).toLocaleString()}</span>
                </div>
              </CardContent>
            </Card>
            {campaign.is_first_campaign ? (
              <Card className="border-none bg-amber-50 dark:bg-amber-950/20 shadow-sm">
                <CardContent className="pt-3 pb-3 text-sm text-amber-700 dark:text-amber-300">
                  First campaign — estimated walk-ins (no guarantee yet). Guarantee unlocks from campaign #2.
                </CardContent>
              </Card>
            ) : campaign.guaranteed_redemptions > 0 ? (
              <Card className="border-none bg-emerald-50 dark:bg-emerald-950/20 shadow-sm">
                <CardContent className="pt-3 pb-3 text-sm text-emerald-700 dark:text-emerald-300">
                  Guaranteed: {campaign.guaranteed_redemptions}+ walk-ins or we top up your next campaign.
                </CardContent>
              </Card>
            ) : null}
          </div>
        )}
      </div>



      {/* Gallery Dialog removed — photo picker is inline in Step 3 */}
    </div>
  )
}


