
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { CheckCircle2, Sparkles, Zap, ShieldCheck, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

interface SubscriptionComparisonModalProps {
  open: boolean
  onClose: () => void
  currentPlan?: 'GOLD'
  onSelectPlan?: (plan: 'GOLD') => void
  isChangingPlan?: boolean
  planDefaults: {
    gold_floor: number
    gold_commission: number
  }
}

interface FeatureRow {
  name: string
  gold: string | boolean
}

export function SubscriptionComparisonModal({
  open,
  onClose,
  planDefaults,
}: SubscriptionComparisonModalProps) {
  const FEATURES: FeatureRow[] = [
    { name: 'Digital QR Menu (Unlimited HQ photos)', gold: true },
    { name: 'Online ordering via QR + Web', gold: true },
    { name: 'WhatsApp ordering', gold: true },
    { name: 'Loyalty rewards (earn & redeem across the network)', gold: true },
    { name: 'Listed on the FLAMEZO consumer app', gold: true },
    { name: 'Video menu & stories', gold: true },
    { name: 'Custom-branded QR codes', gold: true },
    { name: 'AI menu recommendations & upselling', gold: true },
    { name: 'Advanced analytics dashboard', gold: true },
    { name: 'Customer CRM & insights', gold: true },
    { name: 'Marketing Studio (SMS, WhatsApp, Email)', gold: true },
    { name: 'Gamification (Spin-the-Wheel)', gold: true },
    { name: 'Table & banquet booking', gold: true },
    { name: 'POS integration (PetPooja, UrbanPiper, RestroWorks)', gold: 'Deep Sync' },
    { name: 'Self-Managed Delivery (custom rates per km)', gold: true },
    { name: 'Coupons & targeted offers', gold: true },
    { name: 'Data ownership', gold: 'You' },
    { name: 'Success Share on online orders', gold: `${planDefaults.gold_commission}%` },
  ]

  const renderCell = (value: string | boolean) => {
    if (typeof value === 'boolean') {
      return value ? <CheckCircle2 className="h-5 w-5 mx-auto text-primary" /> : null
    }
    return <span className="text-sm font-medium text-primary">{value}</span>
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto p-0 gap-0 border-none shadow-2xl">
        <div className="sticky top-0 z-20 bg-background/95 backdrop-blur-md border-b p-6 pb-4">
          <button
            onClick={onClose}
            className="absolute right-6 top-6 p-2 rounded-full hover:bg-muted/80 transition-colors z-30"
            aria-label="Close"
          >
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
          <DialogHeader className="mb-6">
            <div className="flex items-center gap-2 mb-1">
              <Badge variant="outline" className="px-2 py-0.5 text-[10px] font-bold tracking-widest uppercase border-primary/30 text-primary">
                Your Plan
              </Badge>
            </div>
            <DialogTitle className="text-3xl font-black tracking-tight flex items-center gap-2">
              One plan. Every feature unlocked.
            </DialogTitle>
            <DialogDescription className="text-base">
              Free onboarding. {planDefaults.gold_commission}% Success Share per online order — no monthly floor, no minimums, no tiers to chase.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-3 gap-4 items-end">
            <div className="pb-2 col-span-2">
              <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground">What you get</span>
            </div>
            <div className="text-center space-y-3 p-3 rounded-2xl bg-muted/5 border border-muted/10 relative">
              <div className="space-y-1">
                <p className="text-sm font-bold uppercase tracking-tighter text-primary">Flamezo</p>
                <p className="text-2xl font-black">
                  {planDefaults.gold_commission}%
                  <span className="text-sm font-medium"> Success Share</span>
                </p>
                <p className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">
                  No monthly floor · Free onboarding
                </p>
              </div>
              <Button size="sm" variant="ghost" className="w-full h-8 text-xs font-bold rounded-lg" disabled>
                Current Plan
              </Button>
            </div>
          </div>
        </div>

        <div className="px-6 py-2">
          <table className="w-full">
            <tbody className="divide-y border-b">
              {FEATURES.map((feature, i) => (
                <tr key={i} className="hover:bg-muted/30 transition-colors">
                  <td className="py-4 text-sm font-medium text-muted-foreground w-2/3">
                    {feature.name}
                  </td>
                  <td className="py-4 text-center bg-primary/[0.03]">
                    {renderCell(feature.gold)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="p-8 bg-muted/30">
          <div className="flex flex-col md:flex-row items-center gap-6">
            <div className="flex-1 space-y-2">
              <h4 className="text-lg font-bold flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-amber-500" /> Ownership. Not just a tool.
              </h4>
              <p className="text-sm text-muted-foreground leading-relaxed">
                You only pay when your customers pay you online. Until then the plan is free —
                no setup fee, no annual fee, no unlock fee.
              </p>
            </div>
            <div className="shrink-0 bg-background p-4 rounded-2xl border border-primary/20 text-center shadow-sm">
              <p className="text-[10px] font-black uppercase tracking-widest text-primary mb-1">Success Share</p>
              <p className="text-3xl font-black tracking-tighter">{planDefaults.gold_commission}%</p>
              <p className="text-[10px] text-muted-foreground mt-1">per online order</p>
            </div>
          </div>
        </div>

        <div className="p-4 border-t bg-background flex items-center justify-between text-[11px] text-muted-foreground font-medium uppercase tracking-wider px-8">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1"><ShieldCheck className="h-3.5 w-3.5 text-emerald-500" /> PCI-DSS Secure</span>
            <span className="flex items-center gap-1"><Zap className="h-3.5 w-3.5 text-amber-500" /> Instant Activation</span>
          </div>
          <button onClick={onClose} className="hover:text-foreground transition-colors flex items-center gap-1">
            <X className="h-3.5 w-3.5" /> Close
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
