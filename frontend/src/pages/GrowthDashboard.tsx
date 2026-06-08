import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { TrendingUp, Users, Receipt, Banknote, Target, CheckSquare, BarChart3, ChevronRight, CheckCircle2 } from 'lucide-react'
import { useCurrency } from '@/hooks/useCurrency'
import { cn } from '@/lib/utils'

function MetricCard({ 
  title, 
  before, 
  after, 
  icon: Icon,
  highlight = false
}: { 
  title: string, 
  before: string | number, 
  after: string | number,
  icon: any,
  highlight?: boolean
}) {
  return (
    <Card className={cn(
      "relative overflow-hidden transition-all duration-300 shadow-sm border",
      highlight ? "border-emerald-500/30 bg-emerald-50/30 dark:bg-emerald-950/20" : "bg-card"
    )}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
          <Icon className={cn("h-4 w-4", highlight ? "text-emerald-500" : "text-primary")} />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between mt-2">
          <div className="text-left">
            <span className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Before</span>
            <span className="text-xl font-medium text-muted-foreground/60">{before}</span>
          </div>
          <div className="mx-4 flex items-center justify-center">
            <ChevronRight className={cn("h-5 w-5", highlight ? "text-emerald-500" : "text-primary/50")} />
          </div>
          <div className="text-right">
            <span className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">After (45 Days)</span>
            <span className={cn(
              "text-2xl font-bold tracking-tight",
              highlight ? "text-emerald-600 dark:text-emerald-400" : "text-foreground"
            )}>
              {after}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function RevenueRow({ label, before, after, isExpense = false }: any) {
  return (
    <div className="flex justify-between items-center text-sm py-2">
      <span className="text-muted-foreground font-medium">{label}</span>
      <div className="flex items-center gap-6">
        <span className="text-muted-foreground/60 w-24 text-right">{before}</span>
        <span className={cn("w-24 text-right font-bold", isExpense ? "text-rose-500" : "text-foreground")}>
          {after}
        </span>
      </div>
    </div>
  )
}

function SourceRow({ label, value, max }: any) {
  const percentage = (parseInt(value) / max) * 100
  return (
    <div className="space-y-1.5 py-1">
      <div className="flex justify-between text-xs font-medium">
        <span>{label}</span>
        <span className="font-bold">{value} customers</span>
      </div>
      <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
        <div 
          className="h-full bg-primary rounded-full transition-all duration-1000 ease-out"
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  )
}

function OutcomeCheck({ text, highlight = false }: any) {
  return (
    <div className={cn(
      "flex items-center gap-3 p-3 rounded-xl border",
      highlight 
        ? "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-900/50" 
        : "bg-muted/30 border-border"
    )}>
      <CheckCircle2 className={cn("h-5 w-5 shrink-0", highlight ? "text-emerald-500" : "text-primary")} />
      <span className={cn(
        "text-sm font-medium",
        highlight ? "text-emerald-700 dark:text-emerald-400 font-bold" : "text-foreground"
      )}>
        {text}
      </span>
    </div>
  )
}

export default function GrowthDashboard() {
  const { formatAmountNoDecimals } = useCurrency()

  return (
    <div className="space-y-8 pb-10 max-w-5xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-700">
      {/* Header */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-6 w-6 text-primary" />
          <h1 className="text-3xl font-bold tracking-tight text-foreground">Merchant Growth Outcome</h1>
        </div>
        <p className="text-muted-foreground text-sm">
          Simulation data showcasing the ROI of joining FlameZO after 45 days.
        </p>
      </div>

      {/* KEY METRICS CARDS */}
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricCard 
          icon={Users}
          title="Total Customers"
          before="1,027"
          after="1,129"
        />
        <MetricCard 
          icon={Target}
          title="New Customers"
          before="0"
          after="102"
          highlight
        />
        <MetricCard 
          icon={Receipt}
          title="Average Bill"
          before="₹448"
          after="₹545"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* REVENUE BREAKDOWN */}
        <Card className="shadow-sm border-none bg-card">
          <CardHeader>
            <CardTitle className="text-lg font-bold flex items-center gap-2">
              <Banknote className="h-5 w-5 text-primary" />
              Revenue Breakdown
            </CardTitle>
            <CardDescription>Financial impact over 45 days</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <RevenueRow label="Gross Revenue" before="₹4,60,096" after="₹6,15,305" />
            <RevenueRow label="Total Cashback + Offer Cost" before="₹0" after="₹45,532" isExpense />
            <RevenueRow label="FlameZO Commission" before="₹0" after="₹18,459" isExpense />
            
            <div className="pt-4 mt-2 border-t border-border">
              <div className="flex justify-between items-center">
                <span className="text-base font-bold text-foreground">Net Revenue</span>
                <div className="text-right flex items-center gap-3">
                  <span className="text-sm text-muted-foreground line-through">₹4,60,096</span>
                  <span className="text-xl font-bold text-emerald-600 dark:text-emerald-400">₹5,51,314</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* SOURCES OF NEW CUSTOMERS */}
        <Card className="shadow-sm border-none bg-card">
          <CardHeader>
            <CardTitle className="text-lg font-bold flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-primary" />
              Sources of New Customers
            </CardTitle>
            <CardDescription>Attribution for the 102 acquired customers</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <SourceRow label="Instagram Story Campaign" value="41" max={41} />
            <SourceRow label="FlameZO Community" value="29" max={41} />
            <SourceRow label="Flamezo Boost" value="18" max={41} />
            <SourceRow label="Organic Word of Mouth" value="14" max={41} />

            <div className="pt-4 mt-6 border-t border-border">
              <div className="flex justify-between items-center">
                <span className="text-base font-bold text-foreground">Total New Customers</span>
                <span className="text-xl font-bold text-emerald-600 dark:text-emerald-400">102</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* MERCHANT OUTCOME SUMMARY */}
      <Card className="shadow-sm border-none bg-gradient-to-br from-card to-card/50 overflow-hidden relative">
        <div className="absolute right-0 top-0 opacity-[0.03] pointer-events-none -translate-y-1/4 translate-x-1/4">
          <TrendingUp className="h-[300px] w-[300px]" />
        </div>
        <CardHeader>
          <CardTitle className="text-2xl font-bold">ROI Summary</CardTitle>
          <CardDescription>What the merchant actually achieved</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid sm:grid-cols-2 gap-4">
            <OutcomeCheck text="102 new customers in 45 days" />
            <OutcomeCheck text="9.9% customer growth" />
            <OutcomeCheck text="Average bill increased by 21.7% (₹448 → ₹545)" />
            <OutcomeCheck text="₹91,218 additional net revenue after all %, cashback and FlameZO commission" highlight />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
