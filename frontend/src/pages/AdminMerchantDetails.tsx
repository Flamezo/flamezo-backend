import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useFrappePostCall, useFrappeGetCall, useFrappeAuth } from '@/lib/frappe'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { toast } from 'sonner'
import { getFrappeError, cn, copyToClipboard } from '@/lib/utils'
import { 
  Shield,
  ArrowLeft,
  RefreshCw,
  Settings,
  Coins,
  CreditCard,
  Info,
  Activity,
  Zap,
  ShieldAlert,
  UploadCloud,
  ExternalLink,
  Globe,
  User,
  ShieldCheck,
  Save,
  Undo2,
  ClipboardCopy,
  MessageSquare,
  Sparkles,
  Loader2,
  ImagePlus,
  Eye,
  EyeOff
} from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import MenuImageExtractorForm from '@/components/MenuImageExtractorForm'
import { UpdateSuccessShareModal } from '@/components/UpdateSuccessShareModal'
import { UpdateLimelightModal } from '@/components/UpdateLimelightModal'

interface Merchant {
  name: string
  restaurant_id: string
  restaurant_name: string
  owner_email?: string
  owner_phone?: string
  owner_name?: string
  onboarding_password?: string
  is_active: number
  is_featured: number
  is_signature: number
  coins_balance: number
  platform_fee_percent: number
  creation: string
  modified: string
  description?: string
  slug?: string
  subdomain?: string
  billing_status: string
  mandate_status: string
  razorpay_account_id?: string
  razorpay_kyc_status?: '' | 'under_review' | 'needs_clarification' | 'activated' | 'suspended' | 'rejected'
  // ── Razorpay Route hybrid state (May 2026) ──
  route_mode?: '' | 'flamezo_hold' | 'direct_split' | 'disabled'
  outstanding_commission_paise?: number
  cash_payments_disabled_until?: string | null
  cash_sweep_failure_count?: number
  last_cash_sweep_error?: string
  // ── Route KYC fields submitted by the merchant ──
  legal_name?: string
  business_type?: string
  pan_number?: string
  bank_account_number?: string
  bank_ifsc?: string
  bank_holder_name?: string
  enable_loyalty: number
  enable_dine_in: number
  tax_rate: number
  gst_number?: string
  total_revenue: number
  commission_earned: number
  total_orders: number
  timezone: string
  currency: string
  tables: number
  google_map_url?: string
  referral_code?: string
  referred_by_restaurant?: string
  branch_group?: string
}

function AdminMerchantDetailsPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  
  // States
  const [merchant, setMerchant] = useState<Merchant | null>(null)
  const [originalMerchant, setOriginalMerchant] = useState<Merchant | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [isMenuModalOpen, setIsMenuModalOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('overview')

  const [isRouteActionLoading, setIsRouteActionLoading] = useState(false)

  const [isOnboardModalOpen, setIsOnboardModalOpen] = useState(false)
  const [onboardName, setOnboardName] = useState('')
  const [onboardEmail, setOnboardEmail] = useState('')
  const [isOnboarding, setIsOnboarding] = useState(false)
  const [onboardResult, setOnboardResult] = useState<{message: string, generatedPassword?: string, emailSent: boolean} | null>(null)
  
  const [manualRechargeAmount, setManualRechargeAmount] = useState('')
  const [generatedRechargeLink, setGeneratedRechargeLink] = useState('')
  const [isGeneratingRecharge, setIsGeneratingRecharge] = useState(false)
  const [isLinkModalOpen, setIsLinkModalOpen] = useState(false)
  const [linkToCopy, setLinkToCopy] = useState('')

  // Opens the "Update Success Share?" prompt right after the Signature
  // switch is flipped. Confirming here stages platform_fee_percent into the
  // same local `merchant` draft as the toggle itself — both are saved
  // together (or discarded together) via the existing Save Changes flow,
  // so it never fires a second, separate API call on this page.
  const [showShareModal, setShowShareModal] = useState(false)
  const [shareModalBaseRate, setShareModalBaseRate] = useState(0)
  const [showLimelightModal, setShowLimelightModal] = useState(false)

  const [isAdmin, setIsAdmin] = useState(false)

  const { currentUser } = useFrappeAuth()
  
  useEffect(() => {
    if (!currentUser) return
    const win = window as any
    const userRoles: string[] = win.frappe?.boot?.user_roles || win.frappe?.boot?.user?.roles || win.frappe?.user_roles || []
    
    const isSupervisor = userRoles.includes('Flamezo Supervisor')
    const hasSystemManager = userRoles.includes('System Manager')
    const isRootAdmin = currentUser === 'Administrator'

    if (isRootAdmin || isSupervisor || hasSystemManager) {
      setIsAdmin(true)
    } else {
      setIsAdmin(false)
    }
  }, [currentUser])

  // Legacy Generation Clearance
  const win = window as any
  const userRoles: string[] = win.frappe?.boot?.user_roles || win.frappe?.boot?.user?.roles || win.frappe?.user_roles || []
  const hasSupervisorRole = userRoles.includes('Flamezo Supervisor')
  const hasSystemManager = userRoles.includes('System Manager')
  const isMainAdmin = currentUser === 'Administrator' || hasSystemManager
  const canGenerateLegacy = isMainAdmin || hasSupervisorRole

  const [isGeneratingLegacy, setIsGeneratingLegacy] = useState(false)
  const { call: generateLegacyContent } = useFrappePostCall(
    'flamezo_backend.flamezo.api.legacy.generate_legacy_content'
  )

  const [isGeneratingPhotos, setIsGeneratingPhotos] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const { call: generateBulkPhotos } = useFrappePostCall(
    'flamezo_backend.flamezo.api.admin.admin_generate_bulk_food_photos'
  )

  const handleGeneratePhotos = async () => {
    if (!id) return
    try {
      setIsGeneratingPhotos(true)
      const result = await generateBulkPhotos({ outlet_id: id }) as any
      if (result?.message?.success) {
        toast.success('Bulk photo generation started!', {
          description: 'Background worker is now generating Fal.ai photos for all products without media.'
        })
      } else {
        throw new Error(result?.message?.error || 'Generation failed')
      }
    } catch (error) {
      toast.error('Failed to start bulk generation', { description: getFrappeError(error) })
    } finally {
      setIsGeneratingPhotos(false)
    }
  }

  const handleGenerateLegacy = async () => {
    if (!id) return
    try {
      setIsGeneratingLegacy(true)
      const result = await generateLegacyContent({ outlet_id: id }) as any
      if (result?.message?.success) {
        toast.success('Legacy content successfully generated!', {
          description: 'A premium 10/10 story has been crafted for this merchant.'
        })
      } else {
        throw new Error(result?.message?.error?.message || 'Generation failed')
      }
    } catch (error) {
      toast.error('Failed to generate legacy content', { description: getFrappeError(error) })
    } finally {
      setIsGeneratingLegacy(false)
    }
  }

  // APIs
  const { call: getDetails } = useFrappePostCall<{ success: boolean, data: { restaurant: Merchant } }>(
    'flamezo_backend.flamezo.api.admin.get_outlet_details'
  )
  const { call: updateSettings } = useFrappePostCall<{ success: boolean, message?: string, error?: string }>(
    'flamezo_backend.flamezo.api.admin.admin_update_outlet_settings'
  )
  const { call: onboardOwner } = useFrappePostCall<{ success: boolean, message?: string, error?: string }>(
    'flamezo_backend.flamezo.api.admin.admin_onboard_outlet_owner'
  )
  const { call: createManualLink } = useFrappePostCall<{
    success: boolean,
    payment_link_url?: string,
    amount?: number,
    base_amount?: number,
    gst_amount?: number,
    error?: string
  }>('flamezo_backend.flamezo.api.admin.admin_create_manual_recharge_link')

  const { call: suspendLinkedAccount } = useFrappePostCall<{ success: boolean, error?: string }>(
    'flamezo_backend.flamezo.doctype.merchant.merchant.suspend_linked_account'
  )
  const { call: reactivateLinkedAccount } = useFrappePostCall<{ success: boolean, status?: string, error?: string }>(
    'flamezo_backend.flamezo.doctype.merchant.merchant.reactivate_linked_account'
  )
  
  const { data: platformSettingsData } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.admin.get_platform_settings',
    {},
    'platform-settings-details'
  )
  
  const platformSettings = platformSettingsData?.message?.data || {
    charge_gst: false,
    gst_percent: 18
  }

  const loadDetails = async () => {
    if (!id) return
    try {
      setLoading(true)
      const result = await getDetails({ outlet_id: id }) as any
      // Backend get_outlet_details returns data.restaurant (field name
      // intentionally left un-renamed); the page state is called `merchant`.
      if (result?.message?.data?.restaurant) {
        const data = result.message.data.restaurant
        setMerchant(data)
        setOriginalMerchant(data)
      }
    } catch (error) {
      toast.error('Failed to load merchant details', { description: getFrappeError(error) })
      navigate('/admin/merchants')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDetails()
  }, [id])

  // Detect changes
  const isDirty = useMemo(() => {
    if (!merchant || !originalMerchant) return false
    return JSON.stringify(merchant) !== JSON.stringify(originalMerchant)
  }, [merchant, originalMerchant])

  const handleSaveChanges = async () => {
    if (!id || !merchant || !originalMerchant) return
    
    // Find only changed fields
    const updates: Record<string, any> = {}
    Object.keys(merchant).forEach((key) => {
      const k = key as keyof Merchant
      if (merchant[k] !== originalMerchant[k]) {
        updates[k] = merchant[k]
      }
    })

    if (Object.keys(updates).length === 0) {
      toast.info('No changes to save')
      return
    }

    try {
      setSaving(true)
      const result = await updateSettings({
        outlet_id: id,
        updates
      }) as any
      if (result?.message?.success) {
        toast.success('Changes saved successfully')
        setOriginalMerchant(merchant)
      } else {
        throw new Error(result?.message?.error || 'Failed to save changes')
      }
    } catch (error) {
      toast.error('Failed to save changes', { description: getFrappeError(error) })
    } finally {
      setSaving(false)
    }
  }

  const handleDiscardChanges = () => {
    setMerchant(originalMerchant)
    toast.info('Changes discarded')
  }

  const handleOnboardOwner = async () => {
    if (!id || !onboardEmail) {
      toast.error('Email is required')
      return
    }
    try {
      setIsOnboarding(true)
      const result = await onboardOwner({
        outlet_id: id,
        owner_name: onboardName,
        owner_email: onboardEmail
      }) as any
      
      if (result?.message?.success) {
        const data = result.message.data
        const emailSent = data.email_sent
        const message = result.message.message
        const generatedPassword = data.generated_password
        
        setOnboardResult({message, generatedPassword, emailSent})
        
        if (emailSent) {
          toast.success(message)
          setIsOnboardModalOpen(false)
        } else {
          toast.warning("Access granted, but email delivery failed. Link generated for manual sharing.")
        }
        
        loadDetails()
      } else {
        throw new Error(result?.message?.error || 'Failed to onboard owner')
      }
    } catch (error) {
      toast.error('Failed to onboard owner', { description: getFrappeError(error) })
    } finally {
      setIsOnboarding(false)
    }
  }

  const openOnboardModal = () => {
    setOnboardName(merchant?.owner_name || '')
    setOnboardEmail(merchant?.owner_email || '')
    setOnboardResult(null)
    setIsOnboardModalOpen(true)
  }

  const handleCopyLink = (link: string) => {
    setLinkToCopy(link)
    setIsLinkModalOpen(true)
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString()
  }

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center p-6">
        <Card className="w-full max-w-md border-none shadow-2xl rounded-3xl overflow-hidden">
          <div className="bg-red-600 h-2" />
          <CardContent className="p-10 text-center">
            <div className="mx-auto w-20 h-20 bg-red-100 rounded-2xl flex items-center justify-center mb-8">
              <Shield className="h-10 w-10 text-red-600" />
            </div>
            <h2 className="text-3xl font-black tracking-tight mb-4">RESTRICTED ZONE</h2>
            <p className="text-muted-foreground leading-relaxed font-medium">
              You lack the administrative clearance required to access the central outlet control hub.
            </p>
            <Button onClick={() => navigate('/')} className="mt-8 rounded-xl px-10 h-12 font-bold uppercase tracking-widest text-xs">
              Return Home
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center space-y-4">
        <RefreshCw className="h-10 w-10 animate-spin text-primary opacity-20" />
        <p className="text-muted-foreground animate-pulse">Loading outlet intelligence...</p>
      </div>
    )
  }

  if (!merchant) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <Card className="w-full max-w-md border-destructive/20 shadow-lg">
          <CardContent className="p-8 text-center">
            <ShieldAlert className="h-12 w-12 text-destructive mx-auto mb-4" />
            <h2 className="text-2xl font-bold mb-2">Outlet Not Found</h2>
            <p className="text-muted-foreground mb-6">The requested outlet ID does not exist.</p>
            <Button onClick={() => navigate('/admin/merchants')}>Go Back</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background p-6 lg:p-10 pb-32">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex flex-col xl:flex-row xl:items-start justify-between gap-6 pb-2">
          <div className="space-y-4 flex-1 min-w-0">
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={() => navigate('/admin/merchants')}
              className="group -ml-2 text-muted-foreground hover:text-primary"
            >
              <ArrowLeft className="h-4 w-4 mr-2 group-hover:-translate-x-1 transition-transform" />
              Back to Fleet
            </Button>
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-3 mb-1">
                <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight break-words">{merchant.restaurant_name}</h1>
                <Badge 
                  variant={merchant.is_active ? 'default' : 'secondary'}
                  className={cn(
                    "px-3 py-0.5 text-xs font-bold uppercase tracking-wider shrink-0",
                    merchant.is_active ? "bg-green-500/10 text-green-600 border-green-200" : "bg-muted text-muted-foreground"
                  )}
                >
                  {merchant.is_active ? 'Live' : 'Inactive'}
                </Badge>
              </div>
              <div className="text-muted-foreground font-mono text-sm flex flex-wrap items-center gap-2">
                <span className="shrink-0">ID: {merchant.restaurant_id}</span>
                <Separator className="hidden sm:block h-3 w-px mx-1 bg-muted-foreground/30" /> 
                <span className="flex items-center gap-1.5 shrink-0"><Globe className="h-3 w-3" /> {merchant.subdomain || 'no-subdomain'}.flamezo.in</span>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 xl:pt-10 shrink-0">
            {canGenerateLegacy && (
              <>
                <Button 
                  onClick={handleGenerateLegacy}
                  disabled={isGeneratingLegacy}
                  className="bg-amber-500 hover:bg-amber-600 shadow-amber-500/20 shadow-lg gap-2 text-white"
                >
                  {isGeneratingLegacy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  Generate Legacy
                </Button>
                <Button 
                  onClick={handleGeneratePhotos}
                  disabled={isGeneratingPhotos}
                  className="bg-purple-600 hover:bg-purple-700 shadow-purple-500/20 shadow-lg gap-2 text-white"
                >
                  {isGeneratingPhotos ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
                  Generate Product Photo
                </Button>
              </>
            )}

             <Dialog open={isMenuModalOpen} onOpenChange={setIsMenuModalOpen}>
              <DialogTrigger asChild>
                <Button className="bg-indigo-600 hover:bg-indigo-700 shadow-indigo-500/20 shadow-lg gap-2">
                  <UploadCloud className="h-4 w-4" />
                  Upload Catalogue
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-4xl max-h-[90vh] overflow-y-auto p-0 gap-0 border-none shadow-2xl">
                <MenuImageExtractorForm 
                  outletId={merchant.name} 
                  outletName={merchant.restaurant_name}
                  onComplete={() => {
                      toast.success('Catalogue extraction complete!')
                  }}
                  onClose={() => setIsMenuModalOpen(false)}
                />
              </DialogContent>
            </Dialog>

            <Dialog open={isOnboardModalOpen} onOpenChange={(open) => {
              setIsOnboardModalOpen(open)
              if (!open) setOnboardResult(null)
            }}>
              <DialogContent className={onboardResult ? "max-w-md" : ""}>
                <DialogHeader>
                  <DialogTitle>{onboardResult ? "Onboarding Result" : "Onboard Outlet Owner"}</DialogTitle>
                  <DialogDescription>
                    {onboardResult 
                      ? "The owner has been successfully configured in the system."
                      : "Create a system user, assign the required roles, and generate a secure password."}
                  </DialogDescription>
                </DialogHeader>

                {onboardResult ? (
                  <div className="space-y-6 py-4">
                    <div className={cn(
                      "p-4 rounded-xl border flex items-start gap-3",
                      onboardResult.emailSent ? "bg-green-500/5 border-green-200 text-green-700" : "bg-orange-500/5 border-orange-200 text-orange-700"
                    )}>
                      {onboardResult.emailSent ? <ShieldCheck className="h-5 w-5 shrink-0" /> : <ShieldAlert className="h-5 w-5 shrink-0" />}
                      <p className="text-sm font-medium">{onboardResult.message}</p>
                    </div>

                    {onboardResult.generatedPassword && (
                      <div className="space-y-3">
                        <Label className="text-xs uppercase font-bold text-muted-foreground tracking-widest">Generated Credentials</Label>
                        <div className="flex gap-2">
                          <Input value={onboardResult.generatedPassword} readOnly className="font-mono text-sm bg-muted/30 font-bold" />
                          <Button 
                            variant="secondary" 
                            size="icon" 
                            onClick={() => handleCopyLink(onboardResult.generatedPassword!)}
                            title="Copy password"
                          >
                            <Save className="h-4 w-4" />
                          </Button>
                        </div>
                        <p className="text-[10px] text-muted-foreground leading-relaxed italic">
                          Send this password to the owner via WhatsApp or Email. It will allow them to log in to their dashboard.
                        </p>
                      </div>
                    )}

                    <div className="flex justify-end">
                      <Button onClick={() => setIsOnboardModalOpen(false)}>Done</Button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="space-y-4 py-4">
                      <div className="space-y-2">
                        <Label>Owner Name</Label>
                        <Input 
                          value={onboardName} 
                          onChange={(e) => setOnboardName(e.target.value)} 
                          placeholder="e.g. John Doe"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Owner Email (Required)</Label>
                        <Input 
                          type="email"
                          value={onboardEmail} 
                          onChange={(e) => setOnboardEmail(e.target.value)} 
                          placeholder="e.g. john@business.com"
                        />
                        <p className="text-xs text-muted-foreground mt-1">A secure welcome email with credentials will be dispatched to this address.</p>
                      </div>
                    </div>
                    <div className="flex justify-end gap-3">
                      <Button variant="outline" onClick={() => setIsOnboardModalOpen(false)}>Cancel</Button>
                      <Button onClick={handleOnboardOwner} disabled={isOnboarding || !onboardEmail}>
                        {isOnboarding ? <RefreshCw className="h-4 w-4 animate-spin mr-2" /> : <ShieldCheck className="h-4 w-4 mr-2" />}
                        Confirm Onboarding
                      </Button>
                    </div>
                  </>
                )}
              </DialogContent>
            </Dialog>


          </div>
        </div>

        {/* Global Stats Bar */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="bg-primary/5 border-primary/10 overflow-hidden relative">
            <div className="absolute right-[-10px] top-[-10px] opacity-10">
              <Zap className="h-24 w-24 text-primary" />
            </div>
            <CardContent className="p-5">
              <p className="text-[10px] uppercase font-bold tracking-widest text-primary/60 mb-1">Success Share</p>
              {(() => {
                // Platform Success Share rate that this merchant pays (legacy 1.5% vs new 3% vs custom).
                const rate = Number(merchant.platform_fee_percent ?? 0)
                const isLegacy = Math.abs(rate - 1.5) < 0.001
                return (
                  <div className="flex items-center gap-2">
                    <Shield className="h-4 w-4 text-primary" />
                    <span className="text-xl font-bold">{rate}%</span>
                    <Badge
                      variant="outline"
                      className={cn(
                        'px-1.5 py-0 text-[9px] font-black uppercase tracking-wider h-4',
                        isLegacy
                          ? 'bg-amber-50 text-amber-700 border-amber-200'
                          : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      )}
                    >
                      {isLegacy ? 'Legacy' : 'New'}
                    </Badge>
                  </div>
                )
              })()}
            </CardContent>
          </Card>
          
          <Card className="bg-green-500/5 border-green-500/10 overflow-hidden relative">
            <div className="absolute right-[-10px] top-[-10px] opacity-10">
              <Activity className="h-24 w-24 text-green-600" />
            </div>
            <CardContent className="p-5">
              <p className="text-[10px] uppercase font-bold tracking-widest text-green-600/60 mb-1">Revenue (Life)</p>
              <div className="flex items-center gap-2">
                <span className="text-xl font-bold">₹{merchant.total_revenue.toLocaleString()}</span>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-orange-500/5 border-orange-500/10 overflow-hidden relative">
            <div className="absolute right-[-10px] top-[-10px] opacity-10">
              <Coins className="h-24 w-24 text-orange-600" />
            </div>
            <CardContent className="p-5">
              <p className="text-[10px] uppercase font-bold tracking-widest text-orange-600/60 mb-1">Wallet Balance</p>
              <div className="flex items-center gap-2">
                <span className="text-xl font-bold">{merchant.coins_balance.toLocaleString()} Coins</span>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Main Configuration Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList className="bg-muted/50 p-1 rounded-xl h-auto flex flex-wrap gap-1">
            <TabsTrigger value="overview" className="rounded-lg px-4 py-2 gap-2 data-[state=active]:bg-background data-[state=active]:shadow-sm">
              <Info className="h-4 w-4" /> Overview
            </TabsTrigger>
            <TabsTrigger value="billing" className="rounded-lg px-4 py-2 gap-2 data-[state=active]:bg-background data-[state=active]:shadow-sm">
              <CreditCard className="h-4 w-4" /> Billing & Subs
            </TabsTrigger>
            <TabsTrigger value="coins" className="rounded-lg px-4 py-2 gap-2 data-[state=active]:bg-background data-[state=active]:shadow-sm">
              <Coins className="h-4 w-4" /> Coins & Wallet
            </TabsTrigger>

            <TabsTrigger value="operational" className="rounded-lg px-4 py-2 gap-2 data-[state=active]:bg-background data-[state=active]:shadow-sm">
              <Settings className="h-4 w-4" /> Ops Settings
            </TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle className="text-lg">Primary Identification</CardTitle>
                  <CardDescription>Core outlet identity and owner details</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-2">
                      <Label>Legal Business Name</Label>
                      <Input 
                        value={merchant.restaurant_name} 
                        onChange={(e) => setMerchant({...merchant, restaurant_name: e.target.value})}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Internal Slug / ID</Label>
                      <Input value={merchant.restaurant_id} disabled className="bg-muted/50 font-mono" />
                    </div>
                  </div>

                  <Separator />

                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
                        <User className="h-3.5 w-3.5" /> Ownership
                      </h3>
                      <Button size="sm" variant="outline" onClick={openOnboardModal} className="gap-2 border-primary/20 text-primary hover:bg-primary/5">
                        <ShieldCheck className="h-4 w-4" /> Onboard System Owner
                      </Button>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                      <div className="space-y-2">
                        <Label>Owner Name</Label>
                        <Input 
                          value={merchant.owner_name || ''} 
                          onChange={(e) => setMerchant({...merchant, owner_name: e.target.value})}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Owner Email</Label>
                        <Input 
                          value={merchant.owner_email || ''} 
                          onChange={(e) => setMerchant({...merchant, owner_email: e.target.value})}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Owner Phone</Label>
                        <Input 
                          value={merchant.owner_phone || ''} 
                          onChange={(e) => setMerchant({...merchant, owner_phone: e.target.value})}
                        />
                      </div>
                    </div>
                    <div className="mt-4 space-y-2">
                      <Label>Generated Password</Label>
                      <div className="flex items-center gap-2 max-w-sm">
                        <Input 
                          type={showPassword ? "text" : "password"}
                          value={merchant.onboarding_password || 'Onboarding is left'} 
                          readOnly
                          className="bg-muted text-muted-foreground font-mono"
                        />
                        {merchant.onboarding_password && (
                          <>
                            <Button variant="outline" size="icon" onClick={() => setShowPassword(!showPassword)}>
                              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                            </Button>
                            <Button variant="outline" size="icon" onClick={() => {
                              copyToClipboard(merchant.onboarding_password!);
                              toast.success('Password copied to clipboard!');
                            }}>
                              <ClipboardCopy className="h-4 w-4" />
                            </Button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                   <Separator />

                  <div className="space-y-4">
                    <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
                      <Globe className="h-3.5 w-3.5" /> Presence
                    </h3>
                    <div className="space-y-2">
                      <Label>Location Map URL</Label>
                      <div className="flex gap-2">
                        <Input 
                          value={merchant.google_map_url || ''} 
                          onChange={(e) => setMerchant({...merchant, google_map_url: e.target.value})}
                          placeholder="Google Maps URL"
                        />
                        <Button variant="outline" size="icon" onClick={() => window.open(merchant.google_map_url, '_blank')} disabled={!merchant.google_map_url}>
                          <ExternalLink className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label>Description</Label>
                      <Textarea 
                        value={merchant.description || ''} 
                        onChange={(e) => setMerchant({...merchant, description: e.target.value})}
                        rows={4}
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Status & Critical</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="flex items-center justify-between p-4 rounded-xl border bg-muted/20">
                    <div className="space-y-0.5">
                      <Label className="text-base">Active Status</Label>
                      <p className="text-xs text-muted-foreground">Toggle visibility of the outlet platform-wide</p>
                    </div>
                    <Switch
                      checked={!!merchant.is_active}
                      onCheckedChange={(checked) => setMerchant({...merchant, is_active: checked ? 1 : 0})}
                    />
                  </div>

                  <div className="flex items-center justify-between p-4 rounded-xl border bg-muted/20">
                    <div className="space-y-0.5">
                      <Label className="text-base">Featured</Label>
                      <p className="text-xs text-muted-foreground">Show in Hot Drops &amp; Limelight on the discover feed</p>
                    </div>
                    <Switch
                      checked={!!merchant.is_featured}
                      onCheckedChange={(checked) => {
                        if (checked) {
                          setMerchant({...merchant, is_featured: 1})
                          setShowLimelightModal(true)
                        } else {
                          setMerchant({...merchant, is_featured: 0, limelight_start_date: null, limelight_end_date: null})
                        }
                      }}
                    />
                  </div>

                  <div className="flex items-center justify-between p-4 rounded-xl border bg-muted/20">
                    <div className="space-y-0.5">
                      <Label className="text-base">Signature</Label>
                      <p className="text-xs text-muted-foreground">Flamezo curated — awarded for ambience, food &amp; value. Appears in the Signatures tab.</p>
                    </div>
                    <Switch
                      checked={!!merchant.is_signature}
                      onCheckedChange={(checked) => {
                        setShareModalBaseRate(Number(merchant.platform_fee_percent ?? 0))
                        setMerchant({...merchant, is_signature: checked ? 1 : 0})
                        setShowShareModal(true)
                      }}
                    />
                  </div>

                  <div className="space-y-4">
                     <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Admin Metadata</p>
                     <div className="space-y-3">
                        <div className="flex justify-between items-center text-sm">
                          <span className="text-muted-foreground">Created on</span>
                          <span className="font-medium">{formatDate(merchant.creation)}</span>
                        </div>
                        <div className="flex justify-between items-center text-sm">
                          <span className="text-muted-foreground">Last modified</span>
                          <span className="font-medium">{formatDate(merchant.modified)}</span>
                        </div>
                        <div className="flex justify-between items-center text-sm">
                          <span className="text-muted-foreground">Success Share Rate</span>
                          <Badge variant="outline" className="text-primary border-primary/20">{merchant.platform_fee_percent}%</Badge>
                        </div>
                     </div>
                  </div>

                  <div className="space-y-4 pt-4">
                    <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
                       <Zap className="h-3 w-3" /> Refer & Earn
                    </p>
                    <div className="space-y-3">
                       <div className="space-y-1.5">
                         <Label className="text-[10px] uppercase font-bold text-muted-foreground/60">Own Referral Code</Label>
                         <div className="flex gap-2">
                           <Input value={merchant.referral_code || ''} readOnly className="h-8 bg-muted/30 font-mono text-xs" />
                           <Button 
                             variant="outline" 
                             size="sm" 
                             onClick={async () => {
                               if (merchant.referral_code) {
                                 const success = await copyToClipboard(merchant.referral_code)
                                 if (success) toast.success('Code copied')
                               }
                             }}
                             className="h-8 px-2"
                           >
                             <Save className="h-3.5 w-3.5" />
                           </Button>
                         </div>
                       </div>
                       <div className="space-y-1.5">
                         <Label className="text-[10px] uppercase font-bold text-muted-foreground/60">Referred By (Merchant ID)</Label>
                         <Input 
                           value={merchant.referred_by_restaurant || ''} 
                           onChange={(e) => setMerchant({...merchant, referred_by_restaurant: e.target.value})}
                           placeholder="e.g. the-food-court"
                           className="h-8 text-xs font-mono"
                         />
                       </div>
                    </div>
                  </div>

                  <Separator />

                  <div className="p-4 rounded-xl border border-destructive/10 bg-destructive/5 space-y-3">
                    <div className="flex items-center gap-2 text-destructive">
                      <ShieldAlert className="h-4 w-4" />
                      <span className="text-sm font-bold">Admin Zone</span>
                    </div>
                    <p className="text-[10px] text-muted-foreground leading-relaxed">
                      Changes here affect the billing engine and merchant access. Exercise caution.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Billing Tab */}
          <TabsContent value="billing">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* ── Plan & Billing (left) ── */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Plan & Billing</CardTitle>
                  <CardDescription>Success Share rate and admin billing state</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="space-y-2">
                    <Label>Success Share (%)</Label>
                    <NumberInput
                      value={merchant.platform_fee_percent}
                      onChange={(e) => setMerchant({...merchant, platform_fee_percent: parseFloat(e.target.value)})}
                    />
                    <p className="text-[11px] text-muted-foreground">
                      Default 3% for new merchants, 1.5% grandfathered.
                    </p>
                  </div>

                  <Separator />

                  <div className="space-y-3">
                    <Label className="text-xs uppercase font-bold tracking-widest text-muted-foreground">Admin Billing Status</Label>
                    <Select
                      value={merchant.billing_status}
                      onValueChange={(v) => setMerchant({...merchant, billing_status: v})}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="active">Active & Good Standing</SelectItem>
                        <SelectItem value="overdue">Overdue - Warning</SelectItem>
                        <SelectItem value="suspended">Suspended - Locked</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </CardContent>
              </Card>

              {/* ── Payment Route & KYC (right) ── */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Payment Route & KYC</CardTitle>
                  <CardDescription>Razorpay Route settlement state + autopay mandate</CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
                  {/* Settlement Mode + KYC Status — the two most important
                      signals at a glance. */}
                  {(() => {
                    const routeMode = merchant.route_mode || 'flamezo_hold'
                    const kycStatus = merchant.razorpay_kyc_status || ''
                    const routeMap: Record<string, { label: string; cls: string; hint: string }> = {
                      direct_split: { label: 'Direct Split', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', hint: 'Payments split at capture; merchant gets bulk in T+2.' },
                      flamezo_hold: { label: 'Flamezo Hold', cls: 'bg-stone-50 text-stone-700 border-stone-200', hint: 'Payments land in Flamezo; weekly NEFT to merchant.' },
                      disabled: { label: 'Disabled', cls: 'bg-rose-50 text-rose-700 border-rose-200', hint: 'Compliance pause. Customer payments blocked.' },
                    }
                    const r = routeMap[routeMode] || routeMap.flamezo_hold
                    const kycMap: Record<string, { label: string; cls: string }> = {
                      activated: { label: 'Activated', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
                      under_review: { label: 'Under Review', cls: 'bg-blue-50 text-blue-700 border-blue-200' },
                      needs_clarification: { label: 'Needs Info', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
                      rejected: { label: 'Rejected', cls: 'bg-rose-50 text-rose-700 border-rose-200' },
                      suspended: { label: 'Suspended', cls: 'bg-rose-50 text-rose-700 border-rose-200' },
                    }
                    const k = kycMap[kycStatus] || { label: 'Not Started', cls: 'bg-stone-50 text-stone-600 border-stone-200' }
                    return (
                      <div className="grid grid-cols-2 gap-3">
                        <div className="p-3 rounded-xl border bg-muted/20 space-y-1">
                          <p className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground">Settlement Mode</p>
                          <Badge variant="outline" className={cn('font-bold', r.cls)}>{r.label}</Badge>
                          <p className="text-[10px] text-muted-foreground leading-snug">{r.hint}</p>
                        </div>
                        <div className="p-3 rounded-xl border bg-muted/20 space-y-1">
                          <p className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground">KYC Status</p>
                          <Badge variant="outline" className={cn('font-bold', k.cls)}>{k.label}</Badge>
                          <p className="text-[10px] text-muted-foreground leading-snug">
                            {kycStatus === 'activated' ? 'Direct payouts live.'
                              : kycStatus === 'under_review' ? 'Razorpay reviewing 1–3 days.'
                              : kycStatus === 'needs_clarification' ? 'Owner action required.'
                              : kycStatus === 'rejected' ? 'Resubmit corrected details.'
                              : kycStatus === 'suspended' ? 'Razorpay-side pause.'
                              : 'Merchant has not submitted KYC.'}
                          </p>
                        </div>
                      </div>
                    )
                  })()}

                  {/* Razorpay Linked Account ID — read-only audit field. */}
                  <div className="space-y-2">
                    <Label>Razorpay Linked Account ID</Label>
                    <Input
                      value={merchant.razorpay_account_id || ''}
                      disabled
                      className="bg-muted/50 font-mono text-xs"
                      placeholder="— Not created yet —"
                    />
                    {merchant.razorpay_account_id && (() => {
                      const isSuspended = merchant.razorpay_kyc_status === 'suspended'
                      return (
                        <Button
                          size="sm"
                          variant={isSuspended ? 'outline' : 'destructive'}
                          className={isSuspended ? 'border-emerald-300 text-emerald-700 hover:bg-emerald-50' : ''}
                          disabled={isRouteActionLoading}
                          onClick={async () => {
                            const action = isSuspended ? 'reactivate' : 'suspend'
                            const confirmed = window.confirm(
                              isSuspended
                                ? `Reactivate linked account ${merchant.razorpay_account_id} for ${merchant.restaurant_name}?`
                                : `Suspend linked account ${merchant.razorpay_account_id} for ${merchant.restaurant_name}? No Route transfers will go to this merchant until reactivated.`
                            )
                            if (!confirmed) return
                            setIsRouteActionLoading(true)
                            try {
                              const result = isSuspended
                                ? await reactivateLinkedAccount({ merchant: merchant.name }) as any
                                : await suspendLinkedAccount({ merchant: merchant.name }) as any
                              const res = result?.message
                              if (res?.success) {
                                toast.success(isSuspended ? 'Linked account reactivated' : 'Linked account suspended')
                                await loadDetails()
                              } else {
                                toast.error(res?.error || `Failed to ${action} account`)
                              }
                            } catch (e: any) {
                              toast.error(getFrappeError(e) || `Failed to ${action} account`)
                            } finally {
                              setIsRouteActionLoading(false)
                            }
                          }}
                        >
                          {isRouteActionLoading
                            ? (isSuspended ? 'Reactivating…' : 'Suspending…')
                            : (isSuspended ? 'Reactivate Linked Account' : 'Suspend Linked Account')}
                        </Button>
                      )
                    })()}
                  </div>

                  {/* Autopay Mandate — for monthly billing + cash sweep. */}
                  <div className="p-3 rounded-xl border bg-muted/20 space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs uppercase font-bold tracking-widest text-muted-foreground">Autopay Mandate</Label>
                      <Badge
                        variant={merchant.mandate_status === 'active' ? 'default' : 'destructive'}
                        className={merchant.mandate_status === 'active' ? 'bg-emerald-500/10 text-emerald-600 border-emerald-200' : 'text-white'}
                      >
                        {merchant.mandate_status ? merchant.mandate_status.toUpperCase() : 'INACTIVE'}
                      </Badge>
                    </div>
                    <p className="text-[10px] text-muted-foreground leading-snug">
                      Used for cash Success Share sweeps (Tier 2).
                    </p>
                  </div>

                  {/* Outstanding cash Success Share — admin-visible debt. */}
                  {(() => {
                    const outstandingPaise = Number(merchant.outstanding_commission_paise || 0)
                    const throttledUntil = merchant.cash_payments_disabled_until
                    const isThrottled = throttledUntil
                      ? new Date(throttledUntil) >= new Date(new Date().toDateString())
                      : false
                    const failureCount = Number(merchant.cash_sweep_failure_count || 0)
                    if (outstandingPaise === 0 && !isThrottled && failureCount === 0) return null
                    return (
                      <div className={cn(
                        'p-3 rounded-xl border space-y-2',
                        isThrottled ? 'border-rose-200 bg-rose-50/40' : 'border-amber-200 bg-amber-50/40'
                      )}>
                        <div className="flex items-center justify-between">
                          <Label className="text-xs uppercase font-bold tracking-widest text-muted-foreground flex items-center gap-1">
                            <ShieldAlert className={cn('h-3 w-3', isThrottled ? 'text-rose-600' : 'text-amber-600')} />
                            Cash Success Share Engine
                          </Label>
                          {isThrottled && (
                            <Badge variant="outline" className="bg-rose-100 text-rose-700 border-rose-200 text-[10px] font-black uppercase tracking-wider h-4 px-1.5">Throttled</Badge>
                          )}
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground">Outstanding</span>
                          <span className={cn('font-mono font-bold', outstandingPaise > 0 ? 'text-amber-700' : 'text-muted-foreground')}>
                            ₹{(outstandingPaise / 100).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                          </span>
                        </div>
                        {failureCount > 0 && (
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-muted-foreground">Sweep Failures</span>
                            <span className="font-mono font-bold text-rose-700">{failureCount}</span>
                          </div>
                        )}
                        {isThrottled && throttledUntil && (
                          <p className="text-[10px] text-rose-700/80 leading-snug">
                            Cash payments disabled until <span className="font-bold">{throttledUntil}</span> to drain debt via online net-off.
                          </p>
                        )}
                        {merchant.last_cash_sweep_error && (
                          <p className="text-[10px] text-muted-foreground leading-snug truncate" title={merchant.last_cash_sweep_error}>
                            Last error: <span className="font-mono">{merchant.last_cash_sweep_error}</span>
                          </p>
                        )}
                      </div>
                    )
                  })()}

                  {/* Submitted KYC details — only show if any field is on file. */}
                  {(merchant.legal_name || merchant.pan_number || merchant.bank_ifsc) && (
                    <div className="space-y-3">
                      <Label className="text-xs uppercase font-bold tracking-widest text-muted-foreground">Submitted KYC Details</Label>
                      <div className="rounded-xl border divide-y divide-border/40 text-xs">
                        <KycRow label="Legal Name" value={merchant.legal_name} />
                        <KycRow label="Business Type" value={merchant.business_type} mono={false} />
                        <KycRow label="PAN" value={merchant.pan_number} mask={(v) => maskPan(v)} />
                        <KycRow label="Bank Account" value={merchant.bank_account_number} mask={(v) => maskAccount(v)} />
                        <KycRow label="IFSC" value={merchant.bank_ifsc} />
                        <KycRow label="Account Holder" value={merchant.bank_holder_name} mono={false} />
                      </div>
                    </div>
                  )}

                  <Separator />

                  <div className="bg-indigo-500/5 border border-indigo-200/50 p-4 rounded-xl">
                    <p className="text-xs font-bold text-indigo-700 mb-1 flex items-center gap-1.5 uppercase tracking-tighter">
                      <ShieldAlert className="h-3 w-3" /> Success Share Reconciliation
                    </p>
                    <p className="text-[10px] text-indigo-600/80 leading-relaxed">
                      Total Success Share earned from this outlet: <span className="font-bold">₹{(merchant.commission_earned || 0).toLocaleString()}</span>.
                      Reconciled every 24 hours.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Coins Tab */}
          <TabsContent value="coins">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Card className="md:col-span-1 border-orange-200 bg-orange-50/5">
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Coins className="h-5 w-5 text-orange-500" />
                    Wallet Management
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="text-center py-6 bg-orange-500/10 rounded-2xl border border-orange-200">
                    <p className="text-sm text-orange-600 font-bold uppercase tracking-wider mb-2">Current Balance</p>
                    <h2 className="text-5xl font-black text-orange-700">{merchant.coins_balance.toLocaleString()}</h2>
                    <p className="text-[10px] text-orange-600/60 mt-1">Flamezo Coins (1 Coin = ₹1)</p>
                  </div>

                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-4 rounded-xl border bg-background">
                      <div className="space-y-0.5">
                        <Label className="text-base">Auto-Recharge</Label>
                        <p className="text-xs text-muted-foreground">Enabled via Razorpay Mandate</p>
                      </div>
                      <Switch 
                         checked={false} 
                         disabled
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Economics & Consumption</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                   <div className="grid grid-cols-2 gap-4">
                      <div className="p-4 rounded-xl border bg-muted/20">
                         <p className="text-[10px] uppercase font-bold text-muted-foreground mb-1">Total Refilled</p>
                         <p className="text-lg font-bold">₹{(merchant.total_revenue || 0).toLocaleString()}</p>
                      </div>
                      <div className="p-4 rounded-xl border bg-muted/20">
                         <p className="text-[10px] uppercase font-bold text-muted-foreground mb-1">Avg Consump.</p>
                         <p className="text-lg font-bold">14/day</p>
                      </div>
                   </div>
                   
                   <Separator />
                   
                   <div className="space-y-4">
                      <h4 className="text-sm font-bold">Coin Utility Policy</h4>
                      <ul className="text-xs space-y-2 text-muted-foreground list-disc pl-4">
                        <li>AI Product Photo Enhancement: 5 Coins</li>
                        <li>AI Image Generation: 10 Coins</li>
                        <li>SMS/WhatsApp Automation: ~1 Coin/unit</li>
                        <li>Digital Catalogue Customizations (Premium Themes)</li>
                      </ul>
                   </div>
                </CardContent>
              </Card>

              <Card className="md:col-span-1">
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <CreditCard className="h-5 w-5 text-primary" />
                    Manual Recharge Link
                  </CardTitle>
                  <CardDescription>Generate a one-time payment link {platformSettings.charge_gst ? `with ${platformSettings.gst_percent}% GST included` : 'without GST'}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <Label>Base Amount (₹)</Label>
                      <div className="flex gap-2">
                        <NumberInput 
                          
                          placeholder="e.g. 1000"
                          value={manualRechargeAmount}
                          onChange={(e) => {
                            setManualRechargeAmount(e.target.value)
                            setGeneratedRechargeLink('') // Reset link when amount changes
                          }}
                          className="font-bold text-lg"
                        />
                        <Button 
                          onClick={async () => {
                            if (!manualRechargeAmount || parseFloat(manualRechargeAmount) <= 0) {
                              toast.error('Please enter a valid amount')
                              return
                            }
                            try {
                              setIsGeneratingRecharge(true)
                              const res = await createManualLink({
                                outlet_id: id,
                                amount: manualRechargeAmount
                              }) as any
                              if (res?.message?.success) {
                                setGeneratedRechargeLink(res.message.payment_link_url)
                                toast.success('Recharge link generated!')
                              } else {
                                throw new Error(res?.message?.error || 'Generation failed')
                              }
                            } catch (err: any) {
                              toast.error('Failed to generate link', { description: err.message })
                            } finally {
                              setIsGeneratingRecharge(false)
                            }
                          }}
                          disabled={isGeneratingRecharge || !manualRechargeAmount}
                          className="bg-primary hover:bg-primary/90"
                        >
                          {isGeneratingRecharge ? <RefreshCw className="h-4 w-4 animate-spin mr-2" /> : <Zap className="h-4 w-4 mr-2" />}
                          Generate Link
                        </Button>
                      </div>
                    </div>

                    {manualRechargeAmount && parseFloat(manualRechargeAmount) > 0 && (
                      <div className="p-4 rounded-xl border bg-primary/5 space-y-2 border-primary/20">
                        <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">Base Credit:</span>
                          <span className="font-bold">₹{parseFloat(manualRechargeAmount).toLocaleString()}</span>
                        </div>
                        {platformSettings.charge_gst && (
                          <div className="flex justify-between text-sm">
                            <span className="text-muted-foreground">GST ({platformSettings.gst_percent}%):</span>
                            <span className="font-bold">₹{(parseFloat(manualRechargeAmount) * (platformSettings.gst_percent / 100)).toLocaleString()}</span>
                          </div>
                        )}
                        <Separator className="bg-primary/20" />
                        <div className="flex justify-between text-base">
                          <span className="font-bold text-primary">Total Payable:</span>
                          <span className="font-black text-primary text-lg">₹{(parseFloat(manualRechargeAmount) * (1 + (platformSettings.charge_gst ? platformSettings.gst_percent / 100 : 0))).toLocaleString()}</span>
                        </div>
                      </div>
                    )}

                    {generatedRechargeLink && (
                      <div className="space-y-3 animate-in fade-in slide-in-from-top-2 duration-300">
                        <Label className="text-[10px] uppercase font-bold text-muted-foreground tracking-widest">Payment Link Ready</Label>
                        <div className="flex gap-2">
                          <Input value={generatedRechargeLink} readOnly className="font-mono text-[10px] bg-muted/30" />
                          <Button 
                            variant="secondary" 
                            size="icon" 
                            className="shrink-0"
                            onClick={async () => {
                              const success = await copyToClipboard(generatedRechargeLink)
                              if (success) toast.success('Link copied to clipboard')
                            }}
                            title="Copy Link"
                          >
                            <ClipboardCopy className="h-4 w-4" />
                          </Button>
                          <Button 
                            variant="secondary" 
                            size="icon" 
                            className="shrink-0 bg-primary/10 hover:bg-primary/20 text-primary border-primary/20"
                            onClick={async () => {
                              const msg = `Hi ${merchant.owner_name || merchant.restaurant_name}, please use this link to top-up your Flamezo wallet with ₹${parseFloat(manualRechargeAmount).toLocaleString()}: ${generatedRechargeLink}\n\nCredits will reflect in your account automatically after payment. Thanks!`
                              const success = await copyToClipboard(msg)
                              if (success) toast.success('Recharge message copied!')
                            }}
                            title="Copy Professional Message"
                          >
                            <MessageSquare className="h-4 w-4" />
                          </Button>
                        </div>
                        <p className="text-[10px] text-muted-foreground italic">
                          Share the link or the full message with {merchant.owner_name || 'the customer'}.
                        </p>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>



          {/* Operational Tab */}
          <TabsContent value="operational">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
               <Card className="lg:col-span-2">
                  <CardHeader>
                    <CardTitle className="text-lg">Core Fulfillment Settings</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                        <div className="flex flex-col items-center gap-3 p-4 rounded-xl border md:col-span-1">
                           <Label className="text-[10px] uppercase font-bold opacity-50">Dine-In</Label>
                           <Switch checked={!!merchant.enable_dine_in} onCheckedChange={(v) => setMerchant({...merchant, enable_dine_in: v ? 1 : 0})} />
                        </div>
                        <div className="flex flex-col items-center gap-3 p-4 rounded-xl border md:col-span-1">
                           <Label className="text-[10px] uppercase font-bold opacity-50">Loyalty</Label>
                           <Switch checked={!!merchant.enable_loyalty} onCheckedChange={(v) => setMerchant({...merchant, enable_loyalty: v ? 1 : 0})} />
                        </div>
                    </div>

                    <Separator />

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                       <div className="space-y-2">
                          <Label>Currency</Label>
                          <Input value={merchant.currency} disabled className="bg-muted/50" />
                       </div>
                       <div className="space-y-2">
                          <Label>Tax Rate (%)</Label>
                          <NumberInput 
                            
                            value={merchant.tax_rate} 
                            onChange={(e) => setMerchant({...merchant, tax_rate: parseFloat(e.target.value)})}
                          />
                       </div>
                       <div className="space-y-2">
                          <Label>Timezone</Label>
                          <Input value={merchant.timezone} disabled className="bg-muted/50" />
                       </div>
                    </div>

                  </CardContent>
               </Card>

               <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Physical Footprint</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-6">
                     <div className="space-y-4">
                        <div className="p-4 rounded-xl border bg-muted/20 flex items-center justify-between">
                           <div>
                              <p className="text-sm font-bold">Tables Count</p>
                              <p className="text-[10px] text-muted-foreground uppercase">Triggers QR Generation</p>
                           </div>
                           <h2 className="text-2xl font-black">{merchant.tables}</h2>
                        </div>
                        <div className="space-y-2">
                          <Label>Update Tables</Label>
                          <NumberInput 
                             
                             value={merchant.tables} 
                             onChange={(e) => setMerchant({...merchant, tables: parseInt(e.target.value)})}
                          />
                        </div>
                     </div>

                     <Separator />

                     <div className="space-y-2">
                        <Label>GST Identification</Label>
                        <Input 
                          value={merchant.gst_number || ''} 
                          onChange={(e) => setMerchant({...merchant, gst_number: e.target.value})}
                          placeholder="GSTIN"
                        />
                     </div>
                  </CardContent>
               </Card>
            </div>
          </TabsContent>
        </Tabs>
      </div>

      {/* Floating Save Bar */}
      {isDirty && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-in fade-in slide-in-from-bottom-4 duration-300">
          <div className="bg-background/80 backdrop-blur-md border border-primary/20 shadow-2xl rounded-full px-6 py-3 flex items-center gap-6 ring-1 ring-black/5">
            <div className="flex flex-col">
              <span className="text-xs font-bold text-primary flex items-center gap-1.5 leading-none">
                <Info className="h-3 w-3" />
                Unsaved Changes
              </span>
              <span className="text-[10px] text-muted-foreground leading-none mt-1">
                Multiple modifications detected
              </span>
            </div>
            
            <div className="flex items-center gap-2">
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={handleDiscardChanges}
                disabled={saving}
                className="rounded-full gap-2 text-muted-foreground hover:text-foreground"
              >
                <Undo2 className="h-4 w-4" />
                Discard
              </Button>
              <Button 
                size="sm" 
                onClick={handleSaveChanges}
                disabled={saving}
                className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg px-6 gap-2"
              >
                {saving ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
                Save Changes
              </Button>
            </div>
          </div>
        </div>
      )}
      <UpdateSuccessShareModal
        open={showShareModal}
        onOpenChange={setShowShareModal}
        merchantName={merchant.restaurant_name}
        currentRate={shareModalBaseRate}
        onConfirm={(newRate) => {
          setMerchant({ ...merchant, platform_fee_percent: newRate })
          setShowShareModal(false)
        }}
      />

      <UpdateLimelightModal
        open={showLimelightModal}
        onOpenChange={(open) => {
          setShowLimelightModal(open)
          if (!open && !merchant.limelight_start_date) {
            // Revert switch if they cancel out of the modal without confirming dates
            setMerchant(prev => ({...prev, is_featured: 0}))
          }
        }}
        merchantName={merchant.restaurant_name}
        onConfirm={(startDate, endDate) => {
          setMerchant({ 
            ...merchant, 
            is_featured: 1,
            limelight_start_date: startDate,
            limelight_end_date: endDate
          })
          setShowLimelightModal(false)
        }}
      />

      <Dialog open={isLinkModalOpen} onOpenChange={setIsLinkModalOpen}>
        <DialogContent className="sm:max-w-md p-6 rounded-2xl">
          <DialogHeader>
            <DialogTitle>Share Link</DialogTitle>
            <DialogDescription>
              Copy and share this link manualy if automatic sharing fails.
            </DialogDescription>
          </DialogHeader>
          <div className="flex items-center space-x-2 mt-4">
            <div className="grid flex-1 gap-2">
              <Label htmlFor="link" className="sr-only">
                Link
              </Label>
              <Input
                id="link"
                readOnly
                value={linkToCopy}
                className="h-9 font-mono text-xs bg-muted/50"
              />
            </div>
            <Button 
              size="sm" 
              className="px-3"
              onClick={async () => {
                const success = await copyToClipboard(linkToCopy)
                if (success) {
                  toast.success('Copied!')
                }
              }}
            >
              <span className="sr-only">Copy</span>
              <ClipboardCopy className="h-4 w-4" />
            </Button>
          </div>
          <DialogFooter className="sm:justify-start mt-6">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsLinkModalOpen(false)}
              className="rounded-xl"
            >
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Helpers for the Payment Route & KYC card ────────────────────────
// Kept inline at the bottom because they're tightly scoped to this
// page; no value in pulling them into lib/utils.

function KycRow({
  label,
  value,
  mono = true,
  mask,
}: {
  label: string
  value?: string
  mono?: boolean
  mask?: (v: string) => string
}) {
  const display = value ? (mask ? mask(value) : value) : '—'
  return (
    <div className="flex items-center justify-between px-3 py-2">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? 'font-mono font-bold' : 'font-medium'}>{display}</span>
    </div>
  )
}

// PAN: show first 5 + last 2, mask the middle 3. So ABCDE1234F → ABCDE***4F.
function maskPan(pan: string): string {
  if (!pan || pan.length < 7) return pan
  return `${pan.slice(0, 5)}***${pan.slice(-2)}`
}

// Account number: show last 4 only, prefix with mask.
function maskAccount(acct: string): string {
  if (!acct || acct.length <= 4) return acct
  return `••••${acct.slice(-4)}`
}

export default AdminMerchantDetailsPage
