import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappeGetDoc, useFrappePostCall } from '@/lib/frappe'
import { useState, useEffect, useMemo } from 'react'
import { Globe, MapPin, MousePointer2, Phone, Search, Sparkles, Star, ShieldAlert } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { toast } from 'sonner'
import { Link } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'

export default function GoogleGrowth() {
  const { selectedRestaurant, isGold } = useRestaurant()
  const [loading, setLoading] = useState(true)
  const [insights, setInsights] = useState<any>(null)

  const { data: restaurant, isLoading: loadingDoc } = useFrappeGetDoc('Restaurant', selectedRestaurant || '', {
    enabled: !!selectedRestaurant
  })

  const { call: fetchInsights } = useFrappePostCall('flamezo_backend.flamezo.api.google_business.fetch_google_insights')
  const { call: getAuthUrl } = useFrappePostCall('flamezo_backend.flamezo.api.google_business.get_google_auth_url')

  useEffect(() => {
    if (selectedRestaurant) {
      setLoading(true)
      fetchInsights({ restaurant_id: selectedRestaurant })
        .then((res: any) => setInsights(res.message))
        .finally(() => setLoading(false))
    }
  }, [selectedRestaurant, fetchInsights])

  const handleConnect = async () => {
    try {
      const res = await getAuthUrl({ restaurant_id: selectedRestaurant })
      if (res.message?.auth_url) {
        window.open(res.message.auth_url, '_blank')
        toast.info("Opening Google Authorization...")
      }
    } catch (err: any) {
      const errorMsg = err?.message || "Failed to initiate Google connection"
      toast.error(errorMsg)
      console.error("Google Connection Error:", err)
    }
  }

  const chartData = useMemo(() => {
    if (!insights) return []
    return insights.labels.map((label: string, i: number) => ({
      name: label,
      views: insights.monthly_views[i],
      clicks: insights.direction_clicks[i],
      visitors: insights.website_visits[i]
    }))
  }, [insights])

  if (loadingDoc) return <div className="p-8"><Skeleton className="h-64 w-full" /></div>

  const isConnected = !!restaurant?.google_business_location_id

  return (
    <div className="p-6 space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Badge variant="outline" className="bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-900/20 dark:text-blue-400">
              <Globe className="h-3 w-3 mr-1" /> Local SEO
            </Badge>
            {!isGold && (
              <Badge variant="outline" className="bg-amber-50 text-amber-600 border-amber-200">
                <Star className="h-3 w-3 mr-1 fill-amber-600" /> Premium
              </Badge>
            )}
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight">Google Growth</h1>
          <p className="text-muted-foreground mt-1">Boost your restaurant's visibility on Google Maps and Search.</p>
        </div>
        
        <div className="flex items-center gap-3">
          <Button variant="outline" asChild>
            <Link to="/google-growth/sync">Manage Menu Sync</Link>
          </Button>
          <Button className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-500/20" onClick={handleConnect}>
            {isConnected ? 'Reconnect Google Business' : 'Connect Google Business'}
          </Button>
        </div>
      </div>

      {/* Main Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard 
          title="Profile Views" 
          value={insights?.monthly_views.reduce((a:any, b:any) => a + b, 0).toLocaleString() || '0'} 
          change="+12.5%" 
          icon={<Search className="h-5 w-5 text-blue-500" />} 
          description="In the last 6 months"
        />
        <StatCard 
          title="Direction Clicks" 
          value={insights?.direction_clicks.reduce((a:any, b:any) => a + b, 0).toLocaleString() || '0'} 
          change="+8.2%" 
          icon={<MapPin className="h-5 w-5 text-emerald-500" />} 
          description="High intent visitors"
        />
        <StatCard 
          title="Website Visits" 
          value={insights?.website_visits.reduce((a:any, b:any) => a + b, 0).toLocaleString() || '0'} 
          change="+15.1%" 
          icon={<MousePointer2 className="h-5 w-5 text-indigo-500" />} 
          description="From Google Listing"
        />
        <StatCard 
          title="Calls" 
          value={insights?.calls.reduce((a:any, b:any) => a + b, 0).toLocaleString() || '0'} 
          change="+4.3%" 
          icon={<Phone className="h-5 w-5 text-orange-500" />} 
          description="Direct inquiries"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Performance Chart */}
        <Card className="lg:col-span-2 border-none shadow-xl bg-card">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-xl font-bold">Discovery Performance</CardTitle>
                <CardDescription>Monthly views and interactions</CardDescription>
              </div>
              <div className="flex items-center gap-4 text-xs font-medium">
                <div className="flex items-center gap-1.5"><div className="h-2 w-2 rounded-full bg-blue-500" /> Views</div>
                <div className="flex items-center gap-1.5"><div className="h-2 w-2 rounded-full bg-emerald-500" /> Clicks</div>
              </div>
            </div>
          </CardHeader>
          <CardContent className="h-[350px] pt-4">
            {loading ? (
              <Skeleton className="h-full w-full" />
            ) : chartData.length === 0 || chartData.every((d: any) => d.views === 0) ? (
              <EmptyState 
                variant="chart"
                title="No Discovery Data"
                description="Once your Google Business Profile starts getting traffic, we will show your performance trends here."
                icon={Search}
              />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="colorViews" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.1}/>
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="colorClicks" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.1}/>
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fontSize: 12, fill: '#64748B'}} dy={10} />
                  <YAxis axisLine={false} tickLine={false} tick={{fontSize: 12, fill: '#64748B'}} />
                  <Tooltip 
                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                  />
                  <Area type="monotone" dataKey="views" stroke="#3b82f6" strokeWidth={3} fillOpacity={1} fill="url(#colorViews)" />
                  <Area type="monotone" dataKey="clicks" stroke="#10b981" strokeWidth={3} fillOpacity={1} fill="url(#colorClicks)" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Local SEO Audit Card */}
        <div className="space-y-6">
          <Card className={`border-none shadow-xl transition-all duration-500 ${isConnected ? 'bg-gradient-to-br from-indigo-600 via-indigo-700 to-purple-800 text-white' : 'bg-muted/30 dark:bg-slate-900/40 border border-muted/50 text-muted-foreground'}`}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className={`h-5 w-5 ${isConnected ? 'text-indigo-200 animate-pulse' : 'text-muted-foreground'}`} /> Local SEO Score
              </CardTitle>
              <CardDescription className={isConnected ? 'text-indigo-100/80' : 'text-muted-foreground/60'}>
                {isConnected ? 'Audit of your online presence' : 'Connect GMB to see your score'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex flex-col items-center justify-center py-4">
                <div className="relative h-28 w-28">
                  <svg className="h-28 w-28 -rotate-90">
                    <circle className={isConnected ? "text-white/10" : "text-muted/10"} strokeWidth="10" stroke="currentColor" fill="transparent" r="48" cx="56" cy="56" />
                    <circle className={isConnected ? "text-white" : "text-muted-foreground/30"} strokeWidth="10" strokeDasharray={301.6} strokeDashoffset={301.6 * (1 - (isConnected ? 0.78 : 0))} strokeLinecap="round" stroke="currentColor" fill="transparent" r="48" cx="56" cy="56" />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="font-black text-3xl tracking-tighter">
                      {isConnected ? '78' : '--'}
                    </span>
                    {isConnected && <span className="text-[10px] font-bold uppercase tracking-widest opacity-70">Percent</span>}
                  </div>
                </div>
                {isConnected && (
                    <p className="mt-6 text-sm text-indigo-100/90 italic text-center px-4 font-medium leading-relaxed">
                      "Your profile visibility is great! <span className="underline decoration-indigo-300 underline-offset-4">Focus on review replies</span> to boost ranking."
                    </p>
                )}
              </div>
              <div className="space-y-4 pt-2">
                <AuditItem label="GMB Profile Completion" score={isConnected ? 100 : 0} isConnected={isConnected} />
                <AuditItem label="Menu Synchronization" score={isConnected ? 45 : 0} isConnected={isConnected} warning={isConnected} />
                <AuditItem label="Review Response Rate" score={isConnected ? 32 : 0} isConnected={isConnected} warning={isConnected} />
                <AuditItem label="Keyword Optimization" score={isConnected ? 85 : 0} isConnected={isConnected} />
              </div>
              {!isConnected && (
                  <Button className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold h-12 rounded-xl shadow-lg shadow-blue-500/20" onClick={handleConnect}>Connect Google Business</Button>
              )}
            </CardContent>
          </Card>

          <Card className="border shadow-lg">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-amber-500" /> Improvement Tips
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm space-y-3">
              <div className="flex gap-2 p-2 rounded bg-amber-50 dark:bg-amber-900/10 text-amber-800 dark:text-amber-200 border border-amber-200/50">
                <div className="font-bold">•</div>
                <p>Sync your latest 12 dishes to Google Products to increase "near me" traffic.</p>
              </div>
              <div className="flex gap-2 p-2 rounded bg-blue-50 dark:bg-blue-900/10 text-blue-800 dark:text-blue-200 border border-blue-200/50">
                <div className="font-bold">•</div>
                <p>Respond to 3 pending reviews to improve your profile's 'Active' rank.</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

function StatCard({ title, value, change, icon, description }: any) {
  return (
    <Card className="border-none shadow-md hover:shadow-lg transition-shadow bg-card">
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="p-2.5 bg-muted rounded-xl">{icon}</div>
          <span className="text-xs font-bold text-emerald-500 px-2 py-1 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg">{change}</span>
        </div>
        <div className="space-y-1">
          <h3 className="text-sm font-medium text-muted-foreground">{title}</h3>
          <p className="text-2xl font-bold">{value}</p>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider font-semibold">{description}</p>
        </div>
      </CardContent>
    </Card>
  )
}

function AuditItem({ label, score, warning, isConnected }: any) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[11px] font-bold uppercase tracking-wider">
        <span className={isConnected ? "text-indigo-100" : "text-muted-foreground"}>{label}</span>
        <span>{isConnected ? `${score}%` : '--'}</span>
      </div>
      <Progress value={score} className={isConnected ? "h-1.5 bg-white/20" : "h-1.5 bg-muted"} />
    </div>
  )
}
