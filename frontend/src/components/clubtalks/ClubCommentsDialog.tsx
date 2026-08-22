import { useEffect, useState, useCallback } from 'react'
import { Loader2, Trash2, MessageCircle } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useFrappePostCall } from '@/lib/frappe'
import { toast } from 'sonner'
import type { ClubPost } from './ClubPostCard'

const ACCENT = '#E23744'

interface Comment {
  id: string
  author_id: string
  author_name: string
  content: string
  created_at: string
}

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
  onCountChange?: (postId: string, delta: number) => void
}

export default function ClubCommentsDialog({ outletId, post, onClose, onCountChange }: Props) {
  const [comments, setComments] = useState<Comment[]>([])
  const [loading, setLoading] = useState(false)
  const { call: getComments } = useFrappePostCall('flamezo_backend.flamezo.api.merchant_clubs.merchant_get_comments')
  const { call: deleteComment } = useFrappePostCall('flamezo_backend.flamezo.api.merchant_clubs.merchant_delete_comment')

  const load = useCallback(async () => {
    if (!post) return
    setLoading(true)
    try {
      const res: any = await getComments({ outlet_id: outletId, post_id: post.id, limit: 50 })
      const body = res?.message || res
      setComments(body?.data?.comments || [])
    } catch (e: any) {
      toast.error(e.message || 'Could not load comments')
    } finally {
      setLoading(false)
    }
  }, [post, outletId, getComments])

  useEffect(() => { if (post) load() }, [post, load])

  const remove = async (c: Comment) => {
    if (!post) return
    const prev = comments
    setComments(cs => cs.filter(x => x.id !== c.id))
    try {
      await deleteComment({ outlet_id: outletId, comment_id: c.id })
      onCountChange?.(post.id, -1)
    } catch (e: any) {
      setComments(prev)
      toast.error(e.message || 'Could not delete comment')
    }
  }

  return (
    <Dialog open={!!post} onOpenChange={o => !o && onClose()}>
      <DialogContent className="sm:max-w-[480px] max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Comments{comments.length ? ` · ${comments.length}` : ''}</DialogTitle>
        </DialogHeader>
        <div className="flex-1 overflow-y-auto -mx-2 px-2">
          {loading ? (
            <div className="py-12 text-center"><Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" /></div>
          ) : comments.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              <MessageCircle className="h-8 w-8 mx-auto mb-2 opacity-30" />
              No comments yet.
            </div>
          ) : (
            <div className="space-y-4 py-2">
              {comments.map(c => (
                <div key={c.id} className="flex gap-3">
                  <div className="h-8 w-8 shrink-0 rounded-full flex items-center justify-center text-xs font-bold text-white"
                    style={{ backgroundColor: ACCENT }}>{initials(c.author_name)}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-foreground">{c.author_name || 'User'}</span>
                      <span className="text-[10px] text-muted-foreground">{relTime(c.created_at)}</span>
                    </div>
                    <p className="text-[13px] text-foreground/90 leading-snug break-words">{c.content}</p>
                  </div>
                  {post?.is_mine && (
                    <button onClick={() => remove(c)} className="text-muted-foreground hover:text-red-600 shrink-0">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
