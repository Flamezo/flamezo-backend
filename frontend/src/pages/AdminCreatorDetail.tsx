import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import {
  ChevronLeft, RefreshCw, Instagram, Video, Wallet, ShieldAlert,
  CheckCircle2, XCircle, Ban, RotateCcw, MapPin, Calendar, Landmark,
  Tag, Gift, ExternalLink,
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface RateCard {
  deliverable_type: string
  price_inr: number
  accepts_barter: boolean
  barter_min_value_inr: number
}

interface RecentDeal {
  name: string
  status: string
  deal_type: 'cash' | 'barter'
  price_inr: number
  fair_value_inr: number
  creation: string
  outlet_name: string
}

interface OpenDispute {
  name: string
  status: string
  reason: string
  raised_by_role: string
  creation: string
  deal_id: string
}

interface CreatorProfile {
  id: string
  name: string
  phone: string
  status: 'pending' | 'approved' | 'rejected' | 'suspended'
  city: string
  bio: string
  profile_image: string | null
  instagram_handle: string
  meta_followers: number
  meta_avg_views: number
  follower_count_last_synced: string | null
  approved_at: string | null
  badge_tier: string
  collabs_done: number
  total_earned_inr: number
  open_disputes: number
  barter_value_ytd_inr: number
  kyc: {
    status: string
    legal_name: string | null
    pan_number: string | null
    bank_holder_name: string | null
    bank_account_masked: string | null
    bank_ifsc: string | null
    linked_account_id: string | null
  }
  rate_cards: RateCard[]
  recent_deals: RecentDeal[]
  open_disputes_list: OpenDispute[]
  created: string
  last_seen: string
}

const DELIVERABLE_LABELS: Record<string, string> = {
  native_chills: 'Chills reel',
  native_club_post: 'Club Talks post',
  instagram_reel: 'IG reel',
  instagram_story: 'IG story',
  bundle: 'Bundle',
}

const BADGE_TIER_LABELS: Record<string, string> = {
  new_creator: 'New Creator',
  verified_creator: 'Verified Creator',
  top_rated: 'Top Rated',
  elite_creator: 'Elite Creator',
}

const DEAL_STATUS_STYLES: Record<string, string> = {
  released: 'text-green-700 bg-green-50 border-green-200',
  disputed: 'text-red-700 bg-red-50 border-red-200',
  cancelled: 'text-muted-foreground bg-muted border-transparent',
  refunded: 'text-muted-foreground bg-muted border-transparent',
}

const fmtR    = (n?: number) => `₹${(n ?? 0).toLocaleString('en-IN')}`
const fmtDate = (s?: string | null) => s ? new Date(s).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

// A pending action's confirm dialog — approve/reject/suspend/reinstate all
// funnel through the same one_lever admin_update_creator_status endpoint,
// so one dialog shape covers all four rather than four near-duplicates.
type PendingAction = { status: CreatorProfile['status']; label: string; destructive: boolean } | null

export default function AdminCreatorDetail() {
  const { id: creatorId } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [creator, setCreator] = useState<CreatorProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [pendingAction, setPendingAction] = useState<PendingAction>(null)
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const { call: fetchProfile } = useFrappePostCall('flamezo_backend.flamezo.api.admin.admin_get_creator_full_profile')
  const { call: updateStatus } = useFrappePostCall('flamezo_backend.flamezo.api.admin.admin_update_creator_status')

  useEffect(() => { if (creatorId) load() }, [creatorId])

  async function load() {
    setLoading(true)
    try {
      const res: any = await fetchProfile({ creator_id: creatorId })
      if (res.message?.success) setCreator(res.message.data)
      else toast.error(res.message?.error || 'Failed to load creator')
    } catch { toast.error('Failed to load creator') }
    finally { setLoading(false) }
  }

  async function confirmAction() {
    if (!pendingAction || !creator) return
    setSubmitting(true)
    try {
      const res: any = await updateStatus({ creator_id: creator.id, status: pendingAction.status, reason: reason || undefined })
      if (res.message?.success) {
        toast.success(`Creator ${pendingAction.status}`)
        setPendingAction(null); setReason(''); load()
      } else {
        toast.error(res.message?.error || 'Failed to update status')
      }
    } catch { toast.error('Failed to update status') }
    finally { setSubmitting(false) }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-full text-muted-foreground py-32">
      <RefreshCw className="w-5 h-5 animate-spin mr-2" /> Loading creator profile…
    </div>
  )

  if (!creator) return (
    <div className="flex flex-col items-center justify-center h-full py-32 text-muted-foreground">
      <p className="text-lg font-semibold mb-2">Creator not found</p>
      <Button variant="outline" onClick={() => navigate('/admin/creators')}>
        <ChevronLeft className="w-4 h-4 mr-1" /> Back to list
      </Button>
    </div>
  )

  // Every status has exactly the actions that make sense from it — no
  // "approve an already-approved creator" button ever renders.
  const actions: PendingAction[] = (() => {
    switch (creator.status) {
      case 'pending':
        return [
          { status: 'approved', label: 'Approve', destructive: false },
          { status: 'rejected', label: 'Reject', destructive: true },
        ]
      case 'approved':
        return [{ status: 'suspended', label: 'Suspend', destructive: true }]
      case 'suspended':
        return [{ status: 'approved', label: 'Reinstate', destructive: false }]
      case 'rejected':
        return [{ status: 'approved', label: 'Approve anyway', destructive: false }]
      default:
        return []
    }
  })()

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Top bar ── */}
      <div className="flex items-center justify-between px-6 py-4 border-b shrink-0">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground" onClick={() => navigate('/admin/creators')}>
            <ChevronLeft className="w-4 h-4" /> Creator Management
          </Button>
          <span className="text-muted-foreground">/</span>
          <span className="font-semibold text-sm">{creator.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="gap-1.5 text-xs" onClick={load} disabled={loading}>
            <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} /> Refresh
          </Button>
          {actions.map(a => a && (
            <Button
              key={a.status}
              variant={a.destructive ? 'destructive' : 'default'}
              size="sm"
              className="gap-1.5 text-xs"
              onClick={() => setPendingAction(a)}>
              {a.status === 'approved' ? <CheckCircle2 className="w-3.5 h-3.5" />
                : a.status === 'rejected' ? <XCircle className="w-3.5 h-3.5" />
                : a.status === 'suspended' ? <Ban className="w-3.5 h-3.5" />
                : <RotateCcw className="w-3.5 h-3.5" />}
              {a.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">

        {/* ── Header card ── */}
        <Card>
          <CardContent className="pt-6 flex items-start gap-4">
            <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-xl shrink-0 overflow-hidden">
              {creator.profile_image
                ? <img src={creator.profile_image} alt={creator.name} className="w-full h-full object-cover" />
                : (creator.name || '?')[0].toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-lg font-bold">{creator.name}</h2>
                <Badge
                  variant="secondary"
                  className={cn('capitalize', {
                    approved: 'text-green-700 bg-green-50 border-green-200',
                    pending: 'text-amber-700 bg-amber-50 border-amber-200',
                    suspended: 'text-red-700 bg-red-50 border-red-200',
                    rejected: 'text-muted-foreground bg-muted border-transparent',
                  }[creator.status])}>
                  {creator.status}
                </Badge>
                <Badge variant="outline">{BADGE_TIER_LABELS[creator.badge_tier] || creator.badge_tier}</Badge>
              </div>
              <div className="flex items-center gap-4 mt-1.5 text-sm text-muted-foreground flex-wrap">
                <span className="font-mono">{creator.phone}</span>
                {creator.city && <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5" /> {creator.city}</span>}
                {creator.instagram_handle && (
                  <span className="flex items-center gap-1">
                    <Instagram className="w-3.5 h-3.5" /> @{creator.instagram_handle} · {creator.meta_followers.toLocaleString('en-IN')} followers
                  </span>
                )}
                <span className="flex items-center gap-1"><Calendar className="w-3.5 h-3.5" /> Joined {fmtDate(creator.created)}</span>
              </div>
              {creator.bio && <p className="text-sm text-muted-foreground mt-2">{creator.bio}</p>}
            </div>
          </CardContent>
        </Card>

        {/* ── Stats strip ── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Card><CardContent className="pt-4 pb-4">
            <div className="text-xs text-muted-foreground flex items-center gap-1.5 mb-1"><Video className="w-3.5 h-3.5" /> Collabs Done</div>
            <div className="text-xl font-bold">{creator.collabs_done}</div>
          </CardContent></Card>
          <Card><CardContent className="pt-4 pb-4">
            <div className="text-xs text-muted-foreground flex items-center gap-1.5 mb-1"><Wallet className="w-3.5 h-3.5" /> Total Earned</div>
            <div className="text-xl font-bold">{fmtR(creator.total_earned_inr)}</div>
          </CardContent></Card>
          <Card><CardContent className="pt-4 pb-4">
            <div className="text-xs text-muted-foreground flex items-center gap-1.5 mb-1"><Gift className="w-3.5 h-3.5" /> Barter Value (YTD)</div>
            <div className="text-xl font-bold">{fmtR(creator.barter_value_ytd_inr)}</div>
          </CardContent></Card>
          <Card className={creator.open_disputes > 0 ? 'border-red-200' : ''}>
            <CardContent className="pt-4 pb-4">
              <div className={cn('text-xs flex items-center gap-1.5 mb-1', creator.open_disputes > 0 ? 'text-red-600' : 'text-muted-foreground')}>
                <ShieldAlert className="w-3.5 h-3.5" /> Open Disputes
              </div>
              <div className={cn('text-xl font-bold', creator.open_disputes > 0 && 'text-red-600')}>{creator.open_disputes}</div>
            </CardContent>
          </Card>
        </div>

        {/* ── KYC ── */}
        <Card>
          <CardHeader className="pb-3">
            <h3 className="text-sm font-semibold flex items-center gap-1.5"><Landmark className="w-4 h-4" /> Payout KYC</h3>
          </CardHeader>
          <CardContent className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
            <div><div className="text-xs text-muted-foreground mb-0.5">Status</div><Badge variant="outline" className="capitalize">{creator.kyc.status.replace(/_/g, ' ')}</Badge></div>
            <div><div className="text-xs text-muted-foreground mb-0.5">Legal Name</div>{creator.kyc.legal_name || '—'}</div>
            <div><div className="text-xs text-muted-foreground mb-0.5">Bank Account</div><span className="font-mono">{creator.kyc.bank_account_masked || '—'}</span></div>
            <div><div className="text-xs text-muted-foreground mb-0.5">IFSC</div><span className="font-mono">{creator.kyc.bank_ifsc || '—'}</span></div>
            <div><div className="text-xs text-muted-foreground mb-0.5">Account Holder</div>{creator.kyc.bank_holder_name || '—'}</div>
            <div><div className="text-xs text-muted-foreground mb-0.5">Linked Account ID</div><span className="font-mono text-xs">{creator.kyc.linked_account_id || 'Not linked'}</span></div>
          </CardContent>
        </Card>

        {/* ── Rate Cards ── */}
        <Card>
          <CardHeader className="pb-3">
            <h3 className="text-sm font-semibold flex items-center gap-1.5"><Tag className="w-4 h-4" /> Rate Card</h3>
          </CardHeader>
          <CardContent>
            {creator.rate_cards.length === 0 ? (
              <p className="text-sm text-muted-foreground">No rate card set.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {creator.rate_cards.map(rc => (
                  <div key={rc.deliverable_type} className="flex items-center gap-2 text-sm rounded-md border px-3 py-1.5">
                    <span>{DELIVERABLE_LABELS[rc.deliverable_type] || rc.deliverable_type}</span>
                    <span className="font-semibold">{fmtR(rc.price_inr)}</span>
                    {rc.accepts_barter && <Badge variant="outline" className="text-[10px]">Barter OK</Badge>}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── Recent Deals ── */}
        <Card>
          <CardHeader className="pb-3">
            <h3 className="text-sm font-semibold">Recent Deals</h3>
          </CardHeader>
          <CardContent className="p-0">
            {creator.recent_deals.length === 0 ? (
              <p className="text-sm text-muted-foreground px-6 pb-4">No deals yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Outlet</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Value</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Date</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {creator.recent_deals.map(d => (
                    <TableRow key={d.name}>
                      <TableCell className="text-sm">{d.outlet_name || '—'}</TableCell>
                      <TableCell className="text-sm capitalize">{d.deal_type}</TableCell>
                      <TableCell className="text-sm font-medium">{fmtR(d.deal_type === 'cash' ? d.price_inr : d.fair_value_inr)}</TableCell>
                      <TableCell><Badge variant="secondary" className={cn('capitalize text-xs', DEAL_STATUS_STYLES[d.status])}>{d.status}</Badge></TableCell>
                      <TableCell className="text-xs text-muted-foreground">{fmtDate(d.creation)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* ── Open Disputes ── */}
        {creator.open_disputes_list.length > 0 && (
          <Card className="border-red-200">
            <CardHeader className="pb-3">
              <h3 className="text-sm font-semibold flex items-center gap-1.5 text-red-600"><ShieldAlert className="w-4 h-4" /> Open Disputes</h3>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Deal</TableHead>
                    <TableHead>Reason</TableHead>
                    <TableHead>Raised By</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {creator.open_disputes_list.map(d => (
                    <TableRow key={d.name}>
                      <TableCell className="font-mono text-xs">{d.deal_id}</TableCell>
                      <TableCell className="text-sm capitalize">{d.reason.replace(/_/g, ' ')}</TableCell>
                      <TableCell className="text-sm capitalize">{d.raised_by_role}</TableCell>
                      <TableCell><Badge variant="outline" className="capitalize text-xs">{d.status}</Badge></TableCell>
                      <TableCell className="text-xs text-muted-foreground">{fmtDate(d.creation)}</TableCell>
                      <TableCell>
                        <a
                          href={`/app/collab-dispute/${d.name}`}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-primary flex items-center gap-1 hover:underline">
                          Review <ExternalLink className="w-3 h-3" />
                        </a>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

      </div>

      {/* ── Status change confirm dialog ── */}
      <Dialog open={!!pendingAction} onOpenChange={(open) => { if (!open) { setPendingAction(null); setReason('') } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className={cn('flex items-center gap-2', pendingAction?.destructive && 'text-red-600')}>
              {pendingAction?.label} {creator.name}?
            </DialogTitle>
            <DialogDescription>
              This changes the creator's status immediately and is logged as a comment on their record for audit purposes.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <label className="text-sm font-medium">Reason (optional, shown in the audit log)</label>
            <Textarea value={reason} onChange={e => setReason(e.target.value)} placeholder="e.g. Fake follower count reported by a merchant" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setPendingAction(null); setReason('') }}>Cancel</Button>
            <Button variant={pendingAction?.destructive ? 'destructive' : 'default'} onClick={confirmAction} disabled={submitting}>
              {submitting ? 'Saving…' : `Confirm ${pendingAction?.label}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  )
}
