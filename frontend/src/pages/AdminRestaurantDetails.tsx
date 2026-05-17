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
  Terminal,
  Info,
  Activity,
  Zap,
  Star,
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
  Loader2
} from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import MenuImageExtractorForm from '@/components/MenuImageExtractorForm'

interface Restaurant {
  name: string
  restaurant_id: string
  restaurant_name: string
  owner_email?: string
  owner_phone?: string
  owner_name?: string
  is_active: number
  plan_type: 'SILVER' | 'GOLD'
  coins_balance: number
  platform_fee_percent: number
  monthly_minimum: number
  creation: string
  modified: string
  description?: string
  slug?: string
  subdomain?: string
  billing_status: string
  mandate_status: string
  razorpay_account_id?: string
  razorpay_kyc_status?: string
  pos_provider?: string
  pos_enabled: number
  pos_app_key?: string
  pos_app_secret?: string
  pos_access_token?: string
  pos_merchant_id?: string
  enable_loyalty: number
  enable_takeaway: number
  enable_delivery: number
  enable_dine_in: number
  no_ordering: number
  tax_rate: number
  gst_number?: string
  default_delivery_fee: number
  default_packaging_fee: number
  total_revenue: number
  commission_earned: number
  total_orders: number
  minimum_order_value: number
  estimated_prep_time: number
  timezone: string
  currency: string
  tables: number
  google_map_url?: string
  referral_code?: string
  referred_by_restaurant?: string
}

function AdminRestaurantDetailsPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  
  // States
  const [restaurant, setRestaurant] = useState<Restaurant | null>(null)
  const [originalRestaurant, setOriginalRestaurant] = useState<Restaurant | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [isMenuModalOpen, setIsMenuModalOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('overview')

  const [isOnboardModalOpen, setIsOnboardModalOpen] = useState(false)
  const [onboardName, setOnboardName] = useState('')
  const [onboardEmail, setOnboardEmail] = useState('')
  const [isOnboarding, setIsOnboarding] = useState(false)
  const [onboardResult, setOnboardResult] = useState<{message: string, link?: string, emailSent: boolean} | null>(null)
  
  const [manualRechargeAmount, setManualRechargeAmount] = useState('')
  const [generatedRechargeLink, setGeneratedRechargeLink] = useState('')
  const [isGeneratingRecharge, setIsGeneratingRecharge] = useState(false)
  const [isLinkModalOpen, setIsLinkModalOpen] = useState(false)
  const [linkToCopy, setLinkToCopy] = useState('')

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

  const handleGenerateLegacy = async () => {
    if (!id) return
    try {
      setIsGeneratingLegacy(true)
      const result = await generateLegacyContent({ restaurant_id: id }) as any
      if (result?.message?.success) {
        toast.success('Legacy content successfully generated!', {
          description: 'A premium 10/10 story has been crafted for this restaurant.'
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
  const { call: getDetails } = useFrappePostCall<{ success: boolean, data: { restaurant: Restaurant } }>(
    'flamezo_backend.flamezo.api.admin.get_restaurant_details'
  )
  const { call: updateSettings } = useFrappePostCall<{ success: boolean, message?: string, error?: string }>(
    'flamezo_backend.flamezo.api.admin.admin_update_restaurant_settings'
  )
  const { call: onboardOwner } = useFrappePostCall<{ success: boolean, message?: string, error?: string }>(
    'flamezo_backend.flamezo.api.admin.admin_onboard_restaurant_owner'
  )
  const { call: createManualLink } = useFrappePostCall<{ 
    success: boolean, 
    payment_link_url?: string, 
    amount?: number,
    base_amount?: number,
    gst_amount?: number,
    error?: string 
  }>('flamezo_backend.flamezo.api.admin.admin_create_manual_recharge_link')
  
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
      const result = await getDetails({ restaurant_id: id }) as any
      if (result?.message?.data?.restaurant) {
        const data = result.message.data.restaurant
        setRestaurant(data)
        setOriginalRestaurant(data)
      }
    } catch (error) {
      toast.error('Failed to load restaurant details', { description: getFrappeError(error) })
      navigate('/admin/restaurants')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDetails()
  }, [id])

  // Detect changes
  const isDirty = useMemo(() => {
    if (!restaurant || !originalRestaurant) return false
    return JSON.stringify(restaurant) !== JSON.stringify(originalRestaurant)
  }, [restaurant, originalRestaurant])

  const handleSaveChanges = async () => {
    if (!id || !restaurant || !originalRestaurant) return
    
    // Find only changed fields
    const updates: Record<string, any> = {}
    Object.keys(restaurant).forEach((key) => {
      const k = key as keyof Restaurant
      if (restaurant[k] !== originalRestaurant[k]) {
        updates[k] = restaurant[k]
      }
    })

    if (Object.keys(updates).length === 0) {
      toast.info('No changes to save')
      return
    }

    try {
      setSaving(true)
      const result = await updateSettings({
        restaurant_id: id,
        updates
      }) as any
      if (result?.message?.success) {
        toast.success('Changes saved successfully')
        setOriginalRestaurant(restaurant)
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
    setRestaurant(originalRestaurant)
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
        restaurant_id: id,
        owner_name: onboardName,
        owner_email: onboardEmail
      }) as any
      
      if (result?.message?.success) {
        const data = result.message.data
        const emailSent = data.email_sent
        const message = result.message.message
        const link = data.onboard_link
        
        setOnboardResult({message, link, emailSent})
        
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
    setOnboardName(restaurant?.owner_name || '')
    setOnboardEmail(restaurant?.owner_email || '')
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
              You lack the administrative clearance required to access the central restaurant control hub.
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
        <p className="text-muted-foreground animate-pulse">Loading restaurant intelligence...</p>
      </div>
    )
  }

  if (!restaurant) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <Card className="w-full max-w-md border-destructive/20 shadow-lg">
          <CardContent className="p-8 text-center">
            <ShieldAlert className="h-12 w-12 text-destructive mx-auto mb-4" />
            <h2 className="text-2xl font-bold mb-2">Restaurant Not Found</h2>
            <p className="text-muted-foreground mb-6">The requested restaurant ID does not exist.</p>
            <Button onClick={() => navigate('/admin/restaurants')}>Go Back</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background p-6 lg:p-10 pb-32">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 pb-2">
          <div className="space-y-4">
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={() => navigate('/admin/restaurants')}
              className="group -ml-2 text-muted-foreground hover:text-primary"
            >
              <ArrowLeft className="h-4 w-4 mr-2 group-hover:-translate-x-1 transition-transform" />
              Back to Fleet
            </Button>
            <div>
              <div className="flex items-center gap-3 mb-1">
                <h1 className="text-4xl font-extrabold tracking-tight">{restaurant.restaurant_name}</h1>
                <Badge 
                  variant={restaurant.is_active ? 'default' : 'secondary'}
                  className={cn(
                    "px-3 py-0.5 text-xs font-bold uppercase tracking-wider",
                    restaurant.is_active ? "bg-green-500/10 text-green-600 border-green-200" : "bg-muted text-muted-foreground"
                  )}
                >
                  {restaurant.is_active ? 'Live' : 'Inactive'}
                </Badge>
              </div>
              <p className="text-muted-foreground font-mono text-sm flex items-center gap-2">
                ID: {restaurant.restaurant_id} <Separator className="h-3 w-px mx-1 bg-muted-foreground/30" /> 
                <Globe className="h-3 w-3" /> {restaurant.subdomain || 'no-subdomain'}.flamezo_backend.com
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {canGenerateLegacy && (
              <Button 
                onClick={handleGenerateLegacy}
                disabled={isGeneratingLegacy}
                className="bg-amber-500 hover:bg-amber-600 shadow-amber-500/20 shadow-lg gap-2 text-white"
              >
                {isGeneratingLegacy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                Generate Legacy
              </Button>
            )}

             <Dialog open={isMenuModalOpen} onOpenChange={setIsMenuModalOpen}>
              <DialogTrigger asChild>
                <Button className="bg-indigo-600 hover:bg-indigo-700 shadow-indigo-500/20 shadow-lg gap-2">
                  <UploadCloud className="h-4 w-4" />
                  Upload Menu
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-4xl max-h-[90vh] overflow-y-auto p-0 gap-0 border-none shadow-2xl">
                <MenuImageExtractorForm 
                  restaurantId={restaurant.name} 
                  restaurantName={restaurant.restaurant_name}
                  onComplete={() => {
                      toast.success('Menu extraction complete!')
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
                  <DialogTitle>{onboardResult ? "Onboarding Result" : "Onboard Restaurant Owner"}</DialogTitle>
                  <DialogDescription>
                    {onboardResult 
                      ? "The owner has been successfully configured in the system."
                      : "Create a system user, assign the required roles, and send them a secure password-setup email."}
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

                    {onboardResult.link && !onboardResult.emailSent && (
                      <div className="space-y-3">
                        <Label className="text-xs uppercase font-bold text-muted-foreground tracking-widest">Manual Setup Link</Label>
                        <div className="flex gap-2">
                          <Input value={onboardResult.link} readOnly className="font-mono text-[10px] bg-muted/30" />
                          <Button 
                            variant="secondary" 
                            size="icon" 
                            onClick={() => handleCopyLink(onboardResult.link!)}
                            title="Copy link"
                          >
                            <Save className="h-4 w-4" />
                          </Button>
                        </div>
                        <p className="text-[10px] text-muted-foreground leading-relaxed italic">
                          Send this link to the owner via WhatsApp or Email. It will allow them to securely set their password and log in.
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
                          placeholder="e.g. john@restaurant.com"
                        />
                        <p className="text-xs text-muted-foreground mt-1">A secure welcome email will be dispatched to this address.</p>
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

            <Button 
              variant="outline" 
              onClick={loadDetails} 
              disabled={loading}
              className="gap-2"
            >
              <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
              Sync
            </Button>
          </div>
        </div>

        {/* Global Stats Bar */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="bg-primary/5 border-primary/10 overflow-hidden relative">
            <div className="absolute right-[-10px] top-[-10px] opacity-10">
              <Zap className="h-24 w-24 text-primary" />
            </div>
            <CardContent className="p-5">
              <p className="text-[10px] uppercase font-bold tracking-widest text-primary/60 mb-1">Subscription</p>
              <div className="flex items-center gap-2">
                <Shield className="h-4 w-4 text-primary" />
                <span className="text-xl font-bold">{restaurant.plan_type}</span>
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-green-500/5 border-green-500/10 overflow-hidden relative">
            <div className="absolute right-[-10px] top-[-10px] opacity-10">
              <Activity className="h-24 w-24 text-green-600" />
            </div>
            <CardContent className="p-5">
              <p className="text-[10px] uppercase font-bold tracking-widest text-green-600/60 mb-1">Revenue (Life)</p>
              <div className="flex items-center gap-2">
                <span className="text-xl font-bold">₹{restaurant.total_revenue.toLocaleString()}</span>
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
                <span className="text-xl font-bold">{restaurant.coins_balance.toLocaleString()} Coins</span>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-indigo-500/5 border-indigo-500/10 overflow-hidden relative">
            <div className="absolute right-[-10px] top-[-10px] opacity-10">
              <User className="h-24 w-24 text-indigo-600" />
            </div>
            <CardContent className="p-5">
              <p className="text-[10px] uppercase font-bold tracking-widest text-indigo-600/60 mb-1">Total Orders</p>
              <div className="flex items-center gap-2">
                <span className="text-xl font-bold">{restaurant.total_orders.toLocaleString()}</span>
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
            <TabsTrigger value="pos" className="rounded-lg px-4 py-2 gap-2 data-[state=active]:bg-background data-[state=active]:shadow-sm">
              <Terminal className="h-4 w-4" /> POS Integration
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
                  <CardDescription>Core restaurant identity and owner details</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-2">
                      <Label>Legal Restaurant Name</Label>
                      <Input 
                        value={restaurant.restaurant_name} 
                        onChange={(e) => setRestaurant({...restaurant, restaurant_name: e.target.value})}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Internal Slug / ID</Label>
                      <Input value={restaurant.restaurant_id} disabled className="bg-muted/50 font-mono" />
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
                          value={restaurant.owner_name || ''} 
                          onChange={(e) => setRestaurant({...restaurant, owner_name: e.target.value})}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Owner Email</Label>
                        <Input 
                          value={restaurant.owner_email || ''} 
                          onChange={(e) => setRestaurant({...restaurant, owner_email: e.target.value})}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Owner Phone</Label>
                        <Input 
                          value={restaurant.owner_phone || ''} 
                          onChange={(e) => setRestaurant({...restaurant, owner_phone: e.target.value})}
                        />
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
                          value={restaurant.google_map_url || ''} 
                          onChange={(e) => setRestaurant({...restaurant, google_map_url: e.target.value})}
                          placeholder="Google Maps URL"
                        />
                        <Button variant="outline" size="icon" onClick={() => window.open(restaurant.google_map_url, '_blank')} disabled={!restaurant.google_map_url}>
                          <ExternalLink className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label>Description</Label>
                      <Textarea 
                        value={restaurant.description || ''} 
                        onChange={(e) => setRestaurant({...restaurant, description: e.target.value})}
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
                      <p className="text-xs text-muted-foreground">Toggle visibility of the restaurant platform-wide</p>
                    </div>
                    <Switch 
                      checked={!!restaurant.is_active} 
                      onCheckedChange={(checked) => setRestaurant({...restaurant, is_active: checked ? 1 : 0})}
                    />
                  </div>

                  <div className="space-y-4">
                     <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Admin Metadata</p>
                     <div className="space-y-3">
                        <div className="flex justify-between items-center text-sm">
                          <span className="text-muted-foreground">Created on</span>
                          <span className="font-medium">{formatDate(restaurant.creation)}</span>
                        </div>
                        <div className="flex justify-between items-center text-sm">
                          <span className="text-muted-foreground">Last modified</span>
                          <span className="font-medium">{formatDate(restaurant.modified)}</span>
                        </div>
                        <div className="flex justify-between items-center text-sm">
                          <span className="text-muted-foreground">Commission Ratio</span>
                          <Badge variant="outline" className="text-primary border-primary/20">{restaurant.platform_fee_percent}%</Badge>
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
                           <Input value={restaurant.referral_code || ''} readOnly className="h-8 bg-muted/30 font-mono text-xs" />
                           <Button 
                             variant="outline" 
                             size="sm" 
                             onClick={async () => {
                               if (restaurant.referral_code) {
                                 const success = await copyToClipboard(restaurant.referral_code)
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
                         <Label className="text-[10px] uppercase font-bold text-muted-foreground/60">Referred By (Restaurant ID)</Label>
                         <Input 
                           value={restaurant.referred_by_restaurant || ''} 
                           onChange={(e) => setRestaurant({...restaurant, referred_by_restaurant: e.target.value})}
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
                      Changes here affect the billing engine and restaurant access. Exercise caution.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Billing Tab */}
          <TabsContent value="billing">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Subscription Configuration</CardTitle>
                  <CardDescription>Manage tiers, commission and floors</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="space-y-2">
                    <Label>Subscription Tier</Label>
                    <Select 
                      value={restaurant.plan_type} 
                      onValueChange={(v: 'SILVER' | 'GOLD') => setRestaurant({...restaurant, plan_type: v})}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="SILVER"><div className="flex items-center gap-2"><Shield className="h-3 w-3 text-muted-foreground" /> SILVER (Basic)</div></SelectItem>
                        <SelectItem value="GOLD"><div className="flex items-center gap-2"><Zap className="h-3 w-3 text-amber-500" /> GOLD (Full Automation)</div></SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="grid grid-cols-2 gap-6">
                    <div className="space-y-2">
                      <Label>Platform Fee (%)</Label>
                      <NumberInput 
                        
                        value={restaurant.platform_fee_percent} 
                        onChange={(e) => setRestaurant({...restaurant, platform_fee_percent: parseFloat(e.target.value)})}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Monthly Minimum (₹)</Label>
                      <NumberInput 
                         
                        value={restaurant.monthly_minimum} 
                        onChange={(e) => setRestaurant({...restaurant, monthly_minimum: parseFloat(e.target.value)})}
                      />
                    </div>
                  </div>

                  <Separator />

                  <div className="space-y-3">
                    <Label className="text-xs uppercase font-bold tracking-widest text-muted-foreground">Admin Billing Status</Label>
                    <Select 
                      value={restaurant.billing_status} 
                      onValueChange={(v) => setRestaurant({...restaurant, billing_status: v})}
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

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Razorpay Autopay & KYC</CardTitle>
                  <CardDescription>Mandate status and payment connectivity</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="space-y-4">
                    <div className="p-4 rounded-xl border bg-muted/20 space-y-3">
                      <div className="flex items-center justify-between">
                        <Label className="text-sm font-bold">Mandate Status</Label>
                        <Badge 
                          variant={restaurant.mandate_status === 'active' ? 'default' : 'destructive'}
                          className={restaurant.mandate_status === 'active' ? "bg-green-500/10 text-green-600" : ""}
                        >
                          {restaurant.mandate_status ? restaurant.mandate_status.toUpperCase() : 'UNKNOWN'}
                        </Badge>
                      </div>
                      <div className="text-xs text-muted-foreground flex items-center gap-2">
                        <ShieldCheck className="h-3 w-3" /> Tokenized Recurring Access Enabled
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-4">
                      <div className="space-y-2">
                        <Label>Razorpay Account ID</Label>
                        <Input value={restaurant.razorpay_account_id || ''} disabled className="bg-muted/50 font-mono text-xs" />
                      </div>
                      <div className="space-y-2">
                        <Label>KYC Status</Label>
                        <Input value={restaurant.razorpay_kyc_status || 'NOT INITIALIZED'} disabled className="bg-muted/50 font-bold text-xs" />
                      </div>
                    </div>
                  </div>

                  <Separator />
                  
                  <div className="bg-indigo-500/5 border border-indigo-200/50 p-4 rounded-xl">
                      <p className="text-xs font-bold text-indigo-700 mb-1 flex items-center gap-1.5 uppercase tracking-tighter">
                        <ShieldAlert className="h-3 w-3" /> Billing Reconciliation
                      </p>
                      <p className="text-[10px] text-indigo-600/80 leading-relaxed">
                        Total Commission Earned from this restaurant: <span className="font-bold">₹{(restaurant.commission_earned || 0).toLocaleString()}</span>. 
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
                    <h2 className="text-5xl font-black text-orange-700">{restaurant.coins_balance.toLocaleString()}</h2>
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
                         <p className="text-lg font-bold">₹{(restaurant.total_revenue || 0).toLocaleString()}</p>
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
                        <li>Digital Menu Customizations (Premium Themes)</li>
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
                                restaurant_id: id,
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
                              const msg = `Hi ${restaurant.owner_name || restaurant.restaurant_name}, please use this link to top-up your Flamezo wallet with ₹${parseFloat(manualRechargeAmount).toLocaleString()}: ${generatedRechargeLink}\n\nCredits will reflect in your account automatically after payment. Thanks!`
                              const success = await copyToClipboard(msg)
                              if (success) toast.success('Recharge message copied!')
                            }}
                            title="Copy Professional Message"
                          >
                            <MessageSquare className="h-4 w-4" />
                          </Button>
                        </div>
                        <p className="text-[10px] text-muted-foreground italic">
                          Share the link or the full message with {restaurant.owner_name || 'the customer'}.
                        </p>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* POS Tab */}
          <TabsContent value="pos">
            <Card className="max-w-3xl">
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-lg">POS Connection Intelligence</CardTitle>
                  <CardDescription>Sync logic with Petpooja or UrbanPiper</CardDescription>
                </div>
                <Switch 
                  checked={!!restaurant.pos_enabled} 
                  onCheckedChange={(v) => setRestaurant({...restaurant, pos_enabled: v ? 1 : 0})}
                />
              </CardHeader>
              <CardContent className="space-y-6 pt-2">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <Label>Preferred Provider</Label>
                    <Select 
                      value={restaurant.pos_provider || ''} 
                      onValueChange={(v) => setRestaurant({...restaurant, pos_provider: v})}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="No POS Select" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Petpooja">Petpooja (Deep Integration)</SelectItem>
                        <SelectItem value="UrbanPiper">UrbanPiper (Nexus Integration)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Merchant Store ID</Label>
                    <Input 
                      value={restaurant.pos_merchant_id || ''} 
                      onChange={(e) => setRestaurant({...restaurant, pos_merchant_id: e.target.value})}
                    />
                  </div>
                </div>

                <Separator />

                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                     <div className="space-y-2">
                        <Label>API / App Key</Label>
                        <Input 
                          value={restaurant.pos_app_key || ''} 
                          onChange={(e) => setRestaurant({...restaurant, pos_app_key: e.target.value})}
                          className="font-mono text-xs"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>App Secret / Token</Label>
                        <Input 
                          type="password"
                          value={restaurant.pos_app_secret || ''} 
                          onChange={(e) => setRestaurant({...restaurant, pos_app_secret: e.target.value})}
                          className="font-mono text-xs"
                        />
                      </div>
                  </div>
                  <div className="space-y-2">
                    <Label>Special Access Token (e.g. Petpooja)</Label>
                    <Input 
                      type="password"
                      value={restaurant.pos_access_token || ''} 
                      onChange={(e) => setRestaurant({...restaurant, pos_access_token: e.target.value})}
                      className="font-mono text-xs"
                    />
                  </div>
                </div>

                <div className="p-4 rounded-xl border bg-muted/20 text-xs text-muted-foreground flex items-center gap-3">
                    <ShieldCheck className="h-5 w-5 text-green-600 shrink-0" />
                    Credentials are encrypted in the database using high-entropy AES-256. Administrative logs track every access.
                </div>
              </CardContent>
            </Card>
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
                           <Switch checked={!!restaurant.enable_dine_in} onCheckedChange={(v) => setRestaurant({...restaurant, enable_dine_in: v ? 1 : 0})} />
                        </div>
                        <div className="flex flex-col items-center gap-3 p-4 rounded-xl border md:col-span-1">
                           <Label className="text-[10px] uppercase font-bold opacity-50">Delivery</Label>
                           <Switch checked={!!restaurant.enable_delivery} onCheckedChange={(v) => setRestaurant({...restaurant, enable_delivery: v ? 1 : 0})} />
                        </div>
                        <div className="flex flex-col items-center gap-3 p-4 rounded-xl border md:col-span-1">
                           <Label className="text-[10px] uppercase font-bold opacity-50">Takeaway</Label>
                           <Switch checked={!!restaurant.enable_takeaway} onCheckedChange={(v) => setRestaurant({...restaurant, enable_takeaway: v ? 1 : 0})} />
                        </div>
                        <div className="flex flex-col items-center gap-3 p-4 rounded-xl border md:col-span-1">
                           <Label className="text-[10px] uppercase font-bold opacity-50">Loyalty</Label>
                           <Switch checked={!!restaurant.enable_loyalty} onCheckedChange={(v) => setRestaurant({...restaurant, enable_loyalty: v ? 1 : 0})} />
                        </div>
                    </div>

                    <Separator />

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                       <div className="space-y-2">
                          <Label>Currency</Label>
                          <Input value={restaurant.currency} disabled className="bg-muted/50" />
                       </div>
                       <div className="space-y-2">
                          <Label>Tax Rate (%)</Label>
                          <NumberInput 
                            
                            value={restaurant.tax_rate} 
                            onChange={(e) => setRestaurant({...restaurant, tax_rate: parseFloat(e.target.value)})}
                          />
                       </div>
                       <div className="space-y-2">
                          <Label>Timezone</Label>
                          <Input value={restaurant.timezone} disabled className="bg-muted/50" />
                       </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                       <div className="space-y-2">
                          <Label>Default Deliv. Fee</Label>
                          <NumberInput 
                            
                            value={restaurant.default_delivery_fee} 
                            onChange={(e) => setRestaurant({...restaurant, default_delivery_fee: parseFloat(e.target.value)})}
                          />
                       </div>
                       <div className="space-y-2">
                          <Label>Pack. Fee</Label>
                          <NumberInput 
                            
                            value={restaurant.default_packaging_fee} 
                            onChange={(e) => setRestaurant({...restaurant, default_packaging_fee: parseFloat(e.target.value)})}
                          />
                       </div>
                       <div className="space-y-2">
                          <Label>Prep Time (m)</Label>
                          <NumberInput 
                            
                            value={restaurant.estimated_prep_time} 
                            onChange={(e) => setRestaurant({...restaurant, estimated_prep_time: parseInt(e.target.value)})}
                          />
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
                           <h2 className="text-2xl font-black">{restaurant.tables}</h2>
                        </div>
                        <div className="space-y-2">
                          <Label>Update Tables</Label>
                          <NumberInput 
                             
                             value={restaurant.tables} 
                             onChange={(e) => setRestaurant({...restaurant, tables: parseInt(e.target.value)})}
                          />
                        </div>
                     </div>

                     <Separator />

                     <div className="space-y-2">
                        <Label>GST Identification</Label>
                        <Input 
                          value={restaurant.gst_number || ''} 
                          onChange={(e) => setRestaurant({...restaurant, gst_number: e.target.value})}
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

export default AdminRestaurantDetailsPage
