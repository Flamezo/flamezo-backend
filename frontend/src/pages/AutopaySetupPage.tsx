import { SetStateAction, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import {
  AlertCircle,
  IndianRupee,
  Loader2,
  ShieldCheck,
  Zap,
  Info,
  Plus,
  Wallet,
  History,
  ShieldAlert,
  Gem,
  Trophy,
  Smartphone,
  Download,
} from 'lucide-react'
import { toast } from 'sonner'
import { AiRechargeModal } from '@/components/AiRechargeModal'
import { SubscriptionComparisonModal } from '@/components/SubscriptionComparisonModal'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { format, addDays } from 'date-fns'

interface BillingInfo {
  coins_balance: number
  auto_recharge_enabled: boolean
  auto_recharge_threshold: number
  auto_recharge_amount: number
  mandate_active: boolean
  daily_limit: number
  current_daily_vol: number
  deferred_plan_type?: 'SILVER' | 'GOLD' | 'DIAMOND' | null
  plan_change_date?: string | null
  monthly_minimum: number
  platform_fee_percent: number
  plan_defaults: {
    pro_monthly: number   // GOLD monthly minimum
    lux_monthly: number   // DIAMOND monthly minimum
    lux_commission: number
    lux_barrier: number   // DIAMOND upgrade entry requirement
  }
}

export default function AutopaySetupPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { selectedRestaurant, restaurants, planType, refreshConfig } = useRestaurant()

  const [billingInfo, setBillingInfo] = useState<BillingInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [isUpdating, setIsUpdating] = useState(false)
  const [isChangingPlan, setIsChangingPlan] = useState(false)
  const [isSettingUpMandate, setIsSettingUpMandate] = useState(false)
  const [showRecharge, setShowRecharge] = useState(false)

  // Local form state
  const [enabled, setEnabled] = useState(false)
  const [threshold, setThreshold] = useState('200')
  const [amount, setAmount] = useState('1000')

  // Plan change state
  const [showConfirm, setShowConfirm] = useState(false)
  const [showComparison, setShowComparison] = useState(false)
  const [newPlanSelection, setNewPlanSelection] = useState<'SILVER' | 'GOLD' | 'DIAMOND' | null>(null)

  const { call: getInfo } = useFrappePostCall<any>(
    'dinematters.dinematters.api.coin_billing.get_coin_billing_info'
  )
  const { call: updateSettings } = useFrappePostCall<any>(
    'dinematters.dinematters.api.coin_billing.update_autopay_settings'
  )
  const { call: updatePlan } = useFrappePostCall<any>(
    'dinematters.dinematters.api.coin_billing.update_subscription_plan'
  )
  const { call: createTokenOrder } = useFrappePostCall<any>(
    'dinematters.dinematters.api.payments.create_tokenization_order'
  )
  const { call: confirmMandate } = useFrappePostCall<any>(
    'dinematters.dinematters.api.payments.confirm_mandate_setup'
  )

  const activeRes = restaurants.find(r => r.name === selectedRestaurant)

  const loadInfo = async () => {
    if (!selectedRestaurant) return
    setLoading(true)
    try {
      const res = await getInfo({ restaurant: selectedRestaurant })
      if (res.message) {
        setBillingInfo(res.message)
        setEnabled(res.message.auto_recharge_enabled)
        setThreshold(res.message.auto_recharge_threshold.toString())
        setAmount(res.message.auto_recharge_amount.toString())
      }
    } catch (error) {
      toast.error('Failed to load billing info')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadInfo()
  }, [selectedRestaurant])

  // Auto-trigger recharge modal if buy=true is in the URL
  useEffect(() => {
    if (searchParams.get('buy') === 'true') {
      setShowRecharge(true)
      // Clean up the parameter so it doesn't re-trigger on fresh refresh
      searchParams.delete('buy')
      setSearchParams(searchParams, { replace: true })
    }
  }, [searchParams, setSearchParams])

  const handlePlanToggle = async (newPlan: 'SILVER' | 'GOLD' | 'DIAMOND') => {
    if (!selectedRestaurant || newPlan === planType) return

    // 1. Check for pending changes
    if (billingInfo?.deferred_plan_type) {
      toast.error('A plan change is already scheduled for tomorrow.')
      return
    }

    // 2. Entrance Barrier Check
    const proMin = billingInfo?.plan_defaults?.pro_monthly || 999;
    const luxBarrier = billingInfo?.plan_defaults?.lux_barrier || 1299;

    if (newPlan === 'GOLD' && (billingInfo?.coins_balance || 0) < proMin) {
      toast.error('Insufficient Balance', {
        description: `You need at least ₹${proMin} in your wallet to upgrade to GOLD.`
      })
      setShowRecharge(true)
      return
    }

    if (newPlan === 'DIAMOND' && (billingInfo?.coins_balance || 0) < luxBarrier) {
      toast.error('Insufficient Balance', {
        description: `You need at least ₹${luxBarrier} in your wallet to upgrade to DIAMOND.`
      })
      setShowRecharge(true)
      return
    }


    // 3. Trigger Modern Confirmation Dialog
    setNewPlanSelection(newPlan)
    setShowConfirm(true)
  }

  const confirmPlanChange = async () => {
    if (!selectedRestaurant || !newPlanSelection) return

    setIsChangingPlan(true)
    try {
      const res = await updatePlan({
        restaurant: selectedRestaurant,
        plan_type: newPlanSelection
      })

      if (res.message?.success) {
        toast.success(`Success! Plan change scheduled.`, {
          description: res.message.message
        })
      }

      await loadInfo()
      await refreshConfig()
    } catch (error: any) {
      toast.error('Failed to schedule plan change', { description: error.message })
    } finally {
      setIsChangingPlan(false)
      setShowConfirm(false)
      setShowComparison(false)
      setNewPlanSelection(null)
    }
  }

  const handleSaveSettings = async () => {
    if (!selectedRestaurant) return
    setIsUpdating(true)
    try {
      await updateSettings({
        restaurant: selectedRestaurant,
        enabled,
        threshold: parseFloat(threshold),
        amount: parseFloat(amount)
      })
      toast.success('Autopay settings updated')
      loadInfo()
    } catch (error) {
      toast.error('Failed to update settings')
    } finally {
      setIsUpdating(false)
    }
  }

  const handleSetupMandate = async () => {
    setIsSettingUpMandate(true)
    try {
      const loaded = await new Promise<boolean>((resolve) => {
        if ((window as any).Razorpay) return resolve(true)
        const script = document.createElement('script')
        script.src = 'https://checkout.razorpay.com/v1/checkout.js'
        script.onload = () => resolve(true)
        script.onerror = () => resolve(false)
        document.body.appendChild(script)
      })

      if (!loaded) throw new Error('Razorpay failed to load')

      const res = await createTokenOrder({
        restaurant_id: selectedRestaurant,
        customer_name: activeRes?.restaurant_name || activeRes?.name,
        customer_email: (activeRes as any)?.owner_email || ''
      })

      if (!res.message?.success) throw new Error(res.message?.error || 'Failed to start mandate setup')

      const { key_id, razorpay_subscription_id } = res.message.data

      const rzp = new (window as any).Razorpay({
        key: key_id,
        subscription_id: razorpay_subscription_id,
        name: 'DineMatters Autopay',
        description: 'Authorize Mandate (Safety Cap: ₹15,000) — ₹1 verification fee',
        theme: { color: '#f97316' },
        handler: async (response: any) => {
          // Verify signature and save token immediately
          try {
            const confirmRes = await confirmMandate({
              restaurant_id: selectedRestaurant,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_order_id: razorpay_subscription_id, // Pass sub_id as order_id ref
              razorpay_signature: response.razorpay_signature,
            })
            if (confirmRes.message?.mandate_active) {
              toast.success('Autopay mandate activated!', {
                description: 'Your payment method is saved for automatic top-ups.'
              })
            } else {
              toast.success('Payment verified! Mandate will activate shortly.', {
                description: 'We will confirm via webhook within a few minutes.'
              })
            }
          } catch {
            toast.success('Payment done! Mandate activating...', {
              description: 'This may take a few minutes to reflect.'
            })
          }
          setTimeout(loadInfo, 2000)
        },
        modal: {
          ondismiss: () => toast.error('Mandate setup cancelled.'),
        },
      })
      rzp.open()
    } catch (error: any) {
      toast.error('Mandate setup failed', { description: error.message })
    } finally {
      setIsSettingUpMandate(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto space-y-8 pb-20 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black tracking-tight text-foreground">Billing & Subscription</h1>
          <p className="text-sm text-muted-foreground">Manage your DineMatters tier, wallet balance and automatic top-ups.</p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            className="gap-2 border-primary/20 text-primary hover:bg-primary/5"
            onClick={() => {
              window.open('/api/method/dinematters.dinematters.api.payments.download_guide?guide_name=Dinematters_Charges', '_blank')
            }}
          >
            <Download className="h-4 w-4" />
            Download Guide
          </Button>
          <Button variant="outline" size="sm" className="gap-2" onClick={() => navigate('/ledger')}>
            <History className="h-4 w-4" />
            Ledger
          </Button>
          <Button size="sm" className="gap-2 bg-primary text-white" onClick={() => setShowRecharge(true)}>
            <Plus className="h-4 w-4" />
            Top up Wallet
          </Button>
        </div>
      </div>

      {/* Pending Change Alert */}
      {billingInfo?.deferred_plan_type && (
        <Card className="border-primary/20 bg-primary/5 dark:bg-primary/10 overflow-hidden animate-in slide-in-from-top-4 duration-500">
          <CardContent className="p-4 flex items-center gap-4">
            <div className="h-10 w-10 rounded-full bg-primary/20 flex items-center justify-center shrink-0">
              <Loader2 className="h-5 w-5 text-primary animate-spin" />
            </div>
            <div className="flex-1">
              <h4 className="text-sm font-black uppercase tracking-tight text-primary">Plan switch scheduled</h4>
              <p className="text-xs text-muted-foreground">
                Your {billingInfo.deferred_plan_type} plan will be effective from <b>{format(new Date(billingInfo.plan_change_date!), 'do MMMM')} at 12:00 AM</b>.
                {(billingInfo.deferred_plan_type === 'GOLD' || billingInfo.deferred_plan_type === 'DIAMOND') && " Premium features will unlock then."}
              </p>
            </div>
            <Badge variant="outline" className="border-primary/30 text-primary">
              Effective {new Date(billingInfo.plan_change_date!).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' })}
            </Badge>
          </CardContent>
        </Card>
      )}

      {/* Subscription Tier Switcher - Concise Professional Redesign */}
      <Card className="border-none shadow-xl bg-card overflow-hidden ring-1 ring-border/50 relative">
        <div className={cn(
          "absolute -top-24 -right-24 w-48 h-48 blur-[80px] opacity-15 rounded-full",
          planType === 'DIAMOND' ? "bg-indigo-500" :
            planType === 'GOLD' ? "bg-primary" : "bg-muted"
        )} />

        <CardContent className="p-0 relative z-10">
          <div className="flex flex-col md:flex-row items-center divide-y md:divide-y-0 md:divide-x divide-border/40">
            {/* Plan Info Section */}
            <div className="flex-1 p-5 flex items-center gap-4 w-full">
              <div className={cn(
                "w-12 h-12 rounded-xl flex items-center justify-center shrink-0 shadow-md",
                planType === 'DIAMOND' ? "bg-indigo-500 text-white" :
                  planType === 'GOLD' ? "bg-primary text-white" : "bg-muted text-muted-foreground"
              )}>
                {planType === 'DIAMOND' ? <Gem className="h-6 w-6" /> :
                  planType === 'GOLD' ? <Trophy className="h-6 w-6" /> : <Smartphone className="h-6 w-6" />}
              </div>

              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <h3 className="text-xl font-black tracking-tight truncate">{planType} PLAN</h3>
                  <Badge className={cn(
                    "px-2 py-0 text-[9px] font-black uppercase tracking-wider rounded-full h-4 shrink-0",
                    planType === 'DIAMOND' ? "bg-indigo-500/10 text-indigo-500 border border-indigo-500/20" :
                      planType === 'GOLD' ? "bg-primary/10 text-primary border border-primary/20" : "bg-muted text-muted-foreground"
                  )} variant="outline">
                    Active
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground font-medium truncate max-w-[280px]">
                  {planType === 'DIAMOND' ? 'Elite business automation & logistics.' :
                    planType === 'GOLD' ? 'Professional digital growth tools.' :
                      'Essential digital presence.'}
                </p>
              </div>
            </div>

            {/* Investment Section */}
            <div className="p-5 flex flex-col justify-center min-w-[160px] w-full md:w-auto">
              <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">
                {planType === 'DIAMOND' ? 'Monthly Floor Guarantee' : 'Daily Floor'}
              </p>
              <p className="text-base font-bold">
                {planType === 'SILVER' ? '₹0' :
                  planType === 'GOLD' ? `₹${((billingInfo?.plan_defaults?.pro_monthly ?? 999) / 30).toFixed(0)}` :
                    `₹${billingInfo?.plan_defaults?.lux_monthly ?? 399}`}
              </p>
            </div>

            {/* Status Section */}
            <div className="p-5 flex flex-col justify-center min-w-[120px] w-full md:w-auto">
              <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">Status</p>
              <div className="flex items-center gap-1.5 text-emerald-500 font-bold">
                <ShieldCheck className="h-3.5 w-3.5" />
                <span className="text-xs">Verified</span>
              </div>
            </div>

            {/* Action Section */}
            <div className="p-5 flex items-center justify-center bg-muted/30 w-full md:w-auto">
              <div className="flex flex-col items-center gap-2">
                <Button
                  onClick={() => setShowComparison(true)}
                  size="sm"
                  className="gap-2 bg-foreground text-background hover:bg-foreground/90 font-bold px-6 h-9 rounded-lg shadow-sm"
                >
                  <Zap className="h-3.5 w-3.5" />
                  Manage Plan
                </Button>
                <button
                  onClick={() => setShowComparison(true)}
                  className="text-[9px] text-muted-foreground hover:text-foreground font-bold uppercase tracking-widest transition-colors"
                >
                  Compare Tiers
                </button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Balance Card */}
        <Card className="md:col-span-1 shadow-sm border-none bg-primary/10 dark:bg-primary/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium uppercase tracking-wider text-primary">Available Balance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Wallet className="h-8 w-8 text-primary" />
              <div className="text-4xl font-bold tracking-tighter">₹{(billingInfo?.coins_balance ?? 0).toLocaleString()}</div>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">Universal wallet balance for all platform charges.</p>
          </CardContent>
        </Card>

        {/* Mandate Status */}
        <Card className="md:col-span-2 shadow-sm border-none bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium uppercase tracking-wider text-muted-foreground">Autopay Mandate Status</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-full ${billingInfo?.mandate_active ? 'bg-emerald-500/10 text-emerald-600' : 'bg-amber-500/10 text-amber-600'}`}>
                {billingInfo?.mandate_active ? <ShieldCheck className="h-6 w-6" /> : <ShieldAlert className="h-6 w-6" />}
              </div>
              <div>
                <p className="font-bold text-lg">{billingInfo?.mandate_active ? 'Active' : 'Not Setup'}</p>
                <p className="text-xs text-muted-foreground">
                  {billingInfo?.mandate_active
                    ? 'Your account is linked for automatic top-ups.'
                    : 'Mandate required for automatic threshold-based recharging.'}
                </p>
              </div>
            </div>
            <Button
              variant={billingInfo?.mandate_active ? "outline" : "default"}
              onClick={handleSetupMandate}
              disabled={isSettingUpMandate}
            >
              {isSettingUpMandate ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Securing Connection...
                </>
              ) : (
                billingInfo?.mandate_active ? 'Update Card' : 'Setup Autopay'
              )}
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Main Settings */}
      <Card className="shadow-sm border-none bg-card overflow-hidden">
        <CardHeader className="border-b bg-muted/30">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-primary" />
                Automatic Top-up Settings
              </CardTitle>
              <CardDescription>Invisible billing to ensure your AI and Order flow stays uninterrupted.</CardDescription>
            </div>
            <div className="flex items-center gap-2 bg-background p-2 rounded-lg border shadow-sm">
              <Checkbox id="auto-recharge-toggle" checked={enabled} onCheckedChange={(checked) => setEnabled(!!checked)} />
              <Label htmlFor="auto-recharge-toggle" className="font-bold text-xs uppercase tracking-widest cursor-pointer">{enabled ? 'Enabled' : 'Disabled'}</Label>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-6 space-y-8">
          <div className={cn("grid gap-8 md:grid-cols-2 transition-all duration-300", !enabled && "opacity-60 grayscale-[0.5] pointer-events-none select-none")}>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label className="text-sm font-bold">Auto Top-up Threshold (₹)</Label>
                <div className="relative">
                  <IndianRupee className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                  <NumberInput

                    min="300"
                    className={cn(
                      "pl-9 bg-muted/30 border-transparent focus:bg-background focus:border-primary",
                      parseFloat(threshold) < 300 && "border-destructive focus:border-destructive"
                    )}
                    value={threshold}
                    onChange={(e: { target: { value: SetStateAction<string> } }) => setThreshold(e.target.value)}
                  />
                </div>
                {parseFloat(threshold) < 300 ? (
                  <p className="text-[11px] text-destructive flex items-center gap-1 font-medium animate-pulse">
                    <AlertCircle className="h-3 w-3" />
                    Minimum threshold must be ₹300 for system stability.
                  </p>
                ) : (
                  <p className="text-[11px] text-muted-foreground">Trigger recharge when balance drops below this amount.</p>
                )}
              </div>

              <div className="space-y-2">
                <Label className="text-sm font-bold">Top-up Amount (₹)</Label>
                <div className="relative">
                  <IndianRupee className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                  <NumberInput

                    min="500"
                    className={cn(
                      "pl-9 bg-muted/30 border-transparent focus:bg-background focus:border-primary",
                      parseFloat(amount) < 500 && "border-destructive focus:border-destructive"
                    )}
                    value={amount}
                    onChange={(e: { target: { value: SetStateAction<string> } }) => setAmount(e.target.value)}
                  />
                </div>
                {parseFloat(amount) < 500 ? (
                  <p className="text-[11px] text-destructive flex items-center gap-1 font-medium animate-pulse">
                    <AlertCircle className="h-3 w-3" />
                    Minimum recharge amount must be ₹500.
                  </p>
                ) : (
                  <p className="text-[11px] text-muted-foreground">Every time threshold is hit, we will recharge this much.</p>
                )}
              </div>
            </div>

            <div className="space-y-6">
              <div className="rounded-xl border p-4 bg-muted/20 space-y-4">
                <div className="flex items-center justify-between">
                  <Label className="text-xs font-bold uppercase text-muted-foreground">Daily Safety Limit</Label>
                  <Badge variant="secondary">₹{(billingInfo?.daily_limit ?? 0).toLocaleString()}</Badge>
                </div>
                <div className="space-y-1.5">
                  <div className="flex justify-between text-xs">
                    <span>Used Today: ₹{(billingInfo?.current_daily_vol ?? 0).toLocaleString()}</span>
                    <span>Remaining: ₹{((billingInfo?.daily_limit ?? 0) - (billingInfo?.current_daily_vol ?? 0)).toLocaleString()}</span>
                  </div>
                  <div className="h-1.5 w-full bg-background rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all"
                      style={{ width: `${((billingInfo?.current_daily_vol ?? 0) / (billingInfo?.daily_limit ?? 1)) * 100}%` }}
                    />
                  </div>
                </div>
                <p className="text-[10px] text-muted-foreground flex gap-1 items-start">
                  <Info className="h-3 w-3 shrink-0" />
                  This hard limit prevents runaway charges in case of high volume. Contact support to increase.
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between border-t pt-6">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <ShieldCheck className="h-4 w-4 text-emerald-500" />
              PCI-DSS Compliant • SSL Encrypted • Razorpay Secure
            </div>
            <Button
              className="gap-2"
              onClick={handleSaveSettings}
              disabled={isUpdating || (enabled && (parseFloat(threshold) < 300 || parseFloat(amount) < 500))}
            >
              {isUpdating && <Loader2 className="h-4 w-4 animate-spin" />}
              Save Configuration
            </Button>
          </div>
        </CardContent>
      </Card>

      <SubscriptionComparisonModal
        open={showComparison}
        onClose={() => setShowComparison(false)}
        currentPlan={planType as 'SILVER' | 'GOLD' | 'DIAMOND'}
        onSelectPlan={handlePlanToggle}
        isChangingPlan={isChangingPlan}
        planDefaults={{
          pro_monthly: billingInfo?.plan_defaults.pro_monthly || 999,
          lux_monthly: billingInfo?.plan_defaults.lux_monthly || 399,
          lux_commission: billingInfo?.plan_defaults.lux_commission || 1.5,
        }}
      />

      <AiRechargeModal
        open={showRecharge}
        onClose={() => setShowRecharge(false)}
        restaurant={selectedRestaurant!}
        onSuccess={loadInfo}
      />

      <ConfirmDialog
        open={showConfirm}
        onOpenChange={setShowConfirm}
        title={`Switch to ${newPlanSelection} plan?`}
        description={`Your ${newPlanSelection} plan will be effective from tomorrow ${format(addDays(new Date(), 1), 'do MMMM')} at 12:00 AM.`}
        confirmText="Yes, Switch Now"
        cancelText="Maybe Later"
        variant="info"
        onConfirm={confirmPlanChange}
        loading={isChangingPlan}
      />
    </div>
  )
}
