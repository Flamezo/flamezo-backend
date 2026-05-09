import { useState, useEffect } from 'react'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall, useFrappeGetDoc } from '@/lib/frappe'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'
import {
  Trophy, Zap, Globe, Gift, Users, ShieldCheck,
  TrendingUp, Percent, ArrowLeftRight, Info, Star, Clock, AlertTriangle
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter
} from '@/components/ui/dialog'

// ── DineMatters Platform Constants (display only — actual enforcement is backend) ─
const PLATFORM = {
  earn_percentage:          10,
  coin_value_in_inr:        1,
  max_coins_per_order:      1000,
  min_order_to_earn:        100,
  min_redemption_threshold: 250,
  min_billing_for_redemption: 200,
  loyalty_expiry_months:    6,
  welcome_reward_coins:     50,
  referral_share_coins:     30,
  max_opens_per_cycle:      10,
  tier: { silver: 500, gold: 2000, platinum: 5000 },
}

export default function LoyaltySettings() {
  const { selectedRestaurant, isSilver } = useRestaurant()
  const [saving, setSaving] = useState(false)
  const [enableLoyalty, setEnableLoyalty] = useState(false)
  const [showDisableConfirm, setShowDisableConfirm] = useState(false)

  const { data: restaurantDoc, mutate: mutateRestaurant } = useFrappeGetDoc(
    'Restaurant', selectedRestaurant || '',
    selectedRestaurant ? `Restaurant-${selectedRestaurant}` : null
  )
  const { call: updateLoyaltyConfig } = useFrappePostCall('dinematters.dinematters.api.loyalty.update_loyalty_config')

  useEffect(() => {
    if (restaurantDoc) setEnableLoyalty(!!restaurantDoc.enable_loyalty)
  }, [restaurantDoc])

  const saveSettings = async (newValue: boolean) => {
    if (!selectedRestaurant) return
    setSaving(true)
    try {
      const response: any = await updateLoyaltyConfig({
        restaurant_id: selectedRestaurant,
        enable_loyalty: newValue,
        config: {}   // No restaurant-configurable fields in centralized model
      })
      const body = response?.message || response?.data || response
      if (body?.success) {
        setEnableLoyalty(newValue)
        await mutateRestaurant()
        toast.success(newValue
          ? 'Loyalty enabled — your customers can now earn DineMatters Cash!'
          : 'Loyalty disabled. Ordering and Club listing have also been turned off.')
      } else {
        throw new Error(body?.error || 'Failed to save')
      }
    } catch (error: any) {
      toast.error(error.message || 'Failed to save settings')
      // Revert local state on failure
      setEnableLoyalty(!!restaurantDoc?.enable_loyalty)
    } finally {
      setSaving(false)
    }
  }

  // For Silver restaurants: intercept toggle-OFF with a confirmation modal
  const handleLoyaltyToggle = (checked: boolean) => {
    if (!checked && isSilver) {
      setShowDisableConfirm(true)
    } else {
      saveSettings(checked)
    }
  }

  const confirmDisableLoyalty = () => {
    setShowDisableConfirm(false)
    saveSettings(false)
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-12">

      {/* ── Silver: disable loyalty confirmation modal ───────────────── */}
      <Dialog open={showDisableConfirm} onOpenChange={setShowDisableConfirm}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <div className="flex items-center gap-3 mb-1">
              <div className="w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
              </div>
              <DialogTitle>Turn off loyalty?</DialogTitle>
            </div>
            <DialogDescription asChild>
              <div className="space-y-3 text-sm text-muted-foreground pt-1">
                <p>Disabling loyalty on your Silver plan will also:</p>
                <ul className="space-y-2">
                  <li className="flex items-start gap-2">
                    <span className="mt-0.5 text-red-500">✕</span>
                    <span><strong>Turn off ordering</strong> — customers won't be able to place orders via your QR menu.</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-0.5 text-red-500">✕</span>
                    <span><strong>Remove you from DineMatters Club</strong> — customers browsing the Club app won't find your restaurant.</span>
                  </li>
                </ul>
                <p className="pt-1 text-xs border-t border-border mt-2">
                  You can still use your DineMatters QR menu as a digital menu for customers.
                  Re-enable loyalty any time to restore ordering and Club listing.
                </p>
              </div>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setShowDisableConfirm(false)}>
              Keep loyalty on
            </Button>
            <Button variant="destructive" onClick={confirmDisableLoyalty}>
              Yes, disable loyalty & ordering
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Silver: info banner ──────────────────────────────────────── */}
      {isSilver && (
        <div className="flex items-start gap-3 p-4 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20">
          <Info className="w-4 h-4 text-blue-500 mt-0.5 shrink-0" />
          <p className="text-sm text-blue-700 dark:text-blue-300">
            On your Silver plan, <strong>loyalty and ordering are linked</strong>. Keeping loyalty on lets customers
            earn DineMatters Cash, place orders via your QR menu, and discover you on the Club app — all for free.
          </p>
        </div>
      )}

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <Trophy className="w-8 h-8 text-primary" />
            <h1 className="text-3xl font-bold tracking-tight text-foreground">Loyalty & Growth</h1>
            <Badge variant="secondary" className="text-xs font-semibold px-2 py-0.5 bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400 border border-orange-200 dark:border-orange-800">
              DineMatters Network
            </Badge>
          </div>
          <p className="text-muted-foreground mt-2">
            Platform-wide loyalty that rewards customers across every restaurant in the DineMatters network.
          </p>
        </div>

        {/* Master Toggle */}
        <div className="flex items-center gap-4 bg-muted/50 p-3 px-4 rounded-xl border h-14 shrink-0">
          <div className="flex flex-col">
            <Label htmlFor="enable-loyalty" className="text-sm font-semibold">Join Loyalty Network</Label>
            <p className="text-[10px] text-muted-foreground">
              {saving ? <span className="text-primary animate-pulse font-medium">Saving...</span> : 'Enable for your restaurant'}
            </p>
          </div>
          <Switch
            id="enable-loyalty"
            checked={enableLoyalty}
            onCheckedChange={handleLoyaltyToggle}
            disabled={saving}
          />
        </div>
      </div>

      {/* ── Status Banner ────────────────────────────────────────────── */}
      {!enableLoyalty ? (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex gap-3 text-amber-900 dark:bg-amber-900/10 dark:border-amber-900/20 dark:text-amber-400">
          <Info className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <p className="text-sm">
            Loyalty is currently <strong>disabled</strong>. Customers visiting your restaurant won't earn
            DineMatters Cash. Enable it above to join the network and attract repeat customers.
          </p>
        </div>
      ) : (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex gap-3 text-green-900 dark:bg-green-900/10 dark:border-green-900/20 dark:text-green-400">
          <ShieldCheck className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <p className="text-sm">
            Your restaurant is <strong>active on the DineMatters Loyalty Network</strong>. Customers earn cash
            on every order and can discover your restaurant through the explore feed.
          </p>
        </div>
      )}

      <div className={cn('space-y-6 transition-opacity duration-300', !enableLoyalty && 'opacity-50')}>

        {/* ── Network Value Proposition ────────────────────────────────── */}
        <Card className="border-2 border-primary/20 bg-gradient-to-br from-primary/5 via-background to-orange-500/5">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Globe className="w-5 h-5 text-primary" />
              How DineMatters Loyalty Works
            </CardTitle>
            <CardDescription>
              One wallet. Every restaurant. Your customers earn and spend across the entire network.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="flex flex-col gap-2 p-4 rounded-xl bg-background border">
                <div className="w-8 h-8 rounded-full bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center">
                  <Percent className="w-4 h-4 text-orange-600 dark:text-orange-400" />
                </div>
                <p className="text-sm font-semibold">Customer Earns</p>
                <p className="text-2xl font-bold text-primary">10% Cash</p>
                <p className="text-xs text-muted-foreground">on every qualifying order at your restaurant</p>
              </div>
              <div className="flex flex-col gap-2 p-4 rounded-xl bg-background border">
                <div className="w-8 h-8 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                  <ArrowLeftRight className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                </div>
                <p className="text-sm font-semibold">Spend Anywhere</p>
                <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">1 Cash = ₹1</p>
                <p className="text-xs text-muted-foreground">across any DineMatters partner restaurant</p>
              </div>
              <div className="flex flex-col gap-2 p-4 rounded-xl bg-background border">
                <div className="w-8 h-8 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                  <Users className="w-4 h-4 text-green-600 dark:text-green-400" />
                </div>
                <p className="text-sm font-semibold">You Get</p>
                <p className="text-2xl font-bold text-green-600 dark:text-green-400">New Diners</p>
                <p className="text-xs text-muted-foreground">from across the network discovering your restaurant</p>
              </div>
            </div>

            <div className="mt-4 rounded-lg bg-muted/50 border p-3 flex items-start gap-2">
              <TrendingUp className="w-4 h-4 text-primary mt-0.5 shrink-0" />
              <p className="text-xs text-muted-foreground">
                <strong className="text-foreground">The DineMatters Settlement Model:</strong> When a customer
                redeems cash earned at another restaurant at <em>yours</em>, you're not paying a fee —
                you're gaining a customer who discovered you through the network. That discovery is the value.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* ── Platform Rates (Read-Only) ───────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Zap className="w-4 h-4 text-orange-500" />
                Earning Rules
              </CardTitle>
              <CardDescription>Applied uniformly across the entire network</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {[
                { label: 'Earn Rate',           value: `${PLATFORM.earn_percentage}% of bill` },
                { label: 'Min. Order to Earn',  value: `₹${PLATFORM.min_order_to_earn}` },
                { label: 'Max. Cash per Order', value: `₹${PLATFORM.max_coins_per_order}` },
                { label: 'Cash Expiry',         value: `${PLATFORM.loyalty_expiry_months} months` },
              ].map(({ label, value }) => (
                <div key={label} className="flex items-center justify-between py-1.5 border-b last:border-0">
                  <span className="text-sm text-muted-foreground">{label}</span>
                  <span className="text-sm font-semibold tabular-nums">{value}</span>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Gift className="w-4 h-4 text-blue-500" />
                Redemption Rules
              </CardTitle>
              <CardDescription>Protects against micro-redemptions and abuse</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {[
                { label: 'Coin Value',            value: `1 Cash = ₹${PLATFORM.coin_value_in_inr}` },
                { label: 'Min. Wallet to Redeem', value: `₹${PLATFORM.min_redemption_threshold}` },
                { label: 'Min. Bill to Redeem',   value: `₹${PLATFORM.min_billing_for_redemption}` },
              ].map(({ label, value }) => (
                <div key={label} className="flex items-center justify-between py-1.5 border-b last:border-0">
                  <span className="text-sm text-muted-foreground">{label}</span>
                  <span className="text-sm font-semibold tabular-nums">{value}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        {/* ── Growth & Referral ────────────────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Star className="w-4 h-4 text-yellow-500" />
                Referral Rewards
              </CardTitle>
              <CardDescription>Drive viral growth — every customer becomes a promoter</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {[
                { label: 'Welcome Bonus (new user)',  value: `₹${PLATFORM.welcome_reward_coins} Cash` },
                { label: 'Referrer Reward / open',    value: `₹${PLATFORM.referral_share_coins} Cash` },
                { label: 'Max Rewards per Cycle',     value: `${PLATFORM.max_opens_per_cycle} opens` },
              ].map(({ label, value }) => (
                <div key={label} className="flex items-center justify-between py-1.5 border-b last:border-0">
                  <span className="text-sm text-muted-foreground">{label}</span>
                  <span className="text-sm font-semibold tabular-nums">{value}</span>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Trophy className="w-4 h-4 text-amber-500" />
                Customer Tiers
              </CardTitle>
              <CardDescription>Global tiers based on lifetime Cash earned across all restaurants</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {[
                { tier: 'Bronze',   threshold: '0',                              color: 'text-amber-700 bg-amber-100 dark:bg-amber-900/30' },
                { tier: 'Silver',   threshold: `₹${PLATFORM.tier.silver}+`,     color: 'text-slate-600 bg-slate-100 dark:bg-slate-800' },
                { tier: 'Gold',     threshold: `₹${PLATFORM.tier.gold}+`,       color: 'text-yellow-600 bg-yellow-100 dark:bg-yellow-900/30' },
                { tier: 'Platinum', threshold: `₹${PLATFORM.tier.platinum}+`,   color: 'text-purple-600 bg-purple-100 dark:bg-purple-900/30' },
              ].map(({ tier, threshold, color }) => (
                <div key={tier} className="flex items-center justify-between py-1">
                  <span className={cn('text-xs font-bold px-2 py-0.5 rounded-full', color)}>{tier}</span>
                  <span className="text-xs text-muted-foreground">{threshold} lifetime earnings</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        {/* ── Platform Policy ──────────────────────────────────────────── */}
        <Card className="bg-muted/30 border-dashed">
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2 text-muted-foreground">
              <ShieldCheck className="w-4 h-4" />
              DineMatters Platform Policy
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground space-y-2">
            <p>• All earn and redemption rates are <strong>fixed platform-wide</strong> — uniform, fair, and fraud-resistant across all network restaurants.</p>
            <p>• <strong>Fraud protection:</strong> Phone verification required for all referral rewards. IP + browser fingerprinting on referral opens.</p>
            <p>• <strong>Settlement:</strong> No monetary charge per redemption. You gain new diners from the network; that discovery is the value exchange.</p>
            <p>• Changes to platform rates apply to future transactions only. Existing earned Cash is never affected.</p>
            <p className="flex items-center gap-1.5"><Clock className="w-3 h-3" /> To request a rate review, contact the DineMatters partner team.</p>
          </CardContent>
        </Card>
      </div>

    </div>
  )
}
