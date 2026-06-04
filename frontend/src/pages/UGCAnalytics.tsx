import { useState } from 'react'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappeGetCall } from '@/lib/frappe'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Users, Eye, Wallet, TrendingUp, Loader2, IndianRupee, ArrowUpRight, ShoppingBag, Sparkles } from 'lucide-react'

const STATUS_LABELS: Record<string, string> = {
  offer_shown: 'Offer shown',
  story_shared: 'Story shared',
  story_verified: 'Story verified',
  proof_submitted: 'Proof submitted',
  flagged: 'Flagged',
  credited: 'Credited',
  rejected: 'Rejected',
  expired: 'Expired',
}

const MOCK_ANALYTICS_DATA = {
  total_submissions: 1642,
  reach_impressions: 74850,
  coins_issued: 48950,
  approval_rate: 94.2,
  monthly_budget: 30000,
  issued_this_month: 23450,
  total_revenue: 324500,
  referral_revenue: 112400,
  roi: 8.9,
  conversion_rate: 4.8,
  by_status: {
    offer_shown: 142,
    story_shared: 58,
    story_verified: 74,
    proof_submitted: 32,
    flagged: 12,
    credited: 1245,
    rejected: 24,
    expired: 55,
  }
}

export default function UGCAnalytics() {
  const { selectedRestaurant } = useRestaurant()
  const [demoMode, setDemoMode] = useState(true)

  const { data, isLoading } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.ugc.get_ugc_analytics',
    selectedRestaurant ? { restaurant_id: selectedRestaurant } : undefined,
    selectedRestaurant ? `ugc-analytics-${selectedRestaurant}` : undefined,
  )

  if (!selectedRestaurant) return <div className="p-8 text-center text-muted-foreground">Select a restaurant.</div>

  const body: any = (data as any)?.message || data
  const realData = body?.success ? body.data : null

  // Use mock data in demo mode, fallback to mock if no real data exists yet
  const d = demoMode ? MOCK_ANALYTICS_DATA : (realData || {
    total_submissions: 0,
    reach_impressions: 0,
    coins_issued: 0,
    approval_rate: 0,
    monthly_budget: 0,
    issued_this_month: 0,
    total_revenue: 0,
    referral_revenue: 0,
    roi: 0,
    conversion_rate: 0,
    by_status: {}
  })

  const budgetPct = d && d.monthly_budget > 0 ? Math.min(100, Math.round((d.issued_this_month / d.monthly_budget) * 100)) : 0

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">UGC Analytics</h1>
          <p className="text-muted-foreground mt-1">Lifetime performance of your story-for-cashback loop.</p>
        </div>
        <div className="flex items-center gap-2.5 bg-muted/60 border rounded-full px-3 py-1.5 text-xs font-medium self-start sm:self-center">
          <span className={demoMode ? "text-orange-500 font-semibold" : "text-muted-foreground"}>Simulated Data</span>
          <button
            onClick={() => setDemoMode(!demoMode)}
            className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none bg-muted ${
              demoMode ? 'bg-orange-500' : 'bg-gray-200 dark:bg-gray-800'
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                demoMode ? 'translate-x-4' : 'translate-x-0'
              }`}
            />
          </button>
          <span className={!demoMode ? "text-primary font-semibold" : "text-muted-foreground"}>Live Data</span>
        </div>
      </div>

      {demoMode && (
        <div className="bg-orange-500/10 border border-orange-500/20 text-orange-600 dark:text-orange-400 px-4 py-2.5 rounded-2xl text-sm font-medium">
          Showing simulated real-world preview data. Toggle to <strong>Live Data</strong> to view your actual metrics.
        </div>
      )}

      {isLoading && !demoMode ? (
        <div className="p-12 text-center text-muted-foreground"><Loader2 className="w-6 h-6 animate-spin mx-auto" /></div>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Stat icon={Users} label="Submissions" value={d.total_submissions} />
            <Stat icon={Eye} label="Story reach (views)" value={d.reach_impressions} accent="text-blue-600" />
            <Stat icon={Wallet} label="Cashback issued (₹)" value={d.coins_issued} accent="text-green-600" />
            <Stat icon={TrendingUp} label="Approval rate" value={`${d.approval_rate}%`} accent="text-orange-600" />
          </div>

          {/* Business Impact & ROI Section */}
          <div className="space-y-3.5 pt-2">
            <h2 className="text-lg font-bold tracking-tight flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-primary" />
              Business Impact & ROI
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card className="bg-primary/5 border-primary/20 relative overflow-hidden shadow-sm">
                <CardContent className="p-5">
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Total Revenue Earned</p>
                      <h3 className="text-3xl font-extrabold tracking-tight mt-1.5 text-primary">
                        ₹{(d.total_revenue + d.referral_revenue).toLocaleString('en-IN')}
                      </h3>
                    </div>
                    <div className="bg-primary/10 p-2.5 rounded-xl text-primary shrink-0">
                      <IndianRupee className="w-5 h-5" />
                    </div>
                  </div>
                  <div className="mt-4 flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span className="font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded-md flex items-center gap-0.5 shrink-0">
                      <ArrowUpRight className="w-3.5 h-3.5" /> {d.roi}x ROI
                    </span>
                    <span className="truncate">earned back per ₹1 cashback issued</span>
                  </div>
                </CardContent>
              </Card>

              <Card className="shadow-sm">
                <CardContent className="p-5">
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Direct Campaign Sales</p>
                      <h3 className="text-2xl font-bold mt-1.5">
                        ₹{d.total_revenue.toLocaleString('en-IN')}
                      </h3>
                    </div>
                    <div className="bg-muted p-2 rounded-lg text-muted-foreground shrink-0">
                      <ShoppingBag className="w-4 h-4" />
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-5">Direct revenue from {d.total_submissions} customer visits</p>
                </CardContent>
              </Card>

              <Card className="shadow-sm">
                <CardContent className="p-5">
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Estimated Referral Sales</p>
                      <h3 className="text-2xl font-bold mt-1.5">
                        ₹{d.referral_revenue.toLocaleString('en-IN')}
                      </h3>
                    </div>
                    <div className="bg-blue-500/10 p-2 rounded-lg text-blue-600 shrink-0">
                      <Users className="w-4 h-4" />
                    </div>
                  </div>
                  <div className="mt-5 flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span className="text-blue-600 dark:text-blue-400 font-semibold bg-blue-500/10 px-1.5 py-0.5 rounded-md shrink-0">
                      {d.conversion_rate}%
                    </span>
                    <span className="truncate">estimated view-to-order conversion</span>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>

          {d.monthly_budget > 0 && (
            <Card>
              <CardHeader><CardTitle className="text-base">Monthly Budget</CardTitle></CardHeader>
              <CardContent>
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-muted-foreground">₹{d.issued_this_month} issued</span>
                  <span className="text-muted-foreground">of ₹{d.monthly_budget}</span>
                </div>
                <div className="h-3 bg-muted rounded-full overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-orange-500 to-amber-400" style={{ width: `${budgetPct}%` }} />
                </div>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader><CardTitle className="text-base">Funnel by status</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {Object.entries(STATUS_LABELS).map(([key, label]) => (
                <div key={key} className="flex items-center justify-between py-1.5 border-b last:border-0">
                  <span className="text-sm text-muted-foreground">{label}</span>
                  <span className="text-sm font-semibold tabular-nums">{d.by_status?.[key] || 0}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

function Stat({ icon: Icon, label, value, accent }: { icon: any; label: string; value: any; accent?: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <Icon className={`w-5 h-5 mb-2 ${accent || 'text-primary'}`} />
        <div className={`text-2xl font-bold ${accent || ''}`}>{value ?? 0}</div>
        <div className="text-xs text-muted-foreground mt-0.5">{label}</div>
      </CardContent>
    </Card>
  )
}
