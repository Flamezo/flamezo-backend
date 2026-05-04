import { ReactNode, useState } from 'react'
import { useFrappeGetDocList, useFrappeGetCall } from '@/lib/frappe'
import { LogisticsHubCard } from '@/components/LogisticsHubCard'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { 
  ShoppingCart, 
  Package, 
  TrendingUp, 
  Clock, 
  CheckCircle, 
  XCircle, 
  AlertCircle, 
  Crown, 
  Lock,
  Zap,
  Star,
  Activity,
  MapPin,
  QrCode,
  Users,
  Copy,
  Gift
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useCurrency } from '@/hooks/useCurrency'
import { cn, copyToClipboard } from '@/lib/utils'
import { 
  PieChart, 
  Pie, 
  Cell, 
  ResponsiveContainer, 
  Tooltip as RechartsTooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis
} from 'recharts'
import { EmptyState } from '@/components/EmptyState'

// Enhanced Stat Card with Trends
function StatCard({ 
  title, 
  value, 
  subtext, 
  icon: Icon, 
  trend, 
  trendValue, 
  isGold, 
  gradient 
}: { 
  title: string, 
  value: string | number, 
  subtext: string, 
  icon: any, 
  trend?: 'up' | 'down', 
  trendValue?: string,
  isGold?: boolean,
  gradient?: string
}) {
  return (
    <Card className={cn(
      "relative overflow-hidden transition-all duration-300 hover:shadow-lg border-none bg-card shadow-sm",
      isGold && gradient && `bg-gradient-to-br ${gradient} text-white`
    )}>
      {isGold && (
        <div className="absolute top-0 right-0 p-3 opacity-10">
          <Icon className="h-16 w-16" />
        </div>
      )}
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
        <CardTitle className={cn("text-xs font-medium uppercase tracking-wider", isGold ? "text-white/80" : "text-muted-foreground")}>
          {title}
        </CardTitle>
        {!isGold && <Icon className="h-4 w-4 text-primary" />}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold tracking-tight">
          {value}
        </div>
        <div className="mt-1 flex items-center gap-2">
          {trend && (
            <span className={cn(
              "flex items-center text-[10px] font-bold px-1.5 py-0.5 rounded-full",
              trend === 'up' 
                ? (isGold ? "bg-white/20 text-white" : "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400")
                : (isGold ? "bg-white/10 text-white/80" : "bg-rose-100 text-rose-700 dark:bg-rose-950/30 dark:text-rose-400")
            )}>
              {trend === 'up' ? <TrendingUp className="h-2.5 w-2.5 mr-1" /> : <TrendingUp className="h-2.5 w-2.5 mr-1 rotate-180" />}
              {trendValue}
            </span>
          )}
          <p className={cn("text-[11px]", isGold ? "text-white/70" : "text-muted-foreground")}>
            {subtext}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}

// Custom SVG Line Chart for Revenue
function RevenueTrendChart({ data }: { data: number[] }) {
  if (!data || data.length === 0 || data.every(v => v === 0)) {
    return (
      <EmptyState 
        variant="chart"
        title="No Revenue Data"
        description="Waiting for your first few orders to generate growth insights."
        icon={TrendingUp}
      />
    )
  }
  
  const max = Math.max(...data) || 1
  const height = 100
  const width = 300
  const points = data.map((val, i) => ({
    x: (i / (data.length - 1)) * width,
    y: height - (val / max) * height
  }))
  
  const pathData = points.reduce((acc, p, i) => 
    i === 0 ? `M ${p.x} ${p.y}` : `${acc} L ${p.x} ${p.y}`, ""
  )
  
  const areaData = `${pathData} L ${width} ${height} L 0 ${height} Z`

  return (
    <div className="w-full h-[120px] relative mt-4 group">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full overflow-visible">
        <defs>
          <linearGradient id="gradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="var(--primary)" stopOpacity="0.4" />
            <stop offset="100%" stopColor="var(--primary)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaData} fill="url(#gradient)" className="transition-all duration-700" />
        <path d={pathData} fill="none" stroke="var(--primary)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="transition-all duration-700 opacity-80 group-hover:opacity-100" />
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="4" fill="var(--background)" stroke="var(--primary)" strokeWidth="2" className="opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
        ))}
      </svg>
    </div>
  )
}

// Bar Chart for Top Products
function TopProductsChart({ products }: { products: { name: string, count: number, total: number }[] }) {
  if (!products || products.length === 0 || products.every(p => p.count === 0)) {
    return (
      <EmptyState 
        variant="chart"
        title="No Sales Yet"
        description="Your best-selling dishes will appear here once guests start ordering."
        icon={Package}
      />
    )
  }
  const max = Math.max(...products.map(p => p.count)) || 1
  
  return (
    <div className="space-y-4 mt-2">
      {products.map((p, i) => (
        <div key={i} className="space-y-1.5">
          <div className="flex justify-between text-xs font-medium">
            <span className="truncate max-w-[150px]">{p.name}</span>
            <span className="text-muted-foreground">{p.count} orders</span>
          </div>
          <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
            <div 
              className="h-full bg-primary rounded-full transition-all duration-1000 ease-out"
              style={{ width: `${(p.count / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

// Menu Heatmap Table (Views vs Orders Gap)
function MenuHeatmapTable({ heatmap }: { heatmap: any[] }) {
  if (!heatmap || heatmap.length === 0) {
    return (
      <EmptyState 
        variant="chart"
        title="Analysis Pending"
        description="We need more guest interactions to identify friction in your menu."
        icon={Activity}
      />
    )
  }
  
  return (
    <div className="space-y-6 mt-4">
      {/* Visual Bar Chart for Top Gap Items */}
      <div className="h-[200px] w-full bg-muted/5 rounded-2xl p-4 border border-border/20">
        <p className="text-[10px] uppercase font-bold text-muted-foreground mb-4 tracking-widest text-center">Engagement vs Conversion</p>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={heatmap.slice(0, 5)} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <XAxis dataKey="item_name" hide />
            <YAxis hide />
            <RechartsTooltip 
               cursor={{ fill: 'rgba(0,0,0,0.05)' }}
               contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
            />
            <Bar dataKey="views" fill="#f59e0b" radius={[4, 4, 0, 0]} barSize={20} name="Views (Interest)" />
            <Bar dataKey="orders" fill="#10b981" radius={[4, 4, 0, 0]} barSize={20} name="Orders (Sales)" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-4 text-[10px] uppercase font-bold text-muted-foreground px-2">
        <span className="col-span-2">Dish Name</span>
        <span className="text-center">Views</span>
        <span className="text-right">Conv.</span>
      </div>
      <div className="space-y-1">
        {heatmap.map((item, i) => (
          <div key={i} className="group grid grid-cols-4 items-center p-2 rounded-xl bg-muted/20 hover:bg-muted/40 transition-all border border-transparent hover:border-border/40">
            <div className="col-span-2 flex flex-col">
              <span className="text-xs font-bold truncate">{item.item_name}</span>
              <span className={cn(
                "text-[9px] font-medium",
                item.status === 'Optimal' ? "text-emerald-500" : "text-amber-500"
              )}>
                {item.status}
              </span>
            </div>
            <div className="text-center">
              <span className="text-xs font-mono">{item.views}</span>
            </div>
            <div className="text-right flex flex-col items-end">
              <span className={cn(
                "text-xs font-bold",
                item.conversion > 10 ? "text-emerald-500" : item.conversion > 5 ? "text-amber-500" : "text-rose-500"
              )}>
                {item.conversion}%
              </span>
              <div className="h-1 w-10 bg-muted rounded-full mt-1 overflow-hidden">
                <div 
                  className={cn(
                    "h-full rounded-full transition-all duration-700",
                    item.conversion > 10 ? "bg-emerald-500" : item.conversion > 5 ? "bg-amber-500" : "bg-rose-500"
                  )}
                  style={{ width: `${Math.min(item.conversion * 2, 100)}%` }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// QR ROAS Breakdown with Donut Chart
function QRRoasSection({ roas }: { roas: any[] }) {
  if (!roas || roas.length === 0) {
    return (
      <EmptyState 
        variant="chart"
        title="No Attribution Data"
        description="Orders tracked back to specific physical QR scans will show up here."
        icon={QrCode}
      />
    )
  }
  const { formatAmountNoDecimals } = useCurrency()
  
  const COLORS = ['#6366f1', '#8b5cf6', '#3b82f6', '#10b981', '#f59e0b']

  return (
    <div className="space-y-6 mt-4">
      <div className="h-[180px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={roas}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={80}
              paddingAngle={5}
              dataKey="revenue"
              nameKey="source"
            >
              {roas.map((_, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <RechartsTooltip 
              contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
              formatter={(value: any) => [formatAmountNoDecimals(value), 'Revenue']}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {roas.map((item, i) => (
          <div key={i} className="p-3 rounded-xl bg-muted/20 border border-border/40 space-y-1">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
              <span className="text-[10px] font-bold uppercase tracking-tight truncate">{item.source}</span>
            </div>
            <p className="text-sm font-black">{formatAmountNoDecimals(item.revenue)}</p>
            <p className="text-[9px] text-muted-foreground">{item.orders} orders</p>
          </div>
        ))}
      </div>
    </div>
  )
}

// Locked Content Wrapper
function LockedInsight({ title, description, children, isUnlocked }: { title: string, description: string, children: ReactNode, isUnlocked: boolean }) {
  if (isUnlocked) return <>{children}</>
  
  return (
    <div className="relative overflow-hidden rounded-xl border bg-card/50 p-6 min-h-[200px] flex flex-col justify-center">
      <div className="absolute inset-0 blur-[3px] opacity-40 select-none pointer-events-none grayscale">
        {children}
      </div>
      <div className="relative z-10 flex flex-col items-center text-center space-y-3">
        <div className="h-12 w-12 bg-primary/10 rounded-full flex items-center justify-center">
          <Lock className="h-6 w-6 text-primary" />
        </div>
        <div className="space-y-1">
          <h3 className="font-bold text-lg">{title}</h3>
          <p className="text-sm text-muted-foreground max-w-[250px] mx-auto">
            {description}
          </p>
        </div>
        <Button 
          variant="default" 
          size="sm" 
          className="rounded-full bg-primary hover:bg-primary/90 text-white shadow-lg shadow-primary/20"
          asChild
        >
          <Link to="/billing">
            <Crown className="h-4 w-4 mr-2" />
            Unlock Gold Insights
          </Link>
        </Button>
      </div>
    </div>
  )
}

// Main Dashboard Component
export default function Dashboard() {
  const { selectedRestaurant, referralCode } = useRestaurant()
  const [showReferralInfo, setShowReferralInfo] = useState(false)
  const [copied, setCopied] = useState(false)
  const { isGold, isDiamond } = useRestaurant()
  const isAtLeastGold = isGold || isDiamond
  const { formatAmountNoDecimals } = useCurrency()
  const navigate = useNavigate()
  
  // Fetch data
  const { data: orders, isLoading: ordersLoading } = useFrappeGetDocList('Order', {
    fields: ['name', 'status', 'total', 'creation', 'restaurant', 'table_number', 'order_type', 'delivery_partner', 'delivery_status', 'delivery_fee'],
    filters: selectedRestaurant ? ({ restaurant: selectedRestaurant } as any) : undefined,
    limit: 100,
    orderBy: { field: 'creation', order: 'desc' }
  }, selectedRestaurant ? `orders-dashboard-${selectedRestaurant}` : null)

  const { data: products } = useFrappeGetDocList('Menu Product', {
    fields: ['name', 'product_name', 'price', 'is_active', 'restaurant'],
    filters: selectedRestaurant ? ({ restaurant: selectedRestaurant } as any) : undefined,
    limit: 100
  }, selectedRestaurant ? `products-dashboard-${selectedRestaurant}` : null)

  const { data: restaurants } = useFrappeGetDocList('Restaurant', {
    fields: ['name', 'restaurant_name', 'is_active', 'owner_email', 'city', 'state'],
    filters: selectedRestaurant ? ({ name: selectedRestaurant } as any) : undefined,
    limit: 100
  }, selectedRestaurant ? `restaurants-dashboard-${selectedRestaurant}` : null)
  
  // Real-time Analytics Summary
  const { data: analytics } = useFrappeGetCall('dinematters.dinematters.api.analytics.get_dashboard_summary', {
    restaurant_id: selectedRestaurant
  }, selectedRestaurant ? `analytics-dashboard-${selectedRestaurant}` : null)

  const analyticsData = analytics?.message?.success ? analytics.message : (analytics?.success ? analytics : null)

  // Calculations
  const totalOrders = orders?.length || 0
  const totalRevenue = orders?.reduce((sum, order) => sum + (order.total || 0), 0) || 0

  // Today's Stats
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  const todayOrders = orders?.filter((o: any) => new Date(o.creation) >= today) || []


  // 7-day Trend for Chart
  const last7Days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date()
    d.setDate(d.getDate() - (6 - i))
    d.setHours(0, 0, 0, 0)
    return d
  })

  const dailyRevenue = last7Days.map(date => {
    const nextDay = new Date(date)
    nextDay.setDate(nextDay.getDate() + 1)
    return orders?.filter(o => {
      const d = new Date(o.creation)
      return d >= date && d < nextDay
    }).reduce((sum, o) => sum + (o.total || 0), 0) || 0
  })

  // Top Products — real order-count data from analyticsData.topPerformers
  // Falls back to menu products slice ONLY when no analytics data available
  const topProducts = (analyticsData?.topPerformers && analyticsData.topPerformers.length > 0)
    ? analyticsData.topPerformers.map((p: any) => ({
        name: p.item_name || p.name || 'Unknown',
        count: p.order_count ?? p.views ?? 0,
        total: p.total_revenue ?? 100
      }))
    : (products?.slice(0, 4).map(p => ({
        name: p.product_name || p.name,
        count: 0,
        total: 0
      })) || [])

  const getStatusIcon = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'completed':
      case 'delivered':
        return <CheckCircle className="h-4 w-4 text-emerald-500" />
      case 'cancelled':
      case 'rejected':
        return <XCircle className="h-4 w-4 text-rose-500" />
      case 'pending':
        return <Clock className="h-4 w-4 text-amber-500" />
      default:
        return <AlertCircle className="h-4 w-4 text-muted-foreground" />
    }
  }

  return (
    <div className="space-y-8 pb-10">
      {/* Top Banner & Strategy */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="text-3xl font-bold tracking-tight text-foreground">Dashboard</h1>
          </div>
          <p className="text-muted-foreground text-sm flex items-center gap-1.5">
            <Activity className="h-4 w-4 text-primary" />
            Showing rolling 7-day performance for <span className="font-bold text-foreground">{restaurants?.[0]?.restaurant_name || selectedRestaurant}</span>
          </p>
        </div>

        {/* Merchant Referrals - Compact Header Version */}
        <div className="relative overflow-hidden rounded-xl bg-gradient-to-r from-indigo-900 to-indigo-800 p-4 text-white shadow-lg shadow-indigo-500/10 border border-indigo-700/30 flex items-center gap-4 group cursor-pointer hover:shadow-indigo-500/20 transition-all duration-300 max-w-sm"
          onClick={() => setShowReferralInfo(true)}
        >
          <div className="absolute -top-2 -right-2 opacity-5">
            <Users className="h-16 w-16" />
          </div>
          <div className="h-10 w-10 bg-indigo-500 rounded-lg flex items-center justify-center shadow-lg shadow-indigo-500/20 group-hover:scale-110 transition-transform">
             <Star className="h-5 w-5 text-indigo-100 fill-indigo-100" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <p className="text-[10px] uppercase font-bold text-indigo-200/60 tracking-wider">Refer & Earn ₹500</p>
              <div className="h-1 w-1 rounded-full bg-indigo-400/50" />
              <p className="text-[10px] font-mono font-bold text-white tracking-widest">{referralCode || '...'}</p>
            </div>
            <p className="text-xs font-medium text-indigo-100/90 line-clamp-1">Share code with other merchants</p>
          </div>
          <div className="bg-emerald-500 p-2 rounded-lg shadow-lg shadow-emerald-500/20 group-hover:bg-emerald-400 transition-colors">
            <svg className="h-4 w-4 fill-white" viewBox="0 0 24 24">
              <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/>
            </svg>
          </div>
        </div>
      </div>

      {/* --- PRODUCTION ANALYTICS GRID --- */}
      <div className="space-y-8">
        
        {/* Layer 1: Guest Engagement (Addiction - For All Tiers) */}
        <div>
          <div className="flex items-center gap-2 mb-4">
             <div className="h-1 w-8 bg-primary rounded-full" />
             <h2 className="text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">Guest Engagement</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard 
              title="Menu Scans (7D)"
              value={analyticsData?.traffic?.totalViews || 0}
              subtext={`Total: ${analyticsData?.traffic?.lifetimeScans || 0} Lifetime`}
              icon={QrCode}
              trend={analyticsData?.traffic?.growth >= 0 ? 'up' : 'down'}
              trendValue={`${Math.abs(analyticsData?.traffic?.growth || 0)}%`}
              isGold={false}
            />
            <StatCard 
              title="Unique Guests"
              value={analyticsData?.traffic?.uniqueVisitors || 0}
              subtext="Unique brand reach (7D)"
              icon={Users}
              isGold={false}
            />
            <StatCard 
              title="Peak Discovery"
              value={analyticsData?.traffic?.peakHour || "00:00"}
              subtext="Busiest time for menu scans"
              icon={Clock}
              isGold={false}
            />
            <StatCard 
              title="Menu Health"
              value={`${products?.length || 0} Items`}
              subtext={`${analyticsData?.traffic?.totalViews || 0} impressions served`}
              icon={Package}
              isGold={false}
            />
          </div>
        </div>

        {/* Layer 2: Business Performance (Impact - For GOLD/DIAMOND) */}
        {isAtLeastGold && (
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-700">
            <div className="flex items-center gap-2 mb-4">
               <div className="h-1 w-8 bg-indigo-500 rounded-full" />
               <h2 className="text-xs font-bold uppercase tracking-[0.2em] text-indigo-500/80">Business Performance</h2>
            </div>
            
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-4">
              <div className="lg:col-span-2">
                 <LogisticsHubCard orders={orders || []} isLoading={ordersLoading} />
              </div>
              <div className="lg:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-4">
                <StatCard 
                  title="7D Revenue"
                  value={formatAmountNoDecimals(totalRevenue)}
                  subtext={`vs ${formatAmountNoDecimals(totalRevenue * 0.9)} last 7D`}
                  icon={TrendingUp}
                  trend="up"
                  trendValue="10%"
                  isGold={true}
                  gradient="from-indigo-600 to-blue-500"
                />
                <StatCard 
                  title="Weekly Orders"
                  value={totalOrders}
                  subtext={`${Math.round(totalOrders / 7)} orders daily average`}
                  icon={ShoppingCart}
                  isGold={true}
                  gradient="from-emerald-600 to-teal-500"
                />
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-2">
              <StatCard 
                title="Conv. Rate %"
                value={`${analyticsData?.enhanced?.conversionRate || 0}%`}
                subtext="Scans to Order success"
                icon={Zap}
                isGold={true}
                gradient="from-amber-500 to-orange-500"
              />
              <StatCard 
                title="Avg Order Value"
                value={formatAmountNoDecimals(analyticsData?.enhanced?.avgOrderValue || 0)}
                subtext="Spend per customer visit"
                icon={Activity}
                isGold={true}
                gradient="from-rose-500 to-pink-500"
              />
            </div>
          </div>
        )}
      </div>

      {/* Insights & Actions Grid */}
      <div className="grid gap-6 lg:grid-cols-7 pt-4">
        {/* Revenue & Scan Trends Comparison Chart */}
        <Card className="lg:col-span-4 shadow-sm border-none bg-card">
          <CardHeader className="flex flex-row items-center justify-between">
            <div className="space-y-1">
              <CardTitle className="text-lg font-bold flex items-center gap-2">
                 Growth Intelligence
                 <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">GOLD</span>
              </CardTitle>
              <CardDescription>Visualizing revenue vs guest discovery paths</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <LockedInsight 
              isUnlocked={isAtLeastGold} 
              title="Trend Analysis" 
              description="See how your scans drive orders across the week."
            >
              <div className="flex items-end justify-between mt-4 mb-2 h-[20px]">
                {last7Days.map((d, i) => (
                  <span key={i} className="text-[10px] text-muted-foreground font-medium">
                    {d.toLocaleDateString(undefined, { weekday: 'short' })}
                  </span>
                ))}
              </div>
              <RevenueTrendChart data={dailyRevenue} />
              <div className="mt-8 grid grid-cols-2 lg:grid-cols-4 gap-4">
                 <div className="p-3 bg-muted/30 rounded-xl border border-border/40">
                     <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wide">Peak Day</p>
                     <p className="text-sm font-bold">
                       {analyticsData?.traffic?.peakDay || <span className="text-muted-foreground text-xs italic">No data yet</span>}
                     </p>
                  </div>
                 <div className="p-3 bg-muted/30 rounded-xl border border-border/40">
                     <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wide">Ticket Size</p>
                     <p className="text-sm font-bold">{formatAmountNoDecimals(analyticsData?.enhanced?.avgOrderValue || 0)}</p>
                  </div>
                 <div className="p-3 bg-muted/30 rounded-xl border border-border/40">
                     <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wide">Scan Efficiency</p>
                     <p className={cn(
                       "text-sm font-bold",
                       analyticsData?.enhanced?.scanEfficiency === 'High' && 'text-primary',
                       analyticsData?.enhanced?.scanEfficiency === 'Medium' && 'text-amber-500',
                       analyticsData?.enhanced?.scanEfficiency === 'Low' && 'text-rose-500',
                       !analyticsData?.enhanced?.scanEfficiency && 'text-muted-foreground'
                     )}>
                       {analyticsData?.enhanced?.scanEfficiency || '—'}
                     </p>
                  </div>
                  <div className="p-3 bg-muted/30 rounded-xl border border-border/40">
                     <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wide">Churn Risk</p>
                     <p className={cn(
                       "text-sm font-bold",
                       analyticsData?.enhanced?.churnRiskColor === 'emerald' && 'text-emerald-500',
                       analyticsData?.enhanced?.churnRiskColor === 'amber' && 'text-amber-500',
                       analyticsData?.enhanced?.churnRiskColor === 'rose' && 'text-rose-500',
                       !analyticsData?.enhanced?.churnRiskLabel && 'text-muted-foreground'
                     )}>
                       {analyticsData?.enhanced?.churnRiskLabel
                         ? `${analyticsData.enhanced.churnRiskLabel} ${analyticsData.enhanced.churnRate > 0 ? `(${analyticsData.enhanced.churnRate}%)` : ''}`
                         : '—'}
                     </p>
                  </div>
              </div>
            </LockedInsight>
          </CardContent>
        </Card>

        {/* Top Performers (Reach vs Sales) */}
        <Card className="lg:col-span-3 shadow-sm border-none bg-card">
          <CardHeader>
            <CardTitle className="text-lg font-bold">Top Products</CardTitle>
            <CardDescription>Reach metrics for your menu items</CardDescription>
          </CardHeader>
          <CardContent>
            <LockedInsight 
              isUnlocked={isAtLeastGold} 
              title="Engagement Insights" 
              description="Learn which dishes attract eyes and which ones attract cash."
            >
              <TopProductsChart products={analyticsData?.topPerformers?.map((p: any) => ({
                name: p.item_name,
                count: p.views,
                total: analyticsData.traffic.totalViews
              })) || topProducts} />
              <div className="mt-10 pt-6 border-t border-border flex justify-between items-center">
                 <p className="text-[11px] text-muted-foreground italic flex items-center gap-1">
                   <Clock className="h-3 w-3" /> Updated in real-time
                 </p>
                <Button variant="outline" size="sm" className="text-xs rounded-full px-4" asChild>
                  <Link to="/products">Manage Menu</Link>
                </Button>
              </div>
            </LockedInsight>
          </CardContent>
        </Card>
      </div>

      {/* Advanced Insights Layer: Heatmap & ROAS */}
      <div className="grid gap-6 lg:grid-cols-7 pt-4">
         {/* Menu Heatmap: The "Click-to-Order" Gap */}
         <Card className="lg:col-span-4 shadow-sm border-none bg-card overflow-hidden">
            <div className="absolute top-0 right-0 p-6 opacity-[0.02] pointer-events-none">
              <TrendingUp className="h-32 w-32" />
            </div>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <CardTitle className="text-lg font-bold flex items-center gap-2">
                    Menu Heatmap
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-200">GAP ANALYSIS</span>
                  </CardTitle>
                  <CardDescription>Identifying dishes that are clicked but not ordered</CardDescription>
                </div>
                <div className="h-10 w-10 rounded-full bg-primary/5 flex items-center justify-center">
                  <Zap className="h-5 w-5 text-primary" />
                </div>
              </div>
            </CardHeader>
            <CardContent>
               <LockedInsight 
                 isUnlocked={isAtLeastGold} 
                 title="Heatmap Data" 
                 description="Unlock deep-dive metrics on dish friction and pricing sensitivity."
               >
                 <MenuHeatmapTable heatmap={analyticsData?.menuHeatmap || []} />
                 
                 {analyticsData?.menuHeatmap?.some((h: any) => h.status !== 'Optimal') && (
                   <div className="mt-6 p-4 rounded-2xl bg-amber-50 dark:bg-amber-950/20 border border-amber-100 dark:border-amber-900/30 flex gap-3 items-start animate-pulse">
                     <AlertCircle className="h-5 w-5 text-amber-500 mt-0.5" />
                     <div className="space-y-1">
                        <p className="text-xs font-bold text-amber-800 dark:text-amber-400">Optimization Required</p>
                        <p className="text-[11px] text-amber-700/80 dark:text-amber-500/80 leading-relaxed">
                          We noticed high friction on some items. High views but 0 orders usually indicates the price point is slightly higher than guest expectations.
                        </p>
                     </div>
                   </div>
                 )}
               </LockedInsight>
            </CardContent>
         </Card>

         {/* QR ROAS: Revenue Attribution */}
         <Card className="lg:col-span-3 shadow-sm border-none bg-card">
            <CardHeader>
              <CardTitle className="text-lg font-bold flex items-center gap-2">
                QR Revenue Attribution
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 border border-indigo-200">ROAS</span>
              </CardTitle>
              <CardDescription>Revenue tracked back to specific scan sources</CardDescription>
            </CardHeader>
            <CardContent>
               <LockedInsight 
                 isUnlocked={isAtLeastGold} 
                 title="ROAS Intelligence" 
                 description="Track which physical QR stickers are generating the most money for your outlet."
               >
                 <QRRoasSection roas={analyticsData?.qrRoas || []} />
                 
                 <div className="mt-8 p-4 rounded-2xl bg-indigo-50/50 dark:bg-indigo-950/10 border border-indigo-100/50 dark:border-indigo-900/20">
                    <div className="flex items-center justify-between mb-2">
                       <p className="text-[10px] uppercase font-bold text-indigo-500 tracking-wider">Top Performing Source</p>
                       <Crown className="h-3 w-3 text-amber-500" />
                    </div>
                    <p className="text-sm font-bold">
                       {[...(analyticsData?.qrRoas || [])].sort((a: any, b: any) => b.revenue - a.revenue)[0]?.source || 'Scanning Data...'}
                    </p>
                    <p className="text-[10px] text-muted-foreground mt-1 italic">
                       This source contributes to {Math.round(([...(analyticsData?.qrRoas || [])].sort((a: any, b: any) => b.revenue - a.revenue)[0]?.revenue / (totalRevenue || 1)) * 100) || 0}% of your total digital revenue.
                    </p>
                 </div>
               </LockedInsight>
            </CardContent>
         </Card>
      </div>

      {/* Quick Actions and Activity Layer */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Real-time Feed (Recent Orders) */}
        <Card className="shadow-sm border-none bg-card">
          <CardHeader className="flex flex-row items-center justify-between">
            <div className="space-y-1">
              <CardTitle className="text-lg font-bold">Today's Transactions</CardTitle>
              <CardDescription>Latest order activities</CardDescription>
            </div>
            <Button variant="ghost" size="sm" className="text-xs rounded-full" asChild>
              <Link to="/orders">View Ledger</Link>
            </Button>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {todayOrders.length > 0 ? (
                todayOrders.slice(0, 5).map((order: any) => (
                  <div key={order.name} className="flex items-center justify-between p-3 rounded-2xl bg-muted/20 hover:bg-muted/40 transition-colors border border-transparent hover:border-border/40">
                    <div className="flex items-center gap-3">
                      <div className="h-9 w-9 rounded-full bg-background border border-border/60 flex items-center justify-center">
                        {getStatusIcon(order.status)}
                      </div>
                      <div>
                        <p className="text-sm font-bold">{order.name}</p>
                        <p className="text-[11px] text-muted-foreground">
                          Table {order.table_number || 'N/A'} • {new Date(order.creation).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                       <p className="text-sm font-bold text-foreground">{formatAmountNoDecimals(order.total)}</p>
                    </div>
                  </div>
                ))
              ) : (
                <EmptyState 
                  variant="chart"
                  title="No Orders Today"
                  description="Waiting for your first scan of the day..."
                  icon={ShoppingCart}
                  className="py-12"
                />
              )}
            </div>
          </CardContent>
        </Card>

        {/* Smart Recommendations Engine Overlay */}
        <div className="space-y-6">
           <Card className="shadow-sm border-none bg-card relative overflow-hidden group">
             <div className="absolute top-0 right-0 p-4 opacity-[0.03] group-hover:opacity-[0.08] transition-opacity">
                <Zap className="h-32 w-32" />
             </div>
             <CardHeader className="pb-2">
               <CardTitle className="text-lg font-bold flex items-center gap-2">
                 <div className="h-8 w-8 bg-amber-100 dark:bg-amber-950/40 rounded-lg flex items-center justify-center">
                    <Star className="h-4 w-4 text-amber-500 fill-amber-500" />
                 </div>
                 Smart Growth Engine
               </CardTitle>
             </CardHeader>
             <CardContent className="space-y-4">
                 <div className="p-4 rounded-2xl bg-primary/5 border border-primary/10 relative">
                   <p className="text-sm text-foreground/80 leading-relaxed font-sans italic">
                     "AI indicates that <strong>{analyticsData?.traffic?.topCategory?.[0]?.event_value || 'Beverages'}</strong> are being viewed more than they are being ordered. Suggest adding a <strong>'Featured Combo'</strong> to boost sales."
                   </p>
                 </div>
                 <div className="grid grid-cols-2 gap-4">
                    <Button variant="default" size="sm" className="bg-primary hover:bg-primary/90 text-white rounded-xl h-11 transition-all" asChild>
                      <Link to="/recommendations-engine" className="flex items-center gap-2">
                        <Activity className="h-4 w-4" />
                        AI Analysis
                      </Link>
                    </Button>
                    <Button variant="outline" size="sm" className="rounded-xl h-11 border-primary/20 hover:bg-primary/5 hover:text-primary transition-all" asChild>
                       <Link to="/accept-orders">
                         Queue Settings
                       </Link>
                    </Button>
                 </div>
             </CardContent>
           </Card>

           <div className="grid grid-cols-2 gap-4">
              <Card className="p-5 flex flex-col items-center justify-center gap-3 bg-muted/20 border-border/40 hover:bg-muted/40 transition-all cursor-pointer group" onClick={() => navigate('/products/new')}>
                 <div className="h-10 w-10 rounded-full bg-indigo-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                    <Package className="h-5 w-5 text-indigo-500" />
                 </div>
                 <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Add Dish</p>
              </Card>
              <Card className="p-5 flex flex-col items-center justify-center gap-3 bg-muted/20 border-border/40 hover:bg-muted/40 transition-all cursor-pointer group" onClick={() => navigate('/setup')}>
                 <div className="h-10 w-10 rounded-full bg-emerald-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                    <MapPin className="h-5 w-5 text-emerald-500" />
                 </div>
                 <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">My Store</p>
              </Card>
           </div>
        </div>
      </div>

      {/* Multi-Location Management View */}
      <Card className="shadow-sm border-none bg-card">
        <CardHeader className="flex flex-row items-center justify-between pb-6">
          <div className="space-y-1">
            <CardTitle className="text-lg font-bold">Outlets</CardTitle>
            <CardDescription>Switch between your managed locations</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {restaurants?.map((restaurant: any) => (
              <div 
                key={restaurant.name}
                className={cn(
                  "group flex items-center justify-between p-4 rounded-2xl border transition-all duration-300 cursor-pointer",
                  restaurant.name === selectedRestaurant 
                    ? "bg-primary/10 border-primary/30 shadow-md shadow-primary/5" 
                    : "bg-muted/30 border-border/40 hover:bg-muted/50"
                )}
              >
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "h-10 w-10 rounded-xl flex items-center justify-center transition-all",
                    restaurant.name === selectedRestaurant ? "bg-primary text-white" : "bg-background border border-border text-muted-foreground"
                  )}>
                    <MapPin className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-sm font-bold truncate max-w-[120px]">{restaurant.restaurant_name || restaurant.name}</p>
                    <p className="text-[11px] text-muted-foreground italic">
                      {restaurant.city || 'Standard Area'}
                    </p>
                  </div>
                </div>
                {restaurant.name === selectedRestaurant && (
                  <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Refer & Earn Information Modal */}
      <Dialog open={showReferralInfo} onOpenChange={setShowReferralInfo}>
        <DialogContent className="sm:max-w-[450px] p-0 overflow-hidden border-none shadow-2xl">
          <div className="bg-gradient-to-br from-indigo-600 to-purple-700 p-8 text-white relative">
            <div className="absolute top-0 right-0 p-4 opacity-10">
              <Gift className="h-32 w-32" />
            </div>
            <div className="relative z-10 flex flex-col items-center text-center">
              <div className="h-16 w-16 bg-white/20 backdrop-blur-md rounded-2xl flex items-center justify-center mb-4 shadow-xl border border-white/30">
                <Star className="h-8 w-8 text-white fill-white" />
              </div>
              <h2 className="text-2xl font-black tracking-tight mb-2">Refer & Earn ₹500</h2>
              <p className="text-indigo-100/80 text-sm leading-relaxed">
                Grow your network and get rewarded for every restaurant you bring to DineMatters.
              </p>
            </div>
          </div>
          
          <div className="p-6 space-y-6 bg-card">
            {/* Reward Summary */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-emerald-50 dark:bg-emerald-950/20 p-4 rounded-xl border border-emerald-100 dark:border-emerald-900/30 text-center">
                <p className="text-[10px] uppercase font-bold text-emerald-600 dark:text-emerald-400 mb-1">You Get</p>
                <p className="text-xl font-black text-emerald-700 dark:text-emerald-300">₹500</p>
                <p className="text-[9px] text-emerald-600/70 font-medium">Wallet Credit</p>
              </div>
              <div className="bg-indigo-50 dark:bg-indigo-950/20 p-4 rounded-xl border border-indigo-100 dark:border-indigo-900/30 text-center">
                <p className="text-[10px] uppercase font-bold text-indigo-600 dark:text-indigo-400 mb-1">They Get</p>
                <p className="text-xl font-black text-indigo-700 dark:text-indigo-300">₹500</p>
                <p className="text-[9px] text-indigo-600/70 font-medium">Joining Bonus</p>
              </div>
            </div>

            {/* Code Selection */}
            <div className="space-y-3">
              <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest pl-1">Your Referral Code</p>
              <div className="flex items-center gap-2">
                <div className="flex-1 bg-muted/50 border border-border h-14 rounded-xl flex items-center px-4 font-mono font-bold text-lg tracking-[0.2em] text-foreground">
                  {referralCode || 'DINE-XXXX-XXXX'}
                </div>
                <Button 
                  className={cn(
                    "h-14 w-14 rounded-xl transition-all shadow-md",
                    copied ? "bg-emerald-500 hover:bg-emerald-600" : "bg-primary hover:bg-primary/90"
                  )}
                  onClick={async () => {
                    const success = await copyToClipboard(referralCode || '')
                    if (success) {
                      setCopied(true)
                      setTimeout(() => setCopied(false), 2000)
                    }
                  }}
                >
                  {copied ? <CheckCircle className="h-5 w-5" /> : <Copy className="h-5 w-5" />}
                </Button>
              </div>
            </div>

            {/* Info Points */}
            <div className="space-y-3 pt-2">
               <div className="flex items-start gap-3">
                  <div className="h-5 w-5 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <span className="text-[10px] font-bold text-primary">1</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-snug">Share your code with any merchant or restaurant owner.</p>
               </div>
               <div className="flex items-start gap-3">
                  <div className="h-5 w-5 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <span className="text-[10px] font-bold text-primary">2</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-snug">They enter your code during their registration or onboarding.</p>
               </div>
               <div className="flex items-start gap-3">
                  <div className="h-5 w-5 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <span className="text-[10px] font-bold text-primary">3</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-snug">Both of you receive <span className="font-bold text-foreground">₹500 Credit</span> once they complete their first top-up of ₹1,000 or more.</p>
               </div>
            </div>
          </div>

          <DialogFooter className="p-6 pt-0 flex flex-col sm:flex-row gap-3">
            <Button 
              className="bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl h-12 flex-1 shadow-lg shadow-emerald-500/20 font-bold"
              onClick={() => {
                const text = `Hey! I'm using DineMatters for my restaurant and it's amazing. Use my referral code *${referralCode}* to get ₹500 bonus on your first recharge. Register at: https://dinematters.com`
                window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, '_blank')
              }}
            >
              <div className="flex items-center gap-2">
                <svg className="h-5 w-5 fill-current" viewBox="0 0 24 24">
                  <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/>
                </svg>
                Share on WhatsApp
              </div>
            </Button>
            <Button variant="ghost" onClick={() => setShowReferralInfo(false)} className="rounded-xl h-12 text-muted-foreground flex-1">
              Maybe Later
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}







