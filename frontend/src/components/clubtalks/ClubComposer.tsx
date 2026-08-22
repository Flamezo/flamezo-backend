import { useRef, useState, useEffect } from 'react'
import { ImagePlus, Send, X, Loader2, Film } from 'lucide-react'
import { cn } from '@/lib/utils'
import { clubMediaKind } from '@/lib/clubUpload'

const ACCENT = '#E23744'

interface Props {
  /** Publishes the post. Returns a promise; composer clears on success. */
  onPost: (args: { content: string; file: File | null }) => Promise<void>
  disabled?: boolean
}

/** WhatsApp-channel style composer: pick image/video + write + broadcast. */
export default function ClubComposer({ onPost, disabled }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    if (!file) { setPreviewUrl(null); return }
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const isVideo = file ? clubMediaKind(file) === 'video' : false
  const canSend = !sending && !disabled && (text.trim().length > 0 || !!file)

  const send = async () => {
    if (!canSend) return
    setSending(true)
    try {
      await onPost({ content: text.trim(), file })
      setText('')
      setFile(null)
      if (fileRef.current) fileRef.current.value = ''
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="border-t bg-card px-3 py-2.5">
      {previewUrl && (
        <div className="relative mb-2 inline-block">
          {isVideo
            ? <video src={previewUrl} muted className="h-20 w-20 rounded-xl object-cover border" />
            : <img src={previewUrl} alt="" className="h-20 w-20 rounded-xl object-cover border" />}
          {isVideo && <Film className="absolute bottom-1 left-1 h-4 w-4 text-white drop-shadow" />}
          <button
            onClick={() => { setFile(null); if (fileRef.current) fileRef.current.value = '' }}
            className="absolute -right-2 -top-2 rounded-full bg-black/80 p-1 text-white"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      )}
      <div className="flex items-end gap-2">
        <button
          onClick={() => fileRef.current?.click()}
          disabled={sending || disabled}
          className="p-2 text-muted-foreground hover:text-foreground disabled:opacity-40"
          title="Add image or video"
        >
          <ImagePlus className="h-6 w-6" />
        </button>
        <input
          ref={fileRef} type="file" accept="image/*,video/*" className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) setFile(f) }}
        />
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          placeholder="Broadcast to your followers…"
          rows={1}
          className="flex-1 resize-none rounded-[22px] border bg-muted/40 px-4 py-2.5 text-sm outline-none focus:ring-1 focus:ring-ring max-h-28"
        />
        <button
          onClick={send}
          disabled={!canSend}
          className={cn('flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-white transition-opacity',
            !canSend && 'opacity-40')}
          style={{ backgroundColor: ACCENT }}
        >
          {sending ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
        </button>
      </div>
    </div>
  )
}
