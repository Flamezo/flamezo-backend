/**
 * RouteKycPage — Set Up Direct Bank Payouts
 *
 * One-page onboarding flow for restaurant owners to connect their bank
 * account to Razorpay Route. Designed for non-technical owners:
 *   • Plain-language status ("Not started" / "We're checking your docs" /
 *     "Direct payouts active") with a concrete next-step line each time.
 *   • Two grouped sections — Business identity, then Bank — instead of one
 *     long form.
 *   • Inline format hints + real-time uppercase coercion for PAN/IFSC.
 *   • A "what happens next" card so owners understand WHY we need this data.
 *
 * Visual language mirrors AutopaySetupPage / Dashboard: max-w-5xl container,
 * fade-in animation, `shadow-sm border-none bg-card` section cards, hero
 * card with the blurred-radial accent and 12px square icon tile, tiny
 * uppercase widest-tracking section labels.
 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappeGetDoc, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import {
  ShieldCheck,
  Loader2,
  CircleCheckBig,
  Clock,
  AlertTriangle,
  XCircle,
  Building2,
  Landmark,
  Lock,
  ArrowRight,
  ArrowLeft,
  Download,
  Sparkles,
  UploadCloud,
  FileText
} from 'lucide-react'

const PAN_REGEX = /^[A-Z]{5}[0-9]{4}[A-Z]{1}$/
const IFSC_REGEX = /^[A-Z]{4}0[A-Z0-9]{6}$/

interface RestaurantDoc {
  name: string
  restaurant_name?: string
  legal_name?: string
  business_type?: string
  pan_number?: string
  bank_account_number?: string
  bank_ifsc?: string
  bank_holder_name?: string
  razorpay_account_id?: string
  razorpay_kyc_status?: '' | 'under_review' | 'needs_clarification' | 'activated' | 'suspended' | 'rejected'
  route_mode?: '' | 'flamezo_hold' | 'direct_split' | 'disabled'
  gst_number?: string
}

type FormFields = {
  legal_name: string
  business_type: string
  pan_number: string
  bank_account_number: string
  bank_ifsc: string
  bank_holder_name: string
}

const BUSINESS_TYPES: { value: string; label: string; hint: string }[] = [
  { value: 'proprietorship', label: 'Proprietorship', hint: 'Owned by a single person (most small restaurants)' },
  { value: 'partnership', label: 'Partnership', hint: '2 or more partners, no incorporation' },
  { value: 'llp', label: 'LLP', hint: 'Limited Liability Partnership' },
  { value: 'private_limited', label: 'Private Limited', hint: 'Pvt. Ltd. company' },
  { value: 'public_limited', label: 'Public Limited', hint: 'Listed / public company' },
  { value: 'individual', label: 'Individual', hint: 'No registered business entity yet' },
]

export default function RouteKycPage() {
  const navigate = useNavigate()
  const { selectedRestaurant, payments, refreshConfig } = useRestaurant()

  // Hydrate the form with whatever's already on the Restaurant doc so owners
  // can come back to edit / resubmit if Razorpay asks for clarification.
  const { data: restaurantDoc, mutate: reloadDoc, isLoading: docLoading } =
    useFrappeGetDoc<RestaurantDoc>('Restaurant', selectedRestaurant || '')

  const [form, setForm] = useState<FormFields>({
    legal_name: '',
    business_type: '',
    pan_number: '',
    bank_account_number: '',
    bank_ifsc: '',
    bank_holder_name: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [entryMode, setEntryMode] = useState<'upload' | 'manual'>('upload')
  const [analyzingImage, setAnalyzingImage] = useState(false)
  const [uploadedFileName, setUploadedFileName] = useState('')

  const { call: extractDetails } = useFrappePostCall<{ success: boolean; data: any }>('flamezo_backend.flamezo.api.kyc_ai.extract_bank_details')

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    
    setUploadedFileName(file.name)
    setAnalyzingImage(true)
    try {
      const reader = new FileReader()
      reader.onloadend = async () => {
        const base64_image = reader.result as string
        const res: any = await extractDetails({ base64_image })
        const data = res?.message ?? res
        if (data?.success && data?.data) {
          setForm(prev => ({
            ...prev,
            legal_name: data.data.legal_business_name || prev.legal_name,
            bank_account_number: data.data.account_number || prev.bank_account_number,
            bank_ifsc: data.data.ifsc_code || prev.bank_ifsc,
            bank_holder_name: data.data.legal_business_name || prev.bank_holder_name
          }))
          toast.success("Bank details extracted successfully!")
        } else {
          toast.error("Could not extract all details. Please verify and enter manually.")
        }
        setAnalyzingImage(false)
      }
      reader.readAsDataURL(file)
    } catch (err) {
      console.error(err)
      toast.error("Error processing image")
      setAnalyzingImage(false)
    }
  }

  // Sync server state into form once it loads.
  useEffect(() => {
    if (!restaurantDoc) return
    setForm({
      legal_name: restaurantDoc.legal_name || restaurantDoc.restaurant_name || '',
      business_type: restaurantDoc.business_type || '',
      pan_number: restaurantDoc.pan_number || '',
      bank_account_number: restaurantDoc.bank_account_number || '',
      bank_ifsc: restaurantDoc.bank_ifsc || '',
      bank_holder_name: restaurantDoc.bank_holder_name || '',
    })
  }, [restaurantDoc])

  const { call: submitKyc } = useFrappePostCall<{
    success: boolean
    error?: string
    missing_fields?: string[]
    linked_account_id?: string
    kyc_status?: string
    created?: boolean
  }>('flamezo_backend.flamezo.api.commission.submit_route_kyc')

  // Per-field validation. Returns null when valid, otherwise the error message.
  const fieldErrors = useMemo(() => {
    const errs: Partial<Record<keyof FormFields, string>> = {}
    if (form.legal_name && form.legal_name.trim().length < 3) errs.legal_name = 'Enter the full legal name'
    if (form.pan_number && !PAN_REGEX.test(form.pan_number)) errs.pan_number = 'PAN must be 10 characters like ABCDE1234F'
    if (form.bank_ifsc && !IFSC_REGEX.test(form.bank_ifsc)) errs.bank_ifsc = 'IFSC must be 11 characters like HDFC0001234'
    if (form.bank_account_number && !/^[0-9]{6,18}$/.test(form.bank_account_number)) errs.bank_account_number = 'Enter only the digits of your account number'
    if (form.bank_holder_name && form.bank_holder_name.trim().length < 3) errs.bank_holder_name = 'Enter the name as on the bank passbook'
    return errs
  }, [form])

  const isComplete =
    !!form.legal_name &&
    !!form.business_type &&
    !!form.pan_number &&
    !!form.bank_account_number &&
    !!form.bank_ifsc &&
    !!form.bank_holder_name &&
    Object.keys(fieldErrors).length === 0

  // Status: prefer the freshest value from RestaurantContext.payments (which
  // reads from get_restaurant_config and refreshes on save). Fall back to
  // the doc query while context is hydrating.
  const kycStatus =
    (payments?.razorpayKycStatus as string) ||
    (restaurantDoc?.razorpay_kyc_status as string) ||
    ''
  const linkedAccountId = restaurantDoc?.razorpay_account_id || ''

  const handleSubmit = async () => {
    if (!isComplete || submitting || !selectedRestaurant) return
    setSubmitting(true)
    try {
      const res = await submitKyc({
        restaurant_id: selectedRestaurant,
        legal_name: form.legal_name.trim(),
        business_type: form.business_type,
        pan_number: form.pan_number.trim().toUpperCase(),
        bank_account_number: form.bank_account_number.trim(),
        bank_ifsc: form.bank_ifsc.trim().toUpperCase(),
        bank_holder_name: form.bank_holder_name.trim(),
      })
      const data: any = (res as any)?.message ?? res
      if (data?.success) {
        toast.success(
          data.created
            ? 'Submitted! Razorpay is reviewing your details.'
            : 'Updated successfully.',
          { description: data.linked_account_id ? `Linked Account: ${data.linked_account_id}` : undefined }
        )
        await Promise.all([refreshConfig(), reloadDoc()])
      } else if (data?.error === 'incomplete_kyc') {
        toast.error('Some details are missing', { description: (data.missing_fields || []).join(', ') })
      } else {
        toast.error(data?.error || 'Could not submit. Please try again.')
      }
    } catch (e: any) {
      toast.error(e?.message || 'Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  // Plain-language status configuration. Each variant explains WHAT IT MEANS
  // and WHAT TO DO NEXT — no jargon.
  const statusVariant = (() => {
    if (kycStatus === 'activated') {
      return {
        icon: CircleCheckBig,
        iconBg: 'bg-emerald-500 text-white',
        accent: 'bg-emerald-500',
        title: 'Direct payouts are active',
        body: 'Customer payments now settle directly to your bank in T+2 business days. Flamezo automatically retains the Success Share — no manual reconciliation.',
        badge: { text: 'Active', cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
        nextStep: 'You can update bank details below if anything changes.',
        actionLabel: 'Update Details',
      }
    }
    if (kycStatus === 'under_review') {
      return {
        icon: Clock,
        iconBg: 'bg-blue-500 text-white',
        accent: 'bg-blue-500',
        title: 'Razorpay is reviewing your documents',
        body: "Typical review time is 1–3 business days. We'll activate direct payouts automatically the moment they verify — no action needed from you.",
        badge: { text: 'Under Review', cls: 'bg-blue-100 text-blue-700 border-blue-200' },
        nextStep: 'Until then, your customer payments are held safely by Flamezo and settled weekly via NEFT.',
        actionLabel: 'Update Details',
      }
    }
    if (kycStatus === 'needs_clarification') {
      return {
        icon: AlertTriangle,
        iconBg: 'bg-amber-500 text-white',
        accent: 'bg-amber-500',
        title: 'Razorpay needs more information',
        body: 'Check your registered email from Razorpay for the specific clarification request. Update the relevant fields below and re-submit.',
        badge: { text: 'Needs Clarification', cls: 'bg-amber-100 text-amber-800 border-amber-200' },
        nextStep: 'Fix the flagged details below and click "Re-submit" — Razorpay will pick it up automatically.',
        actionLabel: 'Re-submit Details',
      }
    }
    if (kycStatus === 'rejected') {
      return {
        icon: XCircle,
        iconBg: 'bg-rose-500 text-white',
        accent: 'bg-rose-500',
        title: 'Submission was rejected',
        body: 'Common reasons: PAN holder name doesn\'t match bank holder name, wrong IFSC, or business-type mismatch. Double-check and re-submit.',
        badge: { text: 'Rejected', cls: 'bg-rose-100 text-rose-700 border-rose-200' },
        nextStep: 'Make sure your PAN holder name and bank holder name match exactly. Then re-submit below.',
        actionLabel: 'Re-submit Details',
      }
    }
    if (kycStatus === 'suspended') {
      return {
        icon: Lock,
        iconBg: 'bg-rose-500 text-white',
        accent: 'bg-rose-500',
        title: 'Account temporarily suspended',
        body: 'Razorpay has paused direct payouts. Customer payments are being held by Flamezo and will be settled to you weekly while this is resolved.',
        badge: { text: 'Suspended', cls: 'bg-rose-100 text-rose-700 border-rose-200' },
        nextStep: 'Please contact Flamezo support — we\'ll help you resolve this with Razorpay.',
        actionLabel: 'Update Details',
      }
    }
    // Not started yet.
    return {
      icon: ShieldCheck,
      iconBg: 'bg-primary text-white',
      accent: 'bg-primary',
      title: 'Get paid directly to your bank',
      body: 'Today, Flamezo holds your customer payments and settles to you weekly. Submit your bank + PAN details below and Razorpay will start sending money to your account in T+2 business days — no manual chasing.',
      badge: { text: 'Not Started', cls: 'bg-stone-100 text-stone-700 border-stone-200' },
      nextStep: 'Takes ~3 minutes. Razorpay reviews your docs in 1–3 business days.',
      actionLabel: 'Submit for Verification',
    }
  })()

  const StatusIcon = statusVariant.icon

  return (
    <div className="max-w-5xl mx-auto space-y-8 pb-20 animate-in fade-in duration-500">
      {/* ── Page header ──────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div className="min-w-0">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(-1)}
            className="-ml-2 mb-2 h-7 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5 mr-1" />
            Back
          </Button>
          <h1 className="text-3xl font-black tracking-tight text-foreground">Direct Bank Payouts</h1>
          <p className="text-sm text-muted-foreground font-medium mt-1 max-w-2xl">
            Connect your bank account so customer payments settle to you directly — no more waiting for our weekly transfer.
          </p>
        </div>
        <Button
          variant="outline"
          className="gap-2 border-primary/20 text-primary hover:bg-primary/5 mt-2 md:mt-7 shrink-0"
          onClick={() => {
            // The backend serves the guide as a PDF via the `download_guide`
            // whitelisted endpoint. Opens in a new tab so the owner doesn't
            // lose their place in the form.
            window.open(
              '/api/method/flamezo_backend.flamezo.api.payments.download_guide?guide_name=Flamezo_Direct_Bank_Payouts_Guide',
              '_blank'
            )
          }}
          title="Download a PDF of this whole setup guide"
        >
          <Download className="h-4 w-4" />
          Download Guide
        </Button>
      </div>

      {/* ── Hero status card (mirrors AutopaySetupPage plan card) ── */}
      <Card className="border-none shadow-xl bg-card overflow-hidden ring-1 ring-border/50 relative">
        <div
          className={cn(
            'absolute -top-24 -right-24 w-48 h-48 blur-[80px] opacity-15 rounded-full',
            statusVariant.accent
          )}
          aria-hidden
        />
        <CardContent className="p-0 relative z-10">
          <div className="flex flex-col md:flex-row md:items-center md:divide-x md:divide-border/60">
            <div className="flex-1 p-5 flex items-center gap-4">
              <div
                className={cn(
                  'w-12 h-12 rounded-xl flex items-center justify-center shrink-0 shadow-md',
                  statusVariant.iconBg
                )}
              >
                <StatusIcon className="h-6 w-6" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                  <h3 className="text-xl font-black tracking-tight truncate">{statusVariant.title}</h3>
                  <Badge
                    variant="outline"
                    className={cn(
                      'px-2 py-0 text-[9px] font-black uppercase tracking-wider rounded-full h-4 shrink-0',
                      statusVariant.badge.cls
                    )}
                  >
                    {statusVariant.badge.text}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground font-medium max-w-prose">
                  {statusVariant.body}
                </p>
              </div>
            </div>

            <div className="p-5 flex flex-col justify-center min-w-[220px] w-full md:w-auto">
              <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">Next Step</p>
              <p className="text-xs font-medium leading-relaxed">{statusVariant.nextStep}</p>
              {linkedAccountId && (
                <p className="text-[10px] font-mono text-muted-foreground mt-2 truncate">
                  Linked Acct: {linkedAccountId}
                </p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Section 1: Business identity ─────────────────────────── */}
      <Card className="shadow-sm border-none bg-card overflow-hidden">
        <CardContent className="p-0">
          <div className="flex items-center gap-3 p-5 border-b border-border/40 bg-muted/20">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 bg-primary/10 text-primary">
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-0.5">Step 1 of 2</p>
              <h3 className="text-base font-black tracking-tight">Business Details</h3>
              <p className="text-xs text-muted-foreground font-medium">Information about your business as registered with the government.</p>
            </div>
          </div>

          <div className="p-5 space-y-5">
            <Field
              label="Legal Business Name"
              hint="Example: 'Sharma Restaurant' — must match your PAN card or registration certificate exactly."
              error={fieldErrors.legal_name}
            >
              <Input
                id="legal_name"
                placeholder="As on your PAN card"
                value={form.legal_name}
                onChange={(e) => setForm({ ...form, legal_name: e.target.value })}
                disabled={docLoading}
                className="h-11 rounded-xl"
              />
            </Field>

            <Field
              label="Business Type"
              hint="Most small restaurants are Proprietorship. Choose what's on your GST or company papers."
            >
              <Select
                value={form.business_type}
                onValueChange={(v) => setForm({ ...form, business_type: v })}
                disabled={docLoading}
              >
                <SelectTrigger id="business_type" className="h-11 rounded-xl">
                  <SelectValue placeholder="Choose your business type" />
                </SelectTrigger>
                <SelectContent>
                  {BUSINESS_TYPES.map(t => (
                    <SelectItem key={t.value} value={t.value}>
                      <div className="flex flex-col">
                        <span className="font-medium">{t.label}</span>
                        <span className="text-[11px] text-muted-foreground">{t.hint}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>

            <Field
              label="PAN Number"
              hint="10 characters — 5 letters, 4 numbers, 1 letter. Use the PAN of the business owner (for Proprietorship) or the company PAN."
              error={fieldErrors.pan_number}
            >
              <Input
                id="pan_number"
                placeholder="ABCDE1234F"
                maxLength={10}
                value={form.pan_number}
                onChange={(e) => setForm({ ...form, pan_number: e.target.value.toUpperCase() })}
                className="h-11 rounded-xl font-mono tracking-widest uppercase"
                disabled={docLoading}
              />
            </Field>
          </div>
        </CardContent>
      </Card>

      {/* ── Section 2: Bank details ──────────────────────────────── */}
      <Card className="shadow-sm border-none bg-card overflow-hidden">
        <CardContent className="p-0">
          <div className="flex items-center gap-3 p-5 border-b border-border/40 bg-muted/20">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 bg-primary/10 text-primary">
              <Landmark className="h-5 w-5" />
            </div>
            <div>
              <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-0.5">Step 2 of 2</p>
              <h3 className="text-base font-black tracking-tight">Bank Account</h3>
              <p className="text-xs text-muted-foreground font-medium">The account where customer payments will land.</p>
            </div>
          </div>

          <div className="p-5 space-y-5">
            <div className="flex bg-muted/50 p-1 rounded-xl w-full sm:w-fit">
              <button
                onClick={() => setEntryMode('upload')}
                className={cn('flex-1 sm:flex-none px-4 py-2 text-xs font-bold rounded-lg transition-colors flex items-center justify-center gap-2', entryMode === 'upload' ? 'bg-background shadow-sm text-primary ring-1 ring-black/5' : 'text-muted-foreground hover:text-foreground')}
              >
                <Sparkles className="h-3.5 w-3.5" />
                Auto-fill (Upload)
              </button>
              <button
                onClick={() => setEntryMode('manual')}
                className={cn('flex-1 sm:flex-none px-4 py-2 text-xs font-bold rounded-lg transition-colors flex items-center justify-center gap-2', entryMode === 'manual' ? 'bg-background shadow-sm text-foreground ring-1 ring-black/5' : 'text-muted-foreground hover:text-foreground')}
              >
                <FileText className="h-3.5 w-3.5" />
                Manual Entry
              </button>
            </div>

            {entryMode === 'upload' ? (
              <div className="border-2 border-dashed border-primary/20 bg-primary/5 rounded-xl p-8 flex flex-col items-center justify-center text-center transition-colors hover:border-primary/40 hover:bg-primary/10 relative overflow-hidden">
                <input
                  type="file"
                  accept="image/*"
                  onChange={handleImageUpload}
                  disabled={analyzingImage || docLoading}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed z-10"
                />
                {analyzingImage ? (
                  <>
                    <Loader2 className="h-8 w-8 animate-spin text-primary mb-3" />
                    <p className="text-sm font-bold text-foreground">Analyzing document with AI...</p>
                    <p className="text-[11px] text-muted-foreground mt-1">Extracting Account Number, IFSC, and Name</p>
                  </>
                ) : (
                  <>
                    <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary mb-3 shadow-inner">
                      <UploadCloud className="h-6 w-6" />
                    </div>
                    <p className="text-sm font-bold text-foreground">
                      {uploadedFileName ? 'Upload a different cheque' : 'Upload Cancelled Cheque'}
                    </p>
                    <p className="text-[11px] text-muted-foreground mt-1 max-w-[250px]">
                      {uploadedFileName ? `Last uploaded: ${uploadedFileName}` : 'We will use AI to automatically extract and fill your bank details to prevent typos.'}
                    </p>
                  </>
                )}
              </div>
            ) : null}

            <div className={cn("space-y-5 transition-all duration-500", entryMode === 'upload' ? 'opacity-90' : 'opacity-100')}>
              <Field
                label="Account Number"
              hint="Numbers only. Find it on your passbook or cheque book."
              error={fieldErrors.bank_account_number}
            >
              <Input
                id="bank_account_number"
                inputMode="numeric"
                placeholder="e.g. 50100123456789"
                value={form.bank_account_number}
                onChange={(e) => setForm({ ...form, bank_account_number: e.target.value.replace(/\D/g, '') })}
                className="h-11 rounded-xl font-mono"
                disabled={docLoading}
              />
            </Field>

            <Field
              label="IFSC Code"
              hint="11 characters — your bank's branch code. Printed on cheque leaves and in your bank's mobile app."
              error={fieldErrors.bank_ifsc}
            >
              <Input
                id="bank_ifsc"
                placeholder="HDFC0001234"
                maxLength={11}
                value={form.bank_ifsc}
                onChange={(e) => setForm({ ...form, bank_ifsc: e.target.value.toUpperCase() })}
                className="h-11 rounded-xl font-mono tracking-widest uppercase"
                disabled={docLoading}
              />
            </Field>

            <Field
              label="Account Holder Name"
              hint={
                <>
                  <strong className="text-amber-700">Important:</strong> this must match the PAN holder name above. Razorpay will reject the KYC if they differ.
                </>
              }
              error={fieldErrors.bank_holder_name}
            >
              <Input
                id="bank_holder_name"
                placeholder="As printed on the bank passbook"
                value={form.bank_holder_name}
                onChange={(e) => setForm({ ...form, bank_holder_name: e.target.value })}
                disabled={docLoading}
                className="h-11 rounded-xl"
              />
            </Field>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Submit row ───────────────────────────────────────────── */}
      <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3 sticky bottom-4 z-10">
        <Button
          variant="ghost"
          onClick={() => navigate(-1)}
          disabled={submitting}
          className="text-muted-foreground hover:text-foreground"
        >
          Cancel
        </Button>
        <div className="flex flex-col items-end gap-2 w-full sm:w-auto">
          {!isComplete && !docLoading && (
            <p className="text-[11px] text-muted-foreground">
              Fill all 6 fields correctly to enable the button.
            </p>
          )}
          <Button
            size="lg"
            onClick={handleSubmit}
            disabled={!isComplete || submitting || docLoading}
            className="w-full sm:w-auto min-w-[220px] h-12 rounded-xl bg-primary text-white hover:bg-primary/90 font-bold shadow-lg shadow-primary/20 gap-2"
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Submitting…
              </>
            ) : (
              <>
                {statusVariant.actionLabel}
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </Button>
        </div>
      </div>

      {/* ── "What happens next" explainer ─────────────────────────── */}
      <Card className="shadow-sm border-none bg-muted/30">
        <CardContent className="p-5">
          <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-3">After you submit</p>
          <div className="grid gap-4 md:grid-cols-3">
            <Step n="1" title="Razorpay verifies your documents" body="Takes 1–3 business days. They check PAN ↔ bank holder name match, business type, IFSC validity." />
            <Step n="2" title="Direct payouts get activated" body="The next customer payment automatically splits — your bank receives the merchant share, Flamezo keeps the Success Share." />
            <Step n="3" title="Money lands in T+2 days" body="Razorpay settles to your account in 2 business days. Track every payout in the Billing tab." />
          </div>
          <div className="flex items-start gap-2 pt-4 mt-4 border-t border-border/40 text-[11px] text-muted-foreground">
            <Lock className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <p>
              Your details are sent directly to Razorpay's encrypted KYC system. Flamezo never sees or stores your bank login or OTPs.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string
  hint?: React.ReactNode
  error?: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs font-bold uppercase tracking-wide text-foreground">{label}</Label>
      {children}
      {hint && !error && (
        <p className="text-[11px] text-muted-foreground font-medium leading-relaxed">{hint}</p>
      )}
      {error && (
        <p className="text-[11px] text-rose-600 font-medium">{error}</p>
      )}
    </div>
  )
}

function Step({ n, title, body }: { n: string; title: string; body: string }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <div className="h-6 w-6 rounded-lg bg-primary/10 text-primary text-xs font-black flex items-center justify-center shrink-0">
          {n}
        </div>
        <p className="text-xs font-black tracking-tight">{title}</p>
      </div>
      <p className="text-[11px] text-muted-foreground leading-relaxed pl-8">{body}</p>
    </div>
  )
}
