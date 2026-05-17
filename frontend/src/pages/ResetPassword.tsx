import { useState, useEffect } from 'react'
import { Input } from '@/components/ui/input'
import loginImage from '/images/login-flamezo_backend.webp'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, CheckCircle2, AlertCircle, Loader2, ShieldCheck, ArrowRight } from 'lucide-react'
import { cn } from '@/lib/utils'

export default function ResetPassword() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const key = searchParams.get('key')

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    if (!key) {
      toast.error('Security violation: Missing reset credentials.')
      navigate('/login')
    }
  }, [key, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (password !== confirmPassword) {
      toast.error('Validation Error: Passwords do not match.')
      return
    }

    if (password.length < 8) {
      toast.error('Security Policy: Password must be at least 8 characters long.')
      return
    }

    setLoading(true)
    try {
      const form = new URLSearchParams()
      form.append('key', key || '')
      form.append('new_password', password)
      form.append('logout_all_sessions', '1')

      const res = await fetch('/api/method/frappe.core.doctype.user.user.update_password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
        },
        body: form.toString()
      })

      if (res.ok) {
        toast.success('Security identity updated successfully!')
        setSuccess(true)
        // Auto redirect after 3 seconds
        setTimeout(() => {
          window.location.href = '/flamezo_backend'
        }, 3000)
      } else {
        const data = await res.json().catch(() => ({}))
        const msg = data?.message || 'Authorization failed. The secure link may have expired.'
        toast.error(msg)
      }
    } catch (err: any) {
      console.error('Reset password error:', err)
      toast.error('Synchronization error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const isPasswordValid = password.length >= 8
  const doPasswordsMatch = password === confirmPassword && confirmPassword !== ''

  return (
    <div className="min-h-screen flex bg-slate-50 dark:bg-slate-950 overflow-hidden font-inter">
      {/* Visual Side (Left) */}
      <div className="hidden lg:block relative w-1/2 min-h-screen overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/30 to-transparent z-10 mix-blend-overlay" />
        <img
          src={loginImage}
          alt="Security"
          className="absolute inset-0 h-full w-full object-cover grayscale-[10%] brightness-75"
        />
        <div className="absolute top-12 left-12 z-20">
          <div className="flex items-center gap-3 bg-white/10 backdrop-blur-md px-6 py-3 rounded-2xl border border-white/20">
            <ShieldCheck className="text-white h-6 w-6" />
            <span className="text-white font-black tracking-widest text-sm uppercase">Flamezo Vault</span>
          </div>
        </div>
      </div>

      {/* Form Side (Right) */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-6 md:p-12 bg-card relative">
        <div className="w-full max-w-md relative z-10">
          <div className="space-y-2 mb-10 text-center lg:text-left">
            <h2 className="text-4xl font-black tracking-tight text-foreground">Secure Reset</h2>
            <p className="text-muted-foreground font-medium">Update your administrative credentials.</p>
          </div>
          
          {success ? (
            <div className="bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-100 dark:border-emerald-900/30 p-10 rounded-[2.5rem] text-center space-y-8 animate-in zoom-in-95 duration-500 shadow-2xl shadow-emerald-500/5">
              <div className="mx-auto w-24 h-24 bg-emerald-100 dark:bg-emerald-900/40 rounded-3xl flex items-center justify-center">
                <CheckCircle2 size={56} className="text-emerald-600 dark:text-emerald-400" />
              </div>
              <div className="space-y-3">
                <h3 className="text-2xl font-black text-emerald-900 dark:text-emerald-50">Access Restored</h3>
                <p className="text-emerald-700 dark:text-emerald-300 font-medium leading-relaxed">
                  Your new password is now active. We are redirecting you to your restaurant dashboard...
                </p>
              </div>
              <Button asChild className="w-full h-14 rounded-2xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold transition-all shadow-lg shadow-emerald-600/20">
                <Link to="/dashboard" className="flex items-center justify-center gap-2">
                  Launch Dashboard <ArrowRight size={18} />
                </Link>
              </Button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
              <div className="space-y-6">
                <div className="space-y-2">
                  <label className="text-xs font-black uppercase tracking-widest text-muted-foreground ml-1">New Secure Password</label>
                  <div className="relative group">
                    <Input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Minimum 8 characters"
                      className={cn(
                        "h-14 rounded-2xl border-stone-200 pr-12 focus:ring-primary/20 bg-background shadow-sm transition-all",
                        password && !isPasswordValid && "border-amber-300 focus:ring-amber-500/20"
                      )}
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                  {password && !isPasswordValid && (
                    <p className="text-[10px] font-bold text-amber-600 flex items-center gap-1 ml-1">
                      <AlertCircle size={12} /> Password too short
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-black uppercase tracking-widest text-muted-foreground ml-1">Confirm Identity</label>
                  <Input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Repeat new password"
                    className={cn(
                      "h-14 rounded-2xl border-stone-200 focus:ring-primary/20 bg-background shadow-sm transition-all",
                      confirmPassword && !doPasswordsMatch && "border-red-300 focus:ring-red-500/20"
                    )}
                    required
                  />
                  {confirmPassword && !doPasswordsMatch && (
                    <div className="flex items-center text-[10px] font-bold text-red-600 gap-1.5 ml-1 animate-in fade-in duration-200">
                      <AlertCircle size={12} /> Passwords do not match
                    </div>
                  )}
                </div>
              </div>

              <Button 
                type="submit" 
                className={cn(
                  "w-full h-14 rounded-2xl text-base font-black shadow-lg transition-all hover:-translate-y-0.5 active:translate-y-0",
                  loading ? "bg-primary/80" : "bg-primary shadow-primary/20 hover:shadow-primary/30"
                )}
                disabled={loading}
              >
                {loading ? (
                  <div className="flex items-center justify-center gap-2">
                    <Loader2 className="animate-spin" size={20} />
                    Securing Account...
                  </div>
                ) : (
                  'Authorize Password Update'
                )}
              </Button>

              <div className="text-center">
                <Link to="/login" className="text-sm font-bold text-muted-foreground hover:text-primary transition-colors">
                  Return to Dashboard Login
                </Link>
              </div>
            </form>
          )}

          <div className="mt-12 text-center">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground/60 font-black">
              System Instance: {window.location.hostname}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
