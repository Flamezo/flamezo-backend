import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall } from '@/lib/frappe'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Megaphone, Send, Zap, Users, TrendingUp, Coins, BarChart3, ArrowRight, AlertCircle, MessageSquare, Mail, Phone, ChevronRight } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

interface OverviewData {
  total_sent_month: number
  total_coins_month: number
  conversion_rate: number
  active_triggers: number
  channel_breakdown: { sms: number; whatsapp: number; email: number }
  recent_campaigns: Array<{
    name: string
    campaign_name: string
    channel: string
    status: string
    total_sent: number
    total_conversions: number
    total_cost_coins: number
    sent_at: string
    creation: string
  }>
}

const STATUS_COLORS: Record<string, string> = {
  Draft: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  Scheduled: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  Sending: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300',
  Sent: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
  Failed: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
  Cancelled: 'bg-slate-100 text-slate-500',
}

const CHANNEL_ICON: Record<string, React.ReactNode> = {
  SMS: <Phone className="h-3.5 w-3.5" />,
  WhatsApp: <MessageSquare className="h-3.5 w-3.5 text-green-500" />,
  Email: <Mail className="h-3.5 w-3.5 text-blue-500" />,
}



export default function MarketingOverview() {
  const { selectedRestaurant, isGold } = useRestaurant()
  const [data, setData] = useState<OverviewData | null>(null)
  const [loading, setLoading] = useState(true)

  const { call: fetchOverview } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.get_marketing_overview')

  useEffect(() => {
    if (!selectedRestaurant || !isGold) return
    setLoading(true)
    fetchOverview({ restaurant_id: selectedRestaurant })
      .then((res: any) => {
        if (res?.message?.success) {
          setData(res.message.data)
        }
      })
      .catch((err) => console.error("Failed to fetch overview:", err))
      .finally(() => setLoading(false))
  }, [selectedRestaurant])

  if (!isGold) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4 text-center p-8">
        <div className="p-4 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 text-white">
          <Megaphone className="h-8 w-8" />
        </div>
        <h2 className="text-2xl font-bold">Marketing Studio</h2>
        <p className="text-muted-foreground max-w-md">
          Upgrade to <strong>GOLD</strong> to access the Marketing Studio — run WhatsApp campaigns, SMS blasts, and fully automated customer retention triggers.
        </p>
        <Link to="/autopay-setup">
          <Button className="bg-gradient-to-r from-indigo-500 to-purple-600 text-white">Upgrade to GOLD</Button>
        </Link>
      </div>
    )
  }

  const kpis = [
    {
      label: 'Messages Sent (Month)',
      value: loading ? '—' : (data?.total_sent_month?.toLocaleString() ?? '0'),
      icon: <Send className="h-5 w-5 text-blue-500" />,
      sub: 'Across all channels',
    },
    {
      label: 'Coins Spent (Month)',
      value: loading ? '—' : `₹${(data?.total_coins_month ?? 0).toFixed(1)}`,
      icon: <Coins className="h-5 w-5 text-amber-500" />,
      sub: 'Marketing deductions',
    },
    {
      label: 'Conversion Rate',
      value: loading ? '—' : `${data?.conversion_rate ?? 0}%`,
      icon: <TrendingUp className="h-5 w-5 text-green-500" />,
      sub: 'Orders within 24h of message',
    },
    {
      label: 'Active Automations',
      value: loading ? '—' : String(data?.active_triggers ?? 0),
      icon: <Zap className="h-5 w-5 text-yellow-500" />,
      sub: 'Running triggers',
    },
  ]

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1.5 text-[11px] font-bold tracking-widest uppercase text-muted-foreground/60 mb-2">
        <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
        <ChevronRight className="h-3 w-3" />
        <span className="text-foreground">Marketing</span>
      </nav>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-lg">
            <Megaphone className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Marketing Overview</h1>
            <p className="text-sm text-muted-foreground">Campaigns, automation, and customer growth</p>
          </div>
        </div>
        <Link to="/marketing/campaigns">
          <Button className="bg-gradient-to-r from-indigo-500 to-purple-600 text-white gap-2 shadow-md hover:shadow-indigo-500/20">
            <Send className="h-4 w-4" /> New Campaign
          </Button>
        </Link>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((kpi) => (
          <Card key={kpi.label} className="border shadow-sm">
            <CardContent className="p-4 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">{kpi.label}</span>
                {kpi.icon}
              </div>
              {loading ? (
                <Skeleton className="h-7 w-20" />
              ) : (
                <p className="text-2xl font-bold">{kpi.value}</p>
              )}
              <p className="text-xs text-muted-foreground">{kpi.sub}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Channel Breakdown + Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Channel Breakdown */}
        <Card className="lg:col-span-1">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Channel Breakdown</CardTitle>
            <CardDescription className="text-xs">Messages sent this month</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {loading ? (
              <div className="space-y-2">{[1, 2, 3].map(i => <Skeleton key={i} className="h-9 w-full" />)}</div>
            ) : (
              <>
                {[
                  { label: 'WhatsApp', value: data?.channel_breakdown?.whatsapp ?? 0, color: 'bg-green-500', icon: '💬' },
                  { label: 'SMS', value: data?.channel_breakdown?.sms ?? 0, color: 'bg-blue-500', icon: '📱' },
                  { label: 'Email', value: data?.channel_breakdown?.email ?? 0, color: 'bg-purple-500', icon: '📧' },
                ].map(ch => {
                  const total = (data?.total_sent_month ?? 0) || 1
                  const pct = Math.round((ch.value / total) * 100)
                  return (
                    <div key={ch.label} className="space-y-1">
                      <div className="flex justify-between text-sm">
                        <span>{ch.icon} {ch.label}</span>
                        <span className="font-semibold">{ch.value.toLocaleString()}</span>
                      </div>
                      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${ch.color} transition-all`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  )
                })}
              </>
            )}
          </CardContent>
        </Card>

        {/* Quick Actions */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Quick Actions</CardTitle>
            <CardDescription className="text-xs">Common marketing tasks</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3">
            {[
              { label: 'New Campaign', desc: 'Send a targeted blast', icon: <Send className="h-5 w-5 text-blue-500" />, href: '/marketing/campaigns' },
              { label: 'Set Automation', desc: 'Post-visit review nudge', icon: <Zap className="h-5 w-5 text-yellow-500" />, href: '/marketing/automation' },
              { label: 'Build Segment', desc: 'Group customers', icon: <Users className="h-5 w-5 text-indigo-500" />, href: '/marketing/segments' },
              { label: 'View Analytics', desc: 'Check ROI & conversions', icon: <BarChart3 className="h-5 w-5 text-green-500" />, href: '/marketing/analytics' },
            ].map(a => (
              <Link to={a.href} key={a.label}>
                <div className="flex items-start gap-3 p-3 rounded-lg border hover:bg-muted/50 transition-colors cursor-pointer group">
                  <div className="mt-0.5">{a.icon}</div>
                  <div>
                    <p className="text-sm font-semibold group-hover:text-primary transition-colors">{a.label}</p>
                    <p className="text-xs text-muted-foreground">{a.desc}</p>
                  </div>
                  <ArrowRight className="h-4 w-4 ml-auto text-muted-foreground group-hover:text-primary transition-colors mt-1" />
                </div>
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Recent Campaigns */}
      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-base">Recent Campaigns</CardTitle>
            <CardDescription className="text-xs">Last 5 campaigns</CardDescription>
          </div>
          <Link to="/marketing/campaigns">
            <Button variant="ghost" size="sm" className="gap-1 text-xs">View All <ArrowRight className="h-3.5 w-3.5" /></Button>
          </Link>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3">{[1, 2, 3].map(i => <Skeleton key={i} className="h-12 w-full" />)}</div>
          ) : !data?.recent_campaigns?.length ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center text-muted-foreground">
              <AlertCircle className="h-8 w-8" />
              <p className="text-sm">No campaigns yet. Create your first one!</p>
              <Link to="/marketing/campaigns"><Button size="sm">Create Campaign</Button></Link>
            </div>
          ) : (
            <div className="divide-y">
              {data.recent_campaigns.map(c => (
                <Link to={`/marketing/analytics?campaign=${c.name}`} key={c.name}>
                  <div className="py-3 flex items-center justify-between hover:bg-muted/30 -mx-2 px-2 rounded-md transition-colors">
                    <div className="flex items-center gap-3">
                      <div className="p-1.5 rounded-md bg-muted">{CHANNEL_ICON[c.channel]}</div>
                      <div>
                        <p className="text-sm font-medium">{c.campaign_name}</p>
                        <p className="text-xs text-muted-foreground">{c.total_sent} sent · {c.total_conversions} conversions · {c.total_cost_coins.toFixed(1)} coins</p>
                      </div>
                    </div>
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_COLORS[c.status] ?? ''}`}>{c.status}</span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
