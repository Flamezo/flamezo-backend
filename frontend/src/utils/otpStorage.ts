/**
 * localStorage keys for platform-wide verified phone.
 * Once verified at one restaurant, user stays verified for all.
 */
const VERIFIED_PHONE_KEY = 'flamezo_verified_phone'
const VERIFIED_AT_KEY = 'flamezo_verified_at'

/** Normalize phone by stripping non-numeric chars and extracting base 10 digits */
export function normalizePhone(phone: string): string {
  const digits = (phone || '').replace(/\D/g, '')
  // If it's longer than 10 digits (e.g. 918850603518), take the last 10
  // This is a simple frontend normalization; the backend will do strict E.164 parsing
  return digits.length >= 10 ? digits.slice(-10) : digits
}

export function getStoredVerifiedPhone(): string | null {
  if (typeof window === 'undefined') return null
  try {
    return localStorage.getItem(VERIFIED_PHONE_KEY)
  } catch {
    return null
  }
}

export function setVerifiedPhone(phone: string): void {
  if (typeof window === 'undefined') return
  try {
    const normalized = normalizePhone(phone)
    if (normalized) {
      localStorage.setItem(VERIFIED_PHONE_KEY, normalized)
      localStorage.setItem(VERIFIED_AT_KEY, Date.now().toString())
    }
  } catch {
    // ignore
  }
}

export function clearVerifiedPhone(): void {
  if (typeof window === 'undefined') return
  try {
    localStorage.removeItem(VERIFIED_PHONE_KEY)
    localStorage.removeItem(VERIFIED_AT_KEY)
  } catch {
    // ignore
  }
}

/** Optional: re-verify after 30 days */
export function isVerifiedExpired(maxAgeMs = 30 * 24 * 60 * 60 * 1000): boolean {
  if (typeof window === 'undefined') return true
  try {
    const at = parseInt(localStorage.getItem(VERIFIED_AT_KEY) || '0', 10)
    return at > 0 && Date.now() - at > maxAgeMs
  } catch {
    return true
  }
}
