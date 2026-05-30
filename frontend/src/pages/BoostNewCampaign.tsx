import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall, useFrappeGetCall, useFrappeGetDoc } from '@/lib/frappe'
import { useEffect, useState, useMemo, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  CheckCircle2, XCircle, Sparkles, RefreshCw, Zap, ChevronLeft, ChevronRight,
  DollarSign, Eye, CreditCard, ImagePlus, Upload, X, Loader2, Heart, MessageCircle,
  Send as SendIcon, Bookmark, MoreHorizontal, Copy
} from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { uploadToR2 } from '@/lib/r2Upload'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

// ─── Types & Constants ──────────────────────────────────────────

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

// ─── Component ──────────────────────────────────────────────────

export default function BoostNewCampaign() {
  const { selectedRestaurant } = useRestaurant()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  // Read initial state from URL params (persists across refreshes)
  const urlCampaignId = searchParams.get('id') || ''
  const urlStep = parseInt(searchParams.get('step') || '0', 10)

  const [stepIndex, setStepIndexRaw] = useState(urlStep)
  const [prereqs, setPrereqs] = useState<any>(null)
  const [templates, setTemplates] = useState<Template[]>([])
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

  // Image state
  const [adImageUrl, setAdImageUrl] = useState('')
  const [imagePreview, setImagePreview] = useState('')
  const [uploadingImage, setUploadingImage] = useState(false)
  const [showGalleryDialog, setShowGalleryDialog] = useState(false)

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

  // Get restaurant name
  const { data: restaurantDoc } = useFrappeGetDoc('Restaurant', selectedRestaurant || '', selectedRestaurant ? undefined : null)
  const restaurantName = (restaurantDoc as any)?.restaurant_name || selectedRestaurant || '{restaurantName}'

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

  const currentStep = STEPS[stepIndex]
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

  const handleImageUpload = async (file: File) => {
    if (!selectedRestaurant) return
    setUploadingImage(true)
    try {
      const result = await uploadToR2({ ownerDoctype: 'Boost Campaign', ownerName: selectedRestaurant, mediaRole: 'boost_ad_image', file })
      setAdImageUrl(result.primary_url || ''); setImagePreview(result.primary_url || '')
      setShowGalleryDialog(false); toast.success('Image uploaded')
    } catch (e: any) { toast.error(e.message || 'Upload failed') }
    finally { setUploadingImage(false) }
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
  )

  // ─── Render ───────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* Back */}
      <Button variant="ghost" size="sm" onClick={() => navigate('/boost')} className="gap-1 -ml-2">
        <ChevronLeft className="h-4 w-4" /> Back to Boost
      </Button>

      {/* Step Bar */}
      <Card>
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
          <Card>
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
          <div className="space-y-4">
            <h2 className="text-lg font-bold">Choose Package</h2>
            {PACKAGES.map(p => {
              const [lo, hi] = p.est[grade] || p.est.A
              const revLo = lo * AVG_BILL; const revHi = hi * AVG_BILL
              const roi = Math.round((revLo / p.price) * 10) / 10
              const cost = Math.round(p.price / lo)
              return (
                <button key={p.tier} onClick={() => setPkg(p.tier)}
                  className={cn('w-full p-5 rounded-xl border-2 text-left transition-all relative',
                    pkg === p.tier ? 'border-orange-500 bg-orange-50 dark:bg-orange-950/20' : 'border-border hover:border-orange-200')}>
                  {p.popular && <span className="absolute -top-2.5 right-4 text-[10px] font-semibold bg-orange-500 text-white px-2.5 py-0.5 rounded-full">Most Popular</span>}
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-lg">{p.tier}</span>
                    <span className="font-bold text-xl text-orange-600">₹{p.price.toLocaleString()}</span>
                  </div>
                  <div className="grid grid-cols-4 gap-3 mt-3 pt-3 border-t">
                    <div><p className="text-[10px] text-muted-foreground">Walk-ins</p><p className="text-sm font-semibold">{lo}–{hi}</p></div>
                    <div><p className="text-[10px] text-muted-foreground">Revenue</p><p className="text-sm font-semibold text-emerald-600">₹{(revLo / 1000).toFixed(0)}K–{(revHi / 1000).toFixed(0)}K</p></div>
                    <div><p className="text-[10px] text-muted-foreground">ROI</p><p className="text-sm font-semibold text-emerald-600">{roi}x</p></div>
                    <div><p className="text-[10px] text-muted-foreground">Cost/Customer</p><p className="text-sm font-semibold">₹{cost}</p></div>
                  </div>
                </button>
              )
            })}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Duration</Label>
                <div className="flex gap-2 mt-1.5">{[7, 14].map(d => (
                  <Button key={d} variant={duration === d ? 'default' : 'outline'} size="sm" onClick={() => setDuration(d)}
                    className={cn('flex-1', duration === d && 'bg-orange-500 hover:bg-orange-600')}>{d} Days</Button>
                ))}</div>
              </div>
              <div>
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Radius</Label>
                <div className="flex gap-2 mt-1.5">{[3, 5, 7].map(r => (
                  <Button key={r} variant={radius === r ? 'default' : 'outline'} size="sm" onClick={() => setRadius(r)}
                    className={cn('flex-1', radius === r && 'bg-orange-500 hover:bg-orange-600')}>{r} km</Button>
                ))}</div>
              </div>
            </div>
          </div>
        )}

        {/* Step 2: Template & Offer */}
        {stepIndex === 2 && (
          <div className="space-y-4">
            <h2 className="text-lg font-bold">Choose Template & Offer</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {templates.map(t => (
                <button key={t.template_id} onClick={() => setTemplateId(t.template_id)}
                  className={cn('p-4 rounded-xl border-2 text-left transition-all',
                    templateId === t.template_id ? 'border-orange-500 bg-orange-50 dark:bg-orange-950/20' : 'border-border hover:border-orange-200')}>
                  <div className="flex justify-between items-start">
                    <span className="font-semibold text-sm">{t.template_name}</span>
                    <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">CTR {t.expected_ctr_low}–{t.expected_ctr_high}%</span>
                  </div>
                  <p className="text-xs text-muted-foreground italic mt-1">"{t.hook_formula}"</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">{t.best_for}</p>
                </button>
              ))}
            </div>
            <div>
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Flat Discount (₹)</Label>
              <div className="flex gap-2 mt-1.5">{[50, 100, 150, 200, 300].map(a => (
                <Button key={a} variant={offer === a ? 'default' : 'outline'} size="sm" onClick={() => setOffer(a)}
                  className={cn('flex-1', offer === a && 'bg-orange-500 hover:bg-orange-600')}>₹{a}</Button>
              ))}</div>
            </div>
            {templates.find(t => t.template_id === templateId)?.requires_hero_dish && (
              <div>
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Hero Dish Name</Label>
                <Input value={heroDish} onChange={e => setHeroDish(e.target.value)} placeholder="e.g., Truffle Mushroom Risotto" className="mt-1.5" />
              </div>
            )}
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
                <div className="w-[320px] bg-background border-2 border-border rounded-[2.5rem] p-3 shadow-xl">
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
                    {imagePreview ? (
                      <div className="relative aspect-square bg-muted">
                        <img src={imagePreview} alt="Ad" className="w-full h-full object-cover" />
                        {/* AI overlay badge */}
                        <div className="absolute bottom-2 left-2 bg-black/70 backdrop-blur-sm text-white text-[9px] px-2 py-1 rounded-full flex items-center gap-1">
                          <Sparkles className="h-3 w-3" /> AI Enhanced
                        </div>
                        <button onClick={() => { setImagePreview(''); setAdImageUrl('') }}
                          className="absolute top-2 right-2 p-1 bg-black/60 rounded-full text-white hover:bg-black/80">
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                    ) : (
                      <div className="aspect-square bg-gradient-to-br from-orange-50 to-amber-50 dark:from-orange-950/20 dark:to-amber-950/20 flex flex-col items-center justify-center gap-2">
                        <div className="h-12 w-12 rounded-full bg-orange-100 dark:bg-orange-900/40 flex items-center justify-center">
                          <ImagePlus className="h-6 w-6 text-orange-500" />
                        </div>
                        <p className="text-xs font-medium text-muted-foreground">Select a photo below</p>
                        <p className="text-[10px] text-muted-foreground">AI will generate your ad</p>
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
                      <p className="text-[11px] leading-snug">{campaign.ad_primary_text}</p>
                      <p className="text-[11px] font-bold mt-1">{campaign.ad_headline}</p>
                      <div className="flex items-center gap-1.5 mt-1.5 p-1.5 bg-orange-50 dark:bg-orange-950/20 rounded-md border border-orange-200 dark:border-orange-800">
                        <Zap className="h-3 w-3 text-orange-500" />
                        <span className="text-[10px] font-semibold text-orange-600 flex-1">Get Offer</span>
                        <ChevronRight className="h-3 w-3 text-orange-400" />
                      </div>
                    </div>
                  </div>
                  {/* Phone bottom bar */}
                  <div className="w-20 h-1 bg-muted rounded-full mx-auto mt-2" />
                </div>
              </div>

              {/* Right Panel — Photo Selection + Actions */}
              <div className="flex-1 space-y-4 min-w-0">
                {/* Photo Gallery Picker */}
                <Card>
                  <CardHeader className="pb-2">
                    <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Select Food Photo</h3>
                    <p className="text-xs text-muted-foreground">Pick from your menu photos — AI will create the final ad creative</p>
                  </CardHeader>
                  <CardContent>
                    {existingMedia && existingMedia.length > 0 ? (
                      <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 max-h-56 overflow-y-auto">
                        {existingMedia.map((m: any, idx: number) => (
                          <button key={m.primary_url || idx} onClick={() => { setAdImageUrl(m.primary_url); setImagePreview(m.primary_url) }}
                            className={cn('aspect-square rounded-lg overflow-hidden border-2 transition-all',
                              imagePreview === m.primary_url ? 'border-orange-500 ring-2 ring-orange-500/20' : 'border-transparent hover:border-orange-300')}>
                            <img src={encodeURI(m.primary_url)} alt={m.alt_text || ''} className="w-full h-full object-cover" />
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="text-center py-8">
                        <ImagePlus className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
                        <p className="text-sm text-muted-foreground">No photos in your gallery yet</p>
                        <p className="text-xs text-muted-foreground mt-1">Upload food photos via Menu Management first</p>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Ad Copy */}
                <Card>
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
                <div className="text-xs text-muted-foreground bg-muted/50 rounded-lg p-3 space-y-1">
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
            <Card>
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
              <Card className="border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/20">
                <CardContent className="pt-3 pb-3 text-sm text-amber-700 dark:text-amber-300">
                  First campaign — estimated walk-ins (no guarantee yet). Guarantee unlocks from campaign #2.
                </CardContent>
              </Card>
            ) : campaign.guaranteed_redemptions > 0 ? (
              <Card className="border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/20">
                <CardContent className="pt-3 pb-3 text-sm text-emerald-700 dark:text-emerald-300">
                  Guaranteed: {campaign.guaranteed_redemptions}+ walk-ins or we top up your next campaign.
                </CardContent>
              </Card>
            ) : null}
          </div>
        )}
      </div>

      {/* Navigation Footer */}
      {!success && (
        <div className="flex items-center justify-between pt-4 border-t">
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
            <Button onClick={() => setStepIndex(4)} className="gap-2 bg-gradient-to-r from-orange-500 to-amber-600 text-white">
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
      )}

      {/* Gallery Dialog removed — photo picker is inline in Step 3 */}
    </div>
  )
}
