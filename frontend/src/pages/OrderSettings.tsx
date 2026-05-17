import { useState, useEffect } from 'react'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall, useFrappeGetDoc } from '@/lib/frappe'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from 'sonner'
import { Truck, ShoppingBag, Clock, DollarSign, Settings, Percent, FileText, MessageSquare, Zap, Crown } from 'lucide-react'

export default function OrderSettings() {
  const { selectedRestaurant, billingInfo, isGold } = useRestaurant()
  const [saving, setSaving] = useState(false)
  const [settings, setSettings] = useState({
    enable_takeaway: 1,
    enable_delivery: 0,
    enable_dine_in: 1,
    default_packaging_fee: 0,
    packaging_fee_type: 'Fixed' as 'Fixed' | 'Percentage',
    minimum_order_value: 0,
    estimated_prep_time: 30,
    default_delivery_fee: 0,
    no_ordering: 0,
    order_channel: 'Realtime' as 'Realtime' | 'WhatsApp',
    tax_rate: 5.0,
    gst_number: ''
  })

  const { data: restaurantDoc, isValidating, mutate } = useFrappeGetDoc(
    'Restaurant',
    selectedRestaurant || '',
    selectedRestaurant ? `Restaurant-${selectedRestaurant}` : null
  )

  useEffect(() => {
    if (restaurantDoc) {
      setSettings({
        enable_takeaway: restaurantDoc.enable_takeaway ?? 1,
        enable_delivery: restaurantDoc.enable_delivery ?? 0,
        enable_dine_in: restaurantDoc.enable_dine_in ?? 1,
        default_packaging_fee: restaurantDoc.default_packaging_fee ?? 0,
        packaging_fee_type: (restaurantDoc.packaging_fee_type as any) || 'Fixed',
        minimum_order_value: restaurantDoc.minimum_order_value ?? 0,
        estimated_prep_time: restaurantDoc.estimated_prep_time ?? 30,
        default_delivery_fee: restaurantDoc.default_delivery_fee ?? 0,
        no_ordering: restaurantDoc.no_ordering ?? 0,
        order_channel: (restaurantDoc.order_channel as 'Realtime' | 'WhatsApp') || 'Realtime',
        tax_rate: restaurantDoc.tax_rate ?? 5.0,
        gst_number: restaurantDoc.gst_number ?? ''
      })
    }
  }, [restaurantDoc])

  const { call: updateSettings } = useFrappePostCall<{ success: boolean, data: any }>('flamezo_backend.flamezo.api.config.update_order_settings')

  const handleSave = async () => {
    if (!selectedRestaurant) return
    
    setSaving(true)
    try {
      const response: any = await updateSettings({
        restaurant_id: selectedRestaurant,
        settings: {
          enable_takeaway: settings.enable_takeaway,
          enable_delivery: settings.enable_delivery,
          enable_dine_in: settings.enable_dine_in,
          packaging_fee_type: settings.packaging_fee_type,
          default_packaging_fee: settings.default_packaging_fee,
          minimum_order_value: settings.minimum_order_value,
          estimated_prep_time: settings.estimated_prep_time,
          default_delivery_fee: settings.default_delivery_fee,
          no_ordering: settings.no_ordering,
          order_channel: settings.order_channel,
          tax_rate: settings.tax_rate,
          gst_number: settings.gst_number
        }
      })

      const body = response?.message ?? response
      if (body?.success) {
        await mutate()
        toast.success('Order settings saved successfully')
      } else {
        throw new Error(body?.error?.message || 'Failed to save settings')
      }
    } catch (error: any) {
      console.error('Failed to save settings:', error)
      toast.error(error.message || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = (field: keyof typeof settings) => {
    setSettings(prev => ({
      ...prev,
      [field]: prev[field] ? 0 : 1
    }))
  }

  const handleNumberChange = (field: keyof typeof settings, value: string) => {
    const num = parseFloat(value)
    if (!isNaN(num) && num >= 0) {
      setSettings(prev => ({
        ...prev,
        [field]: num
      }))
    } else if (value === '') {
      setSettings(prev => ({
        ...prev,
        [field]: 0
      }))
    }
  }

  if (isValidating && !restaurantDoc) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Order Settings</h1>
        <p className="text-muted-foreground mt-2">
          Configure takeaway, delivery options, and additional charges.
        </p>
      </div>

      <Card className="border-primary/20 bg-primary/5">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-primary" />
            <CardTitle>Ordering Mode</CardTitle>
          </div>
          <CardDescription>
            Completely disable ordering to use other platform features (Games, Events)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label className="text-base">Disable All Ordering</Label>
              <p className="text-sm text-muted-foreground">
                When enabled, customers can only view the menu. Cart, coupons, and checkout will be hidden.
              </p>
            </div>
            <Checkbox
              checked={settings.no_ordering === 1}
              onCheckedChange={() => handleToggle('no_ordering')}
              className="h-6 w-6"
            />
          </div>
              {settings.no_ordering === 1 && (
                <div className="mt-4 p-3 rounded-lg bg-orange-500/10 border border-orange-500/20 text-orange-600 text-sm font-medium">
                  Note: GOLD plan {billingInfo?.plan_defaults?.gold_commission ?? 1.5}% commission applies per order. When ordering is disabled, the ₹{billingInfo?.plan_defaults?.gold_floor || 399} monthly floor still applies.
                </div>
              )}
        </CardContent>
      </Card>

      {/* Order Channel */}
      <Card className={!isGold ? 'opacity-70' : ''}>
        <CardContent className="pt-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {/* Toggle pill */}
              <button
                type="button"
                disabled={!isGold}
                onClick={() => isGold && setSettings(prev => ({
                  ...prev,
                  order_channel: prev.order_channel === 'Realtime' ? 'WhatsApp' : 'Realtime'
                }))}
                className={[
                  'relative inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none',
                  settings.order_channel === 'WhatsApp' ? 'bg-green-500' : 'bg-primary',
                  !isGold ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
                ].join(' ')}
                aria-checked={settings.order_channel === 'WhatsApp'}
                role="switch"
              >
                <span
                  className={[
                    'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
                    settings.order_channel === 'WhatsApp' ? 'translate-x-5' : 'translate-x-0'
                  ].join(' ')}
                />
              </button>

              {/* Labels */}
              <div className="flex items-center gap-2">
                <span className={`flex items-center gap-1 text-sm font-medium transition-colors ${settings.order_channel === 'Realtime' ? 'text-primary' : 'text-muted-foreground'}`}>
                  <Zap className="w-3.5 h-3.5" /> Real-time
                </span>
                <span className="text-muted-foreground/40 text-xs">/</span>
                <span className={`flex items-center gap-1 text-sm font-medium transition-colors ${settings.order_channel === 'WhatsApp' ? 'text-green-600 dark:text-green-400' : 'text-muted-foreground'}`}>
                  <MessageSquare className="w-3.5 h-3.5" /> WhatsApp
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {!isGold && (
                <span className="flex items-center gap-1 text-xs font-semibold text-amber-600 bg-amber-100 dark:bg-amber-900/30 dark:text-amber-400 px-2 py-0.5 rounded-full">
                  <Crown className="w-3 h-3" /> GOLD
                </span>
              )}
              <div>
                <p className="text-sm font-medium text-right">Order Channel</p>
                <p className="text-xs text-muted-foreground text-right">
                  {!isGold
                    ? 'Upgrade to GOLD to enable real-time ordering'
                    : settings.order_channel === 'WhatsApp'
                      ? 'Customers order via WhatsApp — sidebar orders hidden'
                      : 'In-app checkout with live order tracking'}
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <ShoppingBag className="w-5 h-5 text-primary" />
              <CardTitle>Takeaway Options</CardTitle>
            </div>
            <CardDescription>
              Allow customers to order for pickup
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Enable Takeaway</Label>
                <p className="text-sm text-muted-foreground">
                  Show takeaway option on the ordering page
                </p>
              </div>
              <Checkbox
                checked={settings.enable_takeaway === 1}
                onCheckedChange={() => handleToggle('enable_takeaway')}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Clock className="w-5 h-5 text-primary" />
              <CardTitle>Dine-in Options</CardTitle>
            </div>
            <CardDescription>
              Allow customers to order for dining at the restaurant
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Enable Dine-in</Label>
                <p className="text-sm text-muted-foreground">
                  Show dine-in option on the ordering page
                </p>
              </div>
              <Checkbox
                checked={settings.enable_dine_in === 1}
                onCheckedChange={() => handleToggle('enable_dine_in')}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Truck className="w-5 h-5 text-primary" />
              <CardTitle>Delivery Options</CardTitle>
            </div>
            <CardDescription>
              Allow customers to order for home delivery
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Enable Delivery</Label>
                <p className="text-sm text-muted-foreground">
                  Show delivery option on the ordering page. Configure providers in the <a href="/admin/logistics-hub" className="text-primary hover:underline font-medium">Logistics Hub</a>.
                </p>
              </div>
              <Checkbox
                checked={settings.enable_delivery === 1}
                onCheckedChange={() => handleToggle('enable_delivery')}
              />
            </div>

            {settings.enable_delivery === 1 && (
              <>
                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <Label>Default Delivery Fee</Label>
                    {(restaurantDoc?.preferred_logistics_provider === 'Borzo' || restaurantDoc?.preferred_logistics_provider === 'Flash') && (
                      <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-bold uppercase tracking-wider">
                        Managed by Logistics Hub
                      </span>
                    )}
                  </div>
                  <div className={`flex items-center rounded-md border border-input bg-background overflow-hidden ${(restaurantDoc?.preferred_logistics_provider === 'Borzo' || restaurantDoc?.preferred_logistics_provider === 'Flash') ? 'opacity-50 grayscale select-none cursor-not-allowed' : ''}`}>
                    <span className="flex h-8 items-center border-r border-input px-3 text-sm leading-none text-muted-foreground font-medium">
                      ₹
                    </span>
                    <NumberInput
                      
                      disabled={restaurantDoc?.preferred_logistics_provider === 'Borzo' || restaurantDoc?.preferred_logistics_provider === 'Flash'}
                      className="h-8 border-0 rounded-none shadow-none focus-visible:ring-0 focus-visible:border-0"
                      value={settings.default_delivery_fee || ''}
                      onChange={(e) => handleNumberChange('default_delivery_fee', e.target.value)}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {(restaurantDoc?.preferred_logistics_provider === 'Borzo' || restaurantDoc?.preferred_logistics_provider === 'Flash') 
                      ? 'Fees are calculated dynamically based on courier cost + your markup.' 
                      : 'Flat fee applied to all self-managed delivery orders.'}
                  </p>
                </div>

                <div className="space-y-2">
                  <Label>Minimum Order Value</Label>
                  <div className="flex items-center rounded-md border border-input bg-background overflow-hidden">
                    <span className="flex h-8 items-center border-r border-input px-3 text-sm leading-none text-muted-foreground font-medium">
                      ₹
                    </span>
                    <NumberInput
                      
                      className="h-8 border-0 rounded-none shadow-none focus-visible:ring-0 focus-visible:border-0"
                      value={settings.minimum_order_value || ''}
                      onChange={(e) => handleNumberChange('minimum_order_value', e.target.value)}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">Minimum cart amount required for delivery</p>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Settings className="w-5 h-5 text-primary" />
              <CardTitle>General Ordering Settings</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <Clock className="w-4 h-4" />
                  Estimated Preparation Time (mins)
                </Label>
                <NumberInput
                  
                  value={settings.estimated_prep_time || ''}
                  onChange={(e) => handleNumberChange('estimated_prep_time', e.target.value)}
                />
                <p className="text-xs text-muted-foreground">Default estimated time shown to customers</p>
              </div>

              <div className="space-y-4">
                <div className="space-y-2">
                  <Label className="flex items-center gap-2">
                    <DollarSign className="w-4 h-4" />
                    Packaging Fee Type
                  </Label>
                  <Select
                    value={settings.packaging_fee_type}
                    onValueChange={(val: any) => setSettings(prev => ({ ...prev, packaging_fee_type: val }))}
                  >
                    <SelectTrigger className="h-10">
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Fixed">Fixed Amount (₹)</SelectItem>
                      <SelectItem value="Percentage">Percentage of Order (%)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Packaging Fee Value</Label>
                  <div className="flex items-center rounded-md border border-input bg-background overflow-hidden px-3 h-10">
                    {settings.packaging_fee_type === 'Fixed' && <span className="mr-2 text-sm text-muted-foreground font-medium">₹</span>}
                    <NumberInput
                      
                      className="h-8 border-0 rounded-none shadow-none focus-visible:ring-0 focus-visible:border-0 p-0"
                      value={settings.default_packaging_fee || ''}
                      onChange={(e) => handleNumberChange('default_packaging_fee', e.target.value)}
                    />
                    {settings.packaging_fee_type === 'Percentage' && <span className="ml-2 text-sm text-muted-foreground font-medium">%</span>}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {settings.packaging_fee_type === 'Percentage' 
                      ? `${settings.default_packaging_fee}% of order total applied as packaging fee.`
                      : `Flat ₹${settings.default_packaging_fee} applied to takeaway and delivery orders.`}
                  </p>
                </div>
              </div>

              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <Percent className="w-4 h-4" />
                  Tax Rate (%)
                </Label>
                <div className="flex items-center rounded-md border border-input bg-background overflow-hidden px-3">
                  <NumberInput
                    
                    className="h-8 border-0 rounded-none shadow-none focus-visible:ring-0 focus-visible:border-0 p-0"
                    value={settings.tax_rate || ''}
                    onChange={(e) => handleNumberChange('tax_rate', e.target.value)}
                  />
                  <span className="text-xs text-muted-foreground font-medium">%</span>
                </div>
                <p className="text-xs text-muted-foreground">GST percentage (e.g. 5 for 5% GST)</p>
              </div>

              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <FileText className="w-4 h-4" />
                  GST Number
                </Label>
                <Input
                  value={settings.gst_number || ''}
                  onChange={(e) => setSettings(prev => ({ ...prev, gst_number: e.target.value }))}
                  placeholder="27XXXXX0000X1Z1"
                  className="h-10"
                />
                <p className="text-xs text-muted-foreground">Registered GSTIN for invoice generation</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving} size="lg">
          {saving ? 'Saving...' : 'Save Settings'}
        </Button>
      </div>
    </div>
  )
}
