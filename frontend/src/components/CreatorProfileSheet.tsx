import { useFrappeGetCall } from '@/lib/frappe'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  MapPin, Star, IndianRupee, ShieldCheck, Crown, Zap, Instagram,
  UsersRound, Eye, CalendarCheck, Send, Gift, Video,
} from 'lucide-react'

function initials(name: string) {
  return (name || '?').split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('') || '?'
}

const BADGE_LABELS: Record<string, string> = {
  verified_creator: 'Verified Creator',
  top_rated: 'Top Rated',
  elite_creator: 'Elite Creator',
}
const BADGE_COLORS: Record<string, string> = {
  verified_creator: 'bg-blue-50 text-blue-700 border-blue-200',
  top_rated: 'bg-amber-50 text-amber-700 border-amber-200',
  elite_creator: 'bg-purple-50 text-purple-700 border-purple-200',
}
const DELIVERABLE_LABELS: Record<string, string> = {
  native_chills: 'Chills reel',
  native_club_post: 'Club Talks post',
  instagram_reel: 'Instagram reel',
  instagram_story: 'Instagram story',
  bundle: 'Bundle',
}

interface RateCard {
  deliverable_type: string
  price_inr: number
  accepts_barter: boolean
  barter_min_value_inr: number
}
interface RecentCollab {
  outlet_name: string
  detail: string | null
  rating: number | null
  completed_at: string | null
  source: 'invite' | 'deal'
  value_inr: number | null
  deal_type: 'cash' | 'barter' | null
}
interface CreatorProfile {
  name: string
  display_name: string
  profile_image: string | null
  bio: string | null
  city: string | null
  instagram_handle: string | null
  meta_followers: number
  meta_avg_views: number
  follower_count_last_synced: string | null
  approved_at: string | null
  club: { club_name: string; category: string; niche: string; description: string; cover_image: string | null; followers_count: number } | null
  rate_cards: RateCard[]
  collabs_done: number
  avg_rating: number | null
  rating_count: number
  total_earned_inr: number
  badge_tier: string
  starting_rate_inr: number | null
  accepts_barter: boolean
  available_this_week: boolean
  recent_collabs: RecentCollab[]
}

interface CreatorProfileSheetProps {
  creatorId: string | null
  onClose: () => void
  onInvite?: () => void
}

export default function CreatorProfileSheet({ creatorId, onClose, onInvite }: CreatorProfileSheetProps) {
  const { data, isLoading } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.creator_collabs.get_creator_profile',
    creatorId ? { creator_id: creatorId } : undefined,
    creatorId ? `creator-profile-${creatorId}` : undefined,
  )
  const body: any = (data as any)?.message || data
  const p: CreatorProfile | undefined = body?.data

  return (
    <Sheet open={!!creatorId} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-xl overflow-y-auto p-0">
        {isLoading || !p ? (
          <div className="p-6 space-y-4 animate-pulse">
            <div className="h-20 w-20 rounded-full bg-muted" />
            <div className="h-5 w-40 bg-muted rounded" />
            <div className="h-4 w-64 bg-muted rounded" />
          </div>
        ) : (
          <div className="pb-8">
            {/* Cover image */}
            <div className="h-28 bg-muted relative overflow-hidden">
              {p.club?.cover_image && (
                <img src={p.club.cover_image} alt="" className="h-full w-full object-cover" />
              )}
            </div>

            <div className="px-6">
              {/* Header */}
              <div className="-mt-10 flex items-end justify-between">
                <Avatar className="h-20 w-20 border-4 border-background shadow-sm">
                  {p.profile_image && <AvatarImage src={p.profile_image} alt={p.display_name} />}
                  <AvatarFallback className="text-xl">{initials(p.display_name)}</AvatarFallback>
                </Avatar>
              </div>

              <SheetHeader className="mt-3 text-left space-y-1">
                <SheetTitle className="flex items-center gap-2 text-xl">
                  {p.display_name}
                  {BADGE_LABELS[p.badge_tier] && (
                    <span title={BADGE_LABELS[p.badge_tier]}>
                      {p.badge_tier === 'elite_creator' ? (
                        <Crown className="h-4 w-4 text-purple-600" />
                      ) : (
                        <ShieldCheck className="h-4 w-4 text-blue-600" />
                      )}
                    </span>
                  )}
                </SheetTitle>
                <div className="text-sm text-muted-foreground">
                  {p.club?.niche || p.club?.category || 'Creator'}
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
                  <span className="flex items-center gap-1"><MapPin className="h-3 w-3" /> {p.city || '—'}</span>
                  {p.instagram_handle && (
                    <a
                      href={`https://instagram.com/${p.instagram_handle.replace('@', '')}`}
                      target="_blank" rel="noreferrer"
                      className="flex items-center gap-1 text-pink-600 hover:underline"
                    >
                      <Instagram className="h-3 w-3" /> @{p.instagram_handle.replace('@', '')}
                    </a>
                  )}
                  {p.available_this_week && (
                    <span className="flex items-center gap-1 text-emerald-600 font-medium">
                      <Zap className="h-3 w-3" /> Available now
                    </span>
                  )}
                </div>
                {BADGE_LABELS[p.badge_tier] && (
                  <Badge variant="outline" className={`w-fit h-6 px-2 text-xs mt-1 ${BADGE_COLORS[p.badge_tier]}`}>
                    <ShieldCheck className="h-3 w-3 mr-1" /> {BADGE_LABELS[p.badge_tier]}
                  </Badge>
                )}
              </SheetHeader>

              {onInvite && (
                <Button className="mt-4 w-full" disabled={!p.available_this_week} onClick={onInvite}>
                  <Send className="h-3.5 w-3.5 mr-1.5" /> Send Invite
                </Button>
              )}

              {/* Stats strip — the Upwork "Total earnings / Total jobs / Total hours" row */}
              <div className="grid grid-cols-3 gap-3 mt-5 py-4 border-y">
                <div>
                  <div className="text-lg font-bold flex items-center gap-0.5">
                    <IndianRupee className="h-4 w-4" />{p.total_earned_inr.toLocaleString('en-IN')}
                  </div>
                  <div className="text-xs text-muted-foreground">Total earned</div>
                </div>
                <div>
                  <div className="text-lg font-bold">{p.collabs_done}</div>
                  <div className="text-xs text-muted-foreground">Collabs done</div>
                </div>
                <div>
                  <div className="text-lg font-bold flex items-center gap-1">
                    {p.avg_rating ? (
                      <>
                        <Star className="h-4 w-4 fill-amber-400 text-amber-400" />
                        {p.avg_rating}
                      </>
                    ) : '—'}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {p.rating_count ? `${p.rating_count} review${p.rating_count === 1 ? '' : 's'}` : 'No reviews yet'}
                  </div>
                </div>
              </div>

              {/* Reach */}
              <div className="grid grid-cols-2 gap-3 py-4 border-b text-sm">
                <div className="flex items-center gap-2">
                  <UsersRound className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <div className="font-medium">{(p.meta_followers || p.club?.followers_count || 0).toLocaleString('en-IN')}</div>
                    <div className="text-xs text-muted-foreground">
                      Followers{p.follower_count_last_synced ? ` · synced ${p.follower_count_last_synced.slice(0, 10)}` : ' · not yet synced'}
                    </div>
                  </div>
                </div>
                {p.meta_avg_views > 0 && (
                  <div className="flex items-center gap-2">
                    <Eye className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <div className="font-medium">{p.meta_avg_views.toLocaleString('en-IN')}</div>
                      <div className="text-xs text-muted-foreground">Avg. views</div>
                    </div>
                  </div>
                )}
                {p.approved_at && (
                  <div className="flex items-center gap-2">
                    <CalendarCheck className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <div className="font-medium">{p.approved_at.slice(0, 10)}</div>
                      <div className="text-xs text-muted-foreground">Creator since</div>
                    </div>
                  </div>
                )}
              </div>

              {/* Bio */}
              {(p.bio || p.club?.description) && (
                <div className="py-4 border-b">
                  <h3 className="text-sm font-semibold mb-2">About</h3>
                  <p className="text-sm text-muted-foreground whitespace-pre-line">{p.bio || p.club?.description}</p>
                </div>
              )}

              {/* Rate card */}
              <div className="py-4 border-b">
                <h3 className="text-sm font-semibold mb-2">Rates</h3>
                {p.rate_cards.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    {p.accepts_barter ? 'Open to barter, no fixed cash rate set.' : 'No rate card set yet.'}
                  </p>
                ) : (
                  <div className="space-y-2">
                    {p.rate_cards.map((rc) => (
                      <div key={rc.deliverable_type} className="flex items-center justify-between text-sm rounded-md border px-3 py-2">
                        <span className="flex items-center gap-2">
                          <Video className="h-3.5 w-3.5 text-muted-foreground" />
                          {DELIVERABLE_LABELS[rc.deliverable_type] || rc.deliverable_type}
                        </span>
                        <span className="flex items-center gap-2">
                          <span className="font-medium flex items-center gap-0.5">
                            <IndianRupee className="h-3.5 w-3.5" />{rc.price_inr.toLocaleString('en-IN')}
                          </span>
                          {rc.accepts_barter === true && (
                            <Badge variant="outline" className="h-5 px-1.5 text-[11px]">
                              <Gift className="h-2.5 w-2.5 mr-1" /> Barter OK
                            </Badge>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Collab history */}
              <div className="py-4">
                <h3 className="text-sm font-semibold mb-2">Collab history on Flamezo</h3>
                {p.recent_collabs.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No completed collabs yet.</p>
                ) : (
                  <div className="space-y-2">
                    {p.recent_collabs.map((h, i) => (
                      <div key={i} className="flex items-center justify-between text-sm rounded-md border px-3 py-2">
                        <div className="min-w-0">
                          <div className="font-medium truncate">{h.outlet_name || 'Flamezo merchant'}</div>
                          {h.completed_at && (
                            <div className="text-xs text-muted-foreground">{h.completed_at.slice(0, 10)}</div>
                          )}
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {h.value_inr != null && (
                            <span className="flex items-center gap-0.5 text-muted-foreground">
                              <IndianRupee className="h-3 w-3" />{h.value_inr.toLocaleString('en-IN')}
                            </span>
                          )}
                          {h.rating != null && (
                            <span className="flex items-center gap-0.5 text-muted-foreground">
                              <Star className="h-3 w-3 fill-amber-400 text-amber-400" />{h.rating}
                            </span>
                          )}
                        </div>
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
  )
}
