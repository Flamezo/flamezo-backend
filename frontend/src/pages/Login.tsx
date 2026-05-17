import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Eye, EyeOff } from 'lucide-react'

import { Input } from '@/components/ui/input'
import loginImage from '/images/login-flamezo_backend.webp'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)


  const handleSubmit = async (e: any) => {
    e.preventDefault()
    setLoading(true)
    try {
      const form = new URLSearchParams()
      form.append('usr', email)
      form.append('pwd', password)

      const res = await fetch('/api/method/login', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
        },
        body: form.toString()
      })

      if (res.ok) {
        toast.success('Logged in successfully')
        // Reload to let server set boot and session
        window.location.href = '/flamezo_backend'
      } else {
        const data = await res.json().catch(() => ({}))
        const msg = data?.message || 'Login failed'
        toast.error(msg)
      }
    } catch (err: any) {
      console.error(err)
      toast.error('Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex bg-gradient-to-br from-primary/20 via-background to-primary/10 dark:from-primary/25 dark:via-background dark:to-primary/15">
      {/* Left 50% - Image (full 50% cover) */}
      <div className="hidden md:block relative w-1/2 min-h-screen overflow-hidden">
        <img
          src={loginImage}
          alt="Flamezo"
          width={1080}
          height={1080}
          fetchPriority="high"
          decoding="async"
          className="absolute inset-0 h-full w-full object-cover"
        />
      </div>
      {/* Right 50% - Login card */}
      <div className="w-full md:w-1/2 flex items-center justify-center p-6 md:p-12">
        <div className="w-full max-w-md p-8 bg-card rounded-lg shadow-lg border border-border">
          <h2 className="text-2xl font-semibold mb-4 text-center text-foreground">Welcome to Flamezo</h2>
          <p className="text-sm text-muted-foreground mb-6 text-center">Sign in to manage your restaurants</p>
          <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs font-medium block mb-1 text-foreground">Username or Email</label>
            <Input
              type="text"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="username or you@company.com"
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium block text-foreground">Password</label>
            <div className="relative">
              <Input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                className="pr-10"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors focus:outline-none"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? (
                  <EyeOff size={18} className="animate-in fade-in zoom-in duration-200" />
                ) : (
                  <Eye size={18} className="animate-in fade-in zoom-in duration-200" />
                )}
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Link to="/forgot-password" className="text-sm text-muted-foreground hover:text-primary hover:underline transition-colors">Forgot Password?</Link>

            </div>

          </div>
          <div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Signing in...' : 'Sign in'}
            </Button>
          </div>
          </form>
        </div>
      </div>
    </div>
  )
}

