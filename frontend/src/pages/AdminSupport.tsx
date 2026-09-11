import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useFrappeAuth, useFrappePostCall } from '@/lib/frappe'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { toast } from 'sonner'
import { ArrowLeft, CheckCircle2, Inbox, Phone, Search, Send, Shield } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useFillViewportHeight } from '@/hooks/useFillViewportHeight'
import { SupportMessageList, fmtTime, parseDate, type SupportMessage } from '@/components/support/SupportMessageList'

/**
 * Admin-only: every support request from customers (app) and merchants
 * (dashboard) in one queue. Admins read the conversation, reply, and resolve —
 * resolving WhatsApps the requester (support.agent_update_thread). The team's
 * WhatsApp alert "Open ticket" button deep-links to /admin/support/<ID>.
 */

const API = 'flamezo_backend.flamezo.api.support'

type AgentThread = {
  name: string
  customer_name?: string
  customer_phone?: string
  requester_user?: string
  requester_email?: string
  requester_phone?: string
  outlet?: string
  source: 'app' | 'dashboard' | string
  status: string
  priority: string
  category: string
  app_area?: string
  subject?: string
  unread_for_agent: number
  last_message_at: string
  creation: string
  reply_due_at?: string
  callback_requested?: number
  callback_time?: string
  escalated_at?: string
}

const CATEGORY_LABEL: Record<string, string> = {
  payment: 'Payment',
  booking: 'Booking',
  offers: 'Offers & cashback',
  account: 'Account',
  creator: 'Creator collabs',
  crowd: 'Crowd & Clubs',
  technical: 'App not working',
  feedback: 'Feedback',
  grievance: 'Grievance',
  settlement: 'Settlement / payout',
  kyc: 'KYC & onboarding',
  commission: 'Commission & fees',
  menu: 'Menu & offers',
  profile: 'Outlet profile',
  other: 'Something else',
  callback: 'Call back request',
}

// Status as the team needs it: who has to act next.
const STATUS: Record<string, { label: string; tone: string }> = {
  open: { label: 'Needs reply', tone: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200' },
  awaiting_agent: { label: 'Needs reply', tone: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200' },
  awaiting_customer: { label: 'Waiting on requester', tone: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200' },
  resolved: { label: 'Resolved', tone: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200' },
  closed: { label: 'Closed', tone: 'bg-muted text-muted-foreground' },
}

const PRIORITY_TONE: Record<string, string> = {
  urgent: 'bg-red-600 text-white',
  high: 'bg-orange-500 text-white',
  normal: 'bg-muted text-foreground',
  low: 'bg-muted text-muted-foreground',
}

const ACTIVE = ['open', 'awaiting_agent', 'awaiting_customer']

// The customer tapped "Request update" after the promised reply time passed.
const isUpdateRequested = (t: AgentThread) => !!t.escalated_at && ACTIVE.includes(t.status)

const unwrap = (res: any) => (res?.message || res)?.data

const fmtFull = (s?: string) => {
  const d = s ? parseDate(s) : null
  return d && !Number.isNaN(d.getTime())
    ? d.toLocaleString([], { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
    : ''
}

/** Same rule as the other admin pages, plus the Support Agent role. */
function useIsSupportAdmin(): boolean | null {
  const { currentUser } = useFrappeAuth()
  if (!currentUser) return null
  const win = window as any
  const roles: string[] = win.frappe?.boot?.user_roles || win.frappe?.boot?.user?.roles || win.frappe?.user_roles || []
  return (
    currentUser === 'Administrator' ||
    ['System Manager', 'Flamezo Supervisor', 'Flamezo Admin', 'Support Agent'].some((r) => roles.includes(r))
  )
}

export default function AdminSupport() {
  const allowed = useIsSupportAdmin()
  const navigate = useNavigate()
  const { id: activeId } = useParams()

  const [status, setStatus] = useState<'open' | 'done' | 'all'>('open')
  const [tab, setTab] = useState<'dashboard' | 'app' | 'calls'>('dashboard')
  const [search, setSearch] = useState('')
  const [threads, setThreads] = useState<AgentThread[]>([])
  const [loadingList, setLoadingList] = useState(true)

  const [detail, setDetail] = useState<AgentThread | null>(null)
  const [messages, setMessages] = useState<SupportMessage[]>([])
  const [loadingThread, setLoadingThread] = useState(false)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [confirmResolve, setConfirmResolve] = useState(false)
  const [resolving, setResolving] = useState(false)
  const chatRef = useRef<HTMLDivElement | null>(null)
  const [fillRef, fillHeight] = useFillViewportHeight()

  const { call: listThreads } = useFrappePostCall(`${API}.agent_list_threads`)
  const { call: getThread } = useFrappePostCall(`${API}.agent_get_thread`)
  const { call: sendMessage } = useFrappePostCall(`${API}.agent_send_message`)
  const { call: updateThread } = useFrappePostCall(`${API}.agent_update_thread`)

  const refreshList = useCallback(async () => {
    try {
      const res = await listThreads({
        ...(status !== 'open' ? { status } : {}),
        limit: 200,
      })
      setThreads(unwrap(res)?.threads || [])
    } catch (e: any) {
      toast.error(e?.message || 'Could not load support requests')
    } finally {
      setLoadingList(false)
    }
  }, [status, listThreads])

  useEffect(() => {
    if (!allowed) return
    setLoadingList(true)
    refreshList()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowed, status])

  // New requests and replies show up without a page refresh.
  useEffect(() => {
    if (!allowed) return
    const t = setInterval(() => {
      if (document.visibilityState === 'visible') refreshList()
    }, 15000)
    return () => clearInterval(t)
  }, [allowed, refreshList])

  const loadThread = useCallback(
    async (id: string, quiet = false) => {
      if (!quiet) setLoadingThread(true)
      try {
        const d = unwrap(await getThread({ thread_id: id }))
        setDetail(d?.thread || null)
        setMessages(d?.messages || [])
      } catch (e: any) {
        if (!quiet) {
          toast.error(e?.message || "This request isn't available")
          setDetail(null)
        }
      } finally {
        if (!quiet) setLoadingThread(false)
      }
    },
    [getThread],
  )

  // The open request stays live: the requester's replies appear on their own.
  useEffect(() => {
    if (!allowed || !activeId) {
      setDetail(null)
      setMessages([])
      return
    }
    setDraft('')
    loadThread(activeId)
    const t = setInterval(() => {
      if (document.visibilityState === 'visible') loadThread(activeId, true)
    }, 8000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowed, activeId])

  // Keep the newest message in view as the conversation grows. Scroll the chat
  // box itself — scrollIntoView would also scroll the whole page up.
  useEffect(() => {
    const el = chatRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages.length, activeId])

  // Merchants and customers are separate queues (the tabs); both counts show.
  const counts = useMemo(
    () => ({
      dashboard: threads.filter((t) => t.source === 'dashboard').length,
      app: threads.filter((t) => t.source !== 'dashboard').length,
      calls: threads.filter((t) => !!t.callback_requested).length,
    }),
    [threads],
  )

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase()
    const inTab = threads.filter((t) =>
      tab === 'calls' ? !!t.callback_requested : tab === 'dashboard' ? t.source === 'dashboard' : t.source !== 'dashboard',
    )
    const found = !q
      ? inTab
      : inTab.filter((t) =>
          [t.name, t.subject, t.customer_name, t.customer_phone, t.outlet, t.requester_user].some((v) =>
            (v || '').toLowerCase().includes(q),
          ),
        )
    // Overdue requests the customer chased ("Request update") jump to the top.
    return [...found].sort((a, b) => Number(isUpdateRequested(b)) - Number(isUpdateRequested(a)))
  }, [threads, search, tab])

  const send = async () => {
    const text = draft.trim()
    if (!text || !activeId || sending) return
    setSending(true)
    try {
      await sendMessage({ thread_id: activeId, message: text })
      setDraft('')
      await loadThread(activeId, true)
      refreshList()
    } catch (e: any) {
      toast.error(e?.message || 'Reply not sent — try again')
    } finally {
      setSending(false)
    }
  }

  const resolve = async () => {
    if (!activeId) return
    setResolving(true)
    try {
      await updateThread({ thread_id: activeId, status: 'resolved' })
      toast.success(`${activeId} resolved — they've been told on WhatsApp`)
      setConfirmResolve(false)
      await loadThread(activeId, true)
      refreshList()
    } catch (e: any) {
      toast.error(e?.message || 'Could not resolve this request')
    } finally {
      setResolving(false)
    }
  }

  if (allowed === null) {
    return (
      <div className="p-6">
        <Skeleton className="h-8 w-48" />
      </div>
    )
  }
  if (!allowed) {
    return (
      <div className="p-6">
        <Card className="max-w-md mx-auto p-8 text-center">
          <Shield className="h-8 w-8 mx-auto mb-3 text-muted-foreground" />
          <h2 className="font-semibold text-lg">Admins only</h2>
          <p className="text-sm text-muted-foreground mt-1">Support requests are visible to Flamezo admins only.</p>
          <Button className="mt-5" onClick={() => navigate('/')}>
            Return home
          </Button>
        </Card>
      </div>
    )
  }

  const isOpen = !!detail && ACTIVE.includes(detail.status)
  const who = (t: AgentThread) => t.customer_name || t.outlet || t.customer_phone || t.requester_user || '—'

  // Fixed-height workspace: the page itself never scrolls — the queue and the
  // conversation each scroll inside their own box.
  return (
    <div ref={fillRef} style={{ height: fillHeight }} className="p-4 md:px-6 md:py-4 flex flex-col gap-3 overflow-hidden">
      <div className="flex flex-wrap items-end justify-between gap-3 shrink-0">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Inbox className="h-5 w-5 text-primary" /> Support Requests
          </h1>
          <p className="text-sm text-muted-foreground">
            Every request from customers (app) and merchants (dashboard). Reply here — resolving tells them on WhatsApp.
          </p>
        </div>
        <div className="inline-flex rounded-lg border bg-muted/40 p-1" role="tablist" aria-label="Requester type">
          {(['dashboard', 'app', 'calls'] as const).map((s) => (
            <button
              key={s}
              role="tab"
              aria-selected={tab === s}
              onClick={() => setTab(s)}
              className={cn(
                'px-4 py-1.5 text-sm font-medium rounded-md transition-colors',
                tab === s ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {s === 'dashboard' ? 'Merchants' : s === 'app' ? 'Customers' : 'Call requests'}
              <span className="ml-1.5 text-xs tabular-nums opacity-70">{counts[s]}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-[360px_1fr] flex-1 min-h-0">
        {/* ── queue ─────────────────────────────────────────────── */}
        <Card className={cn('flex flex-col overflow-hidden min-h-0 py-0 gap-0', activeId && 'hidden md:flex')}>
          <div className="p-3 border-b space-y-2 shrink-0">
            <div className="flex items-center justify-between px-0.5">
              <h2 className="font-semibold text-sm">{tab === 'dashboard' ? 'Merchant requests' : tab === 'app' ? 'Customer requests' : 'Call requests'}</h2>
              <span className="text-xs text-muted-foreground tabular-nums">{shown.length} shown</span>
            </div>
            <div className="relative">
              <Search className="h-4 w-4 absolute left-2.5 top-2.5 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search ID, name, phone, subject"
                className="pl-8"
              />
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {(['open', 'done', 'all'] as const).map((s) => (
                <Button key={s} size="sm" variant={status === s ? 'default' : 'outline'} onClick={() => setStatus(s)}>
                  {s === 'open' ? 'Open' : s === 'done' ? 'Resolved' : 'All'}
                </Button>
              ))}
            </div>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto">
            {loadingList ? (
              <div className="p-3 space-y-3">
                {[0, 1, 2, 3, 4].map((i) => (
                  <Skeleton key={i} className="h-[72px] w-full" />
                ))}
              </div>
            ) : shown.length === 0 ? (
              <p className="p-8 text-sm text-center text-muted-foreground">No requests here.</p>
            ) : (
              shown.map((t) => (
                <button
                  key={t.name}
                  onClick={() => navigate(`/admin/support/${t.name}`)}
                  className={cn(
                    'w-full text-left px-4 py-2.5 border-b hover:bg-muted/50 transition-colors',
                    activeId === t.name && 'bg-muted ring-1 ring-inset ring-primary/40',
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-muted-foreground">{t.name}</span>
                    {t.priority !== 'normal' && (
                      <span className={cn('text-[10px] font-bold uppercase px-1.5 rounded', PRIORITY_TONE[t.priority])}>
                        {t.priority}
                      </span>
                    )}
                    {!!t.callback_requested && (
                      <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold px-1.5 rounded bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-200">
                        <Phone className="h-2.5 w-2.5" /> Call back
                      </span>
                    )}
                    {isUpdateRequested(t) && (
                      <span className="text-[10px] font-semibold px-1.5 rounded bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200">
                        Update requested
                      </span>
                    )}
                    {t.unread_for_agent > 0 && (
                      <span className="ml-auto text-[10px] font-bold bg-primary text-primary-foreground rounded-full px-1.5">
                        {t.unread_for_agent}
                      </span>
                    )}
                  </div>
                  <div className="font-medium text-sm truncate mt-0.5">{t.subject || 'Support request'}</div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                    <span className="truncate">
                      {t.source === 'dashboard' ? 'Merchant' : 'Customer'} · {who(t)}
                    </span>
                    <span className="ml-auto shrink-0 tabular-nums">{fmtTime(t.last_message_at)}</span>
                  </div>
                  <span
                    className={cn(
                      'inline-block mt-1.5 text-[10px] font-semibold rounded px-1.5 py-0.5',
                      STATUS[t.status]?.tone,
                    )}
                  >
                    {STATUS[t.status]?.label ?? t.status}
                  </span>
                </button>
              ))
            )}
          </div>
        </Card>

        {/* ── conversation ─────────────────────────────────────── */}
        <Card className={cn('flex flex-col overflow-hidden min-h-0 py-0 gap-0', !activeId && 'hidden md:flex')}>
          {!activeId ? (
            <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground p-10 text-center">
              <Inbox className="h-10 w-10 mb-3" />
              <p className="font-medium">Pick a request to read and reply</p>
            </div>
          ) : loadingThread && !detail ? (
            <div className="p-5 space-y-3">
              <Skeleton className="h-6 w-1/2" />
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : detail ? (
            <>
              <div className="border-b px-4 py-3 flex flex-wrap items-start gap-3 shrink-0">
                <button
                  className="md:hidden p-1 -ml-1"
                  onClick={() => navigate('/admin/support')}
                  aria-label="Back to requests"
                >
                  <ArrowLeft className="h-4 w-4" />
                </button>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-muted-foreground">{detail.name}</span>
                    <span className={cn('text-[10px] font-semibold rounded px-1.5 py-0.5', STATUS[detail.status]?.tone)}>
                      {STATUS[detail.status]?.label ?? detail.status}
                    </span>
                    <span className={cn('text-[10px] font-bold uppercase px-1.5 rounded', PRIORITY_TONE[detail.priority])}>
                      {detail.priority}
                    </span>
                    {!!detail.callback_requested && (
                      <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold px-1.5 rounded bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-200">
                        <Phone className="h-2.5 w-2.5" /> Call requested
                      </span>
                    )}
                  </div>
                  <h2 className="font-semibold text-base mt-1 break-words">{detail.subject || 'Support request'}</h2>
                  <dl className="mt-1.5 grid grid-cols-[auto_1fr] sm:grid-cols-[auto_1fr_auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                    <dt className="text-muted-foreground">From</dt>
                    <dd>
                      {detail.source === 'dashboard' ? 'Merchant' : 'Customer'} · {who(detail)}
                    </dd>
                    {(detail.customer_phone || detail.requester_phone) && (
                      <>
                        <dt className="text-muted-foreground">Phone</dt>
                        <dd className="tabular-nums">
                          {/* Tap to call — the point of a call request. */}
                          <a
                            className="underline underline-offset-2"
                            href={`tel:+91${(detail.customer_phone || detail.requester_phone || '').replace(/\D/g, '').slice(-10)}`}
                          >
                            +91 {(detail.customer_phone || detail.requester_phone || '').replace(/\D/g, '').slice(-10)}
                          </a>
                        </dd>
                      </>
                    )}
                    {detail.requester_user && (
                      <>
                        <dt className="text-muted-foreground">Account</dt>
                        <dd className="break-all">{detail.requester_user}</dd>
                      </>
                    )}
                    {detail.requester_email && (
                      <>
                        <dt className="text-muted-foreground">Email</dt>
                        <dd className="break-all">
                          <a className="underline underline-offset-2" href={`mailto:${detail.requester_email}`}>
                            {detail.requester_email}
                          </a>
                        </dd>
                      </>
                    )}
                    <dt className="text-muted-foreground">Category</dt>
                    <dd>
                      {CATEGORY_LABEL[detail.category] ?? detail.category}
                      {detail.app_area ? ` · ${detail.app_area.replace(/_/g, ' ')}` : ''}
                    </dd>
                    {!!detail.callback_requested && (
                      <>
                        <dt className="text-muted-foreground">Call back</dt>
                        <dd className="font-medium text-violet-700 dark:text-violet-300">
                          Requested · {detail.callback_time || 'Anytime'}
                        </dd>
                      </>
                    )}
                    <dt className="text-muted-foreground">Raised</dt>
                    <dd>{fmtFull(detail.creation)}</dd>
                    {isOpen && detail.reply_due_at && (
                      <>
                        <dt className="text-muted-foreground">Reply due</dt>
                        <dd>{fmtFull(detail.reply_due_at)}</dd>
                      </>
                    )}
                  </dl>
                </div>
                {isOpen && (
                  <Button
                    onClick={() => setConfirmResolve(true)}
                    className="bg-emerald-600 hover:bg-emerald-700 text-white"
                  >
                    <CheckCircle2 className="h-4 w-4 mr-1.5" /> Resolve
                  </Button>
                )}
              </div>

              <div ref={chatRef} className="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-2">
                <SupportMessageList
                  messages={messages}
                  loading={loadingThread && messages.length === 0}
                  perspective="team"
                />
              </div>

              {detail.status !== 'closed' && (
                <div className="border-t p-3 flex items-end gap-2 shrink-0">
                  <Textarea
                    rows={2}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send()
                    }}
                    placeholder={isOpen ? 'Write a reply…  (Ctrl+Enter to send)' : 'Reply to reopen this request…'}
                    className="resize-none"
                  />
                  <Button onClick={send} disabled={sending || !draft.trim()} aria-label="Send reply">
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </>
          ) : (
            <p className="p-8 text-sm text-center text-muted-foreground">This request isn't available.</p>
          )}
        </Card>
      </div>

      <Dialog open={confirmResolve} onOpenChange={setConfirmResolve}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Resolve {detail?.name}?</DialogTitle>
            <DialogDescription>
              {detail ? who(detail) : 'The requester'} gets a WhatsApp message saying their request has been resolved.
              If it isn't sorted, they can reply to reopen it.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmResolve(false)}>
              Cancel
            </Button>
            <Button onClick={resolve} disabled={resolving} className="bg-emerald-600 hover:bg-emerald-700 text-white">
              {resolving ? 'Resolving…' : 'Resolve & notify'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
