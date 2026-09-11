import { useCallback, useEffect, useRef, useState } from 'react'
import { useOutlet } from '@/contexts/OutletContext'
import { useFrappeGetCall, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent } from '@/components/ui/card'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import CreatorProfileSheet from '@/components/CreatorProfileSheet'
import { toast } from 'sonner'
import { getFrappeError } from '@/lib/utils'
import { Users, MapPin, Send, SlidersHorizontal, UsersRound, Star, IndianRupee, ShieldCheck, Crown, Zap, Eye } from 'lucide-react'

interface DiscoveredCreator {
  creator_id: string
  display_name: string
  meta_followers: number
  city: string
  profile_image: string | null
  club_id: string
  club_name: string
  category: string
  niche: string
  followers_count: number
  description: string | null
  available_this_week: boolean
  collabs_done: number
  avg_rating: number | null
  rating_count: number
  total_earned_inr: number
  badge_tier: string
  starting_rate_inr: number | null
  accepts_barter: boolean
}

function initials(name: string) {
  return name.split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('') || '?'
}

// Matches TIER_ORDER in flamezo_backend/flamezo/utils/creator_badges.py.
// "new_creator" isn't shown as a badge — everyone starts there, so it's
// not a distinguishing signal worth a pill on the card.
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
// Small solid-fill dot colors, for the avatar-corner tier badge — separate
// from BADGE_COLORS (which is the outlined pill style used elsewhere).
const BADGE_DOT_COLORS: Record<string, string> = {
  verified_creator: 'bg-blue-600',
  top_rated: 'bg-amber-500',
  elite_creator: 'bg-purple-600',
}

export default function CreatorMarketplaceDiscover() {
  const { selectedOutlet } = useOutlet()
  // Applied filters — only these drive the actual request; the modal edits
  // its own draft copy and commits here on "Apply" (see filtersOpen below).
  const [category, setCategory] = useState('')
  const [city, setCity] = useState('')
  const [minFollowers, setMinFollowers] = useState('')
  const [page, setPage] = useState(1)

  const [filtersOpen, setFiltersOpen] = useState(false)
  const [draftCategory, setDraftCategory] = useState('')
  const [draftCity, setDraftCity] = useState('')
  const [draftMinFollowers, setDraftMinFollowers] = useState('')

  const [invitingCreator, setInvitingCreator] = useState<DiscoveredCreator | null>(null)
  const [offerDetails, setOfferDetails] = useState('')
  const [deliverable, setDeliverable] = useState('')
  const [sending, setSending] = useState(false)
  const [viewingProfileId, setViewingProfileId] = useState<string | null>(null)

  const activeFilterCount = [category, city, minFollowers].filter(Boolean).length

  const openFilters = () => {
    setDraftCategory(category)
    setDraftCity(city)
    setDraftMinFollowers(minFollowers)
    setFiltersOpen(true)
  }

  const applyFilters = () => {
    setCategory(draftCategory)
    setCity(draftCity)
    setMinFollowers(draftMinFollowers)
    setPage(1)
    resetList()
    setFiltersOpen(false)
  }

  const clearFilters = () => {
    setDraftCategory('')
    setDraftCity('')
    setDraftMinFollowers('')
  }

  const params: Record<string, any> = { page, limit: 20 }
  if (category) params.category = category
  if (city) params.city = city
  if (minFollowers) params.min_followers = Number(minFollowers)

  const { data, mutate, isLoading } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.creator_collabs.discover_creators',
    params,
    `creator-discover-${JSON.stringify(params)}`,
  )
  const { call: sendInvite } = useFrappePostCall(
    'flamezo_backend.flamezo.api.creator_collabs.send_collab_invite',
  )

  const body: any = (data as any)?.message || data
  const pageCreators: DiscoveredCreator[] = body?.data?.creators || []
  const hasMore: boolean = !!body?.data?.has_more

  // Infinite scroll: accumulate each page's rows keyed by creator_id (so a
  // re-fetch of a page already seen — e.g. after sending an invite calls
  // mutate() — updates that row in place instead of duplicating it).
  // Filters changing resets `page` to 1 via applyFilters, and that reset
  // below clears the accumulator so stale rows from the old filter set
  // never linger under a new one.
  const [creators, setCreators] = useState<DiscoveredCreator[]>([])
  const loadedPageRef = useRef(0)
  useEffect(() => {
    if (!body?.data?.creators) return
    setCreators((prev) => {
      const merged = page === 1 ? [] : prev.filter((c) => !pageCreators.some((n) => n.creator_id === c.creator_id))
      return [...merged, ...pageCreators]
    })
    loadedPageRef.current = page
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [body])

  const resetList = () => {
    setCreators([])
    loadedPageRef.current = 0
  }

  // Refs, not state, for the values the observer's callback reads — the
  // observer itself is created exactly once (empty deps below). Recreating
  // it on every hasMore/isLoading/page change (the first version of this)
  // depends on effect-rerun timing lining up with the sentinel already
  // being in the DOM, which isn't guaranteed — that's what silently
  // stopped loading after page 1 in testing. Refs sidestep the whole
  // problem: the callback always reads current state without needing the
  // observer to be torn down and rebuilt.
  const hasMoreRef = useRef(hasMore)
  const isLoadingRef = useRef(isLoading)
  useEffect(() => { hasMoreRef.current = hasMore }, [hasMore])
  useEffect(() => { isLoadingRef.current = isLoading }, [isLoading])

  // A callback ref, not a plain useRef + a run-once effect — the sentinel
  // div doesn't exist on the very first render at all (the component
  // early-returns a skeleton while data is loading, see below), so an
  // effect with `[]` deps fires once against a still-null ref and never
  // gets a second chance once the real sentinel actually mounts. A
  // callback ref fires exactly when React attaches/detaches the DOM node,
  // whichever render that happens on — the correct fix, not a workaround.
  const observerInstanceRef = useRef<IntersectionObserver | null>(null)
  const sentinelRef = useCallback((node: HTMLDivElement | null) => {
    observerInstanceRef.current?.disconnect()
    observerInstanceRef.current = null
    if (!node) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMoreRef.current && !isLoadingRef.current) {
          setPage((p) => p + 1)
        }
      },
      { rootMargin: '400px' }, // start loading before the sentinel is actually on-screen
    )
    observer.observe(node)
    observerInstanceRef.current = observer
  }, [])

  const openInvite = (creator: DiscoveredCreator) => {
    setInvitingCreator(creator)
    setOfferDetails('')
    setDeliverable('')
  }

  const submitInvite = async () => {
    if (!selectedOutlet || !invitingCreator || !offerDetails.trim()) {
      toast.error('Describe what you\'re offering before sending the invite.')
      return
    }
    setSending(true)
    try {
      await sendInvite({
        outlet_id: selectedOutlet,
        creator_id: invitingCreator.creator_id,
        offer_details: offerDetails,
        deliverable: deliverable || undefined,
      })
      toast.success(`Invite sent to ${invitingCreator.display_name}`)
      setInvitingCreator(null)
      mutate()
    } catch (error: any) {
      toast.error('Could not send invite', { description: getFrappeError(error) })
    } finally {
      setSending(false)
    }
  }

  // Only the very first page load gets the full skeleton — loading page 2+
  // (creators.length already > 0) must not blank out the grid that's
  // already on screen, that's the whole point of infinite scroll.
  if (isLoading && !data && creators.length === 0) return <GenericPageSkeleton />

  return (
    <div className="space-y-6 pb-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Explore Creators</h1>
          <p className="text-muted-foreground text-sm mt-1">Find creators to collab with and send them an invite</p>
        </div>
        <div className="shrink-0">
          <Button variant="outline" onClick={openFilters} className="h-10 px-4 rounded-md shadow-sm hover:shadow transition-all bg-background border-border/60">
            <SlidersHorizontal className="h-4 w-4 mr-2 text-muted-foreground" />
            <span className="font-medium">Filters</span>
            {activeFilterCount > 0 && (
              <Badge variant="secondary" className="ml-2 h-5.5 min-w-[22px] px-1.5 flex items-center justify-center rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition-colors">
                {activeFilterCount}
              </Badge>
            )}
          </Button>
        </div>
      </div>

      <Dialog open={filtersOpen} onOpenChange={setFiltersOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader className="pb-4 border-b border-border/40">
            <DialogTitle className="text-xl flex items-center gap-2">
              <SlidersHorizontal className="h-5 w-5 text-primary" />
              Filter Creators
            </DialogTitle>
            <p className="text-sm text-muted-foreground mt-1.5">Narrow down the list to find the perfect match for your campaign.</p>
          </DialogHeader>
          <div className="space-y-5 py-4">
            <div className="space-y-2">
              <Label htmlFor="category" className="text-sm font-medium text-foreground/80">Category</Label>
              <div className="relative">
                <Input
                  id="category"
                  placeholder="e.g. Dining, Fashion"
                  value={draftCategory}
                  onChange={(e) => setDraftCategory(e.target.value)}
                  className="h-10 pl-9 bg-muted/30 focus-visible:bg-background"
                />
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground font-medium text-sm">#</span>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="city" className="text-sm font-medium text-foreground/80">City</Label>
              <div className="relative">
                <Input
                  id="city"
                  placeholder="e.g. Mumbai, Surat"
                  value={draftCity}
                  onChange={(e) => setDraftCity(e.target.value)}
                  className="h-10 pl-9 bg-muted/30 focus-visible:bg-background"
                />
                <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="followers" className="text-sm font-medium text-foreground/80">Minimum Followers</Label>
              <div className="relative">
                <Input
                  id="followers"
                  type="number"
                  placeholder="e.g. 10000"
                  value={draftMinFollowers}
                  onChange={(e) => setDraftMinFollowers(e.target.value)}
                  className="h-10 pl-9 bg-muted/30 focus-visible:bg-background"
                />
                <UsersRound className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              </div>
            </div>
          </div>
          <DialogFooter className="sm:justify-between pt-4 border-t border-border/40">
            <Button variant="ghost" onClick={clearFilters} className="text-muted-foreground hover:text-foreground">Clear All</Button>
            <Button onClick={applyFilters} className="px-6 rounded-md shadow-sm">Show Results</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {creators.length === 0 ? (
        <Card className="border-dashed bg-muted/30">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <div className="h-16 w-16 rounded-md bg-muted flex items-center justify-center mb-4">
              <Users className="h-8 w-8 text-muted-foreground/60" />
            </div>
            <h3 className="text-lg font-semibold mb-2">No creators found</h3>
            <p className="text-muted-foreground max-w-sm">
              We couldn't find any creators matching your current filters. Try adjusting the city, category, or follower range.
            </p>
            {activeFilterCount > 0 && (
              <Button variant="outline" onClick={clearFilters} className="mt-6 rounded-md">
                Clear Filters
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {creators.map((c) => (
            <Card key={c.creator_id} className="overflow-hidden flex flex-col group hover:shadow-lg transition-all duration-300 border-2 border-border hover:border-foreground/30">
              <CardContent className="p-5 flex flex-col flex-1 gap-4">
                {/* Header: Avatar + Info — clickable, opens the full profile
                    (see CreatorProfileSheet), same target Upwork's own name/
                    avatar click opens the freelancer profile. */}
                <button
                  type="button"
                  onClick={() => setViewingProfileId(c.creator_id)}
                  className="flex gap-4 items-center text-left cursor-pointer"
                >
                  <div className="relative shrink-0">
                    <Avatar className="h-16 w-16 border-2 border-background shadow-sm ring-1 ring-border/20">
                      {c.profile_image && <AvatarImage src={c.profile_image} alt={c.display_name} className="object-cover" />}
                      <AvatarFallback className="text-lg font-medium bg-muted text-muted-foreground">{initials(c.display_name)}</AvatarFallback>
                    </Avatar>
                    <span
                      className={`absolute -top-1 -left-1 h-4.5 w-4.5 rounded-full border-[2.5px] border-background ${c.available_this_week ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.4)]' : 'bg-muted-foreground/40'}`}
                      title={c.available_this_week ? 'Available this week' : 'At weekly accept cap'}
                    />
                    {BADGE_DOT_COLORS[c.badge_tier] && (
                      <span
                        className={`absolute -bottom-1 -right-1 flex h-5.5 w-5.5 items-center justify-center rounded-full border-[2.5px] border-background text-white shadow-sm ${BADGE_DOT_COLORS[c.badge_tier]}`}
                        title={BADGE_LABELS[c.badge_tier]}
                      >
                        {c.badge_tier === 'elite_creator' ? <Crown className="h-3 w-3" /> : <ShieldCheck className="h-3 w-3" />}
                      </span>
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="font-bold text-lg leading-tight truncate group-hover:text-primary transition-colors">{c.display_name}</h3>
                    <p className="text-sm text-muted-foreground truncate flex items-center gap-1.5 mt-1">
                      <span className="font-medium text-foreground/80">{c.niche || c.category || 'Creator'}</span>
                      <span className="text-border/60 text-xs">•</span>
                      <MapPin className="h-3 w-3" /> {c.city || '—'}
                    </p>
                  </div>
                </button>

                {/* Badges */}
                {(BADGE_LABELS[c.badge_tier] || c.category) && (
                  <div className="flex flex-wrap gap-2">
                    {BADGE_LABELS[c.badge_tier] && (
                      <Badge variant="secondary" className={`h-6.5 px-2.5 text-xs font-medium border ${BADGE_COLORS[c.badge_tier]}`}>
                        <ShieldCheck className="h-3.5 w-3.5 mr-1.5" />
                        {BADGE_LABELS[c.badge_tier]}
                      </Badge>
                    )}
                    {c.category && <Badge variant="outline" className="h-6.5 px-2.5 text-xs font-medium bg-secondary/30 border-border/50 text-secondary-foreground/80">{c.category}</Badge>}
                  </div>
                )}

                {/* Bio/Description */}
                <div className="flex-1">
                  {c.description ? (
                    <p className="text-sm text-muted-foreground leading-relaxed line-clamp-2">{c.description}</p>
                  ) : (
                    <p className="text-sm text-muted-foreground/50 italic">No description provided</p>
                  )}
                </div>

                {/* Stats Grid */}
                <div className="grid grid-cols-2 gap-x-4 gap-y-3 mt-1 pt-4 border-t border-border/50">
                  <div className="flex flex-col gap-1">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground/80">Rate</span>
                    <span className="font-semibold text-sm text-foreground flex items-center gap-1">
                      {c.starting_rate_inr ? `₹${c.starting_rate_inr.toLocaleString('en-IN')}+` : c.accepts_barter ? 'Barter OK' : 'Not set'}
                    </span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground/80">Reach</span>
                    <span className="font-semibold text-sm text-foreground flex items-center gap-1.5">
                      <UsersRound className="h-3.5 w-3.5 text-muted-foreground" />
                      {(c.meta_followers || c.followers_count || 0).toLocaleString('en-IN')}
                    </span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground/80">Earned</span>
                    <span className="font-semibold text-sm text-foreground flex items-center gap-1.5">
                      <IndianRupee className="h-3.5 w-3.5 text-muted-foreground" />
                      {c.total_earned_inr > 0 ? c.total_earned_inr.toLocaleString('en-IN') : '0'}
                    </span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground/80">Collabs & Rating</span>
                    <span className="font-semibold text-sm text-foreground flex items-center gap-1.5">
                      {c.avg_rating ? (
                        <span className="flex items-center gap-0.5">
                          {c.avg_rating} <Star className="h-3 w-3 fill-amber-400 text-amber-400" />
                        </span>
                      ) : (
                        <span className="text-muted-foreground font-normal">No rating</span>
                      )}
                      <span className="text-border/60 text-[10px]">•</span>
                      <span className={c.collabs_done > 0 ? 'text-emerald-600' : 'text-muted-foreground font-normal'}>
                        {c.collabs_done} done
                      </span>
                    </span>
                  </div>
                </div>
              </CardContent>

              <div className="px-5 pb-5 pt-0 mt-auto flex gap-2">
                <Button
                  variant="outline"
                  className="flex-1 rounded-lg font-medium cursor-pointer"
                  onClick={() => setViewingProfileId(c.creator_id)}
                >
                  <Eye className="h-4 w-4 mr-2" />
                  View Profile
                </Button>
                <Button
                  className={`flex-1 rounded-lg font-medium transition-all duration-300 cursor-pointer ${c.available_this_week ? 'group-hover:bg-primary/90 shadow-sm group-hover:shadow' : ''}`}
                  variant={c.available_this_week ? 'default' : 'secondary'}
                  disabled={!c.available_this_week}
                  onClick={() => openInvite(c)}
                >
                  {c.available_this_week ? (
                    <>
                      <Send className="h-4 w-4 mr-2" />
                      Send Invite
                    </>
                  ) : (
                    'At Capacity'
                  )}
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Infinite scroll — the sentinel loads the next page once it nears the
          viewport (see the IntersectionObserver above); no Previous/Next.
          Always mounted (not gated on creators.length) so sentinelRef is
          attached from the very first render — the observer above is only
          ever created once and needs a real element to observe by then. */}
      <div ref={sentinelRef} className="flex items-center justify-center py-6">
        {creators.length > 0 && (
          isLoading && loadedPageRef.current < page ? (
            <span className="text-sm text-muted-foreground">Loading more creators…</span>
          ) : !hasMore ? (
            <span className="text-sm text-muted-foreground">You've reached the end of the list.</span>
          ) : null
        )}
      </div>

      <Dialog open={!!invitingCreator} onOpenChange={(open) => !open && setInvitingCreator(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Invite {invitingCreator?.display_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>What are you offering? *</Label>
              <Textarea
                placeholder="e.g. Free meal for two + ₹500, in exchange for a Chills reel"
                value={offerDetails}
                onChange={(e) => setOfferDetails(e.target.value)}
                rows={4}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Deliverable (optional)</Label>
              <Input
                placeholder="e.g. 1 Instagram reel"
                value={deliverable}
                onChange={(e) => setDeliverable(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setInvitingCreator(null)} disabled={sending}>
              Cancel
            </Button>
            <Button onClick={submitInvite} disabled={sending}>
              {sending ? 'Sending…' : 'Send Invite'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <CreatorProfileSheet
        creatorId={viewingProfileId}
        onClose={() => setViewingProfileId(null)}
        onInvite={() => {
          const c = creators.find((x) => x.creator_id === viewingProfileId)
          if (c) {
            setViewingProfileId(null)
            openInvite(c)
          }
        }}
      />
    </div>
  )
}
