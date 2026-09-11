import { useState } from 'react'
import { useOutlet } from '@/contexts/OutletContext'
import { useFrappeGetCall, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import { toast } from 'sonner'
import { getFrappeError } from '@/lib/utils'
import { Plus, Users, X, Gift, IndianRupee } from 'lucide-react'

const DELIVERABLE_TYPES = [
  { value: 'native_chills', label: 'Chills reel' },
  { value: 'native_club_post', label: 'Club Talks post' },
  { value: 'instagram_reel', label: 'Instagram reel' },
  { value: 'instagram_story', label: 'Instagram story' },
]

const BADGE_TIERS = [
  { value: '', label: 'Any creator' },
  { value: 'new_creator', label: 'New Creator+' },
  { value: 'verified_creator', label: 'Verified Creator+' },
  { value: 'top_rated', label: 'Top Rated+' },
  { value: 'elite_creator', label: 'Elite Creator only' },
]

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'outline'> = {
  open: 'default',
  filled: 'secondary',
  expired: 'outline',
  cancelled: 'outline',
}

interface Gig {
  name: string
  title: string
  status: string
  budget_inr: number
  barter_allowed: number
  category: string
  expires_at: string
  creation: string
  applications_count: number
}

interface Application {
  deal_id: string
  creator_id: string
  creator_name: string
  follower_count: number
  deal_type: 'cash' | 'barter'
  proposed_price_inr: number
  proposed_fair_value_inr: number
  status: string
  creation: string
}

export default function CreatorMarketplaceGigs() {
  const { selectedOutlet } = useOutlet()
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('')
  const [budget, setBudget] = useState('')
  const [barterAllowed, setBarterAllowed] = useState(false)
  const [barterDetails, setBarterDetails] = useState('')
  const [deliverableType, setDeliverableType] = useState('native_chills')
  const [deliverableCount, setDeliverableCount] = useState('1')
  const [minFollowers, setMinFollowers] = useState('')
  const [minBadgeTier, setMinBadgeTier] = useState('')
  const [saving, setSaving] = useState(false)
  const [viewingGig, setViewingGig] = useState<Gig | null>(null)

  const { data, mutate, isLoading } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.collab_gigs.list_my_gigs',
    selectedOutlet ? { outlet_id: selectedOutlet } : undefined,
    selectedOutlet ? `my-gigs-${selectedOutlet}` : undefined,
  )
  const { call: createGig } = useFrappePostCall('flamezo_backend.flamezo.api.collab_gigs.create_gig')
  const { call: closeGig } = useFrappePostCall('flamezo_backend.flamezo.api.collab_gigs.close_gig')

  const { data: appsData, mutate: mutateApps, isLoading: appsLoading } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.collab_gigs.list_applications',
    selectedOutlet && viewingGig ? { outlet_id: selectedOutlet, gig_id: viewingGig.name } : undefined,
    selectedOutlet && viewingGig ? `gig-apps-${selectedOutlet}-${viewingGig.name}` : undefined,
  )
  const { call: acceptApplication } = useFrappePostCall(
    'flamezo_backend.flamezo.api.collab_deals.accept_application',
  )

  const body: any = (data as any)?.message || data
  const gigs: Gig[] = body?.data?.gigs || []

  const appsBody: any = (appsData as any)?.message || appsData
  const applications: Application[] = appsBody?.data?.applications || []

  const resetForm = () => {
    setTitle('')
    setCategory('')
    setBudget('')
    setBarterAllowed(false)
    setBarterDetails('')
    setDeliverableType('native_chills')
    setDeliverableCount('1')
    setMinFollowers('')
    setMinBadgeTier('')
  }

  const submitGig = async () => {
    if (!selectedOutlet || !title.trim()) {
      toast.error('Give the collab a title first.')
      return
    }
    if (!barterAllowed && (!budget || Number(budget) <= 0)) {
      toast.error('Set a budget, or turn on barter and describe what you\'re offering.')
      return
    }
    if (barterAllowed && !barterDetails.trim()) {
      toast.error('Describe what the barter offer includes.')
      return
    }
    setSaving(true)
    try {
      await createGig({
        outlet_id: selectedOutlet,
        title,
        deliverables: JSON.stringify([{ type: deliverableType, count: Math.max(1, Math.round(Number(deliverableCount) || 1)) }]),
        budget_inr: Number(budget) || 0,
        barter_allowed: barterAllowed ? 1 : 0,
        barter_details: barterAllowed ? barterDetails : undefined,
        category: category || undefined,
        min_followers: Number(minFollowers) || 0,
        min_badge_tier: minBadgeTier && minBadgeTier !== 'any' ? minBadgeTier : undefined,
      })
      toast.success('Collab posted')
      setCreating(false)
      resetForm()
      mutate()
    } catch (error: any) {
      toast.error('Could not post collab', { description: getFrappeError(error) })
    } finally {
      setSaving(false)
    }
  }

  const handleCloseGig = async (gig: Gig) => {
    if (!selectedOutlet) return
    try {
      await closeGig({ outlet_id: selectedOutlet, gig_id: gig.name })
      toast.success('Collab closed')
      mutate()
    } catch (error: any) {
      toast.error('Could not close collab', { description: getFrappeError(error) })
    }
  }

  const handleAccept = async (app: Application) => {
    if (!selectedOutlet) return
    try {
      await acceptApplication({ outlet_id: selectedOutlet, deal_id: app.deal_id })
      toast.success(`Accepted ${app.creator_name}'s application`)
      mutateApps()
      mutate()
    } catch (error: any) {
      toast.error('Could not accept application', { description: getFrappeError(error) })
    }
  }

  if (isLoading && !data) return <GenericPageSkeleton />

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4 mr-1.5" /> Post a Collab
        </Button>
      </div>

      {gigs.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <Gift className="h-10 w-10 mx-auto mb-3 opacity-40" />
            No collabs posted yet — post one to let creators apply.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Budget</TableHead>
                <TableHead>Applications</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {gigs.map((g) => (
                <TableRow key={g.name}>
                  <TableCell className="font-medium">{g.title}</TableCell>
                  <TableCell>
                    <Badge variant={STATUS_VARIANT[g.status] || 'outline'}>{g.status}</Badge>
                  </TableCell>
                  <TableCell>
                    {g.barter_allowed ? 'Barter' : `₹${g.budget_inr?.toLocaleString('en-IN')}`}
                  </TableCell>
                  <TableCell>{g.applications_count}</TableCell>
                  <TableCell className="text-right space-x-2">
                    <Button variant="outline" size="sm" onClick={() => setViewingGig(g)}>
                      <Users className="h-3.5 w-3.5 mr-1.5" /> View
                    </Button>
                    {g.status === 'open' && (
                      <Button variant="outline" size="sm" onClick={() => handleCloseGig(g)}>
                        Close
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* Create collab dialog */}
      <Dialog open={creating} onOpenChange={(open) => { if (!open) { setCreating(false); resetForm() } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Post a Collab</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
            <div className="space-y-1.5">
              <Label>Title *</Label>
              <Input placeholder="e.g. 2 Instagram reels" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Deliverable</Label>
                <Select value={deliverableType} onValueChange={setDeliverableType}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {DELIVERABLE_TYPES.map((d) => (
                      <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Count</Label>
                <Input type="number" min={1} step={1} value={deliverableCount} onChange={(e) => setDeliverableCount(e.target.value)} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>Category</Label>
              <Input placeholder="e.g. dining" value={category} onChange={(e) => setCategory(e.target.value)} />
            </div>

            <div className="flex items-center justify-between rounded-md border p-3">
              <div>
                <div className="text-sm font-medium">Barter instead of cash</div>
                <div className="text-xs text-muted-foreground">Offer a free item/experience instead of a budget</div>
              </div>
              <Button
                type="button"
                variant={barterAllowed ? 'default' : 'outline'}
                size="sm"
                onClick={() => setBarterAllowed((v) => !v)}
              >
                {barterAllowed ? 'Barter on' : 'Cash budget'}
              </Button>
            </div>

            {barterAllowed ? (
              <div className="space-y-1.5">
                <Label>Barter details *</Label>
                <Textarea
                  placeholder="e.g. Free meal for two, worth ~₹800"
                  value={barterDetails}
                  onChange={(e) => setBarterDetails(e.target.value)}
                  rows={2}
                />
              </div>
            ) : (
              <div className="space-y-1.5">
                <Label>Budget (₹) *</Label>
                <div className="relative">
                  <IndianRupee className="h-3.5 w-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    type="number"
                    className="pl-8"
                    placeholder="1500"
                    value={budget}
                    onChange={(e) => setBudget(e.target.value)}
                  />
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Min. followers</Label>
                <Input type="number" placeholder="0" value={minFollowers} onChange={(e) => setMinFollowers(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label>Min. badge tier</Label>
                <Select value={minBadgeTier} onValueChange={setMinBadgeTier}>
                  <SelectTrigger><SelectValue placeholder="Any creator" /></SelectTrigger>
                  <SelectContent>
                    {BADGE_TIERS.map((t) => (
                      <SelectItem key={t.value || 'any'} value={t.value || 'any'}>{t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setCreating(false); resetForm() }} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={submitGig} disabled={saving}>
              {saving ? 'Posting…' : 'Post Collab'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Applications dialog */}
      <Dialog open={!!viewingGig} onOpenChange={(open) => !open && setViewingGig(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Applications — {viewingGig?.title}</DialogTitle>
          </DialogHeader>
          {appsLoading ? (
            <div className="py-8 text-center text-sm text-muted-foreground">Loading…</div>
          ) : applications.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">No applications yet.</div>
          ) : (
            <div className="space-y-2 max-h-[60vh] overflow-y-auto">
              {applications.map((app) => (
                <div key={app.deal_id} className="flex items-center justify-between rounded-md border p-3">
                  <div>
                    <div className="font-medium text-sm">{app.creator_name}</div>
                    <div className="text-xs text-muted-foreground">
                      {app.follower_count?.toLocaleString('en-IN')} followers
                      {app.deal_type === 'barter'
                        ? (app.proposed_fair_value_inr ? ` · ₹${app.proposed_fair_value_inr.toLocaleString('en-IN')} barter value proposed` : ' · barter')
                        : (app.proposed_price_inr ? ` · ₹${app.proposed_price_inr.toLocaleString('en-IN')} proposed` : '')}
                    </div>
                  </div>
                  {app.status === 'offered' ? (
                    <Button size="sm" onClick={() => handleAccept(app)}>Accept</Button>
                  ) : (
                    <Badge variant="secondary">{app.status}</Badge>
                  )}
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
