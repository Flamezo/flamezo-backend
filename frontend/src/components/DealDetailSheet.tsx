import { useState } from 'react'
import { useFrappeGetCall } from '@/lib/frappe'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import CreatorProfileSheet from '@/components/CreatorProfileSheet'
import {
  IndianRupee, CalendarClock, CheckCircle2, Circle, Clock, ShieldCheck,
  AlertTriangle, Wallet, FileCheck2,
} from 'lucide-react'

function initials(name: string) {
  return (name || '?').split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('') || '?'
}

const STATUS_COLORS: Record<string, string> = {
  offered: 'bg-muted text-muted-foreground border-border',
  accepted: 'bg-blue-50 text-blue-700 border-blue-200',
  funded: 'bg-blue-50 text-blue-700 border-blue-200',
  delivered: 'bg-amber-50 text-amber-700 border-amber-200',
  released: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  disputed: 'bg-red-50 text-red-700 border-red-200',
  refunded: 'bg-muted text-muted-foreground border-border',
  cancelled: 'bg-muted text-muted-foreground border-border',
}
const STATUS_LABELS: Record<string, string> = {
  offered: 'Offered', accepted: 'Accepted', funded: 'Funded', delivered: 'Delivered',
  released: 'Released', disputed: 'Disputed', refunded: 'Refunded', cancelled: 'Cancelled',
}
const DELIVERABLE_LABELS: Record<string, string> = {
  native_chills: 'Chills reel', native_club_post: 'Club Talks post',
  instagram_reel: 'Instagram reel', instagram_story: 'Instagram story', bundle: 'Bundle',
}

interface DealDetail {
  deal_id: string
  status: string
  deal_type: 'cash' | 'barter'
  creator_id: string
  creator_name: string | null
  creator_profile_image: string | null
  outlet_id: string
  outlet_name: string | null
  price_inr: number
  fair_value_inr: number
  commission_pct: number
  deadline: string | null
  origin: 'gig' | 'direct_invite' | 'standing_offer'
  accepted_at: string | null
  funded_at: string | null
  delivered_at: string | null
  released_at: string | null
  creation: string
  terms: { deliverables?: { type: string; count: number }[]; message?: string }
  escrow: { state: string; amount_inr: number; platform_fee_inr: number; creator_net_inr: number; held_at: string | null; released_at: string | null } | null
  delivery: { deliverable_type: string; verified_at: string | null; disclosure_verified: boolean; verification_method: string }[]
  dispute: string | null
  objection_window_ends_at: string | null
}

// Which steps apply — cash walks through Funded, barter skips straight to
// Delivered (see collab_deal.py's own state machine).
function timelineSteps(d: DealDetail) {
  const steps = [
    { key: 'offered', label: 'Offered', at: d.creation },
    { key: 'accepted', label: 'Accepted', at: d.accepted_at },
  ]
  if (d.deal_type === 'cash') steps.push({ key: 'funded', label: 'Escrow Funded', at: d.funded_at })
  steps.push({ key: 'delivered', label: 'Delivered', at: d.delivered_at })
  steps.push({ key: 'released', label: 'Released', at: d.released_at })
  return steps
}

interface DealDetailSheetProps {
  dealId: string | null
  outletId?: string
  phone?: string
  onClose: () => void
  onAccept?: () => void
  onFund?: () => void
  onRelease?: () => void
  busy?: boolean
}

export default function DealDetailSheet({ dealId, outletId, phone, onClose, onAccept, onFund, onRelease, busy }: DealDetailSheetProps) {
  const [viewingCreatorId, setViewingCreatorId] = useState<string | null>(null)
  const { data, isLoading } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.collab_deals.get_deal',
    dealId ? { deal_id: dealId, ...(outletId ? { outlet_id: outletId } : {}), ...(phone ? { phone } : {}) } : undefined,
    dealId ? `deal-detail-${dealId}` : undefined,
  )
  const body: any = (data as any)?.message || data
  const d: DealDetail | undefined = body?.data

  const steps = d ? timelineSteps(d) : []
  const currentIdx = d ? steps.findIndex((s) => s.key === d.status) : -1
  const isTerminalOther = d && !steps.some((s) => s.key === d.status) // disputed/refunded/cancelled

  return (
    <>
    <Sheet open={!!dealId} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-xl overflow-y-auto p-0">
        {isLoading || !d ? (
          <div className="p-6 space-y-4 animate-pulse">
            <div className="h-6 w-48 bg-muted rounded" />
            <div className="h-4 w-64 bg-muted rounded" />
          </div>
        ) : (
          <div className="pb-8">
            {/* Header */}
            <div className="bg-foreground text-background px-6 pt-6 pb-5">
              <SheetHeader className="text-left space-y-3 pr-10">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <SheetTitle className="text-background text-lg">
                    {d.deal_type === 'cash' ? `₹${d.price_inr.toLocaleString('en-IN')} Cash Collab` : `₹${d.fair_value_inr.toLocaleString('en-IN')} Barter Collab`}
                  </SheetTitle>
                  <Badge variant="outline" className={`h-6 px-2 text-xs shrink-0 ${STATUS_COLORS[d.status] || 'bg-background/10 text-background border-background/30'}`}>
                    {STATUS_LABELS[d.status] || d.status}
                  </Badge>
                </div>
                <button
                  type="button"
                  onClick={() => setViewingCreatorId(d.creator_id)}
                  className="flex items-center gap-3 text-left cursor-pointer group"
                >
                  <Avatar className="h-10 w-10 border-2 border-background/30 group-hover:ring-2 group-hover:ring-background/40 transition-all">
                    {d.creator_profile_image && <AvatarImage src={d.creator_profile_image} alt={d.creator_name || d.creator_id} />}
                    <AvatarFallback className="text-xs">{initials(d.creator_name || d.creator_id)}</AvatarFallback>
                  </Avatar>
                  <div className="text-sm">
                    <div className="font-medium group-hover:underline">{d.creator_name || d.creator_id}</div>
                    <div className="text-background/60 text-xs">{d.outlet_name || d.outlet_id}</div>
                  </div>
                </button>
              </SheetHeader>
            </div>

            <div className="px-6">
              {/* Action buttons, contextual to status — same handlers as the list page */}
              {(onAccept || onFund || onRelease) && (
                <div className="flex gap-2 pt-4">
                  {d.status === 'offered' && onAccept && (
                    <Button className="flex-1" disabled={busy} onClick={onAccept}>{busy ? 'Accepting…' : 'Accept'}</Button>
                  )}
                  {d.status === 'accepted' && d.deal_type === 'cash' && onFund && (
                    <Button className="flex-1" disabled={busy} onClick={onFund}>
                      <Wallet className="h-3.5 w-3.5 mr-1.5" /> {busy ? 'Opening…' : 'Fund Escrow'}
                    </Button>
                  )}
                  {d.status === 'delivered' && onRelease && (
                    <Button className="flex-1" disabled={busy} onClick={onRelease}>
                      <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" /> {busy ? 'Releasing…' : 'Approve & Release'}
                    </Button>
                  )}
                </div>
              )}

              {/* Timeline */}
              <div className="py-5 border-b">
                <h3 className="text-sm font-semibold mb-3">Status</h3>
                {isTerminalOther ? (
                  <div className="flex items-center gap-2 text-sm text-red-600">
                    <AlertTriangle className="h-4 w-4" /> {STATUS_LABELS[d.status] || d.status}
                  </div>
                ) : (
                  <div className="space-y-3">
                    {steps.map((s, i) => {
                      const done = i <= currentIdx
                      return (
                        <div key={s.key} className="flex items-center gap-3 text-sm">
                          {done ? (
                            <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                          ) : (
                            <Circle className="h-4 w-4 text-muted-foreground/40 shrink-0" />
                          )}
                          <span className={done ? 'font-medium' : 'text-muted-foreground'}>{s.label}</span>
                          {s.at && <span className="text-xs text-muted-foreground ml-auto">{String(s.at).slice(0, 10)}</span>}
                        </div>
                      )
                    })}
                  </div>
                )}
                {d.status === 'delivered' && d.objection_window_ends_at && (
                  <div className="flex items-center gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2 mt-3">
                    <Clock className="h-3.5 w-3.5 shrink-0" />
                    Auto-releases {String(d.objection_window_ends_at).slice(0, 16).replace('T', ' ')} if not actioned
                  </div>
                )}
              </div>

              {/* Deal terms */}
              <div className="grid grid-cols-2 gap-3 py-5 border-b text-sm">
                <div>
                  <div className="text-xs text-muted-foreground">Value</div>
                  <div className="font-medium flex items-center gap-0.5">
                    <IndianRupee className="h-3.5 w-3.5" />
                    {(d.deal_type === 'cash' ? d.price_inr : d.fair_value_inr).toLocaleString('en-IN')}
                    {d.deal_type === 'barter' && <span className="text-xs text-muted-foreground ml-1">(barter)</span>}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Commission</div>
                  <div className="font-medium">{d.commission_pct}%</div>
                </div>
                {d.deadline && (
                  <div>
                    <div className="text-xs text-muted-foreground">Deadline</div>
                    <div className="font-medium flex items-center gap-1"><CalendarClock className="h-3.5 w-3.5" /> {d.deadline}</div>
                  </div>
                )}
                <div>
                  <div className="text-xs text-muted-foreground">Origin</div>
                  <div className="font-medium capitalize">{d.origin.replace('_', ' ')}</div>
                </div>
              </div>

              {/* Deliverables required */}
              {(d.terms.deliverables?.length ?? 0) > 0 && (
                <div className="py-5 border-b">
                  <h3 className="text-sm font-semibold mb-2">Deliverables</h3>
                  <div className="flex flex-wrap gap-1.5">
                    {d.terms.deliverables!.map((dl, i) => (
                      <Badge key={i} variant="outline" className="h-6 px-2 text-xs">
                        {dl.count}× {DELIVERABLE_LABELS[dl.type] || dl.type}
                      </Badge>
                    ))}
                  </div>
                  {d.terms.message && (
                    <p className="text-sm text-muted-foreground mt-2">"{d.terms.message}"</p>
                  )}
                </div>
              )}

              {/* Escrow */}
              {d.escrow && (
                <div className="py-5 border-b">
                  <h3 className="text-sm font-semibold mb-2 flex items-center gap-1.5">
                    <ShieldCheck className="h-4 w-4" /> Escrow
                  </h3>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <div className="text-xs text-muted-foreground">Status</div>
                      <div className="font-medium capitalize">{d.escrow.state}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">Held</div>
                      <div className="font-medium flex items-center gap-0.5"><IndianRupee className="h-3.5 w-3.5" />{d.escrow.amount_inr.toLocaleString('en-IN')}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">Platform fee</div>
                      <div className="font-medium flex items-center gap-0.5"><IndianRupee className="h-3.5 w-3.5" />{d.escrow.platform_fee_inr.toLocaleString('en-IN')}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">Creator receives</div>
                      <div className="font-medium flex items-center gap-0.5"><IndianRupee className="h-3.5 w-3.5" />{d.escrow.creator_net_inr.toLocaleString('en-IN')}</div>
                    </div>
                  </div>
                </div>
              )}

              {/* Delivery proof */}
              {d.delivery.length > 0 && (
                <div className="py-5">
                  <h3 className="text-sm font-semibold mb-2 flex items-center gap-1.5">
                    <FileCheck2 className="h-4 w-4" /> Delivery Proof
                  </h3>
                  <div className="space-y-2">
                    {d.delivery.map((dp, i) => (
                      <div key={i} className="flex items-center justify-between text-sm rounded-md border px-3 py-2">
                        <span>{DELIVERABLE_LABELS[dp.deliverable_type] || dp.deliverable_type}</span>
                        <span className="flex items-center gap-2 text-xs text-muted-foreground">
                          <span className="capitalize">{dp.verification_method.replace('_', ' ')}</span>
                          {dp.disclosure_verified && (
                            <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
                              <ShieldCheck className="h-2.5 w-2.5 mr-1" /> Disclosed
                            </Badge>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </SheetContent>

    </Sheet>
    <CreatorProfileSheet creatorId={viewingCreatorId} onClose={() => setViewingCreatorId(null)} />
    </>
  )
}
