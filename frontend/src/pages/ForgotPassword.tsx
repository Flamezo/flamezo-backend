import { useState } from 'react'
import { Input } from '@/components/ui/input'
import loginImage from '/images/login-flamezo_backend.webp'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { Link } from 'react-router-dom'
import { ArrowLeft, Mail, CheckCircle2, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email) {
      toast.error('Please enter your email address')
      return
    }

    setLoading(true)
    try {
      const form = new URLSearchParams()
      form.append('user', email)

      const res = await fetch('/api/method/frappe.core.doctype.user.user.reset_password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
        },
        body: form.toString()
      })

      if (res.ok) {
        toast.success('Recovery instructions dispatched!')
        setSubmitted(true)
      } else {
        const data = await res.json().catch(() => ({}))
        const msg = data?.message || 'Verification failed. Please ensure the email is registered.'
        toast.error(msg)
      }
    } catch (err: any) {
      console.error('Forgot password error:', err)
      toast.error('Network error. Please check your connection and try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={cn("min-h-screen flex bg-slate-50 dark:bg-slate-950 overflow-hidden font-inter")}>
      {/* Visual Side (Left) */}
      <div className="hidden lg:block relative w-1/2 min-h-screen overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-tr from-primary/40 to-transparent z-10 mix-blend-overlay" />
        <img
          src={loginImage}
          alt="Flamezo Hub"
          className="absolute inset-0 h-full w-full object-cover grayscale-[20%] brightness-90 hover:scale-105 transition-transform duration-[10s]"
        />
        <div className="absolute bottom-12 left-12 z-20 max-w-md">
          <div className="bg-white/10 backdrop-blur-md border border-white/20 p-8 rounded-3xl shadow-2xl">
            <h1 className="text-4xl font-black text-white mb-4 tracking-tight">Security First.</h1>
            <p className="text-white/80 font-medium text-lg leading-relaxed">
              We utilize bank-grade encryption to ensure your restaurant data remains protected and private.
            </p>
          </div>
        </div>
      </div>

      {/* Form Side (Right) */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-6 md:p-12 bg-card relative">
        {/* Decorative background elements */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-primary/5 rounded-full -translate-y-1/2 translate-x-1/2 blur-3xl" />
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-primary/5 rounded-full translate-y-1/2 -translate-x-1/2 blur-3xl" />

        <div className="w-full max-w-md relative z-10">
          <Link 
            to="/login" 
            className="group inline-flex items-center text-sm font-bold text-muted-foreground hover:text-primary transition-all mb-10"
          >
            <div className="bg-muted group-hover:bg-primary/10 p-2 rounded-xl mr-3 transition-colors">
              <ArrowLeft size={18} className="group-hover:-translate-x-1 transition-transform" />
            </div>
            Back to Dashboard Sign-in
          </Link>
          
          <div className="space-y-2 mb-10">
            <h2 className="text-4xl font-black tracking-tight text-foreground">Password Recovery</h2>
            <p className="text-muted-foreground font-medium">
              {submitted 
                ? "Verification link sent successfully."
                : "Enter your registered email to receive a secure reset link."}
            </p>
          </div>

          {!submitted ? (
            <form onSubmit={handleSubmit} className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
              <div className="space-y-2">
                <label className="text-xs font-black uppercase tracking-widest text-muted-foreground ml-1">Email Identifier</label>
                <div className="relative group">
                  <div className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground group-focus-within:text-primary transition-colors">
                    <Mail size={18} />
                  </div>
                  <Input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@restaurant.com"
                    className="pl-12 h-14 rounded-2xl border-stone-200 focus:ring-primary/20 bg-background shadow-sm transition-all"
                    required
                  />
                </div>
              </div>
              <Button type="submit" className="w-full h-14 rounded-2xl text-base font-bold shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-all hover:-translate-y-0.5 active:translate-y-0" disabled={loading}>
                {loading ? (
                  <div className="flex items-center justify-center gap-2">
                    <Loader2 className="animate-spin" size={20} />
                    Processing Security Request...
                  </div>
                ) : (
                  'Dispatch Reset Link'
                )}
              </Button>
            </form>
          ) : (
            <div className="bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-100 dark:border-emerald-900/30 p-8 rounded-3xl text-center space-y-6 animate-in zoom-in-95 duration-500">
              <div className="mx-auto w-20 h-20 bg-emerald-100 dark:bg-emerald-900/40 rounded-2xl flex items-center justify-center">
                <CheckCircle2 size={40} className="text-emerald-600 dark:text-emerald-400" />
              </div>
              <div className="space-y-2">
                <h3 className="text-xl font-bold text-emerald-900 dark:text-emerald-100">Check your Inbox</h3>
                <p className="text-sm text-emerald-700 dark:text-emerald-300 font-medium leading-relaxed">
                  We've sent a one-time secure link to <span className="font-bold underline">{email}</span>. 
                  Please follow the instructions in the email to restore access.
                </p>
              </div>
              <div className="pt-4 border-t border-emerald-100 dark:border-emerald-900/30">
                <Button 
                  variant="ghost" 
                  className="text-emerald-600 dark:text-emerald-400 font-bold hover:bg-emerald-100 dark:hover:bg-emerald-900/40 rounded-xl" 
                  onClick={() => setSubmitted(false)}
                >
                  Didn't receive it? Try again
                </Button>
              </div>
            </div>
          )}

          <div className="mt-12 text-center">
            <p className="text-sm text-muted-foreground font-medium">
              Protected by Flamezo Security Engine v4.0
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
