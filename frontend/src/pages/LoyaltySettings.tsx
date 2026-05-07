import { useState, useEffect, useMemo } from 'react'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall, useFrappeGetDoc } from '@/lib/frappe'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { NumberInput } from "@/components/ui/number-input"
import { toast } from 'sonner'
import { Coins, Share2, TrendingUp, Info, Trophy, Zap, AlertCircle, CheckCircle2 } from 'lucide-react'
import { LockedFeature } from '@/components/FeatureGate/LockedFeature'
import { cn } from '@/lib/utils'
import { Switch } from '@/components/ui/switch'

// ── DineMatters Platform Guardrails (mirrored from backend) ───────────────────
// These are displayed to the restaurant owner as allowed ranges.
const GUARDRAILS = {
  earn_percentage:               { min: 1,    max: 15,   label: '1% – 15%' },
  earn_flat_coins:               { min: 5,    max: 500,  label: '5 – 500 cash' },
  min_order_to_earn:             { min: 0,    max: 2000, label: '₹0 – ₹2,000' },
  max_coins_per_order:           { min: 10,   max: 1000, label: '10 – 1,000 cash' },
  min_billing_for_redemption:    { min: 0,    max: 5000, label: '₹0 – ₹5,000' },
  min_redemption_threshold:      { min: 0,    max: 5000, label: '0 – 5,000 cash' },
  share_reward_coins:            { min: 0,    max: 500,  label: '0 – 500 cash' },
  referral_order_reward_coins:   { min: 0,    max: 1000, label: '0 – 1,000 cash' },
  new_user_welcome_reward_coins: { min: 0,    max: 500,  label: '0 – 500 cash' },
  max_opens_rewarded_per_share:  { min: 1,    max: 50,   label: '1 – 50' },
  coins_per_unique_open:         { min: 1,    max: 100,  label: '1 – 100 cash' },
}

type EarnType = 'Percentage of Bill' | 'Flat Cash per Order'

interface FieldError { field: string; message: string }

export default function LoyaltySettings() {
  const { selectedRestaurant, isDiamond } = useRestaurant()
  const [saving, setSaving] = useState(false)
  const [enableLoyalty, setEnableLoyalty] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldError[]>([])

  const [settings, setSettings] = useState({
    earn_type: 'Percentage of Bill' as EarnType,
    earn_percentage: 5,
    earn_flat_coins: 50,
    min_order_to_earn: 0,
    max_coins_per_order: 500,
    min_redemption_threshold: 100,
    min_billing_for_redemption: 200,
    share_reward_coins: 20,
    min_unique_opens_for_reward: 2,
    coins_per_unique_open: 30,
    max_opens_rewarded_per_share: 7,
    referral_order_reward_coins: 100,
    new_user_welcome_reward_coins: 50,
    welcome_coupon_discount: 0
  })

  const { data: restaurantDoc, mutate: mutateRestaurant } = useFrappeGetDoc(
    'Restaurant', selectedRestaurant || '',
    selectedRestaurant ? `Restaurant-${selectedRestaurant}` : null
  )
  const { call: getLoyaltyConfig } = useFrappePostCall('dinematters.dinematters.api.loyalty.get_loyalty_config')
  const { call: updateLoyaltyConfig } = useFrappePostCall('dinematters.dinematters.api.loyalty.update_loyalty_config')

  useEffect(() => {
    if (restaurantDoc) setEnableLoyalty(!!restaurantDoc.enable_loyalty)
  }, [restaurantDoc])

  useEffect(() => {
    if (!selectedRestaurant) return
    getLoyaltyConfig({ restaurant_id: selectedRestaurant }).then((res: any) => {
      const config = res?.message?.data || res?.data?.data
      if (!config) return
      setSettings(prev => ({
        ...prev,
        // New fields (with backward compat: if earn_type missing, infer from points_per_inr)
        earn_type: config.earn_type || 'Percentage of Bill',
        earn_percentage: config.earn_percentage ?? (config.points_per_inr ? config.points_per_inr * 100 : 5),
        earn_flat_coins: config.earn_flat_coins ?? 50,
        min_order_to_earn: config.min_order_to_earn ?? 0,
        max_coins_per_order: config.max_coins_per_order ?? 500,
        // Existing fields
        min_redemption_threshold: config.min_redemption_threshold ?? 100,
        min_billing_for_redemption: config.min_billing_for_redemption ?? 200,
        share_reward_coins: config.share_reward_coins ?? 20,
        min_unique_opens_for_reward: config.min_unique_opens_for_reward ?? 2,
        coins_per_unique_open: config.coins_per_unique_open ?? 30,
        max_opens_rewarded_per_share: config.max_opens_rewarded_per_share ?? 7,
        referral_order_reward_coins: config.referral_order_reward_coins ?? 100,
        new_user_welcome_reward_coins: config.new_user_welcome_reward_coins ?? 50,
        welcome_coupon_discount: config.welcome_coupon_discount ?? 0,
      }))
    })
  }, [selectedRestaurant])

  // ── Live preview calculation ──────────────────────────────────────────────
  const livePreview = useMemo(() => {
    const sampleOrder = 1000
    let cash = 0
    if (settings.earn_type === 'Flat Cash per Order') {
      cash = settings.earn_flat_coins
    } else {
      cash = Math.floor(sampleOrder * (settings.earn_percentage / 100))
    }
    cash = Math.min(cash, settings.max_coins_per_order)
    const qualifies = settings.min_order_to_earn === 0 || sampleOrder >= settings.min_order_to_earn
    return { cash, qualifies, sampleOrder }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.earn_type, settings.earn_percentage, settings.earn_flat_coins, settings.min_order_to_earn, settings.max_coins_per_order])

  // ── Inline guardrail validation ───────────────────────────────────────────
  const getFieldError = (field: string): string | null => {
    const err = fieldErrors.find(e => e.field === field)
    return err ? err.message : null
  }

  const validateField = (field: keyof typeof GUARDRAILS, value: number) => {
    const rules = GUARDRAILS[field]
    if (!rules) return
    const newErrors = fieldErrors.filter(e => e.field !== field)
    if (value < rules.min || value > rules.max) {
      newErrors.push({ field, message: `Allowed: ${rules.label}` })
    }
    setFieldErrors(newErrors)
  }

  const handleNumberChange = (field: keyof typeof settings, value: string) => {
    const num = parseFloat(value)
    const safeNum = isNaN(num) ? 0 : num
    setSettings(prev => ({ ...prev, [field]: safeNum }))
    if (field in GUARDRAILS) validateField(field as keyof typeof GUARDRAILS, safeNum)
  }

  const handleSave = async () => {
    if (!selectedRestaurant) return
    if (fieldErrors.length > 0) {
      toast.error('Please fix the highlighted errors before saving.')
      return
    }
    setSaving(true)
    try {
      const response: any = await updateLoyaltyConfig({
        restaurant_id: selectedRestaurant,
        enable_loyalty: enableLoyalty,
        config: { ...settings, coin_value_in_inr: 1 }
      })
      const body = response?.message || response?.data || response
      if (body?.success) {
        await mutateRestaurant()
        toast.success('Loyalty settings saved successfully')
      } else {
        const err = body?.error
        if (err?.code === 'GUARDRAIL_VIOLATION') {
          toast.error(`Validation error: ${err.messages?.[0]}`)
        } else {
          throw new Error(typeof err === 'string' ? err : err?.message || 'Failed to save settings')
        }
      }
    } catch (error: any) {
      toast.error(error.message || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  if (!isDiamond) return <LockedFeature feature="loyalty" requiredPlan={['DIAMOND']} />

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <Trophy className="w-8 h-8 text-primary" />
            <h1 className="text-3xl font-bold tracking-tight text-foreground">Loyalty & Growth</h1>
          </div>
          <p className="text-muted-foreground mt-2">
            Enterprise reward and referral engine to drive repeat business and viral growth.
          </p>
        </div>
        {/* Single Master Toggle */}
        <div className="flex items-center gap-3 bg-muted/50 p-3 px-4 rounded-xl border h-14">
          <div className="flex flex-col">
            <Label htmlFor="enable-loyalty" className="text-sm font-semibold">Enable Loyalty Engine</Label>
            <p className="text-[10px] text-muted-foreground">Turns all loyalty features on/off</p>
          </div>
          <Switch
            id="enable-loyalty"
            checked={enableLoyalty}
            onCheckedChange={setEnableLoyalty}
          />
        </div>
      </div>

      {!enableLoyalty && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex gap-3 text-amber-900 dark:bg-amber-900/10 dark:border-amber-900/20 dark:text-amber-400">
          <Info className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <p className="text-sm">Loyalty engine is currently <strong>disabled</strong>. Customers won't earn cash or see the loyalty wallet. Toggle it on above to activate.</p>
        </div>
      )}

      <div className={cn('space-y-6 transition-opacity duration-300', !enableLoyalty && 'opacity-40 pointer-events-none')}>
        {/* ── Earning Configuration ─────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Coins className="w-5 h-5 text-orange-500" />
              Earning Configuration
            </CardTitle>
            <CardDescription>Define how customers earn cash on every order.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Earn Mode Toggle */}
            <div className="space-y-2">
              <Label className="text-sm font-medium">Earn Mode</Label>
              <div className="grid grid-cols-2 gap-2 p-1 bg-muted rounded-lg max-w-sm">
                {(['Percentage of Bill', 'Flat Cash per Order'] as EarnType[]).map(mode => (
                  <button
                    key={mode}
                    onClick={() => setSettings(p => ({ ...p, earn_type: mode }))}
                    className={cn(
                      'px-3 py-2 rounded-md text-xs font-semibold transition-all duration-200',
                      settings.earn_type === mode
                        ? 'bg-background shadow text-foreground'
                        : 'text-muted-foreground hover:text-foreground'
                    )}
                  >
                    {mode === 'Percentage of Bill' ? '% of Bill' : 'Flat Cash'}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Dynamic earn rate input */}
              {settings.earn_type === 'Percentage of Bill' ? (
                <div className="grid gap-2">
                  <Label className="flex items-center gap-1.5 text-sm font-medium">
                    Earn Percentage (%)
                    <span className="text-[10px] text-muted-foreground font-normal">Allowed: {GUARDRAILS.earn_percentage.label}</span>
                  </Label>
                  <div className="relative">
                    <NumberInput
                      value={settings.earn_percentage}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleNumberChange('earn_percentage', e.target.value)}
                      className={cn(getFieldError('earn_percentage') && 'border-destructive')}
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm font-bold">%</span>
                  </div>
                  {getFieldError('earn_percentage') && (
                    <p className="text-[11px] text-destructive flex items-center gap-1"><AlertCircle className="w-3 h-3" />{getFieldError('earn_percentage')}</p>
                  )}
                  <p className="text-[11px] text-muted-foreground">e.g. 5% → Customer earns ₹5 of cash per ₹100 spent</p>
                </div>
              ) : (
                <div className="grid gap-2">
                  <Label className="flex items-center gap-1.5 text-sm font-medium">
                    Flat Cash per Order
                    <span className="text-[10px] text-muted-foreground font-normal">Allowed: {GUARDRAILS.earn_flat_coins.label}</span>
                  </Label>
                  <NumberInput
                    value={settings.earn_flat_coins}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleNumberChange('earn_flat_coins', e.target.value)}
                    className={cn(getFieldError('earn_flat_coins') && 'border-destructive')}
                  />
                  {getFieldError('earn_flat_coins') && (
                    <p className="text-[11px] text-destructive flex items-center gap-1"><AlertCircle className="w-3 h-3" />{getFieldError('earn_flat_coins')}</p>
                  )}
                  <p className="text-[11px] text-muted-foreground">Fixed cash given on every qualifying order, regardless of order size.</p>
                </div>
              )}

              <div className="grid gap-2">
                <Label className="flex items-center gap-1.5 text-sm font-medium">
                  Min. Order to Earn (₹)
                  <span className="text-[10px] text-muted-foreground font-normal">Allowed: {GUARDRAILS.min_order_to_earn.label}</span>
                </Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm font-medium">₹</span>
                  <NumberInput
                    className={cn('pl-7', getFieldError('min_order_to_earn') && 'border-destructive')}
                    value={settings.min_order_to_earn}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleNumberChange('min_order_to_earn', e.target.value)}
                  />
                </div>
                {getFieldError('min_order_to_earn') && (
                  <p className="text-[11px] text-destructive flex items-center gap-1"><AlertCircle className="w-3 h-3" />{getFieldError('min_order_to_earn')}</p>
                )}
                <p className="text-[11px] text-muted-foreground">Orders below this value earn zero cash. Set to 0 to always earn.</p>
              </div>

              <div className="grid gap-2">
                <Label className="flex items-center gap-1.5 text-sm font-medium">
                  Max Cash per Order
                  <span className="text-[10px] text-muted-foreground font-normal">Allowed: {GUARDRAILS.max_coins_per_order.label}</span>
                </Label>
                <NumberInput
                  value={settings.max_coins_per_order}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleNumberChange('max_coins_per_order', e.target.value)}
                  className={cn(getFieldError('max_coins_per_order') && 'border-destructive')}
                />
                {getFieldError('max_coins_per_order') && (
                  <p className="text-[11px] text-destructive flex items-center gap-1"><AlertCircle className="w-3 h-3" />{getFieldError('max_coins_per_order')}</p>
                )}
                <p className="text-[11px] text-muted-foreground">Hard cap per transaction. Prevents excess cash accumulation on high-value orders.</p>
              </div>

              <div className="grid gap-2">
                <Label className="text-sm font-medium">Min. Bill to Redeem (₹)</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm font-medium">₹</span>
                  <NumberInput className="pl-7" value={settings.min_billing_for_redemption} onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleNumberChange('min_billing_for_redemption', e.target.value)} />
                </div>
                <p className="text-[11px] text-muted-foreground">Minimum order value required to redeem cash.</p>
              </div>

              <div className="grid gap-2">
                <Label className="text-sm font-medium">Min. Cash to Redeem</Label>
                <NumberInput value={settings.min_redemption_threshold} onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleNumberChange('min_redemption_threshold', e.target.value)} />
                <p className="text-[11px] text-muted-foreground">Minimum cash in wallet before customer can redeem.</p>
              </div>
            </div>

            {/* Live Preview Box */}
            <div className={cn(
              'rounded-xl border p-4 flex items-start gap-4 transition-colors',
              livePreview.qualifies ? 'bg-green-50 border-green-200 dark:bg-green-900/10 dark:border-green-900/30' : 'bg-orange-50 border-orange-200 dark:bg-orange-900/10 dark:border-orange-900/30'
            )}>
              <div className={cn('mt-0.5', livePreview.qualifies ? 'text-green-600' : 'text-orange-500')}>
                {livePreview.qualifies ? <CheckCircle2 className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
              </div>
              <div>
                <p className={cn('text-sm font-semibold', livePreview.qualifies ? 'text-green-800 dark:text-green-300' : 'text-orange-800 dark:text-orange-300')}>
                  Live Preview — ₹{livePreview.sampleOrder.toLocaleString()} order
                </p>
                {livePreview.qualifies ? (
                  <p className="text-sm text-muted-foreground mt-0.5">
                    Customer earns <strong className="text-foreground">{livePreview.cash} cash (₹{livePreview.cash} value)</strong>
                    {livePreview.cash === settings.max_coins_per_order && (
                      <span className="text-orange-500 ml-2 text-xs">(capped at max)</span>
                    )}
                  </p>
                ) : (
                  <p className="text-sm text-muted-foreground mt-0.5">
                    Order doesn't qualify — minimum order is ₹{settings.min_order_to_earn}
                  </p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ── Referral & Growth ─────────────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Share2 className="w-5 h-5 text-blue-500" />
                Referral (Viral Growth)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="rounded-lg border border-blue-100 bg-blue-50/50 dark:bg-blue-900/10 dark:border-blue-900/20 p-3">
                <p className="text-[11px] text-muted-foreground">
                  Rewards given for <strong>Unique Opens</strong> only. Limit resets after each new order.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label className="text-[11px] font-medium">Max Rewards / Cycle</Label>
                  <NumberInput value={settings.max_opens_rewarded_per_share} onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleNumberChange('max_opens_rewarded_per_share', e.target.value)} />
                  <p className="text-[10px] text-muted-foreground">Allowed: {GUARDRAILS.max_opens_rewarded_per_share.label}</p>
                </div>
                <div className="grid gap-2">
                  <Label className="text-[11px] font-medium">Cash / Unique Open</Label>
                  <NumberInput value={settings.coins_per_unique_open} onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleNumberChange('coins_per_unique_open', e.target.value)} />
                  <p className="text-[10px] text-muted-foreground">Allowed: {GUARDRAILS.coins_per_unique_open.label}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-green-500" />
                Growth & Conversion Rewards
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-2">
                <Label className="text-sm font-medium">Referrer Bonus (when friend orders)</Label>
                <NumberInput value={settings.referral_order_reward_coins} onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleNumberChange('referral_order_reward_coins', e.target.value)} />
                <p className="text-[11px] text-muted-foreground">Allowed: {GUARDRAILS.referral_order_reward_coins.label}</p>
              </div>
              <div className="grid gap-2">
                <Label className="text-sm font-medium">New User Welcome Cash</Label>
                <NumberInput value={settings.new_user_welcome_reward_coins} onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleNumberChange('new_user_welcome_reward_coins', e.target.value)} />
                <p className="text-[11px] text-muted-foreground">Allowed: {GUARDRAILS.new_user_welcome_reward_coins.label}</p>
              </div>
              <div className="grid gap-2">
                <Label className="text-sm font-medium">Welcome Discount (₹)</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm font-medium">₹</span>
                  <NumberInput className="pl-7" value={settings.welcome_coupon_discount} onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleNumberChange('welcome_coupon_discount', e.target.value)} />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* ── Platform Policy (Read-Only) ───────────────────────────── */}
        <Card className="bg-muted/30 border-dashed">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2 text-muted-foreground">
              <Zap className="w-4 h-4" />
              DineMatters Platform Policy
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground space-y-2">
            <p>• <strong>1 Cash = ₹1</strong> — Fixed platform value. Non-configurable.</p>
            <p>• All earn rates are bounded by DineMatters guardrails to protect your margins.</p>
            <p>• Fraud protection: IP & browser fingerprinting on referral opens.</p>
            <p>• Changes apply to future transactions only. Existing earned cash are unaffected.</p>
          </CardContent>
        </Card>
      </div>

      <div className="flex justify-end pt-6 border-t border-border">
        <Button size="lg" onClick={handleSave} disabled={saving || fieldErrors.length > 0} className="px-12 font-semibold shadow-sm h-12">
          {saving ? 'Saving...' : 'Save Loyalty Settings'}
        </Button>
      </div>
    </div>
  )
}
