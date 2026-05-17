import { useState, useEffect } from 'react'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall, useFrappeGetDoc } from '@/lib/frappe'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from 'sonner'
import { Truck, Percent, Info, Coins, CheckCircle2, Wallet, User } from 'lucide-react'

type Provider = 'Borzo' | 'Flash' | 'Self'


export default function LogisticsHub() {
  const { selectedRestaurant } = useRestaurant()
  const [saving, setSaving] = useState(false)
  const [settings, setSettings] = useState({
    preferred_logistics_provider: 'Flash' as Provider,
    delivery_markup_type: 'Fixed',
    delivery_markup_value: 0,
    default_delivery_fee: 0
  })

  const { data: restaurantDoc, isValidating, mutate } = useFrappeGetDoc(
    'Restaurant',
    selectedRestaurant || '',
    selectedRestaurant ? `Restaurant-Logistics-${selectedRestaurant}` : null
  )

  useEffect(() => {
    if (restaurantDoc) {
      setSettings({
        preferred_logistics_provider: (restaurantDoc.preferred_logistics_provider || 'Flash') as Provider,
        delivery_markup_type: restaurantDoc.delivery_markup_type || 'Fixed',
        delivery_markup_value: restaurantDoc.delivery_markup_value || 0,
        default_delivery_fee: restaurantDoc.default_delivery_fee || 0
      })
    }
  }, [restaurantDoc])

  const { call: updateSettings } = useFrappePostCall<{ success: boolean; data: any }>(
    'flamezo_backend.flamezo.api.config.update_logistics_settings'
  )

  const handleSave = async () => {
    if (!selectedRestaurant) return
    setSaving(true)
    try {
      const response: any = await updateSettings({
        restaurant_id: selectedRestaurant,
        settings: {
          preferred_logistics_provider: settings.preferred_logistics_provider,
          delivery_markup_type: settings.delivery_markup_type,
          delivery_markup_value: settings.delivery_markup_value,
          default_delivery_fee: settings.default_delivery_fee
        }
      })
      const body = response?.message ?? response
      if (body?.success) {
        await mutate()
        toast.success('Logistics settings saved successfully')
      } else {
        throw new Error(body?.error?.message || 'Failed to save settings')
      }
    } catch (error: any) {
      toast.error(error.message || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const handleNumberChange = (field: keyof typeof settings, value: string) => {
    const num = parseFloat(value)
    setSettings(prev => ({ ...prev, [field]: isNaN(num) || num < 0 ? 0 : num }))
  }

  const isSelf = settings.preferred_logistics_provider === 'Self'
  const platformFee = isSelf ? 0 : 5
  const courierEstimate = isSelf ? 0 : 40

  const markupAmount = isSelf
    ? settings.default_delivery_fee // For self, this is the fee
    : settings.delivery_markup_type === 'Percentage'
    ? (courierEstimate * settings.delivery_markup_value) / 100
    : settings.delivery_markup_value

  const packagingFee = restaurantDoc?.default_packaging_fee || 0
  const totalCustomerPays = courierEstimate + markupAmount + platformFee + packagingFee
  const coinsDeducted = courierEstimate + platformFee

  if (isValidating && !restaurantDoc) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-1">
        <h1 className="text-3xl font-bold tracking-tight">Logistics Hub & Revenue Engine</h1>
        <p className="text-muted-foreground">
          Choose how you fulfill deliveries and configure your profit margins.
        </p>
      </div>

      {/* How it works — adapts to provider */}
      <Card className="bg-primary/5 border-primary/20">
        <CardContent className="pt-6">
          <div className="flex gap-3">
            <Info className="h-5 w-5 text-primary shrink-0 mt-0.5" />
            <div className="space-y-3 w-full">
              <h4 className="font-semibold text-primary">
                {isSelf ? 'Self / Manual Delivery Model' : 'Managed Logistics Model (Borzo / Flash)'}
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                {isSelf ? (
                  <>
                    <div className="flex gap-2 items-start">
                      <span className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-bold shrink-0">1</span>
                      <span className="text-muted-foreground"><strong>Customer pays</strong> your fixed delivery fee at checkout</span>
                    </div>
                    <div className="flex gap-2 items-start">
                      <span className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-bold shrink-0">2</span>
                      <span className="text-muted-foreground"><strong>Your rider</strong> picks up and delivers the order manually</span>
                    </div>
                    <div className="flex gap-2 items-start">
                      <span className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-bold shrink-0">3</span>
                      <span className="text-muted-foreground"><strong>No coins deducted</strong> — you manage your own delivery economics</span>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="flex gap-2 items-start">
                      <span className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-bold shrink-0">1</span>
                      <span className="text-muted-foreground"><strong>Customer pays</strong> delivery fee (Courier + Your Markup + ₹5 Platform fee)</span>
                    </div>
                    <div className="flex gap-2 items-start">
                      <span className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-bold shrink-0">2</span>
                      <span className="text-muted-foreground"><strong>Flamezo dispatches</strong> the rider from the shared provider account</span>
                    </div>
                    <div className="flex gap-2 items-start">
                      <span className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-bold shrink-0">3</span>
                      <span className="text-muted-foreground"><strong>Coins are deducted</strong> (Courier Cost + ₹5). Your markup is pure profit.</span>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Provider Selection */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Truck className="w-5 h-5 text-primary" />
              <CardTitle>Delivery Provider</CardTitle>
            </div>
            <CardDescription>Choose how your deliveries are fulfilled</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Preferred Provider</Label>
              <Select
                value={settings.preferred_logistics_provider}
                onValueChange={val => setSettings(prev => ({ ...prev, preferred_logistics_provider: val as Provider }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Borzo">🛵 Borzo (Local Courier)</SelectItem>
                  <SelectItem value="Flash">⚡ uEngage Flash (Aggregator)</SelectItem>
                  <SelectItem value="Self">🚶 Self / Own Riders (Manual)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Status badge  */}
            {isSelf ? (
              <div className="rounded-lg border bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-900 p-3 flex gap-2 text-sm">
                <User className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium text-blue-700 dark:text-blue-300">Manual Delivery Mode</p>
                  <p className="text-blue-600/80 dark:text-blue-400/80 text-xs mt-0.5">
                    Your team handles all deliveries. The "Book Rider" button in Order Detail will mark the delivery as manually assigned.
                  </p>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border bg-muted/40 p-3 flex gap-2 text-sm">
                <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium">Fully Managed by Flamezo</p>
                  <p className="text-muted-foreground text-xs mt-0.5">
                    Provider credentials, store ID, and dispatch are managed centrally. No setup required on your end.
                  </p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Delivery Fee / Markup */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Percent className="w-5 h-5 text-primary" />
              <CardTitle>{isSelf ? 'Delivery Fee (Your Charge)' : 'Logistics Markup (Your Profit)'}</CardTitle>
            </div>
            <CardDescription>
              {isSelf
                ? 'Set a flat delivery fee your customers will pay'
                : 'Earn additional revenue on top of the courier cost'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!isSelf && (
              <div className="space-y-2">
                <Label>Markup Type</Label>
                <Select
                  value={settings.delivery_markup_type}
                  onValueChange={val => setSettings(prev => ({ ...prev, delivery_markup_type: val }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Fixed">Fixed Amount (₹)</SelectItem>
                    <SelectItem value="Percentage">Percentage of Courier Fee (%)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="space-y-2">
              <Label>{isSelf ? 'Flat Delivery Charge' : 'Markup Value'}</Label>
              <div className="flex items-center rounded-md border border-input bg-background overflow-hidden px-3 h-10">
                {(isSelf || settings.delivery_markup_type === 'Fixed') && (
                  <span className="text-muted-foreground mr-2 text-sm">₹</span>
                )}
                <NumberInput
                  
                  min="0"
                  className="border-0 shadow-none focus-visible:ring-0 p-0"
                  value={isSelf ? (settings.default_delivery_fee || '') : (settings.delivery_markup_value || '')}
                  onChange={e => handleNumberChange(isSelf ? 'default_delivery_fee' : 'delivery_markup_value', e.target.value)}
                />
                {!isSelf && settings.delivery_markup_type === 'Percentage' && (
                  <span className="text-muted-foreground ml-2 text-sm">%</span>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                {isSelf
                  ? `₹${settings.default_delivery_fee} is shown to the customer as the delivery fee.`
                  : settings.delivery_markup_type === 'Fixed'
                  ? `₹${settings.delivery_markup_value} added to every delivery. Your margin.`
                  : `${settings.delivery_markup_value}% of courier cost added as your profit.`}
              </p>
            </div>
          </CardContent>
        </Card>


        {/* Live Fee Breakdown */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Wallet className="w-5 h-5 text-primary" />
              <CardTitle>Live Fee Breakdown</CardTitle>
            </div>
            <CardDescription>
              {isSelf ? 'What the customer pays for delivery' : 'Illustrative estimate (courier fee varies by distance)'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {!isSelf && (
              <div className="flex justify-between py-1 border-b">
                <span className="text-muted-foreground">Courier Fee (estimated)</span>
                <span>₹{courierEstimate}</span>
              </div>
            )}
            <div className="flex justify-between py-1 border-b">
              <span className="text-muted-foreground">{isSelf ? 'Your Delivery Fee' : 'Your Markup'}</span>
              <span className="text-green-600 font-medium">+ ₹{markupAmount.toFixed(0)}</span>
            </div>
            <div className="flex justify-between py-1 border-b">
              <span className="text-muted-foreground">Packaging & Overhead</span>
              <div className="flex items-center gap-2">
                <span>+ ₹{packagingFee}</span>
                <a href="/admin/order-settings" className="text-[10px] text-primary hover:underline">Edit</a>
              </div>
            </div>
            {!isSelf && (
              <div className="flex justify-between py-1 border-b">
                <span className="text-muted-foreground flex items-center gap-1">
                  <Coins className="w-3.5 h-3.5" /> Platform Fee (Flamezo)
                </span>
                <span>+ ₹{platformFee}</span>
              </div>
            )}
            <div className="flex justify-between py-2 font-bold text-base">
              <span>Customer Pays</span>
              <span className="text-primary">₹{totalCustomerPays.toFixed(0)}</span>
            </div>

            {isSelf ? (
              <div className="rounded-md bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-900 p-2.5 mt-2">
                <p className="text-xs text-blue-700 dark:text-blue-400">
                  <strong>₹0 deducted from your Coins wallet.</strong>{' '}
                  You manage your own riders and their costs. All delivery revenue (₹{markupAmount.toFixed(0)}) is yours.
                </p>
              </div>
            ) : (
              <div className="rounded-md bg-orange-50 dark:bg-orange-950/30 border border-orange-200 dark:border-orange-900 p-2.5 mt-2">
                <p className="text-xs text-orange-700 dark:text-orange-400">
                  <strong>Coins deducted per delivery: ₹{coinsDeducted}</strong> (Courier + Platform Fee).
                  Your markup of ₹{markupAmount.toFixed(0)} is profit — earned from the customer, not deducted.
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="flex justify-end pb-10">
        <Button onClick={handleSave} disabled={saving} size="lg" className="px-8 shadow-lg shadow-primary/20">
          {saving ? 'Saving...' : 'Save Logistics Configuration'}
        </Button>
      </div>
    </div>
  )
}
