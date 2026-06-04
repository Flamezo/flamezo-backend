// Session resilience utilities for the merchant dashboard.
//
// The dashboard is a long-lived SPA that authenticates via Frappe's `sid`
// cookie and a CSRF token (`window.csrf_token`) captured once at page load.
// When the server-side session ends or the CSRF token goes stale, Frappe
// clears the cookie and the SPA — which trusts a frozen boot snapshot — would
// otherwise dump the user at /login with no warning.
//
// This module is the shared toolkit the SessionGuard uses to:
//   • refresh a stale CSRF token without a full reload (self-heal writes)
//   • probe liveness for the heartbeat
//   • broadcast a single "session expired" signal to the UI
//   • beacon diagnostics so production reveals the real trigger

const METHOD = 'flamezo_backend.flamezo.api.session'

/** Full (non-SPA) login URL — used for hard redirects out of the app. */
export const LOGIN_URL = '/flamezo_backend/login'

const CSRF_PLACEHOLDER = '{{ csrf_token }}'

/** The user baked into the page at load time (object or string, or Guest). */
export function getBootUser(): string {
  const raw = (window as any)?.frappe?.boot?.user
  const name = typeof raw === 'object' && raw != null ? raw.name : raw
  return name || 'Guest'
}

/** True when the page loaded with a real (non-Guest) authenticated user. */
export function bootedAuthenticated(): boolean {
  const u = getBootUser()
  return !!u && u !== 'Guest'
}

/** Current CSRF token the SDK will send, or '' if unusable. */
export function currentCsrfToken(): string {
  const t = (window as any)?.csrf_token
  return t && t !== CSRF_PLACEHOLDER ? String(t) : ''
}

function setCsrfToken(token: string) {
  if (token) (window as any).csrf_token = token
}

interface CsrfResult {
  authenticated: boolean
  csrf_token: string
}

/**
 * Ask the server for a fresh CSRF token and update `window.csrf_token`.
 * The SDK reads `window.csrf_token` on every request, so updating it here is
 * enough for subsequent (and retried) writes to carry the correct token.
 * Returns `authenticated: false` when the session is already gone.
 */
export async function refreshCsrfToken(): Promise<CsrfResult> {
  try {
    const res = await fetch(`/api/method/${METHOD}.get_csrf_token`, {
      method: 'GET',
      credentials: 'include',
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    })
    const json = await res.json().catch(() => ({}))
    const data = json?.message ?? json
    const token = data?.csrf_token || ''
    if (token) setCsrfToken(token)
    return { authenticated: !!data?.authenticated, csrf_token: token }
  } catch {
    return { authenticated: false, csrf_token: '' }
  }
}

/** Cheap heartbeat probe. Never throws; reports live auth state. */
export async function pingSession(): Promise<CsrfResult> {
  try {
    const res = await fetch(`/api/method/${METHOD}.ping`, {
      method: 'GET',
      credentials: 'include',
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    })
    const json = await res.json().catch(() => ({}))
    const data = json?.message ?? json
    const token = data?.csrf_token || ''
    if (token) setCsrfToken(token)
    return { authenticated: !!data?.authenticated, csrf_token: token }
  } catch {
    // Network blip — assume still alive; the next real request decides.
    return { authenticated: true, csrf_token: currentCsrfToken() }
  }
}

export interface SessionLossContext {
  reason: string
  url?: string
  method?: string
  status?: number
  responseSnippet?: string
  hadSidCookie?: boolean
  bootUser?: string
  at?: string
}

/** Was a `sid` cookie present at this moment? (HttpOnly hides the real one, */
/** but a duplicate non-HttpOnly `sid` — the classic logout cause — shows up.) */
export function readableSidCookiePresent(): boolean {
  return document.cookie.split(';').some((c) => c.trim().startsWith('sid='))
}

/**
 * Beacon the captured state at a forced logout so production logs the real
 * trigger. Uses sendBeacon (survives page unload) and falls back to fetch.
 */
export function reportSessionLoss(ctx: SessionLossContext): void {
  try {
    const payload = JSON.stringify({
      context: {
        ...ctx,
        bootUser: ctx.bootUser ?? getBootUser(),
        hadSidCookie: ctx.hadSidCookie ?? readableSidCookiePresent(),
        at: ctx.at ?? new Date().toISOString(),
        userAgent: navigator.userAgent,
        path: window.location.pathname,
      },
    })
    const url = `/api/method/${METHOD}.log_session_diagnostic`
    const body = new Blob([payload], { type: 'application/json' })
    if (navigator.sendBeacon && navigator.sendBeacon(url, body)) return
    fetch(url, { method: 'POST', credentials: 'include', body: payload, headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, keepalive: true }).catch(() => {})
  } catch {
    // Diagnostics are best-effort.
  }
}

// ─── Single "session expired" signal ────────────────────────────────────────
// One source of truth so the whole app reacts once (modal), not N times.

let sessionExpired = false
const listeners = new Set<() => void>()

export function onSessionExpired(cb: () => void): () => void {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

export function isSessionExpired(): boolean {
  return sessionExpired
}

/** Fire the session-expired signal exactly once. */
export function triggerSessionExpired(ctx: SessionLossContext): void {
  if (sessionExpired) return
  sessionExpired = true
  reportSessionLoss(ctx)
  listeners.forEach((cb) => {
    try {
      cb()
    } catch {
      /* listener errors must not cascade */
    }
  })
}

/** Reset (used after a successful re-auth in dev/tests). */
export function clearSessionExpired(): void {
  sessionExpired = false
}

// ─── Error classification ───────────────────────────────────────────────────

/** A stale/missing CSRF token — recoverable by refreshing + retrying once. */
export function isCsrfError(err: any): boolean {
  const status = err?.response?.status
  if (status !== 400 && status !== 403) return false
  const data = err?.response?.data
  const excType = String(data?.exc_type || data?.exception || '')
  // Frappe reliably tags CSRF rejections with this exc_type — prefer it so we
  // never mistake a PermissionError (also 403) for a recoverable CSRF failure.
  if (/CSRFToken/i.test(excType)) return true
  // Fallback only when no exc_type is present (e.g. a bare proxy/CSRF reject).
  if (!excType) {
    const messages = JSON.stringify(data?._server_messages || data?.message || '')
    return /csrf/i.test(messages)
  }
  return false
}

/** A genuinely gone session — not recoverable without re-login. */
export function isSessionGoneError(err: any): boolean {
  const status = err?.response?.status
  const data = err?.response?.data
  if (status === 401) return true
  // Frappe sets this on the response when it clears the session.
  if (data?.session_expired === 1 || data?.session_expired === '1') return true
  const excType = data?.exc_type || data?.exception || ''
  return /(AuthenticationError|SessionExpired)/i.test(excType)
}
