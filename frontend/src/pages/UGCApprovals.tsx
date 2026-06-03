import { useState } from 'react'
import { useRestaurant } from '@/contexts/RestaurantContext'
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
import { CheckCircle2, XCircle, PlayCircle, Loader2, Inbox } from 'lucide-react'

type Tab = 'verify' | 'flagged'

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
  const { selectedRestaurant } = useRestaurant()
  const [tab, setTab] = useState<Tab>('verify')
  const [demoMode, setDemoMode] = useState(true)
  const [reviewing, setReviewing] = useState<any | null>(null)
  const [viewCount, setViewCount] = useState('')
  const [busy, setBusy] = useState(false)

  const params = selectedRestaurant ? { restaurant_id: selectedRestaurant } : {}

  const verifyQ = useDataTable({
    customEndpoint: 'flamezo_backend.flamezo.api.ugc.list_pending_story_verifications',
    customParams: params, initialPageSize: 20,
    debugId: `ugc-verify-${selectedRestaurant}`,
  })
  const flaggedQ = useDataTable({
    customEndpoint: 'flamezo_backend.flamezo.api.ugc.list_flagged_ugc',
    customParams: params, initialPageSize: 20,
    debugId: `ugc-flagged-${selectedRestaurant}`,
  })

  const { call: verifyStory } = useFrappePostCall('flamezo_backend.flamezo.api.ugc.verify_ugc_story')
  const { call: reviewUgc } = useFrappePostCall('flamezo_backend.flamezo.api.ugc.review_ugc')

  const active = tab === 'verify'
    ? (demoMode ? { data: mockVerifyData, totalCount: mockVerifyData.length, isLoading: false, mutate: () => {} } : verifyQ)
    : (demoMode ? { data: mockFlaggedData, totalCount: mockFlaggedData.length, isLoading: false, mutate: () => {} } : flaggedQ)

  const doVerify = async (sub: any, action: 'approve' | 'reject') => {
    if (demoMode) {
      toast.success(action === 'approve' ? 'Story verified (Simulated)' : 'Story rejected (Simulated)')
      return
    }
    const notes = action === 'reject' ? (window.prompt('Reason for rejection?') || '') : undefined
    if (action === 'reject' && notes === '') return
    setBusy(true)
    try {
      const res: any = await verifyStory({ restaurant_id: selectedRestaurant, submission_id: sub.name, action, notes })
      const body = res?.message || res
      if (body?.success) {
        toast.success(action === 'approve' ? 'Story verified — diner can upload views tomorrow' : 'Story rejected')
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
        restaurant_id: selectedRestaurant, submission_id: reviewing.name, action,
        view_count: action === 'approve' ? Number(viewCount) : undefined, notes,
      })
      const body = res?.message || res
      if (body?.success) {
        toast.success(action === 'approve' ? `Credited ₹${body.data?.cashback_coins ?? ''} cashback` : 'Claim rejected')
        flaggedQ.mutate(); setReviewing(null); setViewCount('')
      } else throw new Error(body?.message || 'Failed')
    } catch (e: any) { toast.error(e.message) } finally { setBusy(false) }
  }

  if (!selectedRestaurant) {
    return <div className="p-8 text-center text-muted-foreground">Select a restaurant.</div>
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">UGC Approvals</h1>
          <p className="text-muted-foreground mt-1">Verify diners' stories in person, then resolve any view-counts the AI couldn't auto-approve.</p>
        </div>
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
      </div>

      {demoMode && (
        <div className="bg-orange-500/10 border border-orange-500/20 text-orange-600 dark:text-orange-400 px-4 py-2.5 rounded-2xl text-sm font-medium">
          Showing simulated real-world preview queues. Actions clicked will be simulated in the UI. Toggle to <strong>Live Data</strong> to view actual submissions.
        </div>
      )}

      <div className="flex gap-2">
        <TabBtn active={tab === 'verify'} onClick={() => setTab('verify')} label="Story Verification" count={demoMode ? mockVerifyData.length : verifyQ.totalCount} />
        <TabBtn active={tab === 'flagged'} onClick={() => setTab('flagged')} label="Flagged View-Counts" count={demoMode ? mockFlaggedData.length : flaggedQ.totalCount} />
      </div>

      <Card>
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
                    <Button size="sm" onClick={() => doVerify(s, 'approve')} disabled={busy}>
                      <CheckCircle2 className="w-4 h-4 mr-1" />Verify
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

      {/* Flagged review dialog */}
      <Dialog open={!!reviewing} onOpenChange={o => { if (!o) { setReviewing(null); setViewCount('') } }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Review View-Count Proof</DialogTitle></DialogHeader>
          {reviewing && (
            <div className="space-y-4">
              {reviewing.proof_video_url ? (
                <video src={reviewing.proof_video_url} controls playsInline className="w-full rounded-lg max-h-[50vh] bg-black" />
              ) : <p className="text-sm text-muted-foreground">Video unavailable.</p>}
              <div className="text-sm text-muted-foreground">
                Order amount: <strong>₹{reviewing.order_amount}</strong>. Cashback = min(views, order).
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">View count (from the video)</label>
                <Input type="number" min="0" value={viewCount} onChange={e => setViewCount(e.target.value)} placeholder="e.g. 250" />
              </div>
            </div>
          )}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => doReview('reject')} disabled={busy}>Reject</Button>
            <Button onClick={() => doReview('approve')} disabled={busy}>
              {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}Approve & Credit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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
