import { useState } from 'react'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import CreatorProfileSheet from '@/components/CreatorProfileSheet'
import { IndianRupee, Users, CalendarClock, Gift, Video, ShieldCheck, UsersRound } from 'lucide-react'

function initials(name: string) {
  return (name || '?').split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('') || '?'
}

const STATUS_COLORS: Record<string, string> = {
  open: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  filled: 'bg-blue-50 text-blue-700 border-blue-200',
  expired: 'bg-muted text-muted-foreground border-border',
  cancelled: 'bg-muted text-muted-foreground border-border',
}
const STATUS_LABELS: Record<string, string> = {
  open: 'Open', filled: 'Filled', expired: 'Expired', cancelled: 'Cancelled',
}
const DELIVERABLE_LABELS: Record<string, string> = {
  native_chills: 'Chills reel', native_club_post: 'Club Talks post',
  instagram_reel: 'Instagram reel', instagram_story: 'Instagram story', bundle: 'Bundle',
}
const BADGE_TIER_LABELS: Record<string, string> = {
  new_creator: 'New Creator+', verified_creator: 'Verified Creator+',
  top_rated: 'Top Rated+', elite_creator: 'Elite Creator only',
}

export interface GigDetail {
  name: string
  title: string
  status: string
  budget_inr: number
  barter_allowed: number
  barter_details: string | null
  category: string
  expires_at: string
  creation: string
  applications_count: number
  deliverables: { type: string; count: number }[]
  min_followers: number
  min_badge_tier: string | null
}

export interface Application {
  deal_id: string
  creator_id: string
  creator_name: string
  creator_profile_image: string | null
  follower_count: number
  deal_type: 'cash' | 'barter'
  proposed_price_inr: number
  proposed_fair_value_inr: number
  status: string
  creation: string
}

interface GigDetailSheetProps {
  gig: GigDetail | null
  applications: Application[]
  loading: boolean
  onClose: () => void
  onAccept: (app: Application) => void
  onClose_Gig?: () => void
}

export default function GigDetailSheet({ gig, applications, loading, onClose, onAccept, onClose_Gig }: GigDetailSheetProps) {
  const [viewingCreatorId, setViewingCreatorId] = useState<string | null>(null)
  return (
    <>
    <Sheet open={!!gig} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-xl overflow-y-auto p-0">
        {!gig ? null : (
          <div className="pb-8">
            {/* Header */}
            <div className="bg-foreground text-background px-6 pt-6 pb-5">
              <SheetHeader className="text-left space-y-2 pr-10">
                <div className="flex items-start justify-between gap-3">
                  <SheetTitle className="text-background text-lg leading-tight">{gig.title}</SheetTitle>
                  <Badge variant="outline" className={`h-6 px-2 text-xs shrink-0 ${STATUS_COLORS[gig.status] || 'bg-background/10 text-background border-background/30'}`}>
                    {STATUS_LABELS[gig.status] || gig.status}
                  </Badge>
                </div>
                {gig.category && <div className="text-background/60 text-sm">{gig.category}</div>}
              </SheetHeader>

              {gig.status === 'open' && onClose_Gig && (
                <Button variant="outline" size="sm" className="mt-3 bg-background/10 border-background/30 text-background hover:bg-background/20 hover:text-background" onClick={onClose_Gig}>
                  Close this collab
                </Button>
              )}
            </div>

            <div className="px-6">
              {/* Stats */}
              <div className="grid grid-cols-3 gap-3 py-5 border-b text-sm">
                <div>
                  <div className="text-xs text-muted-foreground">Offering</div>
                  <div className="font-medium flex items-center gap-1">
                    {gig.barter_allowed ? <Gift className="h-3.5 w-3.5" /> : <IndianRupee className="h-3.5 w-3.5" />}
                    {gig.barter_allowed ? 'Barter' : gig.budget_inr.toLocaleString('en-IN')}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Applications</div>
                  <div className="font-medium flex items-center gap-1"><Users className="h-3.5 w-3.5" />{gig.applications_count}</div>
                </div>
                {gig.expires_at && (
                  <div>
                    <div className="text-xs text-muted-foreground">Expires</div>
                    <div className="font-medium flex items-center gap-1"><CalendarClock className="h-3.5 w-3.5" />{gig.expires_at.slice(0, 10)}</div>
                  </div>
                )}
              </div>

              {/* Requirements */}
              <div className="py-5 border-b space-y-3">
                <h3 className="text-sm font-semibold">Requirements</h3>
                {gig.deliverables?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {gig.deliverables.map((dl, i) => (
                      <Badge key={i} variant="outline" className="h-6 px-2 text-xs">
                        {dl.count}× {DELIVERABLE_LABELS[dl.type] || dl.type}
                      </Badge>
                    ))}
                  </div>
                )}
                {(gig.min_followers > 0 || gig.min_badge_tier) && (
                  <div className="flex flex-wrap gap-3 text-sm text-muted-foreground">
                    {gig.min_followers > 0 && (
                      <span className="flex items-center gap-1"><UsersRound className="h-3.5 w-3.5" /> {gig.min_followers.toLocaleString('en-IN')}+ followers</span>
                    )}
                    {gig.min_badge_tier && (
                      <span className="flex items-center gap-1"><ShieldCheck className="h-3.5 w-3.5" /> {BADGE_TIER_LABELS[gig.min_badge_tier] || gig.min_badge_tier}</span>
                    )}
                  </div>
                )}
                {gig.barter_allowed === 1 && gig.barter_details && (
                  <p className="text-sm text-muted-foreground">{gig.barter_details}</p>
                )}
              </div>

              {/* Applications */}
              <div className="py-5">
                <h3 className="text-sm font-semibold mb-3">Applications</h3>
                {loading ? (
                  <div className="py-8 text-center text-sm text-muted-foreground">Loading…</div>
                ) : applications.length === 0 ? (
                  <div className="py-8 text-center text-sm text-muted-foreground">No applications yet.</div>
                ) : (
                  <div className="space-y-2">
                    {applications.map((app) => (
                      <div key={app.deal_id} className="flex items-center gap-3 rounded-md border p-3">
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); setViewingCreatorId(app.creator_id) }}
                          className="shrink-0 cursor-pointer"
                        >
                          <Avatar className="h-10 w-10 border hover:ring-2 hover:ring-primary/30 transition-all">
                            {app.creator_profile_image && <AvatarImage src={app.creator_profile_image} alt={app.creator_name} />}
                            <AvatarFallback className="text-xs">{initials(app.creator_name)}</AvatarFallback>
                          </Avatar>
                        </button>
                        <div className="min-w-0 flex-1">
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); setViewingCreatorId(app.creator_id) }}
                            className="font-medium text-sm text-left cursor-pointer hover:text-primary hover:underline transition-colors"
                          >
                            {app.creator_name}
                          </button>
                          <div className="text-xs text-muted-foreground flex items-center gap-1">
                            <Video className="h-3 w-3" />
                            {app.follower_count?.toLocaleString('en-IN')} followers
                            {app.deal_type === 'barter'
                              ? (app.proposed_fair_value_inr ? ` · ₹${app.proposed_fair_value_inr.toLocaleString('en-IN')} barter value` : ' · barter')
                              : (app.proposed_price_inr ? ` · ₹${app.proposed_price_inr.toLocaleString('en-IN')} proposed` : '')}
                          </div>
                        </div>
                        {app.status === 'offered' ? (
                          <Button size="sm" className="shrink-0" onClick={() => onAccept(app)}>Accept</Button>
                        ) : (
                          <Badge variant="secondary" className="shrink-0">{app.status}</Badge>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
    <CreatorProfileSheet creatorId={viewingCreatorId} onClose={() => setViewingCreatorId(null)} />
    </>
  )
}
