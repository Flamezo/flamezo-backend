/**
 * CoinRechargeModal
 * 
 * Allows restaurants to top-up their Flamezo Wallet using Razorpay.
 * Bundles: 1000, 2000, 5000.
 * ₹1 Balance = ₹1 (Base) + 18% GST (Collected Upfront)
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { NumberInput } from "@/components/ui/number-input"
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'
import { useFrappePostCall, useFrappeGetCall } from '@/lib/frappe'
import { Loader2, Sparkles, Zap, Star, Rocket, PenLine, Wallet, History as HistoryIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

interface CoinRechargeModalProps {
  open: boolean
  onClose: () => void
  restaurant: string
  onSuccess: () => void
}

interface Bundle {
  id: string
  coins: number
  price_inr: number
  label: string
  icon: React.ReactNode
  badge?: string
  bonus?: number
  highlight?: boolean
}

const BUNDLES: Bundle[] = [
  {
    id: '999',
    coins: 1000,
    price_inr: 999,
    label: 'Starter',
    icon: <Zap className="h-5 w-5" />,
    badge: undefined,
    bonus: 1,
    highlight: false,
  },
  {
    id: '2999',
    coins: 3300,
    price_inr: 2999,
    label: 'Popular',
    icon: <Star className="h-5 w-5" />,
    badge: '10% BONUS',
    bonus: 301,
    highlight: true,
  },
  {
    id: '4999',
    coins: 6000,
    price_inr: 4999,
    label: 'Best Value',
    icon: <Rocket className="h-5 w-5" />,
    badge: '20% BONUS',
    bonus: 1001,
    highlight: false,
  },
]

declare global {
  interface Window {
    Razorpay: any
  }
}

function loadRazorpayScript(): Promise<boolean> {
  return new Promise((resolve) => {
    if (window.Razorpay) return resolve(true)
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.onload = () => resolve(true)
    script.onerror = () => resolve(false)
    document.body.appendChild(script)
  })
}

export function AiRechargeModal({ open, onClose, restaurant, onSuccess }: CoinRechargeModalProps) {
  const navigate = useNavigate()
  const [selectedBundle, setSelectedBundle] = useState<string>('2000')
  const [customBalance, setCustomBalance] = useState<string>('')
  const [isProcessing, setIsProcessing] = useState(false)

  const { call: createOrder } = useFrappePostCall(
    'flamezo_backend.flamezo.api.coin_billing.create_coin_purchase_order'
  )
  const { call: verifyPayment } = useFrappePostCall(
    'flamezo_backend.flamezo.api.coin_billing.verify_coin_purchase'
  )
  
  const { data: platformSettingsData } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.admin.get_platform_settings',
    {},
    'platform-settings-modal'
  )
  
  const platformSettings = platformSettingsData?.message?.data || {
    charge_gst: false,
    gst_percent: 18
  }

  const isCustom = selectedBundle === 'custom'
  const customAmount = parseInt(customBalance || '0', 10)
  
  // Calculate bonus dynamically for custom amounts
  const getBonus = (amt: number) => {
    if (amt >= 4999) return Math.round(amt * 0.20)
    if (amt >= 2999) return Math.round(amt * 0.10)
    if (amt === 999) return 1
    return 0
  }

  const basePrice = isCustom ? customAmount : BUNDLES.find(b => b.id === selectedBundle)?.price_inr || 0
  const bonusUnits = isCustom ? getBonus(basePrice) : BUNDLES.find(b => b.id === selectedBundle)?.bonus || 0
  const selectedCoins = basePrice + bonusUnits

  // Dynamic GST Calculation from Settings
  const gstRate = platformSettings.charge_gst ? platformSettings.gst_percent / 100 : 0
  const gstAmount = Math.round(basePrice * gstRate * 100) / 100
  const totalPayable = basePrice + gstAmount

  const canPurchase = isCustom
    ? customAmount >= 300
    : selectedBundle !== ''

  const handlePurchase = async () => {
    if (!canPurchase) {
      toast.error(isCustom ? 'Minimum 300 coins required.' : 'Please select a bundle.')
      return
    }

    setIsProcessing(true)
    try {
      const loaded = await loadRazorpayScript()
      if (!loaded) {
        toast.error('Failed to load Razorpay. Check your internet connection.')
        setIsProcessing(false)
        return
      }

      // 1. Create Razorpay order
      const orderRes = await createOrder({
        restaurant,
        amount: selectedCoins
      })

      if (!orderRes.message?.success) {
        throw new Error(orderRes.message?.error || 'Failed to create order')
      }

      const { razorpay_order_id, amount, key_id } = orderRes.message

      // 2. Open Razorpay modal
      await new Promise<void>((resolve, reject) => {
        const rzp = new window.Razorpay({
          key: key_id,
          amount,
          currency: 'INR',
          order_id: razorpay_order_id,
          name: 'Flamezo Wallet',
          description: `Top-up ₹${selectedCoins} Balance (Price: ₹${basePrice} + GST: ₹${gstAmount})`,
          theme: { color: '#f97316' },
          handler: async (response: any) => {
            try {
              // 3. Verify Payment on Backend
              const verifyRes = await verifyPayment({
                restaurant,
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature
              })

              if (verifyRes.message?.success) {
                toast.success(`✅ Success! ₹${selectedCoins} added to your wallet.`)
                window.dispatchEvent(new CustomEvent('coins-updated', { detail: { refresh: true } }))
                onSuccess()
                resolve()
              } else {
                throw new Error(verifyRes.message?.error || 'Payment verification failed')
              }
            } catch (err: any) {
              toast.error('Verification failed', { description: err.message })
              reject(err)
            }
          },
          modal: {
            ondismiss: () => {
              resolve()
            }
          }
        })
        onClose() // Close the background modal to allow interaction with Razorpay
        rzp.open()
      })
    } catch (err: any) {
      console.error('Coin purchase error:', err)
      toast.error('Purchase failed', { description: err.message })
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <Wallet className="h-5 w-5 text-primary" />
            Top up Wallet
          </DialogTitle>
          <DialogDescription>
            Your wallet balance is used for AI services and platform commissions.
          </DialogDescription>
        </DialogHeader>

        {/* Bundle Selection */}
        <div className="grid grid-cols-3 gap-4 mt-6">
          {BUNDLES.map((bundle) => (
            <button
              key={bundle.id}
              type="button"
              onClick={() => setSelectedBundle(bundle.id)}
              className={cn(
                'relative flex flex-col items-center justify-center gap-2 rounded-2xl border-2 p-6 transition-all duration-300 transform hover:scale-[1.02] active:scale-[0.98] focus:outline-none group',
                selectedBundle === bundle.id && !isCustom
                  ? 'border-primary bg-primary/[0.03] dark:bg-primary/[0.08] shadow-lg shadow-primary/10'
                  : 'border-border/60 hover:border-primary/40 hover:bg-muted/30'
              )}
            >
              {bundle.badge && (
                <div
                  className={cn(
                    'absolute -top-3 left-1/2 -translate-x-1/2 text-[10px] font-black tracking-tighter px-3 py-1 rounded-full shadow-sm whitespace-nowrap',
                    'bg-primary text-white border border-primary/20'
                  )}
                >
                  {bundle.badge}
                </div>
              )}
              <div className={cn(
                'p-3 rounded-2xl transition-colors duration-300',
                selectedBundle === bundle.id && !isCustom
                  ? 'bg-primary text-white'
                  : 'bg-muted text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary'
              )}>
                {bundle.icon}
              </div>
              <div className="flex flex-col items-center">
                <span className="text-2xl font-black tracking-tight">{bundle.coins.toLocaleString()}</span>
                <span className="text-[10px] uppercase font-bold text-muted-foreground tracking-widest -mt-1">Balance</span>
                {bundle.bonus && bundle.bonus > 1 && (
                  <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 mt-1">
                    Incl. ₹{bundle.bonus} Bonus
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>

        {/* Custom Amount */}
        <div className="mt-1">
          <button
            type="button"
            onClick={() => setSelectedBundle('custom')}
            className={cn(
              'w-full flex items-center gap-3 rounded-xl border-2 p-4 transition-all text-left focus:outline-none',
              isCustom
                ? 'border-primary bg-primary/5 dark:bg-primary/10 shadow-md'
                : 'border-border hover:border-primary/40 hover:bg-muted/40'
            )}
          >
            <div className={cn(
              'p-2 rounded-full shrink-0',
              isCustom ? 'bg-primary text-white' : 'bg-muted text-muted-foreground'
            )}>
              <PenLine className="h-4 w-4" />
            </div>
            <div className="flex-1">
              <div className="font-medium text-sm">Custom Amount</div>
              <div className="text-xs text-muted-foreground">Min. 300 coins</div>
            </div>
            {isCustom && (
              <div className="flex items-center gap-1.5">
                <NumberInput
                  
                  min={300}
                  step={1}
                  placeholder="e.g. 1500"
                  value={customBalance}
                  onChange={e => {
                    const val = e.target.value
                    if (val === '' || (Number(val) >= 0 && /^\d*$/.test(val))) {
                      setCustomBalance(val)
                    }
                  }}
                  onBlur={e => {
                    const val = parseInt(e.target.value || '0', 10)
                    if (val > 0 && val < 300) setCustomBalance('300')
                  }}
                  onKeyDown={e => {
                    if (e.key === '-' || e.key === '+' || e.key === 'e') e.preventDefault()
                  }}
                  onClick={e => e.stopPropagation()}
                  className={cn('w-24 text-right', customBalance && customAmount < 300 && customAmount > 0 ? 'border-red-400 focus-visible:ring-red-400' : '')}
                />
                <Label className="text-xs shrink-0">{bonusUnits > 0 ? `+ ₹${bonusUnits} Bonus` : 'Balance'}</Label>
              </div>
            )}
          </button>
        </div>

        {/* Summary Bar with GST Breakdown */}
        <div className="rounded-xl bg-muted/50 p-5 space-y-3 mt-2 border border-border/50">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Original Price</span>
            <span className="font-medium">₹{basePrice.toLocaleString()}</span>
          </div>
          {bonusUnits > 0 && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-emerald-600 dark:text-emerald-400 font-medium italic">Early Bird Bonus Credit</span>
              <span className="font-medium text-emerald-600 dark:text-emerald-400">₹{bonusUnits.toLocaleString()}</span>
            </div>
          )}
          {platformSettings.charge_gst && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">GST ({platformSettings.gst_percent}%)</span>
              <span className="font-medium text-amber-600 dark:text-amber-400">+₹{gstAmount.toLocaleString()}</span>
            </div>
          )}
          <div className="h-px bg-border/50 w-full" />
          <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <div className="flex flex-col">
                <p className="text-sm font-black uppercase tracking-tight">Total Payable</p>
                <p className="text-[10px] text-muted-foreground">Net price to pay now</p>
              </div>
              <p className="text-3xl font-black text-primary tracking-tighter">
                {totalPayable > 0 ? `₹${totalPayable.toLocaleString()}` : '—'}
              </p>
            </div>
            <div className="flex items-center justify-between bg-primary/10 dark:bg-primary/20 p-2 rounded-lg mt-1 border border-primary/20">
               <span className="text-xs font-bold text-primary italic">Total Wallet Credit:</span>
               <span className="text-lg font-black text-primary italic">₹{selectedCoins.toLocaleString()}</span>
            </div>
          </div>
        </div>

        <DialogFooter className="mt-2 flex items-center justify-between sm:justify-between w-full">
          <Button 
            variant="ghost" 
            size="sm" 
            className="text-muted-foreground hover:text-primary gap-2 px-2" 
            onClick={() => {
              onClose()
              navigate('/ledger')
            }}
          >
            <HistoryIcon className="h-4 w-4" />
            Show Ledger
          </Button>

          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={onClose} disabled={isProcessing}>
              Cancel
            </Button>
            <Button
              disabled={!canPurchase || isProcessing || selectedCoins === 0}
              onClick={handlePurchase}
              className="bg-primary hover:bg-primary/90 text-white gap-2"
            >
              {isProcessing ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> Processing...</>
              ) : (
                <><Sparkles className="h-4 w-4" /> Pay ₹{totalPayable}</>
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
