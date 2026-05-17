import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall } from '@/lib/frappe'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Users, Plus, Trash2, RefreshCw, X, Check, Loader2, Edit2, Search, UserX, ChevronRight, Calculator, UserPlus, UserMinus, Award, Zap, Cake, List, Database } from 'lucide-react'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

interface Segment {
  name: string;
  segment_name: string;
  description: string;
  criteria_type: string;
  estimated_reach: number;
  last_computed_at: string;
  days_since_last_visit: number;
  min_visit_count: number;
  min_total_spent: number;
}

const CRITERIA_DATA: Record<string, { description: string; icon: any; color: string; bgColor: string; label: string }> = {
  'All Customers': { 
    label: 'Global Audience',
    description: 'Target every customer in your database. Best for general announcements and major updates.', 
    icon: Users, 
    color: 'text-blue-600', 
    bgColor: 'bg-blue-50' 
  },
  'New Customers': { 
    label: 'Recent Signups',
    description: 'Guests who joined in the last 14 days. Ideal for welcome offers and first-visit follow-ups.', 
    icon: UserPlus, 
    color: 'text-emerald-600', 
    bgColor: 'bg-emerald-50' 
  },
  'At-Risk': { 
    label: 'Win-Back List',
    description: 'Customers slipping away. Re-engage them with special offers before they churn.', 
    icon: UserMinus, 
    color: 'text-rose-600', 
    bgColor: 'bg-rose-50' 
  },
  'Loyal Regulars': { 
    label: 'VIP Regulars',
    description: 'Your most frequent guests. Build exclusive loyalty programs and reward your advocates.', 
    icon: Award, 
    color: 'text-violet-600', 
    bgColor: 'bg-violet-50' 
  },
  'High Spenders': { 
    label: 'Top Spenders',
    description: 'Premium audience with high lifetime value. Perfect for exclusive event invites.', 
    icon: Zap, 
    color: 'text-amber-600', 
    bgColor: 'bg-amber-50' 
  },
  'Birthday This Month': { 
    label: 'Birthday Stars',
    description: 'Celebrate special days. Automate rewards for guests celebrating their birthday this month.', 
    icon: Cake, 
    color: 'text-pink-600', 
    bgColor: 'bg-pink-50' 
  },
  'Manual': { 
    label: 'Custom List',
    description: 'Precision targeting. Manually paste a list of phone numbers for a hyper-targeted broadcast.', 
    icon: List, 
    color: 'text-slate-600', 
    bgColor: 'bg-slate-100' 
  },
  'Custom SQL': { 
    label: 'Advanced Logic',
    description: 'Power users only. Define granular segments using advanced SQL filtering logic.', 
    icon: Database, 
    color: 'text-orange-600', 
    bgColor: 'bg-orange-50' 
  },
}

export default function MarketingSegments() {
  const { selectedRestaurant } = useRestaurant()
  const [segments, setSegments] = useState<Segment[]>([])
  const [loading, setLoading] = useState(true)
  const [showBuilder, setShowBuilder] = useState(false)
  const [saving, setSaving] = useState(false)
  const [previewCount, setPreviewCount] = useState<number | null>(null)
  const [previewing, setPreviewing] = useState(false)

  const [form, setForm] = useState({
    segment_name: '',
    description: '',
    criteria_type: 'All Customers',
    days_since_last_visit: 30,
    min_visit_count: 5,
    min_total_spent: 1000,
    customer_ids: '',
  })

  // Management states
  const [searchQuery, setSearchQuery] = useState('')
  const [activeTab, setActiveTab] = useState('segments')
  const [optOutStats, setOptOutStats] = useState<{total_opted_out: number, recent: any[]}>({ total_opted_out: 0, recent: [] })
  const [editingName, setEditingName] = useState<string | null>(null)
  
  const [confirmDelete, setConfirmDelete] = useState<{open: boolean, name: string, label: string}>({ open: false, name: '', label: '' })

  const { call: fetchSegments } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.get_segments')
  const { call: saveSegmentApi } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.save_segment')
  const { call: deleteSegmentApi } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.delete_segment')
  const { call: previewApi } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.preview_segment_reach')
  const { call: fetchOptOutStatsApi } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.get_optout_stats')

  const load = () => {
    if (!selectedRestaurant) return
    setLoading(true)
    Promise.all([
      fetchSegments({ restaurant_id: selectedRestaurant }),
      fetchOptOutStatsApi({ restaurant_id: selectedRestaurant })
    ]).then(([sRes, oRes]: any[]) => {
      if (sRes?.message?.success) {
        setSegments(sRes.message.data || [])
      }
      if (oRes?.message?.success) {
        setOptOutStats(oRes.message.data)
      }
    }).catch((err) => {
      console.error("Failed to load segments:", err)
    }).finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [selectedRestaurant])

  const handlePreview = async () => {
    if (!selectedRestaurant) return
    setPreviewing(true)
    try {
      const res = await previewApi({ 
        restaurant_id: selectedRestaurant,
        criteria_type: form.criteria_type,
        filters: {
           days_since_last_visit: form.days_since_last_visit,
           min_visit_count: form.min_visit_count,
           min_total_spent: form.min_total_spent,
           customer_ids: form.customer_ids
        }
      })
      if (res?.message?.success) {
        setPreviewCount(res.message.data.reach)
      }
    } catch (e: any) {
      toast.error(e.message)
    } finally {
      setPreviewing(false)
    }
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedRestaurant) return
    setSaving(true)
    try {
      const res = await saveSegmentApi({ 
        restaurant_id: selectedRestaurant, 
        segment_data: { 
          ...form, 
          name: editingName 
        } 
      })
      if (res?.message?.success) {
        toast.success(editingName ? 'Segment updated' : 'Segment created')
        setShowBuilder(false)
        setEditingName(null)
        setForm({
          segment_name: '',
          description: '',
          criteria_type: 'All Customers',
          days_since_last_visit: 30,
          min_visit_count: 5,
          min_total_spent: 1000,
          customer_ids: '',
        })
        load()
      }
    } catch (e: any) {
      toast.error(e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    try {
      await deleteSegmentApi({ restaurant_id: selectedRestaurant, segment_name: confirmDelete.name })
      toast.success('Segment deleted')
      load()
    } catch (e: any) {
      toast.error(e.message)
    }
  }

  const filteredSegments = segments.filter(s => 
    s.segment_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.criteria_type.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      {/* Breadcrumbs */}
      <nav className="flex items-center text-sm text-muted-foreground mb-2">
        <Link to="/marketing" className="hover:text-foreground transition-colors">Marketing</Link>
        <ChevronRight className="h-4 w-4 mx-2" />
        <span className="text-foreground font-medium">Segments</span>
      </nav>

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black tracking-tight flex items-center gap-3">
            <Users className="h-8 w-8 text-primary" />
            Audience Segments
          </h1>
          <p className="text-muted-foreground mt-1">Group your customers into targeted segments for focused marketing.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button onClick={() => { setEditingName(null); setShowBuilder(true); }} className="font-bold">
            <Plus className="h-4 w-4 mr-2" />
            New Segment
          </Button>
        </div>
      </div>

      {showBuilder ? (
        <Card className="border shadow-lg animate-in fade-in slide-in-from-top-2 duration-300 overflow-hidden">
          <CardHeader className="bg-muted/30 border-b py-4">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg font-bold flex items-center gap-2">
                   <Users className="h-5 w-5 text-primary" />
                   {editingName ? 'Edit Segment' : 'Create New Segment'}
                </CardTitle>
                <CardDescription>Define target criteria for your audience segment.</CardDescription>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setShowBuilder(false)} className="h-8 w-8">
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-6">
            <form onSubmit={handleSave} className="space-y-8">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                {/* Left Column: Details */}
                <div className="space-y-6">
                  <div className="space-y-2">
                    <Label htmlFor="segment_name" className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Segment Name *</Label>
                    <Input 
                      id="segment_name" 
                      placeholder="e.g. VIP Regulars" 
                      value={form.segment_name}
                      onChange={e => setForm(f => ({ ...f, segment_name: e.target.value }))}
                      required 
                      className="h-10"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="description" className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Description</Label>
                    <Textarea 
                      id="description" 
                      placeholder="Optional: Internal notes about this segment..." 
                      value={form.description}
                      onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                      className="min-h-[100px] resize-none"
                    />
                  </div>

                  <div className="p-4 rounded-lg bg-primary/5 border border-primary/10 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                        <Calculator className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Est. Reach</p>
                        <p className="text-lg font-bold text-primary">{previewing ? '...' : (previewCount !== null ? `${previewCount} customers` : '—')}</p>
                      </div>
                    </div>
                    <Button type="button" variant="outline" size="sm" onClick={handlePreview} disabled={previewing} className="h-8 text-xs font-bold">
                      {previewing ? <Loader2 className="h-3 w-3 animate-spin mr-2" /> : <RefreshCw className="h-3 w-3 mr-2" />}
                      Update
                    </Button>
                  </div>
                </div>

                {/* Right Column: Logic */}
                <div className="space-y-4">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Selection Logic *</Label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {Object.entries(CRITERIA_DATA).map(([type, data]) => {
                      const Icon = data.icon;
                      const isSelected = form.criteria_type === type;
                      return (
                        <div
                          key={type}
                          onClick={() => setForm(f => ({ ...f, criteria_type: type }))}
                          className={cn(
                            "group p-3 border rounded-xl cursor-pointer transition-all relative overflow-hidden",
                            isSelected 
                              ? "border-primary bg-primary/5 ring-1 ring-primary" 
                              : "bg-muted/10 hover:border-primary/50 hover:bg-muted/20"
                          )}
                        >
                          <div className="flex items-center gap-3 mb-1.5">
                            <Icon className={cn("h-4 w-4", isSelected ? data.color : "text-muted-foreground")} />
                            <p className="text-sm font-bold truncate">{type}</p>
                            {isSelected && <Check className="h-3 w-3 text-primary ml-auto" />}
                          </div>
                          <p className="text-[11px] text-muted-foreground leading-tight line-clamp-2">
                            {data.description}
                          </p>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>

              {/* Dynamic Logic Parameters */}
              {(form.criteria_type === 'Loyal Regulars' || form.criteria_type === 'At-Risk' || form.criteria_type === 'High Spenders' || form.criteria_type === 'Manual') && (
                <div className="p-6 rounded-xl bg-muted/20 border border-dashed animate-in fade-in duration-300">
                  <div className="flex items-center gap-2 mb-4">
                    <Search className="h-4 w-4 text-muted-foreground" />
                    <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Parameters for {form.criteria_type}</p>
                  </div>

                  {form.criteria_type === 'Loyal Regulars' && (
                    <div className="flex items-center gap-4">
                      <div className="space-y-1">
                        <Label className="text-xs font-medium">Minimum Visit Count</Label>
                        <NumberInput value={form.min_visit_count} onChange={(e: any) => setForm(f => ({ ...f, min_visit_count: parseInt(e.target.value) }))} className="h-10 w-32" />
                      </div>
                      <p className="text-sm text-muted-foreground mt-6">Includes customers who have visited at least {form.min_visit_count} times.</p>
                    </div>
                  )}

                  {form.criteria_type === 'At-Risk' && (
                    <div className="flex items-center gap-4">
                      <div className="space-y-1">
                        <Label className="text-xs font-medium">Days of Inactivity</Label>
                        <NumberInput value={form.days_since_last_visit} onChange={(e: any) => setForm(f => ({ ...f, days_since_last_visit: parseInt(e.target.value) }))} className="h-10 w-32" />
                      </div>
                      <p className="text-sm text-muted-foreground mt-6">Targets customers who haven't visited for {form.days_since_last_visit} days.</p>
                    </div>
                  )}

                  {form.criteria_type === 'High Spenders' && (
                    <div className="flex items-center gap-4">
                      <div className="space-y-1">
                        <Label className="text-xs font-medium">Minimum Lifetime Spend (₹)</Label>
                        <NumberInput value={form.min_total_spent} onChange={(e: any) => setForm(f => ({ ...f, min_total_spent: parseInt(e.target.value) }))} className="h-10 w-40" />
                      </div>
                      <p className="text-sm text-muted-foreground mt-6">Targets customers with spend exceeding ₹{form.min_total_spent.toLocaleString()}.</p>
                    </div>
                  )}

                  {form.criteria_type === 'Manual' && (
                    <div className="space-y-2">
                      <Label className="text-xs font-medium">Phone Number List (comma separated)</Label>
                      <Textarea 
                         value={form.customer_ids} 
                         onChange={e => setForm(f => ({ ...f, customer_ids: e.target.value }))} 
                         className="bg-background min-h-[80px]" 
                         placeholder="+919876543210, +918888888888" 
                      />
                    </div>
                  )}
                </div>
              )}

              <div className="flex justify-end gap-3 pt-6 border-t">
                <Button type="button" variant="outline" onClick={() => setShowBuilder(false)} className="h-10 font-bold">Cancel</Button>
                <Button type="submit" disabled={saving} className="min-w-[140px] h-10 font-bold">
                  {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                  {editingName ? 'Update Segment' : 'Save Segment'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      ) : (
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <div className="flex items-center justify-between">
            <TabsList className="bg-muted/50 p-1">
              <TabsTrigger value="segments" className="px-6 flex items-center gap-2">
                <Users className="h-4 w-4" />
                Manage Segments
              </TabsTrigger>
              <TabsTrigger value="optouts" className="px-6 flex items-center gap-2">
                <UserX className="h-4 w-4" />
                Opt-out List
              </TabsTrigger>
            </TabsList>

            {activeTab === 'segments' && (
              <div className="relative w-full max-w-xs hidden md:block">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input 
                  placeholder="Search segments..." 
                  className="pl-9 h-10 rounded-full bg-muted/30 border-none focus-visible:ring-1"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                />
              </div>
            )}
          </div>

          <TabsContent value="segments" className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {loading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <Card key={i} className="border-dashed"><CardContent className="h-40 flex items-center justify-center"><Skeleton className="h-full w-full" /></CardContent></Card>
                ))
              ) : filteredSegments.length === 0 ? (
                <Card className="col-span-full border-dashed border-2 py-16 text-center bg-muted/10">
                  <div className="flex flex-col items-center gap-3">
                    <Users className="h-12 w-12 text-muted-foreground opacity-20" />
                    <p className="text-muted-foreground font-medium">No segments found.</p>
                    <Button variant="link" onClick={() => setShowBuilder(true)}>Create your first segment</Button>
                  </div>
                </Card>
              ) : (
                filteredSegments.map((seg: Segment) => (
                  <Card key={seg.name} className="group hover:shadow-md transition-all duration-300 border bg-card">
                    <CardHeader className="pb-3 border-b bg-muted/5">
                      <div className="flex justify-between items-start">
                        <Badge variant="outline" className="text-[10px] font-bold uppercase tracking-tight bg-background">
                          {seg.criteria_type}
                        </Badge>
                        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-primary" onClick={() => {
                            setEditingName(seg.name)
                            setForm({
                              segment_name: seg.segment_name,
                              description: seg.description || '',
                              criteria_type: seg.criteria_type,
                              days_since_last_visit: seg.days_since_last_visit || 30,
                              min_visit_count: seg.min_visit_count || 5,
                              min_total_spent: seg.min_total_spent || 1000,
                              customer_ids: '',
                            })
                            setShowBuilder(true)
                          }}>
                            <Edit2 className="h-3.5 w-3.5" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => setConfirmDelete({ open: true, name: seg.name, label: seg.segment_name })}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                      <CardTitle className="text-base font-bold mt-2 truncate">{seg.segment_name}</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                      <p className="text-xs text-muted-foreground line-clamp-2 min-h-[32px] mb-4">{seg.description || 'No description provided.'}</p>
                      <div className="flex items-center justify-between pt-3 border-t">
                        <div className="flex items-center gap-2">
                          <Users className="h-4 w-4 text-primary" />
                          <div>
                            <div className="text-sm font-bold leading-none">{seg.estimated_reach.toLocaleString()}</div>
                            <div className="text-[9px] uppercase font-bold text-muted-foreground">Reach</div>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-[9px] uppercase font-bold text-muted-foreground">Updated</div>
                          <div className="text-[10px] font-medium">{seg.last_computed_at ? new Date(seg.last_computed_at).toLocaleDateString() : 'Never'}</div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))
              )}
            </div>
          </TabsContent>

          <TabsContent value="optouts" className="space-y-6">
            <Card className="border-none shadow-none bg-muted/20">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl font-bold">
                  <UserX className="h-5 w-5 text-red-500" />
                  Opt-out Management
                </CardTitle>
                <p className="text-xs text-muted-foreground">Customers who have replied with "STOP" or "UNSUBSCRIBE" are automatically excluded from all campaigns.</p>
              </CardHeader>
              <CardContent>
                {optOutStats.recent.length === 0 ? (
                  <div className="flex flex-col items-center py-12 gap-2 text-muted-foreground">
                    <Check className="h-10 w-10 text-green-500 opacity-20" />
                    <p className="text-sm font-medium">Zero opt-outs! Your audience is highly engaged.</p>
                  </div>
                ) : (
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/50 border-b">
                        <tr>
                          <th className="text-left py-3 px-4 font-bold text-xs uppercase tracking-wider text-muted-foreground">Customer</th>
                          <th className="text-left py-3 px-4 font-bold text-xs uppercase tracking-wider text-muted-foreground">Phone</th>
                          <th className="text-left py-3 px-4 font-bold text-xs uppercase tracking-wider text-muted-foreground">Date</th>
                          <th className="text-left py-3 px-4 font-bold text-xs uppercase tracking-wider text-muted-foreground">Keyword</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y text-[13px]">
                        {optOutStats.recent.map((opt, i) => (
                          <tr key={i} className="hover:bg-muted/5 transition-colors">
                            <td className="py-3 px-4 font-bold">{opt.customer_name || 'Walk-in Customer'}</td>
                            <td className="py-3 px-4 font-mono text-muted-foreground">{opt.phone}</td>
                            <td className="py-3 px-4 text-muted-foreground">{new Date(opt.opted_out_at).toLocaleDateString()}</td>
                            <td className="py-3 px-4"><span className="bg-red-50 text-red-700 px-2 py-0.5 rounded font-black text-[10px] uppercase">{opt.opted_out_keyword}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}

      <ConfirmDialog
        open={confirmDelete.open}
        onOpenChange={(open) => setConfirmDelete(d => ({ ...d, open }))}
        title="Delete Segment?"
        description={`This will permanently delete the group "${confirmDelete.label}". Existing campaigns using this segment will not be affected, but you won't be able to target it in new campaigns.`}
        confirmText="Delete Segment"
        variant="destructive"
        onConfirm={handleDelete}
      />
    </div>
  )
}
