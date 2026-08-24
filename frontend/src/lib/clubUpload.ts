/**
 * Club Talks media upload — presign → direct PUT to R2.
 *
 * Mirrors the app's flow (request_club_post_upload → raw PUT → create_club_post
 * with the object key). No confirm step; the create endpoint resolves the key to
 * a public URL. Supports image AND video (the app is image-only).
 */

export type ClubMediaKind = 'image' | 'video'

export function clubMediaKind(file: File): ClubMediaKind {
  return file.type.startsWith('video/') || /\.(mp4|webm|mov|m4v|ogg)$/i.test(file.name) ? 'video' : 'image'
}

function safeContentType(file: File, kind: ClubMediaKind): string {
  if (file.type) return file.type
  return kind === 'video' ? 'video/mp4' : 'image/jpeg'
}

/**
 * Upload one file for a club post. `requestUpload` is the bound
 * useFrappePostCall for merchant_clubs.merchant_request_upload.
 * Returns the R2 object key + kind to hand to merchant_create_post.
 */
export async function uploadClubMedia(
  outletId: string,
  file: File,
  requestUpload: (args: Record<string, unknown>) => Promise<any>,
): Promise<{ objectKey: string; kind: ClubMediaKind }> {
  const kind = clubMediaKind(file)
  const contentType = safeContentType(file, kind)

  const res: any = await requestUpload({
    outlet_id: outletId,
    filename: file.name || `post.${kind === 'video' ? 'mp4' : 'jpg'}`,
    content_type: contentType,
  })
  const body = res?.message || res
  const data = body?.data || body
  if (!data?.upload_url || !data?.object_key) throw new Error('Could not start upload')

  const put = await fetch(data.upload_url, {
    method: 'PUT',
    headers: { 'Content-Type': contentType },
    body: file,
  })
  if (!put.ok) throw new Error(`Upload failed (${put.status})`)

  return { objectKey: data.object_key, kind }
}
