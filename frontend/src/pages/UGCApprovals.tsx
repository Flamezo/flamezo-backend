import { useState, useEffect, useRef } from 'react'
import { useOutlet } from '@/contexts/OutletContext'
import { useFrappePostCall } from '@/lib/frappe'
import { useDataTable } from '@/hooks/useDataTable'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { toast } from 'sonner'
import { XCircle, PlayCircle, Loader2, Inbox, ShieldCheck, TrendingUp, Users, ImagePlay, CheckCircle2, AlertTriangle, Timer } from 'lucide-react'
import { useFrappeGetCall } from '@/lib/frappe'

type Tab = 'verify' | 'flagged' | 'analytics'

const mockVerifyData = [
  {
    name: "SUB-UGC-101",
    customer: "CUST-101",
    customer_name: "Aarav Sharma",
    customer_phone: "+91 98765 43210",
    order: "ORD-72910",
    order_amount: 1250,
    template_used: "med_tpl1",
    template_url: "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=500&q=80",
    story_shared_at: "2026-06-03 12:30:00",
    submission_date: "2026-06-03 12:25:00"
  },
  {
    name: "SUB-UGC-102",
    customer: "CUST-102",
    customer_name: "Priya Patel",
    customer_phone: "+91 99112 23344",
    order: "ORD-72915",
    order_amount: 850,
    template_used: "med_tpl2",
    template_url: "https://images.unsplash.com/photo-1498837167922-ddd27525d352?w=500&q=80",
    story_shared_at: "2026-06-03 13:05:00",
    submission_date: "2026-06-03 12:55:00"
  },
  {
    name: "SUB-UGC-103",
    customer: "CUST-103",
    customer_name: "Siddharth Verma",
    customer_phone: "+91 98334 45566",
    order: "ORD-72922",
    order_amount: 2450,
    template_used: "med_tpl3",
    template_url: "https://images.unsplash.com/photo-1552566626-52f8b828add9?w=500&q=80",
    story_shared_at: "2026-06-03 13:12:00",
    submission_date: "2026-06-03 13:00:00"
  },
  {
    name: "SUB-UGC-104",
    customer: "CUST-104",
    customer_name: "Neha Deshmukh",
    customer_phone: "+91 97788 99001",
    order: "ORD-72931",
    order_amount: 620,
    template_used: "med_tpl1",
    template_url: "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=500&q=80",
    story_shared_at: "2026-06-03 13:25:00",
    submission_date: "2026-06-03 13:20:00"
  },
  {
    name: "SUB-UGC-105",
    customer: "CUST-105",
    customer_name: "Rohan Das",
    customer_phone: "+91 96655 44332",
    order: "ORD-72944",
    order_amount: 1890,
    template_used: "med_tpl4",
    template_url: "https://images.unsplash.com/photo-1559339352-11d035aa65de?w=500&q=80",
    story_shared_at: "2026-06-03 13:38:00",
    submission_date: "2026-06-03 13:30:00"
  },
  {
    name: "SUB-UGC-106",
    customer: "CUST-106",
    customer_name: "Ishaan Mehta",
    customer_phone: "+91 95556 67788",
    order: "ORD-72950",
    order_amount: 980,
    template_used: "med_tpl2",
    template_url: "https://images.unsplash.com/photo-1544025162-d76694265947?w=500&q=80",
    story_shared_at: "2026-06-03 13:42:00",
    submission_date: "2026-06-03 13:35:00"
  },
  {
    name: "SUB-UGC-110",
    customer: "CUST-110",
    customer_name: "Meera Reddy",
    customer_phone: "+91 94455 66778",
    order: "ORD-72889",
    order_amount: 1100,
    template_used: "med_tpl3",
    template_url: "https://images.unsplash.com/photo-1559339352-11d035aa65de?w=500&q=80",
    story_shared_at: "2026-06-03 13:45:00",
    submission_date: "2026-06-03 13:40:00"
  },
  {
    name: "SUB-UGC-111",
    customer: "CUST-111",
    customer_name: "Arjun Saxena",
    customer_phone: "+91 93322 11009",
    order: "ORD-72895",
    order_amount: 1750,
    template_used: "med_tpl1",
    template_url: "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=500&q=80",
    story_shared_at: "2026-06-03 13:48:00",
    submission_date: "2026-06-03 13:45:00"
  },
  {
    name: "SUB-UGC-112",
    customer: "CUST-112",
    customer_name: "Divya Nair",
    customer_phone: "+91 92233 44556",
    order: "ORD-72901",
    order_amount: 1350,
    template_used: "med_tpl4",
    template_url: "https://images.unsplash.com/photo-1544025162-d76694265947?w=500&q=80",
    story_shared_at: "2026-06-03 13:50:00",
    submission_date: "2026-06-03 13:45:00"
  }
]

const mockFlaggedData = [
  {
    name: "SUB-UGC-107",
    customer: "CUST-107",
    customer_name: "Sneha Joshi",
    customer_phone: "+91 98223 34455",
    order: "ORD-72850",
    order_amount: 1500,
    proof_video: "med_proof1",
    proof_video_url: "https://www.w3schools.com/html/mov_bbb.mp4",
    ai_view_count: 450,
    ai_confidence: 0.62,
    ai_tamper_signals: "screenshot_of_screenshot,inconsistent_numbers",
    proof_submitted_at: "2026-06-02 10:15:00"
  },
  {
    name: "SUB-UGC-108",
    customer: "CUST-108",
    customer_name: "Ananya Iyer",
    customer_phone: "+91 95556 77788",
    order: "ORD-72862",
    order_amount: 620,
    proof_video: "med_proof2",
    proof_video_url: "https://www.w3schools.com/html/movie.mp4",
    ai_view_count: 120,
    ai_confidence: 0.48,
    ai_tamper_signals: "not_story_insights",
    proof_submitted_at: "2026-06-02 11:45:00"
  },
  {
    name: "SUB-UGC-109",
    customer: "CUST-109",
    customer_name: "Rahul Gupta",
    customer_phone: "+91 99887 76655",
    order: "ORD-72877",
    order_amount: 3200,
    proof_video: "med_proof3",
    proof_video_url: "https://www.w3schools.com/html/mov_bbb.mp4",
    ai_view_count: 2450,
    ai_confidence: 0.78,
    ai_tamper_signals: "edited_number",
    proof_submitted_at: "2026-06-02 14:20:00"
  }
]

export default function UGCApprovals() {
  const { selectedOutlet } = useOutlet()
  const [tab, setTab] = useState<Tab>('verify')
  const [demoMode, setDemoMode] = useState(selectedOutlet === 'unvind')

  useEffect(() => {
    setDemoMode(selectedOutlet === 'unvind')
  }, [selectedOutlet])
  const [reviewing, setReviewing] = useState<any | null>(null)
  const [viewCount, setViewCount] = useState('')
  const [busy, setBusy] = useState(false)

  // PIN verification state for story approval
  const [pinTarget, setPinTarget] = useState<any | null>(null)
  const [pin, setPin] = useState('')
  const [pinError, setPinError] = useState('')
  const pinInputRef = useRef<HTMLInputElement>(null)

  const params = selectedOutlet ? { outlet_id: selectedOutlet } : {}

  const verifyQ = useDataTable({
    customEndpoint: 'flamezo_backend.flamezo.api.ugc.list_pending_story_verifications',
    customParams: params, initialPageSize: 20,
    debugId: `ugc-verify-${selectedOutlet}`,
  })
  const flaggedQ = useDataTable({
    customEndpoint: 'flamezo_backend.flamezo.api.ugc.list_flagged_ugc',
    customParams: params, initialPageSize: 20,
    debugId: `ugc-flagged-${selectedOutlet}`,
  })

  const { data: funnelRes } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.ugc.get_ugc_funnel',
    selectedOutlet ? { outlet_id: selectedOutlet, days: 30 } : undefined,
    selectedOutlet ? `ugc-funnel-${selectedOutlet}` : undefined,
  )

  const { call: verifyStory } = useFrappePostCall('flamezo_backend.flamezo.api.ugc.verify_ugc_story')
  const { call: verifyStoryWithPin } = useFrappePostCall('flamezo_backend.flamezo.api.ugc.verify_ugc_story_with_pin')
  const { call: reviewUgc } = useFrappePostCall('flamezo_backend.flamezo.api.ugc.review_ugc')

  const active = tab === 'verify'
    ? (demoMode ? { data: mockVerifyData, totalCount: mockVerifyData.length, isLoading: false, mutate: () => {} } : verifyQ)
    : (demoMode ? { data: mockFlaggedData, totalCount: mockFlaggedData.length, isLoading: false, mutate: () => {} } : flaggedQ)

  const openPinDialog = (sub: any) => {
    setPinTarget(sub)
    setPin('')
    setPinError('')
    setTimeout(() => pinInputRef.current?.focus(), 80)
  }

  const doPinVerify = async () => {
    if (!pinTarget || pin.length !== 4 || busy) return
    if (demoMode) {
      toast.success('Story verified (Simulated)')
      setPinTarget(null)
      return
    }
    setBusy(true)
    setPinError('')
    try {
      const res: any = await verifyStoryWithPin({ outlet_id: selectedOutlet, submission_id: pinTarget.name, pin })
      const body = res?.message || res
      if (body?.success) {
        toast.success('Story verified — customer can now upload their view count')
        verifyQ.mutate()
        setPinTarget(null)
      } else {
        const code = body?.error?.code || ''
        if (code === 'INVALID_PIN') setPinError('Wrong PIN. Try again.')
        else if (code === 'PIN_NOT_SET') setPinError('No PIN set. Go to Setup & Config to add one.')
        else setPinError(body?.message || 'Verification failed')
      }
    } catch (e: any) {
      setPinError(e.message || 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  const doVerify = async (sub: any, action: 'approve' | 'reject') => {
    if (demoMode) {
      toast.success(action === 'approve' ? 'Story verified (Simulated)' : 'Story rejected (Simulated)')
      return
    }
    const notes = action === 'reject' ? (window.prompt('Reason for rejection?') || '') : undefined
    if (action === 'reject' && notes === '') return
    setBusy(true)
    try {
      const res: any = await verifyStory({ outlet_id: selectedOutlet, submission_id: sub.name, action, notes })
      const body = res?.message || res
      if (body?.success) {
        toast.success(action === 'approve' ? 'Story verified — customer can upload views tomorrow' : 'Story rejected')
        verifyQ.mutate()
      } else throw new Error(body?.message || 'Failed')
    } catch (e: any) { toast.error(e.message) } finally { setBusy(false) }
  }

  const doReview = async (action: 'approve' | 'reject') => {
    if (!reviewing) return
    if (action === 'approve' && (!viewCount || Number(viewCount) <= 0)) {
      toast.error('Enter the view count shown in the video'); return
    }
    if (demoMode) {
      toast.success(action === 'approve' ? `Credited simulated cashback` : 'Claim rejected (Simulated)')
      setReviewing(null)
      setViewCount('')
      return
    }
    const notes = action === 'reject' ? (window.prompt('Reason for rejection?') || '') : undefined
    if (action === 'reject' && notes === '') return
    setBusy(true)
    try {
      const res: any = await reviewUgc({
        outlet_id: selectedOutlet, submission_id: reviewing.name, action,
        view_count: action === 'approve' ? Number(viewCount) : undefined, notes,
      })
      const body = res?.message || res
      if (body?.success) {
        toast.success(action === 'approve' ? `Credited ₹${body.data?.cashback_coins ?? ''} cashback` : 'Claim rejected')
        flaggedQ.mutate(); setReviewing(null); setViewCount('')
      } else throw new Error(body?.message || 'Failed')
    } catch (e: any) { toast.error(e.message) } finally { setBusy(false) }
  }

  if (!selectedOutlet) {
    return <div className="p-8 text-center text-muted-foreground">Select an outlet.</div>
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">UGC Approvals</h1>
          <p className="text-muted-foreground mt-1">Verify customers' stories in person, then resolve any view-counts the AI couldn't auto-approve.</p>
        </div>
        {selectedOutlet === 'unvind' && (
          <div className="flex items-center gap-2.5 bg-muted/60 border rounded-full px-3 py-1.5 text-xs font-medium self-start sm:self-center">
            <span className={demoMode ? "text-orange-500 font-semibold" : "text-muted-foreground"}>Simulated Data</span>
            <button
              onClick={() => setDemoMode(!demoMode)}
              className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none bg-muted ${
                demoMode ? 'bg-orange-500' : 'bg-gray-200 dark:bg-gray-800'
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                  demoMode ? 'translate-x-4' : 'translate-x-0'
                }`}
              />
            </button>
            <span className={!demoMode ? "text-primary font-semibold" : "text-muted-foreground"}>Live Data</span>
          </div>
        )}
      </div>

      {demoMode && (
        <div className="bg-orange-500/10 border border-orange-500/20 text-orange-600 dark:text-orange-400 px-4 py-2.5 rounded-2xl text-sm font-medium">
          Showing simulated real-world preview queues. Actions clicked will be simulated in the UI. Toggle to <strong>Live Data</strong> to view actual submissions.
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        <TabBtn active={tab === 'verify'} onClick={() => setTab('verify')} label="Story Verification" count={demoMode ? mockVerifyData.length : verifyQ.totalCount} />
        <TabBtn active={tab === 'flagged'} onClick={() => setTab('flagged')} label="Flagged View-Counts" count={demoMode ? mockFlaggedData.length : flaggedQ.totalCount} />
        <TabBtn active={tab === 'analytics'} onClick={() => setTab('analytics')} label="Analytics" count={0} />
      </div>

      {tab === 'analytics' ? (
        <AnalyticsTab funnelRes={funnelRes} />
      ) : null}

      <Card className={tab === 'analytics' ? 'hidden' : ''}>
        <CardContent className="p-0">
          {active.isLoading && !demoMode ? (
            <div className="p-12 text-center text-muted-foreground"><Loader2 className="w-6 h-6 animate-spin mx-auto" /></div>
          ) : !active.data?.length ? (
            <div className="p-12 text-center text-muted-foreground flex flex-col items-center gap-2">
              <Inbox className="w-8 h-8" />
              <p>{tab === 'verify' ? 'No stories awaiting verification.' : 'No flagged claims. The AI is handling them.'}</p>
            </div>
          ) : tab === 'verify' ? (
            <div className="divide-y">
              {active.data.map((s: any) => (
                <div key={s.name} className="flex items-center gap-4 p-4">
                  {s.template_url
                    ? <img src={s.template_url} className="w-12 h-20 object-cover rounded border" />
                    : <div className="w-12 h-20 rounded border bg-muted" />}
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{s.customer_name || s.customer}</p>
                    <p className="text-sm text-muted-foreground">{s.customer_phone} · Order ₹{s.order_amount}</p>
                    <p className="text-xs text-muted-foreground">Shared {fmt(s.story_shared_at)}</p>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => doVerify(s, 'reject')} disabled={busy}>
                      <XCircle className="w-4 h-4 mr-1" />Reject
                    </Button>
                    <Button size="sm" onClick={() => openPinDialog(s)} disabled={busy}>
                      <ShieldCheck className="w-4 h-4 mr-1" />Verify
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="divide-y">
              {active.data.map((s: any) => (
                <div key={s.name} className="flex items-center gap-4 p-4">
                  <button onClick={() => { setReviewing(s); setViewCount(String(s.ai_view_count || '')) }} className="relative w-12 h-20 rounded border bg-black/80 flex items-center justify-center">
                    <PlayCircle className="w-6 h-6 text-white" />
                  </button>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{s.customer_name || s.customer}</p>
                    <p className="text-sm text-muted-foreground">Order ₹{s.order_amount}</p>
                    <p className="text-xs text-muted-foreground">
                      AI read: <strong>{s.ai_view_count || '—'}</strong> views · conf {Math.round((s.ai_confidence || 0) * 100)}%
                      {s.ai_tamper_signals ? <span className="text-red-500"> · {s.ai_tamper_signals}</span> : null}
                    </p>
                  </div>
                  <Button size="sm" onClick={() => { setReviewing(s); setViewCount(String(s.ai_view_count || '')) }} disabled={busy}>Review</Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* PIN verification dialog */}
      <Dialog open={!!pinTarget} onOpenChange={o => { if (!o) { setPinTarget(null); setPin(''); setPinError('') } }}>
        <DialogContent className="max-w-xs">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-primary" />
              Enter Verification PIN
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <p className="text-sm text-muted-foreground">
              Ask the customer to show their story, then enter your 4-digit restaurant PIN to approve.
            </p>
            {pinTarget && (
              <div className="rounded-lg border bg-muted/40 px-3 py-2 text-sm">
                <p className="font-medium">{pinTarget.customer_name}</p>
                <p className="text-muted-foreground text-xs mt-0.5">{pinTarget.customer_phone} · Order ₹{pinTarget.order_amount}</p>
              </div>
            )}
            <div className="flex gap-2 justify-center">
              {[0, 1, 2, 3].map(i => (
                <div
                  key={i}
                  className="w-12 h-12 rounded-xl border-2 flex items-center justify-center text-xl font-black transition-all"
                  style={{ borderColor: pinError ? '#ef4444' : pin.length > i ? 'hsl(var(--primary))' : 'hsl(var(--border))' }}
                >
                  {pin[i] ? '•' : ''}
                </div>
              ))}
            </div>
            <Input
              ref={pinInputRef}
              type="number"
              inputMode="numeric"
              maxLength={4}
              value={pin}
              onChange={e => {
                const v = e.target.value.replace(/\D/g, '').slice(0, 4)
                setPin(v)
                setPinError('')
                if (v.length === 4) setTimeout(() => doPinVerify(), 120)
              }}
              className="text-center text-lg tracking-[0.5em] font-bold opacity-0 h-0 p-0 border-0"
              autoFocus
            />
            {pinError && <p className="text-center text-sm text-red-500 font-medium">{pinError}</p>}
            <p className="text-center text-xs text-muted-foreground">Tap any digit box above, then type on your keyboard</p>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => { setPinTarget(null); setPin(''); setPinError('') }}>Cancel</Button>
            <Button onClick={doPinVerify} disabled={pin.length !== 4 || busy}>
              {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <ShieldCheck className="w-4 h-4 mr-2" />}
              Approve Story
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Flagged review dialog */}
      <Dialog open={!!reviewing} onOpenChange={o => { if (!o) { setReviewing(null); setViewCount('') } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Review View-Count Proof</DialogTitle>
            {reviewing && (
              <p className="text-sm text-muted-foreground mt-1">
                {reviewing.customer_name} · Order ₹{reviewing.order_amount}
              </p>
            )}
          </DialogHeader>
          {reviewing && (
            <div className="space-y-4">
              {/* Video player */}
              {reviewing.proof_video_url ? (
                <video src={reviewing.proof_video_url} controls playsInline className="w-full rounded-xl max-h-[40vh] bg-black object-contain" />
              ) : reviewing.proof_hidden ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-700 p-3 text-sm text-amber-800 dark:text-amber-300">
                  <strong>Video hidden — retention window elapsed.</strong> The proof video is no longer
                  accessible (7-day limit). Approve only if you have independent confirmation of the view count.
                </div>
              ) : (
                <div className="rounded-lg border bg-muted/40 p-3 text-sm text-muted-foreground text-center">No video uploaded for this submission.</div>
              )}

              {/* AI summary row */}
              <div className="rounded-xl border bg-muted/30 p-3 space-y-3">
                <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">AI Analysis</p>
                <div className="flex items-center gap-4">
                  <div className="text-center">
                    <p className="text-2xl font-black">{reviewing.ai_view_count ?? '—'}</p>
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Views read</p>
                  </div>
                  <div className="flex-1">
                    {/* Confidence bar */}
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium">Confidence</span>
                      <span className={`text-xs font-bold ${(reviewing.ai_confidence || 0) >= 0.85 ? 'text-green-600' : (reviewing.ai_confidence || 0) >= 0.6 ? 'text-amber-600' : 'text-red-500'}`}>
                        {Math.round((reviewing.ai_confidence || 0) * 100)}%
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all"
                        style={{
                          width: `${Math.round((reviewing.ai_confidence || 0) * 100)}%`,
                          background: (reviewing.ai_confidence || 0) >= 0.85 ? '#16a34a' : (reviewing.ai_confidence || 0) >= 0.6 ? '#d97706' : '#ef4444',
                        }}
                      />
                    </div>
                  </div>
                </div>

                {/* Tamper signals */}
                {reviewing.ai_tamper_signals && (
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground mb-1.5">Flags detected</p>
                    <div className="flex flex-wrap gap-1.5">
                      {reviewing.ai_tamper_signals.split(',').map((sig: string) => (
                        <span key={sig} className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
                          {sig.trim().replace(/_/g, ' ')}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Cashback preview */}
              {viewCount && Number(viewCount) > 0 && (
                <div className="rounded-xl bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 p-3 text-sm">
                  <p className="font-semibold text-green-800 dark:text-green-300">
                    Approving will credit ₹{Math.min(Number(viewCount), reviewing.order_amount, 2000)} cashback
                    <span className="font-normal text-green-700 dark:text-green-400 ml-1">(min of {viewCount} views, ₹{reviewing.order_amount} bill, ₹2,000 cap)</span>
                  </p>
                </div>
              )}

              {/* View count input */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium">View count (read from the video)</label>
                <Input
                  type="number" min="0"
                  value={viewCount}
                  onChange={e => setViewCount(e.target.value)}
                  placeholder={`AI suggested: ${reviewing.ai_view_count ?? 'n/a'}`}
                />
                <p className="text-[11px] text-muted-foreground">Override the AI's reading if it's incorrect. Enter what you see in the video.</p>
              </div>
            </div>
          )}
          <DialogFooter className="gap-2">
            <Button variant="outline" className="text-red-600 hover:text-red-700 hover:bg-red-50" onClick={() => doReview('reject')} disabled={busy}>Reject Claim</Button>
            <Button onClick={() => doReview('approve')} disabled={busy || !viewCount || Number(viewCount) <= 0}>
              {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
              Approve &amp; Credit ₹{viewCount && Number(viewCount) > 0 && reviewing ? Math.min(Number(viewCount), reviewing.order_amount, 2000) : '—'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function AnalyticsTab({ funnelRes }: { funnelRes: any }) {
  const body = (funnelRes as any)?.message || funnelRes
  const data = body?.data

  if (!data) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
          Loading analytics…
        </CardContent>
      </Card>
    )
  }

  const funnel: { label: string; key: string; count: number }[] = data.funnel || []
  const max = Math.max(...funnel.map((f: any) => f.count), 1)
  const outcomes = data.outcomes || {}

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-6">
          <p className="text-sm font-semibold mb-1">Submission Funnel <span className="text-xs font-normal text-muted-foreground ml-1">last {data.days} days</span></p>
          <p className="text-xs text-muted-foreground mb-5">How many customers made it through each step of the UGC cashback flow.</p>
          <div className="space-y-3">
            {funnel.map((step: any, i: number) => (
              <div key={step.key}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium flex items-center gap-2">
                    <span className="w-5 h-5 rounded-full bg-primary/10 text-primary text-[10px] flex items-center justify-center font-bold">{i + 1}</span>
                    {step.label}
                  </span>
                  <span className="text-sm font-bold tabular-nums">{step.count}</span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${Math.round((step.count / max) * 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4">
            <AlertTriangle className="w-4 h-4 text-amber-500 mb-2" />
            <p className="text-2xl font-black">{outcomes.flagged ?? 0}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Flagged for review</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <XCircle className="w-4 h-4 text-red-500 mb-2" />
            <p className="text-2xl font-black">{outcomes.rejected ?? 0}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Rejected</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <Timer className="w-4 h-4 text-muted-foreground mb-2" />
            <p className="text-2xl font-black">{outcomes.expired ?? 0}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Expired</p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function TabBtn({ active, onClick, label, count }: { active: boolean; onClick: () => void; label: string; count: number }) {
  return (
    <button onClick={onClick}
      className={`px-4 py-2 rounded-lg text-sm font-medium border transition ${active ? 'bg-primary text-primary-foreground border-primary' : 'bg-background hover:bg-muted'}`}>
      {label}{count ? <Badge variant="secondary" className="ml-2">{count}</Badge> : null}
    </button>
  )
}

function fmt(dt?: string) {
  if (!dt) return '—'
  try { return new Date(dt.replace(' ', 'T')).toLocaleString() } catch { return dt }
}
