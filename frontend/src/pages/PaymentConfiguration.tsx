import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useFrappePostCall } from '@/lib/frappe'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'
import {
  Activity,
  CreditCard,
  Info,
  Loader2,
  Lock,
  Save,
  ShieldAlert,
  Wallet,
  Edit2,
  X,
  ArrowLeft,
  Download
} from 'lucide-react'

interface PaymentStats {
  current_month: string
  total_orders: number
  total_revenue: number
  platform_fee_collected: number
  monthly_minimum: number
  minimum_due: number
  razorpay_customer_id?: string | null
  billing_status?: string | null
  merchant_key_configured?: boolean
  masked_key_id?: string | null
  razorpay_keys_updated_at?: string | null
  razorpay_keys_updated_by?: string | null
}

export default function PaymentConfiguration() {
  const { restaurantId } = useParams()
  const navigate = useNavigate()
  const { selectedRestaurant, billingInfo } = useRestaurant()
  const activeRestaurantId = restaurantId || selectedRestaurant

  const [stats, setStats] = useState<PaymentStats | null>(null)
  const [, setLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isAdmin, setIsAdmin] = useState<boolean>(false)
  const [isEditing, setIsEditing] = useState(false)

  // Form states for Admin settings
  const [merchantKeyId, setMerchantKeyId] = useState('')
  const [merchantKeySecret, setMerchantKeySecret] = useState('')
  const [merchantWebhookSecret, setMerchantWebhookSecret] = useState('')

  const { call: getPaymentStats } = useFrappePostCall<{ success: boolean; data: PaymentStats }>(
    'flamezo_backend.flamezo.api.payments.get_restaurant_payment_stats'
  )
  const { call: setMerchantKeys } = useFrappePostCall(
    'flamezo_backend.flamezo.api.payments.set_restaurant_razorpay_keys'
  )
  const { call: canSetMerchantKeys } = useFrappePostCall<{ success: boolean; allowed: boolean }>(
    'flamezo_backend.flamezo.api.payments.can_set_merchant_keys'
  )

  const loadData = async () => {
    if (!activeRestaurantId) return
    setLoading(true)
    try {
      const statsResp: any = await getPaymentStats({ restaurant_id: activeRestaurantId })
      const statsBody = statsResp?.message ?? statsResp
      if (statsBody?.success && statsBody?.data) {
        setStats(statsBody.data)
        // If keys are configured, show masked values by default
        if (statsBody.data.merchant_key_configured) {
          setMerchantKeyId(statsBody.data.masked_key_id || '')
          setMerchantKeySecret('••••••••••••••••')
          setMerchantWebhookSecret(statsBody.data.merchant_key_configured ? '••••••••••••••••' : '')
          setIsEditing(false)
        }
      }

      const adminResp: any = await canSetMerchantKeys({})
      const adminBody = adminResp?.message ?? adminResp
      if (adminBody?.success) {
        setIsAdmin(Boolean(adminBody.allowed))
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [activeRestaurantId])

  const handleSaveKeys = async () => {
    if (!activeRestaurantId) return
    if (!merchantKeyId || !merchantKeySecret) {
      toast.error('Key ID and Secret are required')
      return
    }

    setIsSaving(true)
    try {
      const resp: any = await setMerchantKeys({
        restaurant_id: activeRestaurantId,
        key_id: merchantKeyId,
        key_secret: merchantKeySecret,
        webhook_secret: merchantWebhookSecret,
      })
      const body = resp?.message ?? resp
      if (body?.success) {
        toast.success('Merchant gateway keys securely saved')
        setMerchantKeySecret('') // Clear secret from state after save
        setMerchantWebhookSecret('')
        loadData() // Refresh stats to update 'keysConfigured' state
      } else {
        throw new Error(body?.error || 'Failed to save merchant keys')
      }
    } catch (err: any) {
      toast.error('Configuration failed', { description: err?.message })
    } finally {
      setIsSaving(false)
    }
  }

  if (!activeRestaurantId) {
    return <div className="p-8 text-center text-muted-foreground">Please select a restaurant to view usage and settings.</div>
  }

  const keysConfigured = Boolean(stats?.merchant_key_configured)

  return (
    <div className="space-y-8 pb-10">
      {/* Header Area */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-1">
          <div className="flex items-center gap-4">
            <Button 
              variant="ghost" 
              size="icon" 
              className="rounded-full h-8 w-8"
              onClick={() => navigate(-1)}
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div className="flex items-center gap-2">
              <h1 className="text-3xl font-bold tracking-tight text-foreground">Payment Configuration</h1>
              {keysConfigured ? (
                <Badge variant="outline" className="bg-emerald-500/10 text-emerald-700 border-emerald-200">Gateway Active</Badge>
              ) : (
                <Badge variant="outline" className="bg-amber-500/10 text-amber-700 border-amber-200">Setup Required</Badge>
              )}
            </div>
          </div>
          <p className="text-muted-foreground text-sm max-w-2xl ml-12">
            Configure the Razorpay merchant credentials for this restaurant.
          </p>
        </div>
        <div className="flex items-center mt-4 md:mt-0">
          <Button
            variant="outline"
            className="rounded-full gap-2 border-primary/20 text-primary hover:bg-primary/5"
            onClick={() => {
              window.open('/api/method/flamezo_backend.flamezo.api.payments.download_guide?guide_name=Flamezo_Razorpay_Guide', '_blank')
            }}
          >
            <Download className="h-4 w-4" />
            Help? Download Guide
          </Button>
        </div>
      </div>

      {/* Main Configuration Area */}
      <div className="grid gap-6 lg:grid-cols-7">
        <div className="lg:col-span-4 space-y-6">
          {!isAdmin ? (
            <Card className="shadow-sm border-none bg-card">
              <CardContent className="p-10 flex flex-col items-center justify-center text-center space-y-4">
                <div className="h-16 w-16 bg-muted rounded-full flex items-center justify-center">
                  <ShieldAlert className="h-8 w-8 text-muted-foreground" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-lg font-bold">Admin Access Required</h3>
                  <p className="text-sm text-muted-foreground max-w-md">
                    Only system administrators can configure customer payment gateways. 
                    Please contact Flamezo support to update your merchant keys.
                  </p>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card className="shadow-sm border-none bg-card overflow-hidden">
              <CardHeader className="flex flex-row items-center justify-between pb-4">
                <div className="space-y-1">
                  <CardTitle className="text-lg font-bold">Payment Gateway Keys</CardTitle>
                  <CardDescription>Configure where customer payments are routed</CardDescription>
                </div>
                <Lock className="h-5 w-5 text-muted-foreground" />
              </CardHeader>
              <CardContent className="space-y-6">
                {keysConfigured && stats?.razorpay_keys_updated_at && (
                  <div className="p-3 rounded-xl bg-muted/50 text-xs text-muted-foreground flex items-center justify-between">
                    <span>Keys are configured.</span>
                    <span>Last updated: {new Date(stats.razorpay_keys_updated_at).toLocaleDateString()} by {stats.razorpay_keys_updated_by}</span>
                  </div>
                )}

                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="key-id" className="text-xs uppercase tracking-wide text-muted-foreground font-bold">Razorpay Key ID</Label>
                    <Input 
                      id="key-id" 
                      value={merchantKeyId} 
                      onChange={(e) => setMerchantKeyId(e.target.value)} 
                      placeholder="rzp_live_..." 
                      disabled={keysConfigured && !isEditing}
                      className="bg-muted/50 border-transparent focus-visible:bg-background focus-visible:border-primary font-mono disabled:opacity-70"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="key-secret" className="text-xs uppercase tracking-wide text-muted-foreground font-bold">Razorpay Key Secret</Label>
                    <Input 
                      id="key-secret" 
                      type="password"
                      value={merchantKeySecret} 
                      onChange={(e) => setMerchantKeySecret(e.target.value)} 
                      placeholder="••••••••••••••••" 
                      disabled={keysConfigured && !isEditing}
                      className="bg-muted/50 border-transparent focus-visible:bg-background focus-visible:border-primary font-mono disabled:opacity-70"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="webhook-secret" className="text-xs uppercase tracking-wide text-muted-foreground font-bold">Webhook Secret (Optional)</Label>
                    <Input 
                      id="webhook-secret" 
                      type="password"
                      value={merchantWebhookSecret} 
                      onChange={(e) => setMerchantWebhookSecret(e.target.value)} 
                      placeholder="Optional webhook validation secret" 
                      disabled={keysConfigured && !isEditing}
                      className="bg-muted/50 border-transparent focus-visible:bg-background focus-visible:border-primary font-mono disabled:opacity-70"
                    />
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-primary/5 border border-primary/10 flex items-start gap-3">
                  <Info className="h-5 w-5 text-primary shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <p className="text-sm font-semibold text-foreground">Zero-Trust Storage</p>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      Your secrets are encrypted at rest in the database. They are never exposed to the frontend after saving. Ensure you have copied them from your Razorpay Dashboard.
                    </p>
                  </div>
                </div>

                <div className="pt-4 border-t border-border flex justify-end gap-3">
                  {keysConfigured && isEditing && (
                    <Button 
                      variant="outline"
                      onClick={() => {
                        setIsEditing(false)
                        loadData() // Revert to masked values
                      }}
                      className="rounded-full border-border hover:bg-muted transition-all gap-2"
                    >
                      <X className="h-4 w-4" />
                      Cancel
                    </Button>
                  )}

                  {keysConfigured && !isEditing ? (
                    <Button 
                      onClick={() => {
                        setIsEditing(true)
                        setMerchantKeyId('')
                        setMerchantKeySecret('')
                        setMerchantWebhookSecret('')
                        toast.info('Enter new credentials to update configuration')
                      }}
                      className="rounded-full bg-orange-600 hover:bg-orange-700 text-white shadow-md transition-all gap-2 min-w-[140px]"
                    >
                      <Edit2 className="h-4 w-4" />
                      Edit Configuration
                    </Button>
                  ) : (
                    <Button 
                      onClick={handleSaveKeys} 
                      disabled={isSaving} 
                      className="rounded-full bg-primary hover:bg-primary/90 text-white shadow-lg shadow-primary/20 transition-all gap-2 min-w-[140px]"
                    >
                      {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                      {keysConfigured ? 'Update Configuration' : 'Save Configuration'}
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Supporting Info Section */}
        <div className="lg:col-span-3 space-y-6">
          <Card className="shadow-sm border-none bg-card">
            <CardHeader>
              <CardTitle className="text-lg font-bold">How Customer Payments Work</CardTitle>
              <CardDescription>Understanding the payment flow</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-start gap-3 p-3 rounded-xl bg-muted/30 hover:bg-muted/50 transition-colors border border-transparent hover:border-border">
                  <div className="h-8 w-8 rounded-full bg-background border border-border flex items-center justify-center shrink-0">
                    <CreditCard className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-bold">1. Customer Checkout</p>
                    <p className="text-[11px] text-muted-foreground">Customers complete orders using the gateway keys defined on this page.</p>
                  </div>
                </div>
                
                <div className="flex items-start gap-3 p-3 rounded-xl bg-muted/30 hover:bg-muted/50 transition-colors border border-transparent hover:border-border">
                  <div className="h-8 w-8 rounded-full bg-background border border-border flex items-center justify-center shrink-0">
                    <Wallet className="h-4 w-4 text-emerald-500" />
                  </div>
                  <div>
                    <p className="text-sm font-bold">2. Direct Settlement</p>
                    <p className="text-[11px] text-muted-foreground">100% of the funds go directly into your linked Razorpay account instantly.</p>
                  </div>
                </div>
                
                <div className="flex items-start gap-3 p-3 rounded-xl bg-muted/30 hover:bg-muted/50 transition-colors border border-transparent hover:border-border">
                  <div className="h-8 w-8 rounded-full bg-background border border-border flex items-center justify-center shrink-0">
                    <Activity className="h-4 w-4 text-blue-500" />
                  </div>
                  <div>
                    <p className="text-sm font-bold">3. Platform Tracking</p>
                    <p className="text-[11px] text-muted-foreground">We track the GMV to calculate the {billingInfo?.plan_defaults?.gold_commission ?? 1.5}% end-of-month platform commission.</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
