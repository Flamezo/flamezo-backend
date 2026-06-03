import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Truck, Navigation, IndianRupee, Clock, Activity, User } from 'lucide-react'
import { useCurrency } from '@/hooks/useCurrency'
import { Progress } from '@/components/ui/progress'
import { EmptyState } from '@/components/EmptyState'

interface Order {
  name: string
  status: string
  order_type: string
  delivery_partner?: string
  delivery_status?: string
  total: number
  delivery_fee?: number
}

interface DeliveryTrackerCardProps {
  orders: Order[]
  isLoading?: boolean
}

export function DeliveryTrackerCard({ orders, isLoading }: DeliveryTrackerCardProps) {
  const { formatAmountNoDecimals } = useCurrency()

  const activeDeliveries = orders.filter(o => 
    o.order_type === 'delivery' && 
    !['delivered', 'cancelled'].includes(o.delivery_status?.toLowerCase() || o.status?.toLowerCase() || '')
  )

  const todayDeliveryRevenue = orders
    .filter(o => o.order_type === 'delivery' && o.status?.toLowerCase() !== 'cancelled')
    .reduce((sum, o) => sum + (o.delivery_fee || 0), 0)

  const latestActive = activeDeliveries[0]

  if (isLoading) {
    return (
      <Card className="animate-pulse bg-muted/20 border-none h-[180px]" />
    )
  }

  return (
    <Card className="relative overflow-hidden border-none bg-gradient-to-br from-zinc-900 to-black text-white shadow-2xl group">
      <div className="absolute top-0 right-0 p-6 opacity-10 group-hover:opacity-20 transition-opacity">
        <Truck className="h-24 w-24" />
      </div>
      
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-black uppercase tracking-widest text-zinc-400 flex items-center gap-2">
          <Activity className="h-3 w-3 text-blue-500" />
          Delivery Tracker
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <p className="text-3xl font-black tracking-tighter">
              {activeDeliveries.length}
            </p>
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-tight">Active Deliveries</p>
          </div>
          
          <div className="space-y-1 text-right">
            <p className="text-xl font-black tracking-tight text-blue-400 flex items-center justify-end gap-1">
              <IndianRupee className="h-4 w-4" />
              {formatAmountNoDecimals(todayDeliveryRevenue)}
            </p>
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-tight">Today's Delivery Revenue</p>
          </div>
        </div>

        {latestActive ? (
          <div className="bg-white/5 border border-white/10 rounded-xl p-3 backdrop-blur-md">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Navigation className="h-3 w-3 text-blue-500 animate-pulse" />
                <span className="text-[10px] font-black uppercase tracking-wider">{latestActive.name}</span>
              </div>
              <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30">
                {latestActive.delivery_status || 'Assigned'}
              </span>
            </div>
            <Progress value={50} className="h-1 bg-white/10" />
          </div>
        ) : (
          <EmptyState 
            variant="compact"
            title="No Active Delivery Movements"
            description="Real-time delivery progress will appear here."
            icon={Clock}
            className="border-none bg-white/5 py-3"
          />
        )}
      </CardContent>
    </Card>
  )
}
