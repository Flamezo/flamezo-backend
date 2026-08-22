import { useEffect, useState, useCallback } from 'react'
import { Loader2, Trash2, Eye, Heart, MessageCircle, MapPin, Users2, Share2 } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useFrappePostCall } from '@/lib/frappe'
import { toast } from 'sonner'
import type { ClubPost } from './ClubPostCard'

const ACCENT = '#E23744'
const PAGE = 'flamezo_backend.flamezo.api.merchant_clubs'

interface Comment { id: string; author_name: string; content: string; created_at: string }

function initials(name?: string) {
  const p = (name || '').trim().split(/\s+/).filter(Boolean)
  return p.length ? (p[0][0] + (p[1]?.[0] || '')).toUpperCase() : '?'
}
function relTime(s?: string) {
  if (!s) return ''
  const t = new Date(s.replace(' ', 'T')).getTime()
  if (Number.isNaN(t)) return ''
  const d = Math.max(0, Date.now() - t) / 1000
  if (d < 60) return 'now'
  if (d < 3600) return `${Math.floor(d / 60)}m`
  if (d < 86400) return `${Math.floor(d / 3600)}h`
  return `${Math.floor(d / 86400)}d`
}

interface Props {
  outletId: string
  post: ClubPost | null
  onClose: () => void
  onDelete?: (post: ClubPost) => void
  onCommentDelta?: (postId: string, delta: number) => void
}

export default function ClubPostDetail({ outletId, post, onClose, onDelete, onCommentDelta }: Props) {
  const [comments, setComments] = useState<Comment[]>([])
  const [loading, setLoading] = useState(false)
  const { call: getComments } = useFrappePostCall(`${PAGE}.merchant_get_comments`)
  const { call: deleteComment } = useFrappePostCall(`${PAGE}.merchant_delete_comment`)

  const load = useCallback(async () => {
    if (!post) return
    setLoading(true)
    try {
      const res: any = await getComments({ outlet_id: outletId, post_id: post.id, limit: 50 })
      setComments((res?.message || res)?.data?.comments || [])
    } catch { /* silent */ } finally { setLoading(false) }
  }, [post, outletId, getComments])

  useEffect(() => { if (post) load() }, [post, load])

  const removeComment = async (c: Comment) => {
    if (!post) return
    const prev = comments
    setComments(cs => cs.filter(x => x.id !== c.id))
    try { await deleteComment({ outlet_id: outletId, comment_id: c.id }); onCommentDelta?.(post.id, -1) }
    catch (e: any) { setComments(prev); toast.error(e.message || 'Could not delete comment') }
  }

  if (!post) return null
  const isVideo = post.post_type === 'video' || !!post.chills?.videoUrl
  const mediaUrl = post.video_url || post.chills?.videoUrl || post.image_url
  const collaborators = post.tagged_outlets || []

  return (
    <Dialog open={!!post} onOpenChange={o => !o && onClose()}>
      <DialogContent className="sm:max-w-[560px] max-h-[90vh] overflow-y-auto p-0">
        {/* header */}
        <DialogHeader className="px-4 pt-4 pb-2">
          <DialogTitle className="flex items-center gap-3">
            <div className="h-9 w-9 shrink-0 rounded-full flex items-center justify-center text-xs font-bold text-white overflow-hidden" style={{ backgroundColor: ACCENT }}>
              {post.creator_image ? <img src={post.creator_image} alt="" className="h-full w-full object-cover" /> : initials(post.creator_name)}
            </div>
            <div className="min-w-0">
              <p className="font-bold text-sm truncate">{post.creator_name || 'Creator'}</p>
              <p className="text-[11px] font-normal text-muted-foreground">{relTime(post.created_at)}</p>
            </div>
          </DialogTitle>
        </DialogHeader>

        {/* media */}
        {mediaUrl && (
          <div className="bg-black">
            {isVideo
              ? <video src={mediaUrl} controls playsInline className="w-full max-h-[50vh] object-contain bg-black" />
              : <img src={mediaUrl} alt="" className="w-full max-h-[50vh] object-contain" />}
          </div>
        )}

        <div className="px-4 pb-4 space-y-3">
          {post.content && <p className="text-[15px] leading-relaxed whitespace-pre-wrap break-words">{post.content}</p>}

          {/* tags */}
          {((post.nicheTags?.length || 0) + (post.customTags?.length || 0)) > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {(post.nicheTags || []).map(t => <span key={t} className="rounded-full bg-primary/10 border border-primary/20 px-2 py-0.5 text-[11px] font-medium text-primary">{t}</span>)}
              {(post.customTags || []).map(t => <span key={t} className="rounded-full bg-muted border px-2 py-0.5 text-[11px] font-medium">{t}</span>)}
            </div>
          )}

          {/* location */}
          {post.location?.name && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <MapPin className="h-3.5 w-3.5 shrink-0" /> <span className="truncate">{post.location.name}</span>
            </div>
          )}

          {/* collaborators */}
          {collaborators.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground mb-1.5">
                <Users2 className="h-3.5 w-3.5" /> Collaborators
              </div>
              <div className="flex flex-wrap gap-2">
                {collaborators.map((o, i) => (
                  <span key={o.id || o.name || i} className="inline-flex items-center gap-1.5 rounded-full border bg-card pl-1 pr-2.5 py-0.5">
                    <span className="h-5 w-5 rounded-full overflow-hidden bg-muted flex items-center justify-center text-[9px] font-bold">
                      {(o.image || o.logo) ? <img src={o.image || o.logo} alt="" className="h-full w-full object-cover" /> : initials(o.outlet_name || o.name)}
                    </span>
                    <span className="text-[12px] font-medium">{o.outlet_name || o.name}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* stats */}
          <div className="flex items-center gap-4 text-sm text-muted-foreground border-y py-2">
            <span className="inline-flex items-center gap-1.5"><Eye className="h-4 w-4" /> {post.views_count || 0}</span>
            <span className="inline-flex items-center gap-1.5"><Heart className="h-4 w-4" /> {post.likes_count || 0}</span>
            <span className="inline-flex items-center gap-1.5"><MessageCircle className="h-4 w-4" /> {post.comments_count || 0}</span>
            <Button variant="ghost" size="sm" className="ml-auto h-7"
              onClick={async () => {
                const url = `https://flamezo.in/club/${post.club_id}`
                const text = `${post.content ? post.content + '\n\n' : ''}via ${post.club_name || 'Flamezo'} 🔥\n${url}`
                try { if (navigator.share) await navigator.share({ text }); else { await navigator.clipboard.writeText(text); toast.success('Link copied') } } catch { /* dismissed */ }
              }}>
              <Share2 className="h-4 w-4 mr-1" /> Share
            </Button>
            {onDelete && post.is_mine && (
              <Button variant="ghost" size="sm" className="text-red-600 hover:text-red-700 h-7"
                onClick={() => { onClose(); onDelete(post) }}>
                <Trash2 className="h-4 w-4 mr-1" /> Delete
              </Button>
            )}
          </div>

          {/* comments */}
          <div>
            <p className="text-xs font-semibold text-muted-foreground mb-2">Comments</p>
            {loading ? (
              <div className="py-6 text-center"><Loader2 className="h-4 w-4 animate-spin mx-auto text-muted-foreground" /></div>
            ) : comments.length === 0 ? (
              <p className="text-sm text-muted-foreground py-3">No comments yet.</p>
            ) : (
              <div className="space-y-3">
                {comments.map(c => (
                  <div key={c.id} className="flex gap-2.5">
                    <div className="h-7 w-7 shrink-0 rounded-full flex items-center justify-center text-[10px] font-bold text-white" style={{ backgroundColor: ACCENT }}>{initials(c.author_name)}</div>
                    <div className="min-w-0 flex-1">
                      <span className="text-xs font-bold">{c.author_name || 'User'}</span>
                      <span className="text-[10px] text-muted-foreground ml-2">{relTime(c.created_at)}</span>
                      <p className="text-[13px] leading-snug break-words">{c.content}</p>
                    </div>
                    <button onClick={() => removeComment(c)} className="text-muted-foreground hover:text-red-600 shrink-0"><Trash2 className="h-3.5 w-3.5" /></button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
