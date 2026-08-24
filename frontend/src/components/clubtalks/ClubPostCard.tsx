import { useState } from 'react'
import { Flame, MessageCircle, Eye, Send, MoreHorizontal, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

/** Crimson accent — matches the app's Club Talks (#E23744). */
const ACCENT = '#E23744'

export interface ClubPost {
  id: string
  club_id: string
  post_type: 'text' | 'image' | 'video' | 'chills'
  content: string
  image_url?: string
  video_url?: string
  chills?: { videoUrl: string; thumbnail: string }
  likes_count: number
  comments_count: number
  views_count: number
  is_liked: boolean
  created_at: string
  club_name?: string
  creator_name?: string
  creator_image?: string
  is_mine?: boolean
  nicheTags?: string[]
  customTags?: string[]
  location?: { name: string; lat?: number; lng?: number; radius?: number } | null
  tagged_outlets?: Array<{ id?: string; name?: string; outlet_name?: string; image?: string; logo?: string }>
}

const fmt = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k` : `${n || 0}`)

function relativeTime(s?: string): string {
  if (!s) return ''
  const t = new Date(s.replace(' ', 'T')).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Math.max(0, Date.now() - t) / 1000
  if (diff < 60) return 'now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`
  if (diff < 604800) return `${Math.floor(diff / 86400)}d`
  return new Date(s.replace(' ', 'T')).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
}

function initials(name?: string): string {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  return (parts[0][0] + (parts[1]?.[0] || '')).toUpperCase()
}

/** Caption with #hashtags tinted in the accent color. */
function Caption({ text }: { text: string }) {
  if (!text) return null
  return (
    <p className="px-4 pt-2.5 pb-1 text-[15px] leading-relaxed text-foreground whitespace-pre-wrap break-words">
      {text.split(/(\s+)/).map((w, i) =>
        w.startsWith('#') ? <span key={i} className="font-bold" style={{ color: ACCENT }}>{w}</span> : w,
      )}
    </p>
  )
}

function ReactBtn({ icon, label, active, onClick }: { icon: React.ReactNode; label?: string; active?: boolean; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={cn('inline-flex items-center gap-1.5 text-[15px] font-medium transition-colors',
        onClick && 'hover:opacity-70', !onClick && 'cursor-default')}
      style={active ? { color: ACCENT } : undefined}
    >
      {icon}
      {label !== undefined && <span className={cn(!active && 'text-muted-foreground')}>{label}</span>}
    </button>
  )
}

interface Props {
  post: ClubPost
  onLike: (post: ClubPost) => void
  onComment: (post: ClubPost) => void
  onShare: (post: ClubPost) => void
  onDelete?: (post: ClubPost) => void
}

export default function ClubPostCard({ post, onLike, onComment, onShare, onDelete }: Props) {
  const [menuOpen, setMenuOpen] = useState(false)
  const isVideo = post.post_type === 'video' || !!post.chills?.videoUrl
  const mediaUrl = post.video_url || post.chills?.videoUrl || post.image_url

  return (
    <div className="relative flex flex-col border-b border-border pb-3">
      {/* header */}
      <div className="flex items-center gap-3 px-4 pt-3 pb-2">
        <div className="h-10 w-10 shrink-0 rounded-full flex items-center justify-center text-sm font-bold text-white overflow-hidden"
          style={{ backgroundColor: ACCENT }}>
          {post.creator_image ? <img src={post.creator_image} alt="" className="h-full w-full object-cover" /> : initials(post.creator_name || post.club_name)}
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-bold text-sm text-foreground truncate">{post.creator_name || post.club_name || 'Creator'}</p>
          {post.created_at && <p className="text-[11px] text-muted-foreground">{relativeTime(post.created_at)}</p>}
        </div>
        {post.is_mine && onDelete && (
          <div className="relative">
            <button onClick={() => setMenuOpen(v => !v)} className="p-1 text-muted-foreground hover:text-foreground">
              <MoreHorizontal className="h-[18px] w-[18px]" />
            </button>
            {menuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                <div className="absolute right-0 top-7 z-20 w-40 rounded-lg border bg-popover shadow-md py-1">
                  <button
                    onClick={() => { setMenuOpen(false); onDelete(post) }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
                  >
                    <Trash2 className="h-4 w-4" /> Delete post
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* media — capped to a phone-like size (like the Flutter app's 4:3 column) */}
      {mediaUrl && (
        <div className="mx-4 mb-1 w-[min(100%,320px)] overflow-hidden rounded-xl bg-muted" style={{ aspectRatio: '4 / 3' }}>
          {isVideo
            ? <video src={mediaUrl} controls playsInline preload="metadata" className="h-full w-full object-cover bg-black" />
            : <img src={mediaUrl} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover" />}
        </div>
      )}

      <Caption text={post.content} />

      {/* reaction bar */}
      <div className="flex items-center gap-5 px-4 pt-2">
        <ReactBtn
          icon={<Flame className="h-[22px] w-[22px]" fill={post.is_liked ? ACCENT : 'none'} />}
          label={fmt(post.likes_count)} active={post.is_liked} onClick={() => onLike(post)}
        />
        <ReactBtn icon={<MessageCircle className="h-[22px] w-[22px]" />} label={fmt(post.comments_count)} onClick={() => onComment(post)} />
        <ReactBtn icon={<Eye className="h-[22px] w-[22px]" />} label={fmt(post.views_count)} />
        <div className="ml-auto">
          <ReactBtn icon={<Send className="h-[22px] w-[22px]" />} onClick={() => onShare(post)} />
        </div>
      </div>
    </div>
  )
}
