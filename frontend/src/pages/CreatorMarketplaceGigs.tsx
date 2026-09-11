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
import { GenericPageSkeleton } from '@/components/PageSkeletons'
import GigDetailSheet, { type GigDetail, type Application } from '@/components/GigDetailSheet'
import { toast } from 'sonner'
import { getFrappeError } from '@/lib/utils'
import { Plus, Users, Gift, IndianRupee, CalendarClock } from 'lucide-react'

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

const STATUS_COLORS: Record<string, string> = {
  open: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  filled: 'bg-blue-50 text-blue-700 border-blue-200',
  expired: 'bg-muted text-muted-foreground border-border',
  cancelled: 'bg-muted text-muted-foreground border-border',
}
const STATUS_LABELS: Record<string, string> = {
  open: 'Open',
  filled: 'Filled',
  expired: 'Expired',
  cancelled: 'Cancelled',
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
  const [viewingGig, setViewingGig] = useState<GigDetail | null>(null)

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
  const gigs: GigDetail[] = body?.data?.gigs || []

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

  const handleCloseGig = async (gigId: string) => {
    if (!selectedOutlet) return
    try {
      await closeGig({ outlet_id: selectedOutlet, gig_id: gigId })
      toast.success('Collab closed')
      setViewingGig(null)
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
    <div className="space-y-6 pb-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">My Collabs</h1>
          <p className="text-muted-foreground text-sm mt-1">Post a collab, review applications & accept the right creator</p>
        </div>
        <div className="shrink-0">
          <Button onClick={() => setCreating(true)} className="h-10 px-5 rounded-md shadow-sm hover:shadow transition-all font-medium">
            <Plus className="h-4 w-4 mr-2" /> Post a Collab
          </Button>
        </div>
      </div>

      {gigs.length === 0 ? (
        <Card className="border-dashed bg-muted/30">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <div className="h-16 w-16 rounded-md bg-muted flex items-center justify-center mb-4">
              <Gift className="h-8 w-8 text-muted-foreground/60" />
            </div>
            <h3 className="text-lg font-semibold mb-2">No collabs posted yet</h3>
            <p className="text-muted-foreground max-w-sm mb-6">
              Create your first collab to invite creators to apply and start working together.
            </p>
            <Button onClick={() => setCreating(true)} className="rounded-md shadow-sm px-6">
              <Plus className="h-4 w-4 mr-2" /> Post a Collab
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {gigs.map((g) => (
            <div key={g.name} className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-lg border border-border bg-card hover:border-foreground/20 transition-all">
              
              {/* Left Side: Title & Stats */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-3">
                  <h3 className="font-semibold text-base leading-tight">
                    {g.title}
                  </h3>
                  <Badge variant="secondary" className={`font-medium px-2 py-0.5 ${STATUS_COLORS[g.status] || ''}`}>
                    {STATUS_LABELS[g.status] || g.status}
                  </Badge>
                </div>
                
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground">
                  <span className="flex items-center gap-1.5 font-medium text-foreground">
                    {g.barter_allowed ? (
                      <>
                        <Gift className="h-3.5 w-3.5" />
                        Barter
                      </>
                    ) : (
                      <>
                        <IndianRupee className="h-3.5 w-3.5" />
                        {g.budget_inr?.toLocaleString('en-IN')}
                      </>
                    )}
                  </span>
                  
                  <span className="flex items-center gap-1.5 border-l pl-4 border-border/60">
                    <Users className="h-3.5 w-3.5" />
                    {g.applications_count} application{g.applications_count === 1 ? '' : 's'}
                  </span>
                  
                  {g.expires_at && (
                    <span className="flex items-center gap-1.5 border-l pl-4 border-border/60">
                      <CalendarClock className="h-3.5 w-3.5" />
                      Expires {g.expires_at.slice(0, 10)}
                    </span>
                  )}
                </div>
              </div>

              {/* Right Side: Actions */}
              <div className="shrink-0 flex gap-2 sm:ml-auto">
                <Button variant="outline" className="rounded-md px-6 font-medium shadow-sm transition-all bg-background border border-border hover:bg-muted w-full sm:w-auto" onClick={() => setViewingGig(g)}>
                  View Applications
                </Button>
                {g.status === 'open' && (
                  <Button variant="ghost" className="rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 w-full sm:w-auto" onClick={() => handleCloseGig(g.name)}>
                    Close
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create collab dialog */}
      <Dialog open={creating} onOpenChange={(open) => { if (!open) { setCreating(false); resetForm() } }}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader className="pb-4 border-b border-border/40">
            <DialogTitle className="text-xl flex items-center gap-2">
              <Gift className="h-5 w-5 text-primary" />
              Post a Collab
            </DialogTitle>
            <p className="text-sm text-muted-foreground mt-1.5">Describe what you need and what you're offering.</p>
          </DialogHeader>
          <div className="space-y-5 py-4 max-h-[60vh] overflow-y-auto px-1">
            <div className="space-y-2">
              <Label className="text-sm font-medium text-foreground/80">Title <span className="text-destructive">*</span></Label>
              <Input placeholder="e.g. 2 Instagram reels" value={title} onChange={(e) => setTitle(e.target.value)} className="h-10 bg-muted/30 focus-visible:bg-background" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-sm font-medium text-foreground/80">Deliverable</Label>
                <Select value={deliverableType} onValueChange={setDeliverableType}>
                  <SelectTrigger className="h-10 bg-muted/30 focus-visible:bg-background"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {DELIVERABLE_TYPES.map((d) => (
                      <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-medium text-foreground/80">Count</Label>
                <Input type="number" min={1} step={1} value={deliverableCount} onChange={(e) => setDeliverableCount(e.target.value)} className="h-10 bg-muted/30 focus-visible:bg-background" />
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-medium text-foreground/80">Category</Label>
              <div className="relative">
                <Input placeholder="e.g. Dining" value={category} onChange={(e) => setCategory(e.target.value)} className="h-10 pl-9 bg-muted/30 focus-visible:bg-background" />
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground font-medium text-sm">#</span>
              </div>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 p-4">
              <div>
                <div className="text-sm font-medium">Barter instead of cash</div>
                <div className="text-xs text-muted-foreground mt-0.5">Offer a free item or experience instead of a fixed budget</div>
              </div>
              <Button
                type="button"
                variant={barterAllowed ? 'default' : 'outline'}
                size="sm"
                className={`rounded-md px-4 ${barterAllowed ? 'shadow-sm' : 'bg-background'}`}
                onClick={() => setBarterAllowed((v) => !v)}
              >
                {barterAllowed ? 'Barter On' : 'Cash Budget'}
              </Button>
            </div>

            {barterAllowed ? (
              <div className="space-y-2">
                <Label className="text-sm font-medium text-foreground/80">Barter details <span className="text-destructive">*</span></Label>
                <Textarea
                  placeholder="e.g. Free meal for two, worth ~₹800"
                  value={barterDetails}
                  onChange={(e) => setBarterDetails(e.target.value)}
                  rows={3}
                  className="bg-muted/30 focus-visible:bg-background resize-none"
                />
              </div>
            ) : (
              <div className="space-y-2">
                <Label className="text-sm font-medium text-foreground/80">Budget (₹) <span className="text-destructive">*</span></Label>
                <div className="relative">
                  <IndianRupee className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    type="number"
                    className="h-10 pl-9 bg-muted/30 focus-visible:bg-background"
                    placeholder="1500"
                    value={budget}
                    onChange={(e) => setBudget(e.target.value)}
                  />
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-sm font-medium text-foreground/80">Min. followers</Label>
                <div className="relative">
                  <Users className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <Input type="number" placeholder="10000" value={minFollowers} onChange={(e) => setMinFollowers(e.target.value)} className="h-10 pl-9 bg-muted/30 focus-visible:bg-background" />
                </div>
              </div>
              <div className="space-y-2">
                <Label className="text-sm font-medium text-foreground/80">Min. badge tier</Label>
                <Select value={minBadgeTier} onValueChange={setMinBadgeTier}>
                  <SelectTrigger className="h-10 bg-muted/30 focus-visible:bg-background"><SelectValue placeholder="Any creator" /></SelectTrigger>
                  <SelectContent>
                    {BADGE_TIERS.map((t) => (
                      <SelectItem key={t.value || 'any'} value={t.value || 'any'}>{t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
          <DialogFooter className="pt-4 border-t border-border/40 sm:justify-between">
            <Button variant="ghost" onClick={() => { setCreating(false); resetForm() }} disabled={saving} className="text-muted-foreground hover:text-foreground">
              Cancel
            </Button>
            <Button onClick={submitGig} disabled={saving} className="rounded-md px-6 shadow-sm">
              {saving ? 'Posting…' : 'Post Collab'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <GigDetailSheet
        gig={viewingGig}
        applications={applications}
        loading={appsLoading}
        onClose={() => setViewingGig(null)}
        onAccept={handleAccept}
        onClose_Gig={viewingGig ? () => handleCloseGig(viewingGig.name) : undefined}
      />
    </div>
  )
}
