import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall } from '@/lib/frappe'
import { useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { BarChart3, TrendingUp, CheckCircle2, Coins, MessageSquare, Phone, Mail, ChevronRight } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

interface CampaignAnalytics {
  campaign: {
    name: string; campaign_name: string; channel: string; status: string
    total_recipients: number; total_sent: number; total_failed: number
    total_conversions: number; total_cost_coins: number; revenue_attributed: number
    sent_at: string; message_template: string
  }
  status_breakdown: Record<string, number>
  events: Array<{
    name: string; customer: string; phone: string; channel: string; status: string
    sent_at: string; converted_at: string; coins_charged: number; conversion_order: string; error_message: string
  }>
}

const STATUS_COLOR_MAP: Record<string, string> = {
  Sent: 'bg-blue-100 text-blue-700',
  Delivered: 'bg-green-100 text-green-700',
  Converted: 'bg-emerald-100 text-emerald-700 font-semibold',
  Failed: 'bg-red-100 text-red-700',
  Queued: 'bg-slate-100 text-slate-600',
}



export default function MarketingAnalytics() {
  const { selectedRestaurant } = useRestaurant()
  const [searchParams] = useSearchParams()
  const [campaigns, setCampaigns] = useState<{ name: string; campaign_name: string; sent_at: string }[]>([])
  const [selectedCampaign, setSelectedCampaign] = useState<string>(searchParams.get('campaign') ?? '')
  const [analytics, setAnalytics] = useState<CampaignAnalytics | null>(null)
  const [loading, setLoading] = useState(false)

  const { call: fetchCampaigns } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.get_campaigns')
  const { call: fetchAnalytics } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.get_campaign_analytics')

  useEffect(() => {
    if (!selectedRestaurant) return
    fetchCampaigns({ restaurant_id: selectedRestaurant }).then((res: any) => {
      if (res?.message?.success) {
        const list = res.message.data || []
        const sentList = list.filter((c: any) => c.status === 'Sent')
        setCampaigns(sentList)
        if (!selectedCampaign && sentList.length > 0) {
          setSelectedCampaign(sentList[0].name)
        }
      }
    }).catch((err) => console.error("Failed to load campaigns for analytics:", err))
  }, [selectedRestaurant])

  useEffect(() => {
    if (!selectedCampaign) return
    setLoading(true)
    fetchAnalytics({ campaign_id: selectedCampaign }).then((res: any) => {
      if (res?.message?.success) setAnalytics(res.message.data)
    }).catch((err) => console.error("Failed to load campaign analytics:", err))
    .finally(() => setLoading(false))
  }, [selectedCampaign])

  const deliveryRate = analytics ? Math.round(((analytics.campaign.total_sent - analytics.campaign.total_failed) / Math.max(analytics.campaign.total_sent, 1)) * 100) : 0
  const conversionRate = analytics ? ((analytics.campaign.total_conversions / Math.max(analytics.campaign.total_sent, 1)) * 100).toFixed(1) : '0'

  const kpis = analytics ? [
    { label: 'Total Sent', value: analytics.campaign.total_sent.toLocaleString(), icon: <MessageSquare className="h-5 w-5 text-blue-500" />, sub: `${analytics.campaign.total_failed} failed` },
    { label: 'Delivery Rate', value: `${deliveryRate}%`, icon: <CheckCircle2 className="h-5 w-5 text-green-500" />, sub: 'Messages delivered' },
    { label: 'Conversion Rate', value: `${conversionRate}%`, icon: <TrendingUp className="h-5 w-5 text-indigo-500" />, sub: `${analytics.campaign.total_conversions} orders placed` },
    { label: 'Cost', value: `${analytics.campaign.total_cost_coins.toFixed(1)} Coins`, icon: <Coins className="h-5 w-5 text-amber-500" />, sub: `₹${analytics.campaign.revenue_attributed.toFixed(0)} revenue attributed` },
  ] : []

  const channelIcon = (channel: string) =>
    channel === 'WhatsApp' ? <MessageSquare className="h-3.5 w-3.5 text-green-500" />
      : channel === 'SMS' ? <Phone className="h-3.5 w-3.5 text-blue-500" />
        : <Mail className="h-3.5 w-3.5 text-purple-500" />

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1.5 text-[11px] font-bold tracking-widest uppercase text-muted-foreground/60 mb-2">
        <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
        <ChevronRight className="h-3 w-3" />
        <Link to="/marketing" className="hover:text-foreground transition-colors">Marketing</Link>
        <ChevronRight className="h-3 w-3" />
        <span className="text-foreground font-bold">Analytics</span>
      </nav>

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2 font-bold tracking-tight"><BarChart3 className="h-6 w-6 text-indigo-500" /> Analytics</h1>
          <p className="text-sm text-muted-foreground">Deep-dive into campaign performance</p>
        </div>
        <div className="w-64">
          <Select value={selectedCampaign} onValueChange={setSelectedCampaign}>
            <SelectTrigger><SelectValue placeholder="Select a campaign…" /></SelectTrigger>
            <SelectContent>
              {campaigns.map(c => (
                <SelectItem key={c.name} value={c.name}>
                  {c.campaign_name} {c.sent_at && `(${new Date(c.sent_at).toLocaleDateString()})`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {!selectedCampaign ? (
        <div className="flex flex-col items-center py-16 gap-3 text-muted-foreground">
          <BarChart3 className="h-12 w-12 opacity-20" />
          <p className="text-sm">Select a campaign above to view its analytics.</p>
        </div>
      ) : loading ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-28 w-full" />)}
          </div>
          <Skeleton className="h-64 w-full" />
        </div>
      ) : !analytics ? null : (
        <>
          {/* KPI Row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {kpis.map(kpi => (
              <Card key={kpi.label} className="border shadow-sm">
                <CardContent className="p-4 flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-muted-foreground">{kpi.label}</span>
                    {kpi.icon}
                  </div>
                  <p className="text-2xl font-bold">{kpi.value}</p>
                  <p className="text-xs text-muted-foreground">{kpi.sub}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Status Breakdown + Message Preview */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Status Breakdown</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {Object.entries(analytics.status_breakdown).map(([status, count]) => {
                  const total = analytics.campaign.total_sent || 1
                  const pct = Math.min(Math.round((count / total) * 100), 100)
                  const colorClass = STATUS_COLOR_MAP[status] ?? 'bg-muted text-muted-foreground'
                  return (
                    <div key={status} className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className={`px-2 py-0.5 rounded-full font-medium ${colorClass}`}>{status}</span>
                        <span className="font-semibold">{count} ({pct}%)</span>
                      </div>
                      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div className={`h-full rounded-full transition-all ${
                          status === 'Converted' ? 'bg-emerald-500'
                            : status === 'Sent' ? 'bg-blue-400'
                              : status === 'Failed' ? 'bg-red-400'
                                : 'bg-slate-300'
                        }`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  )
                })}
              </CardContent>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Message Sent</CardTitle>
                <CardDescription className="text-xs">
                  {analytics.campaign.channel} · Sent {analytics.campaign.sent_at ? new Date(analytics.campaign.sent_at).toLocaleString() : '—'}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="rounded-lg bg-muted/40 border p-4 text-sm whitespace-pre-wrap font-mono text-muted-foreground">
                  {analytics.campaign.message_template || '—'}
                </div>
                <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">{channelIcon(analytics.campaign.channel)} {analytics.campaign.channel}</span>
                  <span>~{analytics.campaign.total_recipients} recipients</span>
                  <span>{analytics.campaign.total_cost_coins.toFixed(1)} Coins total</span>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Per-customer event log */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Delivery Log</CardTitle>
              <CardDescription className="text-xs">Individual message status for each recipient (up to 500)</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="pb-2 font-medium pr-4">Customer</th>
                      <th className="pb-2 font-medium pr-4">Phone</th>
                      <th className="pb-2 font-medium pr-4">Status</th>
                      <th className="pb-2 font-medium pr-4">Sent At</th>
                      <th className="pb-2 font-medium pr-4">Converted</th>
                      <th className="pb-2 font-medium">Coins</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {analytics.events.slice(0, 100).map(ev => (
                      <tr key={ev.name} className="hover:bg-muted/30">
                        <td className="py-2 pr-4 text-foreground font-medium">{ev.customer || '—'}</td>
                        <td className="py-2 pr-4 font-mono">{ev.phone}</td>
                        <td className="py-2 pr-4">
                          <span className={`px-2 py-0.5 rounded-full text-xs ${STATUS_COLOR_MAP[ev.status] ?? 'bg-muted'}`}>{ev.status}</span>
                        </td>
                        <td className="py-2 pr-4 text-muted-foreground">{ev.sent_at ? new Date(ev.sent_at).toLocaleTimeString() : '—'}</td>
                        <td className="py-2 pr-4">
                          {ev.conversion_order ? (
                            <span className="flex items-center gap-1 text-emerald-600">
                              <CheckCircle2 className="h-3.5 w-3.5" /> {new Date(ev.converted_at).toLocaleDateString()}
                            </span>
                          ) : <span className="text-muted-foreground">—</span>}
                        </td>
                        <td className="py-2">{ev.coins_charged > 0 ? ev.coins_charged.toFixed(2) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {analytics.events.length > 100 && (
                  <p className="text-xs text-muted-foreground text-center mt-3">Showing 100 of {analytics.events.length} records</p>
                )}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
