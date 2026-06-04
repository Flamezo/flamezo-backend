import { useContext, useEffect, useRef, useState } from 'react'
import { FrappeContext } from 'frappe-react-sdk'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Loader2 } from 'lucide-react'
import {
  LOGIN_URL,
  bootedAuthenticated,
  isCsrfError,
  isSessionGoneError,
  onSessionExpired,
  pingSession,
  refreshCsrfToken,
  triggerSessionExpired,
} from '@/lib/session'

// How often the heartbeat checks the session is still alive (ms).
const HEARTBEAT_MS = 4 * 60 * 1000
// Debounce window for focus/visibility-driven checks (ms).
const FOCUS_DEBOUNCE_MS = 30 * 1000
// URLs we must never re-handle, or we'd loop on our own recovery calls.
const IGNORED = ['flamezo_backend.flamezo.api.session.', '/api/method/login', '/api/method/logout']

function shouldIgnore(url?: string): boolean {
  if (!url) return false
  return IGNORED.some((u) => url.includes(u))
}

/**
 * SessionGuard makes the long-lived dashboard resilient to session loss.
 *
 *  1. Self-heals stale CSRF tokens — on a CSRF 403 it fetches a fresh token
 *     and retries the request once, so writes stop silently failing.
 *  2. Heartbeat — periodically (and on tab focus) confirms the session is
 *     alive and keeps the CSRF token current.
 *  3. Graceful expiry — when the session is genuinely gone, it shows a clear
 *     "session expired" dialog (preserving the current page) instead of an
 *     abrupt redirect, and beacons diagnostics so we can pin the trigger.
 *
 * Mounted once, inside FrappeProvider, above the router.
 */
export default function SessionGuard() {
  const frappe = useContext(FrappeContext)
  const [expired, setExpired] = useState(false)
  const lastFocusCheck = useRef(0)

  // ── Install axios interceptors on the SDK's shared instance ──────────────
  useEffect(() => {
    const axios = (frappe as any)?.app?.axios
    if (!axios) return

    const respId = axios.interceptors.response.use(
      (res: any) => res,
      async (error: any) => {
        const config = error?.config
        const url: string | undefined = config?.url

        if (!config || shouldIgnore(url)) {
          return Promise.reject(error)
        }

        // (1) Recoverable: stale CSRF token → refresh once and retry.
        if (isCsrfError(error) && !config.__csrfRetried) {
          config.__csrfRetried = true
          const { authenticated, csrf_token } = await refreshCsrfToken()
          if (authenticated && csrf_token) {
            config.headers = config.headers || {}
            config.headers['X-Frappe-CSRF-Token'] = csrf_token
            return axios.request(config)
          }
          // CSRF failed AND we're no longer authenticated → session is gone.
          triggerSessionExpired({
            reason: 'csrf-refresh-unauthenticated',
            url,
            method: config?.method,
            status: error?.response?.status,
          })
          return Promise.reject(error)
        }

        // (2) Unrecoverable: the session is gone → graceful re-login.
        if (isSessionGoneError(error)) {
          triggerSessionExpired({
            reason: 'session-gone',
            url,
            method: config?.method,
            status: error?.response?.status,
            responseSnippet: safeSnippet(error?.response?.data),
          })
        }

        return Promise.reject(error)
      },
    )

    return () => {
      axios.interceptors.response.eject(respId)
    }
  }, [frappe])

  // ── Subscribe to the single session-expired signal ───────────────────────
  useEffect(() => onSessionExpired(() => setExpired(true)), [])

  // ── Heartbeat: keep the session warm + detect expiry proactively ─────────
  useEffect(() => {
    if (!bootedAuthenticated()) return

    let cancelled = false

    const check = async () => {
      if (cancelled || document.hidden) return
      const { authenticated } = await pingSession()
      if (!cancelled && !authenticated) {
        triggerSessionExpired({ reason: 'heartbeat-unauthenticated' })
      }
    }

    const interval = window.setInterval(check, HEARTBEAT_MS)

    const onFocus = () => {
      const now = Date.now()
      if (now - lastFocusCheck.current < FOCUS_DEBOUNCE_MS) return
      lastFocusCheck.current = now
      check()
    }

    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onFocus)

    return () => {
      cancelled = true
      window.clearInterval(interval)
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onFocus)
    }
  }, [])

  const [redirecting, setRedirecting] = useState(false)
  const goToLogin = () => {
    setRedirecting(true)
    // Preserve where they were so login can return them after re-auth.
    try {
      sessionStorage.setItem('flamezo:return-to', window.location.pathname + window.location.search)
    } catch {
      /* ignore */
    }
    window.location.replace(LOGIN_URL)
  }

  if (!expired) return null

  return (
    <Dialog open onOpenChange={() => { /* non-dismissible */ }}>
      <DialogContent
        className="sm:max-w-md [&>button]:hidden"
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Session expired</DialogTitle>
          <DialogDescription>
            For your security you've been signed out. Please sign in again to
            continue — your work on this page is preserved until you do.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button onClick={goToLogin} disabled={redirecting} className="w-full">
            {redirecting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Sign in again'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function safeSnippet(data: any): string | undefined {
  try {
    return JSON.stringify(data).slice(0, 300)
  } catch {
    return undefined
  }
}
