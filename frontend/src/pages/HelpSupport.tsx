import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useOutlet } from '@/contexts/OutletContext'
import { useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from 'sonner'
import { ArrowLeft, BellRing, LifeBuoy, MessageSquare, Phone, Plus, Send } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useFillViewportHeight } from '@/hooks/useFillViewportHeight'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { SupportMessageList, fmtTime, type SupportMessage as Message } from '@/components/support/SupportMessageList'

/**
 * Help & Support — the merchant's side of support chat.
 *
 * Backed by api/support.py's merchant_* endpoints: the caller is the logged-in
 * Frappe user and every thread is scoped to the selected outlet, using the
 * same outlet-access check every other merchant API uses. Replies arrive via
 * an 8-second long-poll (see support.poll for why not a socket).
 *
 * Can be opened pre-filled from anywhere in the dashboard:
 *   /help-support?category=settlement&area=payments&ctx_doctype=Order&ctx_name=ORD-1
 */

const API = 'flamezo_backend.flamezo.api.support'

type Thread = {
  thread_id: string
  status: string
  category: string
  subject: string
  app_area: string
  agent_name: string
  unread_count: number
  last_message_at: string
  last_message_preview: string
  reply_due_at: string
  escalated: boolean
  can_escalate: boolean
  can_request_update: boolean
}

// "10 Sep, 4:30 pm" — the promised reply time, in the merchant's clock.
const fmtDue = (s: string) =>
  new Date(s.replace(' ', 'T')).toLocaleString([], { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })

// Merchant-side categories. Money and onboarding lead, because those are the
// ones where every hour unanswered is revenue the outlet is missing.
const CATEGORIES = [
  { key: 'settlement', label: 'Settlement / payout' },
  { key: 'kyc', label: 'KYC & onboarding' },
  { key: 'commission', label: 'Commission & fees' },
  { key: 'menu', label: 'Menu & offers' },
  { key: 'profile', label: 'Outlet profile' },
  { key: 'creator', label: 'Creator collabs' },
  { key: 'account', label: 'Account & access' },
  { key: 'other', label: 'Something else' },
]

const categoryLabel = (key: string) => CATEGORIES.find((c) => c.key === key)?.label ?? 'Support'

// Plain language for the merchant — never the internal state names.
const STATUS_LABEL: Record<string, string> = {
  open: "We're on it",
  awaiting_agent: "We're on it",
  awaiting_customer: 'Waiting on you',
  resolved: 'Resolved',
  closed: 'Closed',
}

const unwrap = (res: any) => (res?.message || res)?.data


export default function HelpSupport() {
  const { selectedOutlet } = useOutlet()
  const [params, setParams] = useSearchParams()

  const [threads, setThreads] = useState<Thread[]>([])
  const [loadingList, setLoadingList] = useState(true)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loadingThread, setLoadingThread] = useState(false)
  const [pollThread, setPollThread] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)

  const [composing, setComposing] = useState(false)
  const [newCategory, setNewCategory] = useState<string>('')
  const [newMessage, setNewMessage] = useState('')
  const [newSubject, setNewSubject] = useState('')
  const [callback, setCallback] = useState(false)
  const [callbackTime, setCallbackTime] = useState('Anytime')
  const [listFilter, setListFilter] = useState<'all' | 'open' | 'resolved'>('all')
  const [starting, setStarting] = useState(false)

  const cursorRef = useRef<string | null>(null)
  const chatRef = useRef<HTMLDivElement | null>(null)
  const [fillRef, fillHeight] = useFillViewportHeight()

  const { call: listThreads } = useFrappePostCall(`${API}.merchant_list_threads`)
  const { call: getMessages } = useFrappePostCall(`${API}.merchant_get_messages`)
  const { call: pollMessages } = useFrappePostCall(`${API}.merchant_poll_messages`)
  const { call: sendMessage } = useFrappePostCall(`${API}.merchant_send_message`)
  const { call: markRead } = useFrappePostCall(`${API}.merchant_mark_read`)
  const { call: requestUpdate } = useFrappePostCall(`${API}.merchant_request_update`)
  const { call: startThread } = useFrappePostCall(`${API}.merchant_start_thread`)

  const active = threads.find((t) => t.thread_id === activeId) ?? null

  const refreshList = useCallback(async () => {
    if (!selectedOutlet) return
    try {
      const res = await listThreads({ outlet_id: selectedOutlet, page: 1, limit: 50 })
      setThreads(unwrap(res)?.threads || [])
    } catch (e: any) {
      toast.error(e?.message || 'Could not load your support requests')
    } finally {
      setLoadingList(false)
    }
  }, [selectedOutlet, listThreads])

  // Switching outlet starts clean — tickets belong to one outlet.
  useEffect(() => {
    setActiveId(null)
    setPollThread(null)
    setMessages([])
    setLoadingList(true)
    refreshList()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedOutlet])

  // Keep the list (statuses, unread counts, new replies on other tickets)
  // current without a page refresh. Skipped while the tab is hidden.
  useEffect(() => {
    const t = setInterval(() => {
      if (document.visibilityState === 'visible') refreshList()
    }, 15000)
    return () => clearInterval(t)
  }, [refreshList])

  // Arriving from a "Get help" button elsewhere: open the form pre-filled.
  useEffect(() => {
    const cat = params.get('category')
    if (cat) {
      setNewCategory(CATEGORIES.some((c) => c.key === cat) ? cat : 'other')
      setComposing(true)
      setActiveId(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Scroll the chat box itself — scrollIntoView would also scroll the whole
  // page, shifting both panels up.
  const scrollToEnd = () =>
    requestAnimationFrame(() => {
      const el = chatRef.current
      if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    })

  const openThread = useCallback(
    async (id: string) => {
      setComposing(false)
      setActiveId(id)
      setPollThread(null)
      setMessages([])
      setLoadingThread(true)
      cursorRef.current = null
      try {
        const res = await getMessages({ thread_id: id, limit: 50 })
        const msgs: Message[] = unwrap(res)?.messages || []
        setMessages(msgs)
        cursorRef.current = msgs.length ? msgs[msgs.length - 1].id : null
        markRead({ thread_id: id }).catch(() => {})
        scrollToEnd()
        // Poll only once history is in place, so a reply landing mid-load
        // can't be overwritten by the initial page.
        setPollThread(id)
        refreshList()
      } catch (e: any) {
        toast.error(e?.message || "This conversation isn't available")
        setActiveId(null)
      } finally {
        setLoadingThread(false)
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [getMessages, markRead, refreshList],
  )

  // Long-poll loop for the open thread. Re-issues immediately after each
  // return; backs off on errors so an outage doesn't hot-loop the server.
  useEffect(() => {
    if (!pollThread) return
    let cancelled = false
    const run = async () => {
      while (!cancelled) {
        try {
          const res = await pollMessages({
            thread_id: pollThread,
            ...(cursorRef.current ? { after_id: cursorRef.current } : {}),
          })
          if (cancelled) break
          const fresh: Message[] = unwrap(res)?.messages || []
          if (fresh.length) {
            setMessages((prev) => {
              const ids = new Set(fresh.map((m) => m.id))
              // Same order a reload gives (by when each message happened): a
              // slow request can deliver an older message after a newer one.
              return [...prev.filter((m) => !ids.has(m.id)), ...fresh].sort((a, b) =>
                a.created_at.localeCompare(b.created_at),
              )
            })
            cursorRef.current = fresh[fresh.length - 1].id
            scrollToEnd()
            if (fresh.some((m) => m.sender_type !== 'customer')) {
              markRead({ thread_id: pollThread }).catch(() => {})
              refreshList()
            }
          }
        } catch {
          await new Promise((r) => setTimeout(r, 3000))
        }
      }
    }
    run()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pollThread])

  const send = async () => {
    const text = draft.trim()
    if (!text || !activeId || sending) return
    setSending(true)
    try {
      const res = await sendMessage({ thread_id: activeId, message: text })
      const msg: Message | undefined = unwrap(res)
      setDraft('')
      // The cursor is left alone: a team reply created just before ours may
      // not have been polled yet. The poll returns ours too; ids dedupe it.
      if (msg) setMessages((prev) => (prev.some((m) => m.id === msg.id) ? prev : [...prev, msg]))
      scrollToEnd()
      refreshList()
    } catch (e: any) {
      toast.error(e?.message || 'Could not send your message')
    } finally {
      setSending(false)
    }
  }

  // Request update — only offered once the promised reply time has passed.
  // The automated reply lands in the conversation through the long-poll.
  const askUpdate = async () => {
    if (!activeId) return
    try {
      await requestUpdate({ thread_id: activeId })
      toast.success('Update requested — the team has been alerted')
      refreshList()
    } catch (e: any) {
      toast.error(e?.message || 'Could not reach the team')
    }
  }

  const start = async () => {
    if (!selectedOutlet) return
    if (!newCategory) return toast.error('Pick what this is about')
    if (!newSubject.trim()) return toast.error('Add a short subject')
    if (!newMessage.trim()) return toast.error('Tell us what happened')
    setStarting(true)
    try {
      const res = await startThread({
        outlet_id: selectedOutlet,
        category: newCategory,
        message: newMessage.trim(),
        subject: newSubject.trim(),
        ...(callback ? { callback: 1, callback_time: callbackTime } : {}),
        ...(params.get('area') ? { app_area: params.get('area') } : {}),
        ...(params.get('ctx_doctype') ? { context_doctype: params.get('ctx_doctype') } : {}),
        ...(params.get('ctx_name') ? { context_name: params.get('ctx_name') } : {}),
      })
      const data = unwrap(res)
      if (data?.joined_existing) toast.info('Added to your open request about this')
      setNewMessage('')
      setNewSubject('')
      setCallback(false)
      setCallbackTime('Anytime')
      setNewCategory('')
      setParams({}, { replace: true })
      await refreshList()
      if (data?.thread_id) openThread(data.thread_id)
    } catch (e: any) {
      toast.error(e?.message || 'Could not send your request')
    } finally {
      setStarting(false)
    }
  }

  if (!selectedOutlet) {
    return (
      <div className="p-6 text-sm text-muted-foreground">Select an outlet to see its support requests.</div>
    )
  }

  const showDetail = !!activeId || composing

  const isOpenStatus = (s: string) => s === 'open' || s === 'awaiting_agent' || s === 'awaiting_customer'
  const listCounts = {
    all: threads.length,
    open: threads.filter((t) => isOpenStatus(t.status)).length,
    resolved: threads.filter((t) => !isOpenStatus(t.status)).length,
  }
  const visibleThreads = threads.filter((t) =>
    listFilter === 'all' ? true : listFilter === 'open' ? isOpenStatus(t.status) : !isOpenStatus(t.status),
  )

  // Fixed-height workspace: the page itself never scrolls (scrolling to the
  // newest message used to drag the whole page up) — the request list and
  // the conversation each scroll inside their own box.
  return (
    <div ref={fillRef} style={{ height: fillHeight }} className="p-4 md:px-6 md:py-4 flex flex-col gap-3 overflow-hidden">
      <div className="flex items-start justify-between gap-3 flex-wrap shrink-0">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <LifeBuoy className="h-5 w-5 text-primary" /> Help &amp; Support
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Talk to the Flamezo team about payouts, KYC, your menu or anything else.
          </p>
        </div>
        <Button
          onClick={() => {
            setComposing(true)
            setActiveId(null)
            setPollThread(null)
          }}
        >
          <Plus className="h-4 w-4 mr-1" /> New request
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-[320px_1fr] flex-1 min-h-0">
        {/* Requests list */}
        <Card className={cn('overflow-hidden md:flex flex-col min-h-0 py-0 gap-0', showDetail ? 'hidden' : 'flex')}>
          {/* Header: what this list is, and quick filters */}
          <div className="px-4 pt-3.5 pb-3 border-b shrink-0 space-y-2.5">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-sm">Your requests</h2>
              <span className="text-xs text-muted-foreground tabular-nums">{listCounts.all} total</span>
            </div>
            <div className="flex gap-1" role="tablist" aria-label="Filter requests">
              {(['all', 'open', 'resolved'] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  role="tab"
                  aria-selected={listFilter === f}
                  onClick={() => setListFilter(f)}
                  className={cn(
                    'px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
                    listFilter === f ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                  )}
                >
                  {f === 'all' ? 'All' : f === 'open' ? 'Open' : 'Resolved'}
                  <span className="ml-1 tabular-nums opacity-75">{listCounts[f]}</span>
                </button>
              ))}
            </div>
          </div>
          <CardContent className="p-0 flex-1 min-h-0 overflow-y-auto">
            {loadingList ? (
              <div className="p-4 space-y-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-14 w-full" />
                ))}
              </div>
            ) : visibleThreads.length === 0 ? (
              <div className="p-6 text-center text-sm text-muted-foreground">
                <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-50" />
                {threads.length === 0 ? 'No requests yet.' : 'Nothing here.'}
              </div>
            ) : (
              <ul className="divide-y">
                {visibleThreads.map((t) => (
                  <li key={t.thread_id}>
                    <button
                      type="button"
                      onClick={() => openThread(t.thread_id)}
                      className={cn(
                        'w-full text-left px-4 py-3 hover:bg-muted/60 transition-colors focus-visible:outline-none focus-visible:bg-muted',
                        activeId === t.thread_id && 'bg-muted ring-1 ring-inset ring-primary/40',
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className={cn('text-sm truncate', t.unread_count > 0 ? 'font-bold' : 'font-medium')}>
                          {t.subject || categoryLabel(t.category)}
                        </span>
                        <span className="text-[11px] text-muted-foreground shrink-0 tabular-nums">
                          {fmtTime(t.last_message_at)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2 mt-1">
                        <span className="text-xs text-muted-foreground truncate">
                          {t.last_message_preview || categoryLabel(t.category)}
                        </span>
                        {t.unread_count > 0 ? (
                          <Badge className="h-5 px-1.5 text-[10px]">{t.unread_count}</Badge>
                        ) : (
                          <span
                            className={cn(
                              'text-[11px] shrink-0',
                              t.status === 'awaiting_customer' ? 'text-primary font-semibold' : 'text-muted-foreground',
                            )}
                          >
                            {STATUS_LABEL[t.status] ?? t.status}
                          </span>
                        )}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Detail: new-request form or conversation */}
        <Card className={cn('md:flex flex-col min-h-0 overflow-hidden py-0 gap-0', showDetail ? 'flex' : 'hidden')}>
          {composing ? (
            <CardContent className="p-5 space-y-4 flex-1 min-h-0 overflow-y-auto">
              <button
                type="button"
                className="md:hidden text-sm text-muted-foreground flex items-center gap-1"
                onClick={() => setComposing(false)}
              >
                <ArrowLeft className="h-4 w-4" /> Back
              </button>
              <div>
                <h2 className="font-semibold">New request</h2>
                <p className="text-sm text-muted-foreground">
                  Settlement and KYC requests are treated as urgent.
                </p>
              </div>
              <div className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  What's this about?
                </label>
                <Select value={newCategory} onValueChange={setNewCategory}>
                  <SelectTrigger>
                    <SelectValue placeholder="Choose a topic" />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIES.map((c) => (
                      <SelectItem key={c.key} value={c.key}>
                        {c.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Subject
                </label>
                <Input
                  maxLength={80}
                  value={newSubject}
                  onChange={(e) => setNewSubject(e.target.value)}
                  placeholder="e.g. Yesterday's payout hasn't arrived"
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Tell us what happened
                </label>
                <Textarea
                  rows={6}
                  maxLength={2000}
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  placeholder="e.g. Yesterday's payout of ₹4,250 hasn't reached our bank account"
                />
                {params.get('ctx_name') && (
                  <p className="text-xs text-muted-foreground">
                    We'll attach {params.get('ctx_doctype') || 'record'} {params.get('ctx_name')} so the team can see it.
                  </p>
                )}
              </div>
              {/* Ask the team to phone them — shows on the team's WhatsApp alert. */}
                <div className="rounded-lg border p-3 space-y-2">
                  <label className="flex items-start justify-between gap-3 cursor-pointer">
                    <span>
                      <span className="flex items-center gap-1.5 text-sm font-medium">
                        <Phone className="h-4 w-4 text-primary" /> Request a call back
                      </span>
                      <span className="block text-xs text-muted-foreground mt-0.5">
                        The Flamezo team will call you on your registered number.
                      </span>
                    </span>
                    <Switch checked={callback} onCheckedChange={setCallback} aria-label="Request a call back" />
                  </label>
                  {callback && (
                    <Select value={callbackTime} onValueChange={setCallbackTime}>
                      <SelectTrigger className="h-9">
                        <SelectValue placeholder="Best time to call" />
                      </SelectTrigger>
                      <SelectContent>
                        {['Anytime', 'Morning 9–12', 'Afternoon 12–4', 'Evening 4–8'].map((t) => (
                          <SelectItem key={t} value={t}>
                            {t}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>
              {/* Send request + Cancel together, on the left, below the call-back box. */}
              <div className="flex items-center gap-2">
                <Button onClick={start} disabled={starting}>
                  <Send className="h-4 w-4 mr-1" /> {starting ? 'Sending…' : 'Send request'}
                </Button>
                <Button variant="ghost" onClick={() => setComposing(false)}>
                  Cancel
                </Button>
              </div>
            </CardContent>
          ) : !activeId ? (
            <div className="flex-1 flex items-center justify-center p-8 text-center text-sm text-muted-foreground">
              <div className="space-y-3">
                <LifeBuoy className="h-10 w-10 mx-auto opacity-40" />
                <p>Pick a request on the left, or start a new one.</p>
                <Button
                  onClick={() => {
                    setComposing(true)
                    setActiveId(null)
                    setPollThread(null)
                  }}
                >
                  <Plus className="h-4 w-4 mr-1" /> New request
                </Button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between gap-3 border-b px-4 py-3 shrink-0">
                <div className="flex items-center gap-2 min-w-0">
                  <button
                    type="button"
                    className="md:hidden text-muted-foreground"
                    aria-label="Back to requests"
                    onClick={() => {
                      setActiveId(null)
                      setPollThread(null)
                    }}
                  >
                    <ArrowLeft className="h-4 w-4" />
                  </button>
                  <div className="min-w-0">
                    <div className="font-semibold text-sm truncate">
                      Flamezo Support
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {activeId} · {categoryLabel(active?.category || '')} ·{' '}
                      {STATUS_LABEL[active?.status || ''] ?? active?.status}
                      {active?.reply_due_at && <> · Reply expected by {fmtDue(active.reply_due_at)}</>}
                      {active?.escalated && <> · Escalated</>}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {active?.can_request_update && (
                    <Button size="sm" variant="outline" onClick={askUpdate}>
                      <BellRing className="h-4 w-4 mr-1" /> Request update
                    </Button>
                  )}
                </div>
              </div>

              <div ref={chatRef} className="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-2">
                <SupportMessageList messages={messages} loading={loadingThread} perspective="requester" />
              </div>

              {active?.status === 'closed' ? (
                <div className="border-t px-4 py-3 text-sm text-muted-foreground flex items-center justify-between gap-3 shrink-0">
                  This request is closed.
                  <Button size="sm" onClick={() => setComposing(true)}>
                    Start a new request
                  </Button>
                </div>
              ) : (
                <div className="border-t p-3 flex items-end gap-2 shrink-0">
                  <Textarea
                    rows={2}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      // Enter sends; Shift+Enter keeps a newline.
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        send()
                      }
                    }}
                    placeholder={active?.status === 'resolved' ? 'Still need help? Reply to reopen' : 'Type a message…'}
                    className="resize-none"
                  />
                  <Button onClick={send} disabled={sending || !draft.trim()} aria-label="Send message">
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </>
          )}
        </Card>
      </div>
    </div>
  )
}
