/**
 * EventAIModal
 * AI event creation for the merchant Events page — two modes:
 *   • "Describe Event" — type the event in plain words
 *   • "Upload Poster"  — attach up to 3 images of the SAME event poster
 * Results are shown as review cards; "Edit & Use" pre-fills the Event dialog.
 * For poster mode the uploaded poster is also used as the event image.
 */

import { useState, useEffect, useRef } from 'react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Sparkles, MessageSquareText, ImageIcon, Upload, X, RefreshCw,
  CalendarDays, Clock, MapPin, AlertCircle, ChevronRight, Repeat,
} from 'lucide-react'
import { useFrappePostCall } from '@/lib/frappe'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

export interface AIEvent {
  title: string
  description: string
  category: string
  date: string | null
  time: string
  end_time: string | null
  location: string
  registration_link: string | null
  featured: boolean
  repeat_this_event: boolean
  repeat_on: string | null
  repeat_till: string | null
  status: string
  is_active: number
  monday: number; tuesday: number; wednesday: number; thursday: number
  friday: number; saturday: number; sunday: number
  /** Filled client-side after uploading the poster. */
  image_src?: string
}

type Mode = 'prompt' | 'poster'

const MODES: { value: Mode; label: string; icon: React.ReactNode; hint: string }[] = [
  { value: 'prompt', label: 'Describe Event', icon: <MessageSquareText className="h-4 w-4" />, hint: 'Type the event in your own words — AI builds it.' },
  { value: 'poster', label: 'Upload Poster', icon: <ImageIcon className="h-4 w-4" />, hint: 'Attach your event poster — AI reads it and creates the event.' },
]

const MAX_POSTERS = 3

interface Props {
  open: boolean
  onClose: () => void
  restaurantId: string
  onUseEvent: (event: AIEvent) => void
}

const dayLabel = (e: AIEvent) => {
  const map: [keyof AIEvent, string][] = [
    ['monday', 'Mon'], ['tuesday', 'Tue'], ['wednesday', 'Wed'], ['thursday', 'Thu'],
    ['friday', 'Fri'], ['saturday', 'Sat'], ['sunday', 'Sun'],
  ]
  return map.filter(([k]) => e[k]).map(([, l]) => l).join(', ')
}

export default function EventAIModal({ open, onClose, restaurantId, onUseEvent }: Props) {
  const [mode, setMode] = useState<Mode>('prompt')
  const [userPrompt, setUserPrompt] = useState('')
  const [posterFiles, setPosterFiles] = useState<File[]>([])
  const [posterPreviews, setPosterPreviews] = useState<string[]>([])
  const [events, setEvents] = useState<AIEvent[]>([])
  const [hasGenerated, setHasGenerated] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { call: generate, loading } = useFrappePostCall(
    'flamezo_backend.flamezo.api.events.generate_event_suggestions'
  )

  // Always start clean: clear the previous prompt, poster and results so
  // reopening the modal never shows the last event's leftovers.
  useEffect(() => {
    if (!open) return
    setMode('prompt')
    setEvents([])
    setHasGenerated(false)
    setUserPrompt('')
    setPosterFiles([])
    setPosterPreviews([])
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [open])

  const switchMode = (next: Mode) => {
    if (next === mode) return
    setMode(next)
    setEvents([])
    setHasGenerated(false)
  }

  const handleFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (!files.length) return
    const remaining = MAX_POSTERS - posterFiles.length
    if (remaining <= 0) return toast.error(`You can attach up to ${MAX_POSTERS} images.`)
    const valid = files.filter(f => {
      if (!f.type.startsWith('image/')) { toast.error('Please choose image files.'); return false }
      if (f.size > 10 * 1024 * 1024) { toast.error('Image too large', { description: `"${f.name}" is over 10 MB.` }); return false }
      return true
    }).slice(0, remaining)
    valid.forEach(file => {
      const reader = new FileReader()
      reader.onloadend = () => {
        setPosterPreviews(prev => (prev.length >= MAX_POSTERS ? prev : [...prev, reader.result as string]))
      }
      reader.readAsDataURL(file)
    })
    setPosterFiles(prev => [...prev, ...valid].slice(0, MAX_POSTERS))
  }

  const removePoster = (idx: number) => {
    setPosterFiles(prev => prev.filter((_, i) => i !== idx))
    setPosterPreviews(prev => prev.filter((_, i) => i !== idx))
  }

  const handleGenerate = async () => {
    if (mode === 'prompt' && !userPrompt.trim()) {
      return toast.error('Describe the event first', { description: 'e.g. "Live ghazal night this Saturday 8pm, entry ₹499".' })
    }
    if (mode === 'poster' && posterPreviews.length === 0) {
      return toast.error('Attach your event poster first')
    }
    try {
      const res: any = await generate({
        restaurant_id: restaurantId,
        user_prompt: mode === 'prompt' ? userPrompt.trim() : null,
        poster_base64: mode === 'poster' ? JSON.stringify(posterPreviews) : null,
      })
      const payload = res?.message ?? res
      if (!payload?.success) {
        const code = payload?.error_code || payload?.error?.code
        toast.error(
          code === 'QUOTA_EXCEEDED' ? 'Monthly quota reached'
            : code === 'INSUFFICIENT_BALANCE' ? 'Insufficient wallet balance'
            : 'Could not create the event',
          { description: payload?.message || payload?.error?.message, duration: 6000 },
        )
        return
      }
      const data = payload.data ?? payload
      setEvents(data.events ?? [])
      setHasGenerated(true)
      if (data.coins_deducted > 0) {
        toast.info(`${data.coins_deducted} coins deducted`, { description: 'Paid generation — free quota exhausted.' })
      }
    } catch (err: any) {
      toast.error('Something went wrong', { description: err?.message })
    }
  }

  /** Upload the poster so it can be the event image, then hand the event back. */
  const handleUse = async (ev: AIEvent) => {
    if (mode === 'poster' && posterFiles[0]) {
      setUploading(true)
      try {
        const fd = new FormData()
        fd.append('file', posterFiles[0])
        fd.append('filename', posterFiles[0].name)
        fd.append('is_private', '0')
        const csrf = (window as any).frappe?.csrf_token || (window as any).csrf_token
        const r = await fetch('/api/method/upload_file', {
          method: 'POST', body: fd, headers: { 'X-Frappe-CSRF-Token': csrf },
        })
        const j = await r.json()
        const url = j?.message?.file_url
        if (url) ev = { ...ev, image_src: url }
        else toast.warning('Poster upload failed — add an image in the next step.')
      } catch {
        toast.warning('Poster upload failed — add an image in the next step.')
      } finally {
        setUploading(false)
      }
    }
    onUseEvent(ev)
    onClose()
    toast.success(`"${ev.title}" loaded — review and save.`)
  }

  const canGenerate = mode === 'prompt' ? !!userPrompt.trim() : posterPreviews.length > 0

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto p-0">
        <div className="sticky top-0 z-10 bg-background border-b px-6 py-4">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-xl">
              <Sparkles className="h-5 w-5 text-primary" />
              AI Event Creator
            </DialogTitle>
            <DialogDescription className="text-sm">
              {MODES.find(m => m.value === mode)?.hint}
            </DialogDescription>
          </DialogHeader>

          {/* Mode tabs */}
          <div className="mt-4 grid grid-cols-2 gap-2">
            {MODES.map(m => (
              <button
                key={m.value}
                type="button"
                onClick={() => switchMode(m.value)}
                className={cn(
                  'flex items-center justify-center gap-1.5 rounded-xl border-2 px-2 py-2 transition-all cursor-pointer',
                  mode === m.value
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border hover:border-muted-foreground/40 text-muted-foreground',
                )}
              >
                {m.icon}
                <span className="text-xs font-semibold">{m.label}</span>
              </button>
            ))}
          </div>

          {/* Describe Event */}
          {mode === 'prompt' && (
            <div className="mt-3 flex flex-col gap-1">
              <span className="text-xs text-muted-foreground font-medium">Describe your event</span>
              <textarea
                value={userPrompt}
                onChange={(e) => setUserPrompt(e.target.value)}
                rows={3}
                maxLength={500}
                placeholder='e.g. "Live ghazal night this Saturday 8pm on the rooftop, entry ₹499" or "Every Friday DJ night from 9pm"'
                className="w-full resize-none rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              />
              <span className="text-[11px] text-muted-foreground self-end">{userPrompt.length}/500</span>
            </div>
          )}

          {/* Upload Poster */}
          {mode === 'poster' && (
            <div className="mt-3">
              <input ref={fileInputRef} type="file" accept="image/*" multiple onChange={handleFiles} className="hidden" />
              {posterPreviews.length > 0 ? (
                <div className="flex flex-col gap-2">
                  <div className="grid grid-cols-3 gap-2">
                    {posterPreviews.map((src, i) => (
                      <div key={i} className="relative aspect-square rounded-lg border overflow-hidden bg-muted/30">
                        <img src={src} alt={`Poster ${i + 1}`} className="h-full w-full object-cover" />
                        <button type="button" onClick={() => removePoster(i)}
                          className="absolute top-1 right-1 rounded-full bg-background/90 border shadow p-0.5 hover:bg-muted">
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                    {posterPreviews.length < MAX_POSTERS && (
                      <button type="button" onClick={() => fileInputRef.current?.click()}
                        className="aspect-square flex flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-muted-foreground/30 hover:border-primary/50 text-muted-foreground transition-colors">
                        <Upload className="h-5 w-5 opacity-60" />
                        <span className="text-[11px] font-medium">Add more</span>
                      </button>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    {posterPreviews.length}/{MAX_POSTERS} · all should be the <strong>same event</strong>. The first image becomes the event photo.
                  </p>
                </div>
              ) : (
                <button type="button" onClick={() => fileInputRef.current?.click()}
                  className="w-full flex flex-col items-center gap-2 rounded-xl border-2 border-dashed border-muted-foreground/30 hover:border-primary/50 py-8 text-muted-foreground transition-colors">
                  <Upload className="h-7 w-7 opacity-50" />
                  <span className="text-sm font-medium">Click to upload your event poster (up to {MAX_POSTERS})</span>
                  <span className="text-xs opacity-70 text-center max-w-sm">PNG / JPG — the poster is read by AI <strong>and</strong> used as the event image.</span>
                </button>
              )}
            </div>
          )}

          <div className="mt-3 flex justify-end">
            <Button onClick={handleGenerate} disabled={loading || !canGenerate} className="gap-2 min-w-[170px]">
              {loading
                ? <><RefreshCw className="h-4 w-4 animate-spin" />{mode === 'poster' ? 'Reading poster…' : 'Creating…'}</>
                : hasGenerated
                  ? <><RefreshCw className="h-4 w-4" />Regenerate</>
                  : mode === 'poster'
                    ? <><ImageIcon className="h-4 w-4" />Read Poster & Create</>
                    : <><MessageSquareText className="h-4 w-4" />Create Event</>}
            </Button>
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-4">
          {!hasGenerated && !loading && (
            <div className="py-14 flex flex-col items-center gap-3 text-center text-muted-foreground">
              {mode === 'poster' ? <ImageIcon className="h-12 w-12 opacity-20" /> : <MessageSquareText className="h-12 w-12 opacity-20" />}
              <p className="text-sm font-medium">
                {mode === 'poster' ? 'Upload your event poster' : 'Describe the event you want'}
              </p>
              <p className="text-xs max-w-sm">
                {mode === 'poster'
                  ? 'The AI reads the poster and fills in the title, date, time and venue — and uses it as the event image.'
                  : 'Type it in plain words — the AI turns it into a ready-to-publish event.'}
              </p>
            </div>
          )}

          {loading && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {[0, 1].map(i => (
                <div key={i} className="rounded-xl border bg-card h-44 animate-pulse p-4 space-y-3">
                  <div className="h-4 bg-muted rounded w-2/3" />
                  <div className="h-3 bg-muted rounded w-full" />
                  <div className="h-3 bg-muted rounded w-4/5" />
                  <div className="h-8 bg-muted rounded mt-4" />
                </div>
              ))}
            </div>
          )}

          {hasGenerated && !loading && events.length > 0 && (
            <>
              <p className="text-sm font-medium mb-3">
                {events.length} event{events.length > 1 ? 's' : ''} ready
                <span className="ml-2 text-xs text-muted-foreground font-normal">— review and save</span>
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {events.map((ev, i) => (
                  <div key={i} className="rounded-xl border bg-card shadow-sm flex flex-col overflow-hidden">
                    <div className="h-1 w-full bg-primary" />
                    <div className="p-4 flex flex-col gap-2 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <p className="font-bold text-sm leading-snug">{ev.title}</p>
                        {ev.featured && <Badge className="text-[10px] shrink-0">Featured</Badge>}
                      </div>
                      <p className="text-xs text-muted-foreground line-clamp-2">{ev.description}</p>
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {ev.date && (
                          <span className="text-[11px] bg-muted rounded px-1.5 py-0.5 flex items-center gap-1">
                            <CalendarDays className="h-3 w-3" />{ev.date}
                          </span>
                        )}
                        <span className="text-[11px] bg-muted rounded px-1.5 py-0.5 flex items-center gap-1">
                          <Clock className="h-3 w-3" />{ev.time?.slice(0, 5)}{ev.end_time ? `–${ev.end_time.slice(0, 5)}` : ''}
                        </span>
                        {ev.location && (
                          <span className="text-[11px] bg-muted rounded px-1.5 py-0.5 flex items-center gap-1">
                            <MapPin className="h-3 w-3" />{ev.location}
                          </span>
                        )}
                        {ev.repeat_this_event && (
                          <span className="text-[11px] bg-muted rounded px-1.5 py-0.5 flex items-center gap-1">
                            <Repeat className="h-3 w-3" />{ev.repeat_on}{dayLabel(ev) ? ` · ${dayLabel(ev)}` : ''}
                          </span>
                        )}
                        {ev.category && <span className="text-[11px] bg-muted rounded px-1.5 py-0.5 capitalize">{ev.category}</span>}
                      </div>
                      <Button size="sm" variant="outline" className="w-full mt-auto gap-1.5"
                        disabled={uploading} onClick={() => handleUse(ev)}>
                        {uploading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : null}
                        Edit &amp; Use
                        <ChevronRight className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {hasGenerated && !loading && events.length === 0 && (
            <div className="py-12 flex flex-col items-center gap-2 text-muted-foreground">
              <AlertCircle className="h-8 w-8 opacity-40" />
              <p className="text-sm">Couldn&apos;t read an event. Try more detail or a clearer poster.</p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
