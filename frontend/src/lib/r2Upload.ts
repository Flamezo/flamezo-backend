/**
 * R2 Direct Upload Utility
 * Handles direct upload to Cloudflare R2 via Media Asset API
 */

interface UploadSessionResponse {
  upload_id: string
  object_key: string
  upload_url: string
  headers: Record<string, string>
  expires_in: number
}

interface ConfirmUploadResponse {
  name: string
  media_id: string
  status: string
  primary_url: string
  message?: string
}

interface R2UploadOptions {
  ownerDoctype: string
  ownerName: string
  mediaRole: string
  file: File
  altText?: string
  caption?: string
  displayOrder?: number
}

/**
 * Upload file directly to R2 and create Media Asset
 */
export async function uploadToR2(options: R2UploadOptions): Promise<ConfirmUploadResponse> {
  const { ownerDoctype, ownerName, mediaRole, file, altText, caption, displayOrder } = options

  const csrf = (window as any).frappe?.csrf_token || (window as any).csrf_token

  try {
    // Step 1: Request upload session
    const sessionRes = await fetch('/api/method/flamezo_backend.flamezo.media.api.request_upload_session', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': csrf,
      },
      body: JSON.stringify({
        owner_doctype: ownerDoctype,
        owner_name: ownerName,
        media_role: mediaRole,
        filename: file.name,
        content_type: file.type,
        size_bytes: file.size,
      }),
    })

    if (!sessionRes.ok) {
      const error = await sessionRes.json()
      console.error('CDN Upload - Session request failed:', error)
      throw new Error(error.message || 'Failed to request upload session')
    }

    const sessionJson = await sessionRes.json()
    const session: UploadSessionResponse = sessionJson.message

    if (!session?.upload_url) {
      console.error('CDN Upload - Invalid session response:', sessionJson)
      throw new Error('Invalid upload session response')
    }


    // Step 2: Direct upload to R2 (presigned PUT)
    const putRes = await fetch(session.upload_url, {
      method: 'PUT',
      headers: {
        ...(session.headers || {}),
      },
      body: file,
    })

    if (!putRes.ok) {
      console.error('CDN Upload - R2 upload failed:', putRes.status, putRes.statusText)
      throw new Error(`R2 upload failed: ${putRes.status}`)
    }


    // Step 3: Confirm upload (creates Media Asset + enqueues processing)
    const confirmRes = await fetch('/api/method/flamezo_backend.flamezo.media.api.confirm_upload', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': csrf,
      },
      body: JSON.stringify({
        upload_id: session.upload_id,
        owner_doctype: ownerDoctype,
        owner_name: ownerName,
        media_role: mediaRole,
        alt_text: altText || '',
        caption: caption || '',
        display_order: displayOrder || 0,
      }),
    })

    if (!confirmRes.ok) {
      const error = await confirmRes.json()
      console.error('CDN Upload - Confirm upload failed:', error)
      throw new Error(error.message || 'Confirm upload failed')
    }

    const confirmJson = await confirmRes.json()
    
    const result = confirmJson.message
    
    if (!result || !result.primary_url) {
      console.error('CDN Upload - Invalid confirm response:', confirmJson)
      throw new Error('Invalid confirm upload response')
    }
    
    return result
  } catch (error: any) {
    console.error('CDN Upload - Complete error:', error)
    throw error
  }
}

/**
 * Determine media type from file
 */
export function getMediaType(file: File): 'image' | 'video' {
  const videoExtensions = ['mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv', 'flv', 'wmv']
  const extension = file.name.split('.').pop()?.toLowerCase() || ''

  if (file.type.startsWith('video/') || videoExtensions.includes(extension)) {
    return 'video'
  }
  return 'image'
}
