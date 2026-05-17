import React, { useState, useEffect } from 'react'
import { AlertCircle, ArrowRight, Wallet, Calendar, ShieldAlert, Loader2, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useNavigate } from 'react-router-dom'
import { format } from 'date-fns'

interface BillingNotificationBarProps {
  billingInfo: {
    coins_balance: number
    deferred_plan_type?: 'SILVER' | 'GOLD' | null
    plan_change_date?: string | null
    mandate_active: boolean
    auto_recharge_enabled: boolean
    auto_recharge_threshold: number
    auto_recharge_amount: number
    daily_limit: number
    current_daily_vol: number
    billing_status: 'active' | 'overdue' | 'suspended'
    onboarding_date?: string | null
    last_auto_recharge_date?: string | null
  } | null
  planType: 'SILVER' | 'GOLD'
  isActive?: boolean
}

export const BillingNotificationBar: React.FC<BillingNotificationBarProps> = ({ billingInfo, planType, isActive = true }) => {
  const isGold = planType === 'GOLD'
  const isPremium = isGold
  const navigate = useNavigate()
  const [isDismissed, setIsDismissed] = useState(false)

  // Check for dismissal on mount
  useEffect(() => {
    const dismissedUntil = localStorage.getItem('billing_bar_dismissed_until')
    if (dismissedUntil) {
      const expiration = parseInt(dismissedUntil, 10)
      if (Date.now() < expiration) {
        setIsDismissed(true)
      } else {
        localStorage.removeItem('billing_bar_dismissed_until')
      }
    }
  }, [])

  const handleDismiss = (e: React.MouseEvent) => {
    e.stopPropagation()
    // Dismiss for 24 hours
    const expiresAt = Date.now() + 24 * 60 * 60 * 1000
    localStorage.setItem('billing_bar_dismissed_until', expiresAt.toString())
    setIsDismissed(true)
  }

  if (!billingInfo || isDismissed) return null

  // When restaurant is inactive, show deactivation notice as highest priority
  if (!isActive) {
    return (
      <div className={cn(
        "w-full py-2 px-4 flex items-center justify-center gap-4 text-xs font-semibold animate-in slide-in-from-top-4 duration-500 shadow-inner",
        "bg-gradient-to-r from-red-600 via-red-500 to-orange-500 text-white border-red-400"
      )}>
        <div className="flex items-center gap-2 max-w-7xl w-full">
          <div className="flex items-center gap-2 flex-grow overflow-hidden">
            <div className="p-1 rounded-md bg-white/20 shrink-0">
              <ShieldAlert className="h-4 w-4" />
            </div>
            <span className="truncate">Account suspended due to security reason. Please contact support to reactivate.</span>
          </div>
          <button
            onClick={() => navigate('/account')}
            className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white text-black hover:bg-white/90 transition-all shrink-0 active:scale-95"
          >
            My Account
            <ArrowRight className="h-3 w-3" />
          </button>
        </div>
      </div>
    )
  }

  const notifications = []

  // 1. Account Status (Suspended/Overdue)
  if (billingInfo.billing_status === 'suspended') {
    notifications.push({
      id: 'suspended',
      type: 'critical',
      icon: <ShieldAlert className="h-4 w-4" />,
      message: "Account suspended due to security reason. Please contact support to reactivate.",
      action: { label: 'Contact Support', onClick: () => window.location.href = 'mailto:support@flamezo_backend.ono.menu' }
    })
  } else if (billingInfo.billing_status === 'overdue') {
    notifications.push({
      id: 'overdue',
      type: 'critical',
      icon: <AlertCircle className="h-4 w-4" />,
      message: "Payment overdue! Your account is at risk of suspension shortly.",
      action: { label: 'Pay Now', onClick: () => navigate('/autopay-setup?buy=true') }
    })
  }

  // 2. Scheduled Plan Change
  if (billingInfo.deferred_plan_type) {
    const formattedDate = billingInfo.plan_change_date ? format(new Date(billingInfo.plan_change_date), 'do MMMM') : 'tomorrow'
    notifications.push({
      id: 'plan-change',
      type: 'info',
      icon: <Calendar className="h-4 w-4" />,
      message: `Your plan is scheduled to change to ${billingInfo.deferred_plan_type} on ${formattedDate} at 12:00 AM.`,
      action: { label: 'Manage', onClick: () => navigate('/autopay-setup') }
    })
  }

  // 3. Account Risk (Negative Balance)
  if (billingInfo.coins_balance < 0) {
    notifications.push({
      id: 'account-risk',
      type: 'critical',
      icon: <ShieldAlert className="h-4 w-4" />,
      message: `Your account is at risk of being disabled due to negative balance. Recharge immediately.`,
      action: { label: 'Pay Now', onClick: () => navigate('/autopay-setup?buy=true') }
    })
  }

  // 4. Autopay Daily Limit Warning / Reached
  if (billingInfo.auto_recharge_enabled) {
    if (billingInfo.current_daily_vol >= billingInfo.daily_limit) {
       notifications.push({
        id: 'daily-limit-reached',
        type: 'critical',
        icon: <ShieldAlert className="h-4 w-4" />,
        message: `Daily safety limit of ₹${billingInfo.daily_limit.toLocaleString()} reached. Automatic recharges are paused.`,
        action: { label: 'Increase Limit', onClick: () => navigate('/autopay-setup') }
      })
    } else if (billingInfo.current_daily_vol >= billingInfo.daily_limit * 0.8) {
       notifications.push({
        id: 'daily-limit-near',
        type: 'warning',
        icon: <AlertCircle className="h-4 w-4" />,
        message: `Approaching daily autopay safety limit (Used: ₹${billingInfo.current_daily_vol.toLocaleString()}).`,
        action: { label: 'Settings', onClick: () => navigate('/autopay-setup') }
      })
    }
  }

  // 5. Low Balance Alert (Intelligent)
  if (billingInfo.coins_balance >= 0 && billingInfo.coins_balance < 300) {
    const isAutopayComing = billingInfo.auto_recharge_enabled && billingInfo.mandate_active && (billingInfo.current_daily_vol < billingInfo.daily_limit)
    
    let message = isPremium 
      ? `Wallet balance is dangerously low (₹${billingInfo.coins_balance.toLocaleString()}). ${planType} features may be disabled soon.` 
      : `Wallet balance is dangerously low (₹${billingInfo.coins_balance.toLocaleString()}). AI and Order flow may be interrupted.`
    
    if (isAutopayComing) {
      message = `Low balance (₹${billingInfo.coins_balance.toLocaleString()}). Automatic top-up of ₹${billingInfo.auto_recharge_amount.toLocaleString()} will be triggered shortly.`
    }

    notifications.push({
      id: 'low-balance',
      type: isAutopayComing ? 'info' : 'critical',
      icon: isAutopayComing ? <Loader2 className="h-4 w-4 animate-spin text-white" /> : <ShieldAlert className="h-4 w-4" />,
      message: message,
      action: { label: isAutopayComing ? 'Settings' : 'Top up Now', onClick: () => navigate(isAutopayComing ? '/autopay-setup' : '/autopay-setup?buy=true') }
    })
  } else if (isPremium && billingInfo.coins_balance < 1000) {
    notifications.push({
      id: 'mid-balance',
      type: 'warning',
      icon: <Wallet className="h-4 w-4" />,
      message: `Maintain at least ₹1000 balance to keep ${planType} enabled without interruption.`,
      action: { label: 'Top up Wallet', onClick: () => navigate('/autopay-setup?buy=true') }
    })
  }

  // 6. Mandate/Autopay Logic
  if (isPremium) {
    if (!billingInfo.mandate_active) {
      notifications.push({
        id: 'no-mandate',
        type: 'warning',
        icon: <AlertCircle className="h-4 w-4" />,
        message: `${planType} requires active mandate. Set up Autopay now for seamless operation.`,
        action: { label: 'Set Up', onClick: () => navigate('/autopay-setup') }
      })
    } else if (!billingInfo.auto_recharge_enabled) {
      notifications.push({
        id: 'autopay-off',
        type: 'info',
        icon: <ShieldAlert className="h-4 w-4" />,
        message: "Mandate active! Enable Autopay to avoid manual top-ups.",
        action: { label: 'Enable', onClick: () => navigate('/autopay-setup') }
      })
    }
  }

  // 7. Recent Successful Recharge (Last 24h)
  if (billingInfo.last_auto_recharge_date) {
    const lastRecharge = new Date(billingInfo.last_auto_recharge_date)
    const isRecent = (new Date().getTime() - lastRecharge.getTime()) < 24 * 60 * 60 * 1000
    if (isRecent) {
       notifications.push({
        id: 'recent-success',
        type: 'info',
        icon: <Wallet className="h-4 w-4" />,
        message: `Success! ₹${billingInfo.auto_recharge_amount.toLocaleString()} was automatically added to your wallet.`,
        action: { label: 'History', onClick: () => navigate('/ledger') }
      })
    }
  }

  if (notifications.length === 0) return null

  // Priority logic for multiple notes
  // Suspended > Critical > Warning > Info
  const activeNote = notifications.find(n => n.id === 'suspended') ||
                     notifications.find(n => n.type === 'critical') || 
                     notifications.find(n => n.type === 'warning') || 
                     notifications[0]

  const variantStyles = {
    critical: "bg-gradient-to-r from-red-600 via-red-500 to-orange-500 text-white border-red-400",
    warning: "bg-gradient-to-r from-amber-500 via-orange-500 to-red-500 text-white border-amber-400",
    info: "bg-gradient-to-r from-blue-600 via-indigo-500 to-primary text-white border-blue-400"
  }

  return (
    <div className={cn(
      "w-full py-1.5 sm:py-2 px-3 sm:px-4 flex items-center justify-center gap-2 sm:gap-4 text-[10px] sm:text-xs font-semibold animate-in slide-in-from-top-4 duration-500 shadow-inner",
      variantStyles[activeNote.type as keyof typeof variantStyles]
    )}>
      <div className="flex items-center gap-2 max-w-7xl w-full">
        <div className="flex items-center gap-2 flex-grow overflow-hidden">
          <div className="p-1 rounded-md bg-white/20 shrink-0">
            {activeNote.icon}
          </div>
          <span className="truncate">{activeNote.message}</span>
        </div>
        
        {activeNote.action && (
          <button 
            onClick={activeNote.action.onClick}
            className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white text-black hover:bg-white/90 transition-all shrink-0 active:scale-95"
          >
            {activeNote.action.label}
            <ArrowRight className="h-3 w-3" />
          </button>
        )}

        <button
          onClick={handleDismiss}
          className="p-1 hover:bg-white/20 rounded-full transition-colors shrink-0 ml-1"
          title="Dismiss for 24h"
          aria-label="Close notification"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
