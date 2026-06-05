import React, { useState, useEffect } from 'react'
import { AlertCircle, ArrowRight, Wallet, Calendar, ShieldAlert, Loader2, X, Landmark } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useNavigate } from 'react-router-dom'
import { format } from 'date-fns'
import { useRestaurant } from '@/contexts/RestaurantContext'

/**
 * BillingNotificationBar
 *
 * Top-of-page alert ribbon that surfaces wallet / autopay / mandate /
 * suspension / Route KYC state for the currently selected restaurant.
 */

const SUPPORT_EMAIL = 'hello@onomatrix.com'
const SUSPENSION_COPY =
  'Account suspended due to a billing issue. Please clear dues or contact support to reactivate.'

interface BillingNotificationBarProps {
  billingInfo: {
    coins_balance: number
    deferred_plan_type?: 'GOLD' | null
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
  isActive?: boolean
}

export const BillingNotificationBar: React.FC<BillingNotificationBarProps> = ({
  billingInfo,
  isActive = true,
}) => {
  const navigate = useNavigate()
  const { payments } = useRestaurant()
  const [isDismissed, setIsDismissed] = useState(false)

  // Check for dismissal on mount (sticky for 24h via localStorage)
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

  // Inactive restaurant takes priority over every other state.
  if (!isActive) {
    return (
      <div
        className={cn(
          'w-full py-2 px-4 flex items-center justify-center gap-4 text-xs font-semibold animate-in slide-in-from-top-4 duration-500 shadow-inner',
          'bg-gradient-to-r from-red-600 via-red-500 to-orange-500 text-white border-red-400'
        )}
      >
        <div className="flex items-center gap-2 max-w-7xl w-full">
          <div className="flex items-center gap-2 flex-grow overflow-hidden">
            <div className="p-1 rounded-md bg-white/20 shrink-0">
              <ShieldAlert className="h-4 w-4" />
            </div>
            <span className="truncate">{SUSPENSION_COPY}</span>
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

  const notifications: Array<{
    id: string
    type: 'critical' | 'warning' | 'info'
    icon: React.ReactNode
    message: string
    action?: { label: string; onClick: () => void }
  }> = []

  // 1. Account Status (Suspended / Overdue)
  if (billingInfo.billing_status === 'suspended') {
    notifications.push({
      id: 'suspended',
      type: 'critical',
      icon: <ShieldAlert className="h-4 w-4" />,
      message: SUSPENSION_COPY,
      action: {
        label: 'Contact Support',
        onClick: () => {
          window.location.href = `mailto:${SUPPORT_EMAIL}`
        },
      },
    })
  } else if (billingInfo.billing_status === 'overdue') {
    notifications.push({
      id: 'overdue',
      type: 'critical',
      icon: <AlertCircle className="h-4 w-4" />,
      message:
        'Payment overdue. Your account will be suspended shortly if the balance is not cleared.',
      action: { label: 'Pay Now', onClick: () => navigate('/autopay-setup?buy=true') },
    })
  }

  if (billingInfo.deferred_plan_type) {
    const formattedDate = billingInfo.plan_change_date
      ? format(new Date(billingInfo.plan_change_date), 'do MMMM')
      : 'tomorrow'
    notifications.push({
      id: 'plan-change',
      type: 'info',
      icon: <Calendar className="h-4 w-4" />,
      message: `A plan change is scheduled to take effect on ${formattedDate} at 12:00 AM.`,
      action: { label: 'Manage', onClick: () => navigate('/autopay-setup') },
    })
  }

  // 3. Account Risk (Negative Balance)
  if (billingInfo.coins_balance < 0) {
    notifications.push({
      id: 'account-risk',
      type: 'critical',
      icon: <ShieldAlert className="h-4 w-4" />,
      message:
        'Your wallet is in negative. Recharge immediately to avoid suspension.',
      action: { label: 'Recharge Now', onClick: () => navigate('/autopay-setup?buy=true') },
    })
  }

  // 4. Autopay Daily Limit (Warning / Reached)
  if (billingInfo.auto_recharge_enabled) {
    if (billingInfo.current_daily_vol >= billingInfo.daily_limit) {
      notifications.push({
        id: 'daily-limit-reached',
        type: 'critical',
        icon: <ShieldAlert className="h-4 w-4" />,
        message: `Daily safety limit of ₹${billingInfo.daily_limit.toLocaleString()} reached. Automatic recharges are paused until tomorrow.`,
        action: { label: 'Increase Limit', onClick: () => navigate('/autopay-setup') },
      })
    } else if (billingInfo.current_daily_vol >= billingInfo.daily_limit * 0.8) {
      notifications.push({
        id: 'daily-limit-near',
        type: 'warning',
        icon: <AlertCircle className="h-4 w-4" />,
        message: `Approaching daily autopay safety limit (used ₹${billingInfo.current_daily_vol.toLocaleString()} of ₹${billingInfo.daily_limit.toLocaleString()}).`,
        action: { label: 'Settings', onClick: () => navigate('/autopay-setup') },
      })
    }
  }

  // 5. Low Balance Alert
  //
  // Single-tier model: every restaurant gets the same warning ladder. We
  // describe the failure mode in plain terms ("Success Share recovery may
  // pause and AI / messaging features may be interrupted") instead of
  // referencing a tier name.
  if (billingInfo.coins_balance >= 0 && billingInfo.coins_balance < 300) {
    const isAutopayComing =
      billingInfo.auto_recharge_enabled &&
      billingInfo.mandate_active &&
      billingInfo.current_daily_vol < billingInfo.daily_limit

    const message = isAutopayComing
      ? `Low wallet balance (₹${billingInfo.coins_balance.toLocaleString()}). An automatic top-up of ₹${billingInfo.auto_recharge_amount.toLocaleString()} will be triggered shortly.`
      : `Wallet balance is critically low (₹${billingInfo.coins_balance.toLocaleString()}). Success Share recovery, AI tools, and messaging may be paused soon.`

    notifications.push({
      id: 'low-balance',
      type: isAutopayComing ? 'info' : 'critical',
      icon: isAutopayComing
        ? <Loader2 className="h-4 w-4 animate-spin text-white" />
        : <ShieldAlert className="h-4 w-4" />,
      message,
      action: {
        label: isAutopayComing ? 'Settings' : 'Top up Now',
        onClick: () => navigate(isAutopayComing ? '/autopay-setup' : '/autopay-setup?buy=true'),
      },
    })
  } else if (billingInfo.coins_balance < 1000) {
    notifications.push({
      id: 'mid-balance',
      type: 'warning',
      icon: <Wallet className="h-4 w-4" />,
      message: 'Maintain at least ₹1,000 in your wallet to keep Flamezo features running without interruption.',
      action: { label: 'Top up Wallet', onClick: () => navigate('/autopay-setup?buy=true') },
    })
  }

  // 6. Mandate / Autopay Setup
  if (!billingInfo.mandate_active) {
    notifications.push({
      id: 'no-mandate',
      type: 'warning',
      icon: <AlertCircle className="h-4 w-4" />,
      message: 'Set up Autopay to keep your Success Share billing running automatically.',
      action: { label: 'Set Up', onClick: () => navigate('/autopay-setup') },
    })
  } else if (!billingInfo.auto_recharge_enabled) {
    notifications.push({
      id: 'autopay-off',
      type: 'info',
      icon: <ShieldAlert className="h-4 w-4" />,
      message: 'Mandate active. Enable Autopay to avoid manual top-ups when your balance runs low.',
      action: { label: 'Enable', onClick: () => navigate('/autopay-setup') },
    })
  }

  // ── Route KYC nudge ────────────────────────────────────────────────
  // Soft, low-priority info banner shown when the restaurant is still on
  // the `flamezo_hold` settlement path (customer payments land in
  // Flamezo's account, settled to them weekly via NEFT) AND they haven't
  // submitted Route KYC yet. Activating Route gives them direct T+2
  // payouts. We deliberately don't show this once KYC is `under_review`
  // / `activated` / etc. — those states are already surfaced on the KYC
  // page hero, no need to clutter the banner.
  if (
    payments &&
    payments.routeMode === 'flamezo_hold' &&
    !payments.razorpayKycStatus
  ) {
    notifications.push({
      id: 'route-kyc-nudge',
      type: 'info',
      icon: <Landmark className="h-4 w-4" />,
      message: 'Want your customer payments to land in your bank directly? Set up Direct Bank Payouts.',
      action: { label: 'Set Up', onClick: () => navigate('/route-kyc') },
    })
  }

  // 7. Recent Successful Recharge (Last 24h) — celebratory info banner
  if (billingInfo.last_auto_recharge_date) {
    const lastRecharge = new Date(billingInfo.last_auto_recharge_date)
    const isRecent = new Date().getTime() - lastRecharge.getTime() < 24 * 60 * 60 * 1000
    if (isRecent) {
      notifications.push({
        id: 'recent-success',
        type: 'info',
        icon: <Wallet className="h-4 w-4" />,
        message: `₹${billingInfo.auto_recharge_amount.toLocaleString()} was automatically added to your wallet.`,
        action: { label: 'History', onClick: () => navigate('/ledger') },
      })
    }
  }

  if (notifications.length === 0) return null

  // Priority: Suspended > Critical > Warning > Info
  const activeNote =
    notifications.find((n) => n.id === 'suspended') ||
    notifications.find((n) => n.type === 'critical') ||
    notifications.find((n) => n.type === 'warning') ||
    notifications[0]

  const variantStyles: Record<'critical' | 'warning' | 'info', string> = {
    critical: 'bg-gradient-to-r from-red-600 via-red-500 to-orange-500 text-white border-red-400',
    warning: 'bg-gradient-to-r from-amber-500 via-orange-500 to-red-500 text-white border-amber-400',
    info: 'bg-gradient-to-r from-blue-600 via-indigo-500 to-primary text-white border-blue-400',
  }

  return (
    <div
      className={cn(
        'w-full py-1.5 sm:py-2 px-3 sm:px-4 flex items-center justify-center gap-2 sm:gap-4 text-[10px] sm:text-xs font-semibold animate-in slide-in-from-top-4 duration-500 shadow-inner',
        variantStyles[activeNote.type]
      )}
    >
      <div className="flex items-center gap-2 max-w-7xl w-full">
        <div className="flex items-center gap-2 flex-grow overflow-hidden">
          <div className="p-1 rounded-md bg-white/20 shrink-0">{activeNote.icon}</div>
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
