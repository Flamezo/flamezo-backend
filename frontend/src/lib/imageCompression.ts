/**
 * Client-side image compression for mobile upload reliability
 *
 * Solves multiple mobile-upload issues at once:
 *  - HEIC/HEIF photos from iPhones → normalized to JPEG
 *  - Large 10-15 MB camera photos → compressed to < 2 MB
 *  - Empty/wrong file.type on some mobile browsers → forced to image/jpeg
 *  - Faster uploads on slow mobile connections
 */

/** Max pixel dimension (width or height). Larger images are downscaled proportionally. */
const MAX_DIMENSION = 2048

/** JPEG quality (0-1). 0.82 gives a good quality/size balance for food photos. */
const JPEG_QUALITY = 0.82

/** Skip compression for files already below this size (bytes). */
const SKIP_THRESHOLD = 500 * 1024 // 500 KB

/**
 * Compress an image File for upload.
 *
 * - Decodes the image (including HEIC on supported browsers via <img>)
 * - Downscales to MAX_DIMENSION if larger
 * - Re-encodes as JPEG
 * - Returns a new File with correct name, type, and size
 *
 * Falls back to the original file if compression fails (e.g. corrupt image).
 */
export async function compressImage(file: File): Promise<File> {
  // Skip non-image or already-small files
  if (file.size <= SKIP_THRESHOLD && file.type === 'image/jpeg') {
    return file
  }

  // Skip videos entirely (check both MIME type and extension for Android empty-type case)
  const ext = file.name.split('.').pop()?.toLowerCase() || ''
  const videoExts = ['mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv', 'flv', 'wmv']
  if (file.type.startsWith('video/') || videoExts.includes(ext)) {
    return file
  }

  try {
    const bitmap = await createImageBitmapFromFile(file)
    const { width, height } = getScaledDimensions(bitmap.width, bitmap.height, MAX_DIMENSION)

    const canvas = new OffscreenCanvas(width, height)
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('No 2d context')

    ctx.drawImage(bitmap, 0, 0, width, height)
    bitmap.close()

    const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: JPEG_QUALITY })

    // Build a filename ending in .jpg
    const baseName = file.name.replace(/\.[^.]+$/, '')
    const compressedFile = new File([blob], `${baseName}.jpg`, {
      type: 'image/jpeg',
      lastModified: Date.now(),
    })

    return compressedFile
  } catch {
    // Fallback: try the canvas element approach (wider browser support)
    return compressImageFallback(file)
  }
}

/**
 * Fallback compression using HTMLCanvasElement for browsers without OffscreenCanvas.
 */
async function compressImageFallback(file: File): Promise<File> {
  try {
    const url = URL.createObjectURL(file)
    const img = await loadImage(url)
    URL.revokeObjectURL(url)

    const { width, height } = getScaledDimensions(img.naturalWidth, img.naturalHeight, MAX_DIMENSION)

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height

    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('No 2d context')

    ctx.drawImage(img, 0, 0, width, height)

    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (b) => (b ? resolve(b) : reject(new Error('toBlob failed'))),
        'image/jpeg',
        JPEG_QUALITY,
      )
    })

    const baseName = file.name.replace(/\.[^.]+$/, '')
    return new File([blob], `${baseName}.jpg`, {
      type: 'image/jpeg',
      lastModified: Date.now(),
    })
  } catch {
    // If even the fallback fails, return original file unchanged
    return file
  }
}

function createImageBitmapFromFile(file: File): Promise<ImageBitmap> {
  return createImageBitmap(file)
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('Image load failed'))
    img.src = src
  })
}

function getScaledDimensions(
  srcW: number,
  srcH: number,
  maxDim: number,
): { width: number; height: number } {
  if (srcW <= maxDim && srcH <= maxDim) {
    return { width: srcW, height: srcH }
  }

  const ratio = Math.min(maxDim / srcW, maxDim / srcH)
  return {
    width: Math.round(srcW * ratio),
    height: Math.round(srcH * ratio),
  }
}

/**
 * Infer a safe content type from a File.
 * Mobile browsers sometimes report empty or wrong types.
 */
export function getSafeContentType(file: File): string {
  if (file.type && file.type.startsWith('image/') && file.type !== 'image/heic' && file.type !== 'image/heif') {
    return file.type
  }

  const ext = file.name.split('.').pop()?.toLowerCase() || ''
  const map: Record<string, string> = {
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    png: 'image/png',
    webp: 'image/webp',
    gif: 'image/gif',
    heic: 'image/jpeg', // will be converted by compressImage
    heif: 'image/jpeg',
    mp4: 'video/mp4',
    mov: 'video/quicktime',
    webm: 'video/webm',
  }

  return map[ext] || file.type || 'image/jpeg'
}
