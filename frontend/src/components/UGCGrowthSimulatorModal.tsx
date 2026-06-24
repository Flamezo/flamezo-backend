import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Users, UserPlus, Wallet, TrendingUp, Sparkles, ArrowRight, ArrowDown, Activity, Gift } from 'lucide-react'

interface UGCGrowthSimulatorModalProps {
  isOpen: boolean
  onClose: () => void
}

export default function UGCGrowthSimulatorModal({ isOpen, onClose }: UGCGrowthSimulatorModalProps) {
  const [aov, setAov] = useState<number>(500)
  const [customers, setCustomers] = useState<number>(1)
  const avgViews = 400 // Fixed assumption based on average 400 followers
  const [step, setStep] = useState<number>(0)

  // Auto-progress the animation steps
  useEffect(() => {
    if (!isOpen) {
      setStep(0)
      return
    }
    
    // Sequence timing
    const timers = [
      setTimeout(() => setStep(1), 300),   // Initial customer
      setTimeout(() => setStep(2), 800),   // Story posted
      setTimeout(() => setStep(3), 1400),  // 2 new friends + Return visit 1
      setTimeout(() => setStep(4), 2000),  // Return visit 2
      setTimeout(() => setStep(5), 2600),  // Return visit 3 (Conclusion)
    ]

    return () => timers.forEach(clearTimeout)
  }, [isOpen])

  // Math variables
  const voucherValuePerCustomer = Math.min(aov, 2000) // Cap at 2000 per claim
  const maxDiscountPerVisit = Math.floor(aov * 0.33)
  const numberOfReturns = Math.ceil(voucherValuePerCustomer / maxDiscountPerVisit)
  
  // Calculate total reward given
  let rewardPerCustomer = 0
  let remainingVoucher = voucherValuePerCustomer
  for (let i = 0; i < numberOfReturns; i++) {
    const reward = Math.min(remainingVoucher, Math.floor(aov * 0.33))
    rewardPerCustomer += reward
    remainingVoucher -= reward
  }

  // Calculate totals for Free Dish model
  const totalRewardValue = rewardPerCustomer * customers
  // Real cost is only 33% (Food Cost) of the dish value
  const totalRealCost = Math.floor(totalRewardValue * 0.33) 
  
  const initialRevenue = aov * customers
  const newCustomerRevenue = aov * 2 * customers // 2 new customers
  const repeatVisitsRevenue = (aov * numberOfReturns) * customers
  const totalRevenueGenerated = initialRevenue + newCustomerRevenue + repeatVisitsRevenue
  
  // 1 initial visit + 2 new friends + X repeat visits = total visits
  const totalVisits = (1 + 2 + numberOfReturns) * customers
  const roiMultiplier = (totalRevenueGenerated / initialRevenue).toFixed(1)

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-4xl max-h-[90vh] overflow-y-auto p-0 border-0 bg-gradient-to-b from-orange-50 to-white dark:from-orange-950/20 dark:to-gray-950">
        
        {/* Header Section */}
        <div className="p-6 pb-0 md:p-8 md:pb-0">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-2xl font-bold text-orange-600 dark:text-orange-500">
              <Sparkles className="w-6 h-6" /> 
              How UGC Fuels Your Growth
            </DialogTitle>
            <DialogDescription className="text-base mt-2">
              See the exact math of how UGC stories turn into a predictable growth engine. Adjust the sliders to match your metrics.
            </DialogDescription>
          </DialogHeader>

          {/* Interactive Sliders */}
          <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
            
            {/* AOV Slider */}
            <div className="p-4 bg-white dark:bg-gray-900 rounded-2xl border shadow-sm flex flex-col gap-2">
              <div className="flex items-center gap-3 mb-1">
                <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 bg-orange-100 dark:bg-orange-900/40 text-orange-600 dark:text-orange-400 rounded-full">
                  <Wallet className="w-4 h-4" />
                </div>
                <label className="text-sm font-semibold text-gray-700 dark:text-gray-300">Avg Order Value</label>
              </div>
              <div className="flex justify-between items-center mb-1">
                <span className="text-lg font-bold font-mono text-primary">₹{aov}</span>
              </div>
              <input 
                type="range" 
                min="200" 
                max="2500" 
                step="50" 
                value={aov} 
                onChange={(e) => setAov(Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-orange-500"
              />
              <div className="flex justify-between text-[10px] text-gray-400 font-medium">
                <span>₹200</span>
                <span>₹2,500</span>
              </div>
            </div>

            {/* Customers Slider */}
            <div className="p-4 bg-white dark:bg-gray-900 rounded-2xl border shadow-sm flex flex-col gap-2">
              <div className="flex items-center gap-3 mb-1">
                <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 bg-purple-100 dark:bg-purple-900/40 text-purple-600 dark:text-purple-400 rounded-full">
                  <Users className="w-4 h-4" />
                </div>
                <label className="text-sm font-semibold text-gray-700 dark:text-gray-300">Daily UGC Customers</label>
              </div>
              <div className="flex justify-between items-center mb-1">
                <span className="text-lg font-bold font-mono text-purple-600">{customers}</span>
              </div>
              <input 
                type="range" 
                min="1" 
                max="100" 
                step="1" 
                value={customers} 
                onChange={(e) => setCustomers(Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-purple-500"
              />
              <div className="flex justify-between text-[10px] text-gray-400 font-medium">
                <span>1</span>
                <span>100</span>
              </div>
            </div>

          </div>
        </div>

        {/* Tree Diagram Container */}
        <div className="relative p-6 md:p-10 min-h-[500px] flex flex-col items-center font-sans overflow-hidden">
          
          <AnimatePresence>
            {step >= 1 && (
              <motion.div 
                initial={{ opacity: 0, scale: 0.8, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                className="relative z-10 w-full max-w-sm mb-12"
              >
                <div className="bg-white dark:bg-gray-800 rounded-2xl p-5 shadow-lg border border-orange-100 dark:border-orange-900/30 flex items-center gap-4">
                  <div className="bg-orange-100 dark:bg-orange-900/50 p-3 rounded-full text-orange-600">
                    <Users className="w-6 h-6" />
                  </div>
                  <div>
                    <p className="text-sm font-bold uppercase tracking-wider text-gray-500">Node 1</p>
                    <p className="font-bold text-lg leading-tight">{customers} Current Customer{customers > 1 ? 's' : ''}</p>
                    <p className="text-sm text-green-600 font-semibold mt-1">+ ₹{initialRevenue} Revenue</p>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {step >= 2 && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                className="w-full relative z-0 -mt-8 flex flex-col items-center"
              >
                <div className="h-12 w-0.5 bg-gradient-to-b from-orange-400 to-pink-500" />
                <div className="bg-gradient-to-r from-orange-500 to-pink-500 text-white text-xs font-bold px-4 py-1.5 rounded-full shadow-md transform -translate-y-2 z-10 animate-pulse text-center">
                  {customers > 1 ? `Customers post UGC Stories` : `Customer posts UGC Story`}
                </div>
                
                {/* Visual Customer Nodes Grid */}
                {customers > 1 && (
                  <div className="w-full max-w-lg mt-1 mb-3 flex flex-wrap justify-center gap-1.5 z-10 relative px-4">
                    {Array.from({ length: Math.min(customers, 100) }).map((_, i) => (
                      <motion.div
                        key={i}
                        initial={{ scale: 0, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{ delay: i * 0.005 }}
                        className="w-6 h-6 rounded-full bg-pink-50 dark:bg-pink-900/40 flex items-center justify-center text-pink-500 border border-pink-200 shadow-sm"
                      >
                        <Users className="w-3 h-3" />
                      </motion.div>
                    ))}
                  </div>
                )}
                <div className="h-8 w-0.5 bg-gradient-to-b from-pink-500 to-purple-500" />
                
                {/* Branching line horizontal */}
                <div className="w-[80%] max-w-2xl h-0.5 bg-purple-500/30 relative">
                  <div className="absolute left-0 top-0 w-0.5 h-8 bg-purple-500/30" />
                  <div className="absolute right-0 top-0 w-0.5 h-8 bg-purple-500/30" />
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="w-full max-w-4xl grid grid-cols-1 md:grid-cols-2 gap-8 md:gap-16 pt-8">
            
            {/* Left Branch: New Customers */}
            <div className="flex flex-col items-center gap-4">
              <AnimatePresence>
                {step >= 3 && (
                  <motion.div
                    initial={{ opacity: 0, x: -50, scale: 0.9 }}
                    animate={{ opacity: 1, x: 0, scale: 1 }}
                    className="w-full"
                  >
                    <div className="bg-gradient-to-br from-purple-50 to-white dark:from-purple-900/20 dark:to-gray-800 rounded-2xl p-5 shadow-lg border border-purple-100 dark:border-purple-800/30 relative overflow-hidden">
                      <div className="absolute top-0 right-0 p-3 opacity-10">
                        <UserPlus className="w-20 h-20" />
                      </div>
                      <div className="bg-purple-100 dark:bg-purple-900/50 p-2 rounded-lg w-fit text-purple-600 mb-3">
                        <Sparkles className="w-5 h-5" />
                      </div>
                      <p className="text-sm font-bold uppercase tracking-wider text-purple-600">Free Marketing</p>
                      <p className="font-bold text-xl mt-1">{customers * 2} New Friends</p>
                      <p className="text-sm text-gray-600 dark:text-gray-300 mt-2">
                        They see the stor{customers > 1 ? 'ies' : 'y'} and visit you.
                      </p>
                      <div className="bg-purple-50 dark:bg-purple-900/30 p-2 mt-3 rounded-lg flex items-center gap-2">
                        <Activity className="w-4 h-4 text-purple-500" />
                        <span className="text-xs font-bold text-purple-700 dark:text-purple-300">
                          {(customers * avgViews).toLocaleString()} Views Generated
                        </span>
                      </div>
                      <div className="mt-4 pt-4 border-t border-purple-100 dark:border-purple-800/30">
                        <p className="text-lg font-bold text-green-600">
                          + ₹{newCustomerRevenue} Revenue
                        </p>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Right Branch: Repeat Visits */}
            <div className="flex flex-col items-center gap-4">
              <AnimatePresence>
                {step >= 3 && (
                  <motion.div
                    initial={{ opacity: 0, x: 50, scale: 0.9 }}
                    animate={{ opacity: 1, x: 0, scale: 1 }}
                    className="w-full"
                  >
                    <div className="bg-gradient-to-br from-blue-50 to-white dark:from-blue-900/20 dark:to-gray-800 rounded-2xl p-5 shadow-lg border border-blue-100 dark:border-blue-800/30">
                      <div className="flex justify-between items-start mb-3">
                        <div className="bg-blue-100 dark:bg-blue-900/50 p-2 rounded-lg w-fit text-blue-600">
                          <Gift className="w-5 h-5" />
                        </div>
                        <div className="text-right">
                          <p className="text-xs font-bold text-gray-500 uppercase">Vouchers Earned</p>
                          <p className="font-bold text-blue-600">₹{voucherValuePerCustomer * customers}</p>
                        </div>
                      </div>
                      
                      <p className="text-sm font-bold uppercase tracking-wider text-blue-600">Guaranteed Loyalty</p>
                      <p className="font-bold text-xl mt-1">Forced Repeat Visits</p>
                      <p className="text-sm text-gray-600 dark:text-gray-300 mt-2">
                        They get a Free Dish (up to 33% of bill). They pay full price, and you only pay 33% Food Cost!
                      </p>

                      <div className="mt-4 space-y-2">
                        {/* Visit 1 */}
                        <div className="flex justify-between text-sm py-2 border-b border-gray-100 dark:border-gray-700">
                          <span className="font-medium">Return Visit 1 (x{customers})</span>
                          <span className="text-green-600 font-semibold">+ ₹{aov * customers}</span>
                        </div>
                        
                        {/* Visit 2 */}
                        {step >= 4 && (
                          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex justify-between text-sm py-2 border-b border-gray-100 dark:border-gray-700">
                            <span className="font-medium">Return Visit 2 (x{customers})</span>
                            <span className="text-green-600 font-semibold">+ ₹{aov * customers}</span>
                          </motion.div>
                        )}

                        {/* Visit 3 / Final */}
                        {step >= 5 && numberOfReturns >= 3 && (
                          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex justify-between text-sm py-2">
                            <span className="font-medium">Return Visit 3 (x{customers})</span>
                            <span className="text-green-600 font-semibold">+ ₹{aov * customers}</span>
                          </motion.div>
                        )}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>

        {/* Conclusion Banner */}
        <AnimatePresence>
          {step >= 5 && (
            <motion.div
              initial={{ opacity: 0, y: 50 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-gray-900 text-white p-6 md:p-8"
            >
              <div className="max-w-4xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
                <div>
                  <p className="text-gray-400 font-medium uppercase tracking-widest text-xs mb-2">Net Result of {customers} UGC Stor{customers > 1 ? 'ies' : 'y'}</p>
                  <h3 className="text-3xl md:text-4xl font-black text-white flex items-center gap-3">
                    {roiMultiplier}x ROI <TrendingUp className="w-8 h-8 text-green-400" />
                  </h3>
                  <p className="text-blue-400 text-sm font-semibold mt-2 flex items-center gap-1">
                    <Activity className="w-4 h-4" /> {(customers * avgViews).toLocaleString()} Total Impressions
                  </p>
                </div>
                
                <div className="flex gap-6 md:gap-8 overflow-x-auto">
                  <div className="shrink-0">
                    <p className="text-gray-400 text-xs uppercase mb-1">Face Value</p>
                    <p className="text-2xl font-bold text-gray-300">₹{totalRewardValue}</p>
                  </div>
                  <div className="shrink-0">
                    <p className="text-gray-400 text-xs uppercase mb-1">Actual Food Cost (33%)</p>
                    <p className="text-2xl font-bold text-red-400">- ₹{totalRealCost}</p>
                  </div>
                  <div className="shrink-0">
                    <p className="text-gray-400 text-xs uppercase mb-1">Total Revenue</p>
                    <p className="text-2xl font-bold text-green-400">+ ₹{totalRevenueGenerated}</p>
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

      </DialogContent>
    </Dialog>
  )
}
