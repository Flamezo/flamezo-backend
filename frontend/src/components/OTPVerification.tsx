import React, { useState, useEffect } from 'react'
import { useFrappePostCall } from '@/lib/frappe'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { toast } from 'sonner'

const RESEND_COOLDOWN_SEC = 30
const OTP_LENGTH = 6

interface OTPVerificationProps {
  restaurantId: string
  restaurantName?: string
  phone: string
  name?: string
  email?: string
  onVerified: () => void
  onSkip?: () => void
}

export function OTPVerification({
  restaurantId,
  restaurantName,
  phone,
  name,
  email,
  onVerified,
  onSkip
}: OTPVerificationProps) {
  const [otp, setOtp] = useState('')
  const [token, setToken] = useState<string | null>(null)
  const [step, setStep] = useState<'send' | 'verify'>('send')
  const [sending, setSending] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [cooldown, setCooldown] = useState(0)

  const { call: sendOtp } = useFrappePostCall('flamezo_backend.flamezo.api.otp.send_otp')
  const { call: verifyOtp } = useFrappePostCall('flamezo_backend.flamezo.api.otp.verify_otp')

  // Cooldown timer
  useEffect(() => {
    if (cooldown <= 0) return
    const t = setInterval(() => setCooldown((c) => (c <= 1 ? 0 : c - 1)), 1000)
    return () => clearInterval(t)
  }, [cooldown])

  const handleSendOTP = async () => {
    if (!phone?.trim()) return
    setSending(true)
    try {
      const res = await sendOtp({
        restaurant_id: restaurantId,
        restaurant_name: restaurantName,
        phone: phone.trim(),
        purpose: 'checkout'
      })
      if (res?.success) {
        if (res.skip_verification) {
          onVerified()
          return
        }
        if (res.skip_verification) {
          onVerified()
          return
        }
        if (res.token) {
          setToken(res.token)
          setStep('verify')
          setCooldown(RESEND_COOLDOWN_SEC)
        }
        toast.success(res.message || 'OTP sent')
      } else {
        toast.error(res?.message || res?.error || 'Failed to send OTP')
      }
    } catch (e) {
      toast.error('Failed to send OTP')
    } finally {
      setSending(false)
    }
  }

  const handleVerify = async () => {
    if (!otp || otp.length !== OTP_LENGTH || !token) return
    setVerifying(true)
    try {
      const res = await verifyOtp({
        restaurant_id: restaurantId,
        phone: phone.trim(),
        otp,
        token,
        name,
        email
      })
      if (res?.success && res.verified) {
        toast.success('Phone verified')
        onVerified()
      } else {
        toast.error(res?.error === 'INVALID_OTP' ? 'Invalid OTP' : res?.message || 'Verification failed')
      }
    } catch (e) {
      toast.error('Verification failed')
    } finally {
      setVerifying(false)
    }
  }

  const handleOtpChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value.replace(/\D/g, '').slice(0, OTP_LENGTH)
    setOtp(v)
  }

  if (step === 'send') {
    return (
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Verify your phone to continue. OTP will be sent to {phone}
        </p>
        <Button
          onClick={handleSendOTP}
          disabled={sending}
          className="w-full"
        >
          {sending ? 'Sending...' : 'Send OTP'}
        </Button>
        {onSkip && (
          <Button variant="ghost" onClick={onSkip} className="w-full">
            Skip
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Enter 6-digit OTP</Label>
        <Input
          type="text"
          inputMode="numeric"
          maxLength={OTP_LENGTH}
          placeholder="0000"
          value={otp}
          onChange={handleOtpChange}
          className="text-center text-lg tracking-[0.5em]"
          autoFocus
        />
      </div>
      <Button
        onClick={handleVerify}
        disabled={verifying || otp.length !== OTP_LENGTH}
        className="w-full"
      >
        {verifying ? 'Verifying...' : 'Verify'}
      </Button>
      <Button
        variant="ghost"
        onClick={handleSendOTP}
        disabled={sending || cooldown > 0}
        className="w-full text-sm"
      >
        {cooldown > 0 ? `Resend in ${cooldown}s` : 'Resend OTP'}
      </Button>
    </div>
  )
}
