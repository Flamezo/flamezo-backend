/**
 * Single download path for every media asset in the dashboard.
 *
 * Media lives on the R2 CDN, a different origin than the dashboard, so a plain
 * `<a download>` is ignored by the browser and the file just opens in a tab.
 * Everything routes through the existing `download_proxy` endpoint, then via a
 * blob URL — a blob download still works after an await, where a direct <a>
 * navigation would be dropped because the user gesture is gone.
 */

const PROXY = '/api/method/flamezo_backend.flamezo.api.ai_media.download_proxy'

/** Build a safe filename from a title, falling back to the URL's own basename. */
export function mediaFilename(url: string, title?: string, fallbackExt = 'jpg'): string {
  const fromUrl = url.split('/').pop()?.split('?')[0] || ''
  const urlExt = fromUrl.includes('.') ? fromUrl.split('.').pop()!.toLowerCase() : ''
  const ext = urlExt || fallbackExt
  const base = (title || fromUrl.replace(/\.[^.]+$/, '') || 'download')
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .slice(0, 80) || 'download'
  return `${base}.${ext}`
}

/**
 * Download a media asset to the user's device.
 * Throws on failure so the caller can surface its own toast.
 */
export async function downloadMedia(url: string, filename?: string): Promise<void> {
  if (!url) throw new Error('No file URL')

  const name = filename || mediaFilename(url)

  // Fast path: absolute CDN url — fetch straight from the CDN (no backend hop).
  // Falls back to the proxy if CORS blocks it or it's a relative /files path.
  let blob: Blob | null = null
  if (/^https?:\/\//i.test(url)) {
    try {
      const direct = await fetch(url)
      if (direct.ok) blob = await direct.blob()
    } catch { /* CORS/network — fall through to proxy */ }
  }
  if (!blob) {
    const proxyUrl = `${PROXY}?file_url=${encodeURIComponent(url)}&filename=${encodeURIComponent(name)}`
    const res = await fetch(proxyUrl)
    if (!res.ok) throw new Error(`Download failed (${res.status})`)
    blob = await res.blob()
  }

  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = name
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(objectUrl)
}
