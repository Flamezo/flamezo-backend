import { useState, useEffect, SetStateAction } from 'react'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import { Users, Search, PlusCircle, MinusCircle, User, History, Loader2, ArrowUpRight, ArrowDownLeft, Coins } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from '@/components/ui/label'

export default function CustomerInsights() {
  const { selectedRestaurant } = useRestaurant()
  const [loading, setLoading] = useState(false)
  const [customers, setCustomers] = useState<any[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCustomer, setSelectedCustomer] = useState<any>(null)
  const [adjustModalOpen, setAdjustModalOpen] = useState(false)
  const [adjustAmount, setAdjustAmount] = useState('')
  const [adjustReason, setAdjustReason] = useState('')
  const [adjustType, setAdjustType] = useState<'Earn' | 'Redeem'>('Earn')
  const [adjusting, setAdjusting] = useState(false)
  const [historyModalOpen, setHistoryModalOpen] = useState(false)
  const [transactions, setTransactions] = useState<any[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)

  const { call: getInsights } = useFrappePostCall('dinematters.dinematters.api.loyalty.get_customer_insights')
  const { call: adjustPoints } = useFrappePostCall('dinematters.dinematters.api.loyalty.adjust_customer_points')
  const { call: getTransactions } = useFrappePostCall('dinematters.dinematters.api.loyalty.get_customer_transactions')
  const { restaurantConfig, isSilver, planType } = useRestaurant()

  const { call: unlockCustomerApi } = useFrappePostCall('dinematters.dinematters.api.customers.unlock_customer_data')

  const handleUnlockCustomer = async (customerId: string) => {
    try {
      const res = await unlockCustomerApi({
        restaurant_id: selectedRestaurant,
        customer_id: customerId
      })
      const body = (res as any)?.message || res
      if (body.success) {
        toast.success(body.message || 'Profile unlocked!')
        fetchInsights()
      } else {
        toast.error(body.error || 'Failed to unlock profile')
      }
    } catch (err) {
      toast.error('Internal error occurred')
    }
  }

  const fetchInsights = async () => {
    if (!selectedRestaurant) return
    setLoading(true)
    try {
      const res: any = await getInsights({
        restaurant_id: selectedRestaurant,
        search_query: searchQuery
      })
      if (res.message?.success) {
        setCustomers(res.message.data || [])
      }
    } catch (error) {
      console.error('Failed to fetch insights:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchInsights()
  }, [selectedRestaurant, searchQuery])

  const handleAdjustPoints = async () => {
    if (!selectedRestaurant || !selectedCustomer || !adjustAmount) return

    setAdjusting(true)
    try {
      const res: any = await adjustPoints({
        restaurant_id: selectedRestaurant,
        customer_id: selectedCustomer.id,
        coins: Math.abs(parseInt(adjustAmount)),
        reason: adjustReason || 'Manual Adjustment',
        transaction_type: adjustType
      })

      if (res.message?.success) {
        toast.success(res.message.message)
        setAdjustModalOpen(false)
        setAdjustAmount('')
        setAdjustReason('')
        fetchInsights()
      } else {
        toast.error(res.message?.error || 'Failed to adjust points')
      }
    } catch (error) {
      toast.error('Failed to adjust points')
    } finally {
      setAdjusting(false)
    }
  }

  const fetchHistory = async (customer: any) => {
    if (!selectedRestaurant || !customer) return
    setSelectedCustomer(customer)
    setHistoryModalOpen(true)
    setLoadingHistory(true)
    try {
      const res: any = await getTransactions({
        restaurant_id: selectedRestaurant,
        customer_id: customer.id
      })
      if (res.message?.success) {
        setTransactions(res.message.data || [])
      }
    } catch (error) {
      console.error('Failed to fetch transactions:', error)
      toast.error('Failed to load transaction history')
    } finally {
      setLoadingHistory(false)
    }
  }


  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-12">
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <Users className="w-8 h-8 text-primary" />
            <h1 className="text-3xl font-bold tracking-tight text-foreground">Customer Insights</h1>
          </div>
          <p className="text-muted-foreground mt-2">
            View customer cash, history, and manually reward your loyal customers.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <User className="w-5 h-5 text-muted-foreground" />
              Customer Loyalty List
            </CardTitle>
            <div className="relative w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search name or phone..."
                className="pl-9"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Customer</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead>Birthday</TableHead>
                  <TableHead>Cash Balance</TableHead>
                  <TableHead>Referral Opens</TableHead>
                  <TableHead className="w-[120px]">Cycle Rewards</TableHead>
                  <TableHead>Last Active</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">Loading customers...</TableCell>
                  </TableRow>
                ) : customers.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">No customers found with loyalty history.</TableCell>
                  </TableRow>
                ) : (
                  customers.map((customer) => (
                    <TableRow key={customer.id}>
                      <TableCell className="font-medium text-sm">
                        <div className={!customer.is_unlocked && isSilver ? "select-none opacity-40 brightness-50" : ""}>
                          {customer.name}
                        </div>
                      </TableCell>
                      <TableCell className="text-sm">
                        <div className={!customer.is_unlocked && isSilver ? "select-none opacity-40 brightness-50" : ""}>
                          {customer.phone || 'N/A'}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        <div className={!customer.is_unlocked && isSilver ? "select-none opacity-40 brightness-50" : ""}>
                          {customer.birthday && customer.birthday !== '********' ? new Date(customer.birthday).toLocaleDateString() : '—'}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={customer.balance > 0 ? "default" : "secondary"} className="gap-1">
                          {customer.balance} Cash
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col gap-0.5">
                          <span className="text-sm font-semibold">{customer.referral_opens}</span>
                          <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Total Unique</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden min-w-[60px]">
                            <div
                              className="h-full bg-blue-500 rounded-full transition-all duration-500"
                              style={{ width: `${(customer.cycle_opens / 7) * 100}%` }}
                            />
                          </div>
                          <span className="text-[10px] font-medium text-gray-500">{customer.cycle_opens}/7</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground text-xs">
                        {new Date(customer.last_active).toLocaleDateString()}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          {!customer.is_unlocked && isSilver && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleUnlockCustomer(customer.id)}
                              className="h-8 rounded-lg bg-primary/5 hover:bg-primary/10 border-primary/20 text-primary font-bold transition-all hover:scale-[1.02] active:scale-[0.98] group"
                            >
                              <Coins className="h-3.5 w-3.5 mr-1.5 group-hover:rotate-12 transition-transform" />
                              5 Credits
                            </Button>
                          )}
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-8 gap-1"
                            onClick={() => fetchHistory(customer)}
                            disabled={!customer.is_unlocked && isSilver}
                          >
                            <History className="w-3.5 h-3.5" />
                            History
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-8 gap-1"
                            onClick={() => {
                              setSelectedCustomer(customer)
                              setAdjustType('Earn')
                              setAdjustModalOpen(true)
                            }}
                            disabled={!customer.is_unlocked && isSilver}
                          >
                            <PlusCircle className="w-3.5 h-3.5" />
                            Give Cash
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-8 gap-1 text-destructive hover:text-destructive"
                            onClick={() => {
                              setSelectedCustomer(customer)
                              setAdjustType('Redeem')
                              setAdjustModalOpen(true)
                            }}
                            disabled={!customer.is_unlocked && isSilver}
                          >
                            <MinusCircle className="w-3.5 h-3.5" />
                            Deduct
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Adjustment Modal */}
      <Dialog open={adjustModalOpen} onOpenChange={setAdjustModalOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>{adjustType === 'Earn' ? 'Give Cash' : 'Deduct Cash'}</DialogTitle>
            <DialogDescription>
              {adjustType === 'Earn'
                ? `Reward cash to ${selectedCustomer?.name}.`
                : `Manually deduct cash from ${selectedCustomer?.name}.`
              }
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="amount">Amount of Cash</Label>
              <NumberInput
                id="amount"

                placeholder="e.g. 50"
                value={adjustAmount}
                onChange={(e: { target: { value: SetStateAction<string> } }) => setAdjustAmount(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="reason">Reason (Optional)</Label>
              <Input
                id="reason"
                placeholder="e.g. Compensation for delay"
                value={adjustReason}
                onChange={(e) => setAdjustReason(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAdjustModalOpen(false)}>Cancel</Button>
            <Button
              onClick={handleAdjustPoints}
              disabled={adjusting || !adjustAmount}
              variant={adjustType === 'Redeem' ? 'destructive' : 'default'}
            >
              {adjusting ? 'Processing...' : (adjustType === 'Earn' ? 'Add Cash' : 'Deduct Cash')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* History Modal */}
      <Dialog open={historyModalOpen} onOpenChange={setHistoryModalOpen}>
        <DialogContent className="sm:max-w-[600px] max-h-[80vh] flex flex-col p-0 overflow-hidden">
          <DialogHeader className="p-6 pb-2">
            <DialogTitle className="flex items-center gap-2">
              <History className="w-5 h-5 text-primary" />
              Transaction History
            </DialogTitle>
            <DialogDescription>
              Detailed loyalty cash logs for {selectedCustomer?.name}
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto px-6 pb-6">
            <div className="border rounded-lg overflow-hidden">
              <Table>
                <TableHeader className="bg-muted/50">
                  <TableRow>
                    <TableHead className="text-[11px] uppercase tracking-wider font-bold">Date</TableHead>
                    <TableHead className="text-[11px] uppercase tracking-wider font-bold">Type</TableHead>
                    <TableHead className="text-[11px] uppercase tracking-wider font-bold">Cash</TableHead>
                    <TableHead className="text-[11px] uppercase tracking-wider font-bold">Reason</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loadingHistory ? (
                    <TableRow>
                      <TableCell colSpan={4} className="py-12 text-center">
                        <div className="flex flex-col items-center gap-2">
                          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                          <span className="text-sm text-muted-foreground">Loading history...</span>
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : transactions.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="py-12 text-center text-muted-foreground italic">
                        No transactions found for this customer.
                      </TableCell>
                    </TableRow>
                  ) : (
                    transactions.map((tx: any, idx: number) => (
                      <TableRow key={idx}>
                        <TableCell className="text-xs whitespace-nowrap">
                          {new Date(tx.creation).toLocaleDateString()}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={tx.transaction_type === 'Earn' ? 'default' : 'destructive'}
                            className="text-[10px] h-5 px-1.5 uppercase font-bold"
                          >
                            {tx.transaction_type === 'Earn' ? (
                              <ArrowUpRight className="w-2.5 h-2.5 mr-0.5" />
                            ) : (
                              <ArrowDownLeft className="w-2.5 h-2.5 mr-0.5" />
                            )}
                            {tx.transaction_type}
                          </Badge>
                        </TableCell>
                        <TableCell className={`text-sm font-bold ${tx.transaction_type === 'Earn' ? 'text-green-500' : 'text-red-500'}`}>
                          {tx.transaction_type === 'Earn' ? '+' : '-'}{tx.coins}
                        </TableCell>
                        <TableCell className="text-xs max-w-[200px] truncate" title={tx.reason}>
                          {tx.reason}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </div>

          <DialogFooter className="p-6 pt-2 bg-muted/20 border-t">
            <Button variant="outline" onClick={() => setHistoryModalOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
