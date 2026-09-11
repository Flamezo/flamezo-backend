import { useState } from 'react'
import { useOutlet } from '@/contexts/OutletContext'
import { useFrappeGetCall, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { toast } from 'sonner'
import { getFrappeError } from '@/lib/utils'
import { Users, MapPin, Send, ChevronLeft, ChevronRight, Sparkles } from 'lucide-react'

interface DiscoveredCreator {
  creator_id: string
  display_name: string
  meta_followers: number
  city: string
  club_id: string
  club_name: string
  category: string
  niche: string
  followers_count: number
  available_this_week: boolean
}

export default function CreatorMarketplaceDiscover() {
  const { selectedOutlet } = useOutlet()
  const [category, setCategory] = useState('')
  const [city, setCity] = useState('')
  const [minFollowers, setMinFollowers] = useState('')
  const [page, setPage] = useState(1)
  const [invitingCreator, setInvitingCreator] = useState<DiscoveredCreator | null>(null)
  const [offerDetails, setOfferDetails] = useState('')
  const [deliverable, setDeliverable] = useState('')
  const [sending, setSending] = useState(false)

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
  const creators: DiscoveredCreator[] = body?.data?.creators || []
  const hasMore: boolean = !!body?.data?.has_more

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

  if (isLoading && !data) return <GenericPageSkeleton />

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="pt-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="space-y-1.5">
            <Label>Category</Label>
            <Input
              placeholder="e.g. dining"
              value={category}
              onChange={(e) => { setCategory(e.target.value); setPage(1) }}
            />
          </div>
          <div className="space-y-1.5">
            <Label>City</Label>
            <Input
              placeholder="e.g. Surat"
              value={city}
              onChange={(e) => { setCity(e.target.value); setPage(1) }}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Min. followers</Label>
            <Input
              type="number"
              placeholder="e.g. 5000"
              value={minFollowers}
              onChange={(e) => { setMinFollowers(e.target.value); setPage(1) }}
            />
          </div>
        </CardContent>
      </Card>

      {creators.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <Users className="h-10 w-10 mx-auto mb-3 opacity-40" />
            No creators match these filters yet — try widening the city or follower range.
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {creators.map((c) => (
            <Card key={c.creator_id} className="flex flex-col">
              <CardContent className="pt-6 flex-1 flex flex-col gap-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold">{c.display_name}</div>
                    <div className="text-sm text-muted-foreground flex items-center gap-1">
                      <MapPin className="h-3.5 w-3.5" /> {c.city || '—'}
                    </div>
                  </div>
                  {c.available_this_week ? (
                    <Badge variant="secondary" className="shrink-0">Available</Badge>
                  ) : (
                    <Badge variant="outline" className="shrink-0 text-muted-foreground">At weekly cap</Badge>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5 text-xs">
                  {c.category && <Badge variant="outline">{c.category}</Badge>}
                  {c.niche && <Badge variant="outline">{c.niche}</Badge>}
                </div>
                <div className="text-sm text-muted-foreground flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5" />
                  {(c.meta_followers || c.followers_count || 0).toLocaleString('en-IN')} followers
                </div>
                <Button
                  size="sm"
                  className="mt-auto"
                  disabled={!c.available_this_week}
                  onClick={() => openInvite(c)}
                >
                  <Send className="h-3.5 w-3.5 mr-1.5" /> Send Invite
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {(page > 1 || hasMore) && (
        <div className="flex items-center justify-center gap-3">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            <ChevronLeft className="h-4 w-4 mr-1" /> Previous
          </Button>
          <span className="text-sm text-muted-foreground">Page {page}</span>
          <Button variant="outline" size="sm" disabled={!hasMore} onClick={() => setPage((p) => p + 1)}>
            Next <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
      )}

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
    </div>
  )
}
