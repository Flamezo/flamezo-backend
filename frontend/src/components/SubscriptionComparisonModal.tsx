
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { CheckCircle2, Minus, Sparkles, Zap, ShieldCheck, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'

interface SubscriptionComparisonModalProps {
  open: boolean
  onClose: () => void
  currentPlan: 'SILVER' | 'GOLD' | 'DIAMOND'
  onSelectPlan: (plan: 'SILVER' | 'GOLD' | 'DIAMOND') => void
  isChangingPlan: boolean
  planDefaults: {
    pro_monthly: number
    lux_monthly: number
    lux_commission: number
  }
}

interface FeatureRow {
  name: string
  silver: string | boolean
  gold: string | boolean
  diamond: string | boolean
}

const FEATURES: FeatureRow[] = [
  { name: 'QR Menu (HQ Photos)', silver: 'Standard', gold: 'Unlimited HQ', diamond: 'Unlimited HQ' },
  { name: 'Video Menu & Stories', silver: false, gold: true, diamond: true },
  { name: 'Custom QR Logo (Branding)', silver: 'DM Brackets', gold: 'Own Brand', diamond: 'Own Brand' },
  { name: 'Image Storage Limit', silver: '20', gold: 'Unlimited', diamond: 'Unlimited' },
  { name: 'AI Recommendations', silver: false, gold: true, diamond: true },
  { name: 'Analytics Dashboard', silver: false, gold: 'Advanced', diamond: 'Predictive' },
  { name: 'Gamification (Spin-the-Wheel)', silver: false, gold: true, diamond: true },
  { name: 'Table & Booking Engine', silver: false, gold: true, diamond: true },
  { name: 'WhatsApp Flow', silver: false, gold: 'Manual', diamond: 'Automated' },
  { name: 'Payment Processing', silver: false, gold: false, diamond: true },
  { name: 'Online Ordering Flow', silver: 'Limited', gold: 'Standard', diamond: 'Advanced' },
  { name: 'Loyalty Rewards & CRM', silver: false, gold: false, diamond: true },
  { name: 'Delivery Hub (Logistics)', silver: false, gold: false, diamond: 'Flash/Borzo' },
  { name: 'POS Integration', silver: false, gold: false, diamond: 'Deep Sync' },
  { name: 'Direct Data Ownership', silver: true, gold: true, diamond: true },
  { name: 'Success Share (Growth)', silver: '0%', gold: '0%', diamond: '1.5%' },
]

export function SubscriptionComparisonModal({
  open,
  onClose,
  currentPlan,
  onSelectPlan,
  isChangingPlan,
  planDefaults,
}: SubscriptionComparisonModalProps) {
  const renderCell = (value: string | boolean, isPrimary: boolean = false) => {
    if (typeof value === 'boolean') {
      return value ? (
        <CheckCircle2 className={cn("h-5 w-5 mx-auto", isPrimary ? "text-primary" : "text-emerald-500")} />
      ) : (
        <Minus className="h-5 w-5 mx-auto text-muted-foreground/30" />
      )
    }
    return <span className={cn("text-sm font-medium", isPrimary ? "text-primary" : "text-foreground")}>{value}</span>
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-4xl max-h-[90vh] overflow-y-auto p-0 gap-0 border-none shadow-2xl">
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
                <Badge variant="outline" className="px-2 py-0.5 text-[10px] font-bold tracking-widest uppercase border-primary/30 text-primary">Comparison Guide</Badge>
            </div>
            <DialogTitle className="text-3xl font-black tracking-tight flex items-center gap-2">
                Deep Feature Comparison
            </DialogTitle>
            <DialogDescription className="text-base">
                Choose the perfect tier for your restaurant brand. Ownership, not just a tool.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-4 gap-4 items-end">
            <div className="pb-2">
               <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Core Ecosystem</span>
            </div>
            {/* Silver */}
            <div className="text-center space-y-3">
               <div className="space-y-1">
                  <p className="text-sm font-bold uppercase tracking-tighter">Silver</p>
                  <p className="text-2xl font-black">Free</p>
                  <p className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">Lifetime Access</p>
               </div>
               <Button 
                size="sm" 
                variant={currentPlan === 'SILVER' ? "ghost" : "outline"} 
                className="w-full h-8 text-xs font-bold rounded-lg"
                onClick={() => onSelectPlan('SILVER')}
                disabled={currentPlan === 'SILVER' || isChangingPlan}
               >
                 {currentPlan === 'SILVER' ? 'Current Plan' : 'Downgrade'}
               </Button>
            </div>
            {/* Gold */}
            <div className="text-center space-y-3 p-3 rounded-2xl bg-muted/5 border border-muted/10 relative">
               <div className="space-y-1">
                  <p className="text-sm font-bold uppercase tracking-tighter text-primary">Gold</p>
                  <p className="text-2xl font-black">₹{planDefaults.pro_monthly}</p>
                  <p className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">Per Month</p>
               </div>
                <Button 
                 size="sm" 
                 className="w-full h-8 text-xs font-bold rounded-lg bg-primary text-white"
                 onClick={() => onSelectPlan('GOLD')}
                 disabled={currentPlan === 'GOLD' || isChangingPlan}
                >
                  {currentPlan === 'GOLD' ? 'Current Plan' : 
                   currentPlan === 'DIAMOND' ? 'Downgrade' : 'Upgrade'}
                </Button>
            </div>
            {/* Diamond */}
            <div className="text-center space-y-3 p-3 rounded-2xl bg-primary/5 border border-primary/20 relative shadow-sm">
               <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary text-white text-[8px] font-black tracking-tighter px-2 py-0.5 rounded-full">POPULAR</div>
               <div className="space-y-1">
                  <p className="text-sm font-bold uppercase tracking-tighter text-indigo-600">Diamond</p>
                  <p className="text-2xl font-black">{planDefaults.lux_commission}%</p>
                  <p className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">₹399/Month Guarantee + Success Share</p>
               </div>
               <Button 
                size="sm" 
                className="w-full h-8 text-xs font-bold rounded-lg bg-indigo-600 text-white"
                onClick={() => onSelectPlan('DIAMOND')}
                disabled={currentPlan === 'DIAMOND' || isChangingPlan}
               >
                 {currentPlan === 'DIAMOND' ? 'Current Plan' : 'Mastery'}
               </Button>
            </div>
          </div>
        </div>

        <div className="px-6 py-2">
           <table className="w-full">
              <tbody className="divide-y border-b">
                 {FEATURES.map((feature, i) => (
                    <tr key={i} className="hover:bg-muted/30 transition-colors">
                       <td className="py-4 text-sm font-medium text-muted-foreground">
                          {feature.name}
                       </td>
                       <td className="py-4 text-center">
                          {renderCell(feature.silver)}
                       </td>
                       <td className="py-4 text-center">
                          {renderCell(feature.gold)}
                       </td>
                       <td className="py-4 text-center bg-primary/[0.03]">
                          {renderCell(feature.diamond, true)}
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
                        <Sparkles className="h-5 w-5 text-amber-500" /> Ownership. Not Just a Tool.
                    </h4>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                        For less than a small fraction of your monthly overhead, you get a complete brand ecosystem. 
                        Most brands recover their annual investment within <b>14-21 days</b> through automated upselling and retention.
                    </p>
                </div>
                <div className="shrink-0 bg-background p-4 rounded-2xl border border-primary/20 text-center shadow-sm">
                    <p className="text-[10px] font-black uppercase tracking-widest text-primary mb-1">ROI Potential</p>
                    <p className="text-3xl font-black tracking-tighter">2,100%+</p>
                    <p className="text-[10px] text-muted-foreground mt-1">Average Payback: 2-3 weeks</p>
                </div>
            </div>
        </div>

        <div className="p-4 border-t bg-background flex items-center justify-between text-[11px] text-muted-foreground font-medium uppercase tracking-wider px-8">
            <div className="flex items-center gap-4">
                <span className="flex items-center gap-1"><ShieldCheck className="h-3.5 w-3.5 text-emerald-500" /> PCI-DSS Secure</span>
                <span className="flex items-center gap-1"><Zap className="h-3.5 w-3.5 text-amber-500" /> Instant Activation</span>
            </div>
            <button onClick={onClose} className="hover:text-foreground transition-colors flex items-center gap-1">
                <X className="h-3.5 w-3.5" /> Close Comparison
            </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
