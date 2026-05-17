import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall } from '@/lib/frappe'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { 
  Send, Plus, Loader2, AlertCircle, ChevronRight, X, Check, Users, Trash2, XCircle, 
  BarChart3, Search, MessageSquare, Smartphone, Mail, HeartOff, Trophy, Megaphone, 
  Cake, Edit3, Zap, Calendar as CalendarIcon 
} from 'lucide-react'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { toast } from 'sonner'
import { useDataTable } from '@/hooks/useDataTable'
import { DataPagination } from '@/components/ui/DataPagination'
import { cn } from '@/lib/utils'
import { DatePicker } from '@/components/ui/date-picker'
import { TimePicker } from '@/components/ui/time-picker'

interface Segment { name: string; segment_name: string; estimated_reach: number; criteria_type: string }
interface Campaign {
  name: string; campaign_name: string; channel: string; status: string
  target_segment: string; total_recipients: number; total_sent: number
  total_failed: number; total_conversions: number; total_cost_coins: number
  sent_at: string; creation: string
}

const STATUS_COLORS: Record<string, string> = {
  Draft: 'bg-slate-100 text-slate-600',
  Scheduled: 'bg-blue-100 text-blue-700',
  Sending: 'bg-yellow-100 text-yellow-800 animate-pulse',
  Sent: 'bg-green-100 text-green-700',
  Failed: 'bg-red-100 text-red-700',
  Cancelled: 'bg-slate-100 text-slate-500',
}

const TEMPLATES = {
  'win_back': "Hi {{customer_name}}! We miss you at {{restaurant_name}}. Come back and enjoy a special offer: {{coupon_code}}. Table's waiting!",
  'loyalty_nudge': "Hey {{customer_name}}! You have {{loyalty_balance}} loyalty coins at {{restaurant_name}}. Redeem them on your next visit!",
  'new_offer': "Big news from {{restaurant_name}}! We've got something special just for you. Use code {{coupon_code}} for an exclusive deal!",
  'birthday': "Happy Birthday {{customer_name}}! {{restaurant_name}} wants to celebrate with you. Enjoy a special birthday treat: {{coupon_code}}.",
  'custom': ''
}

type WizardStep = 'audience' | 'message' | 'schedule' | 'review'
const STEPS: WizardStep[] = ['audience', 'message', 'schedule', 'review']
const STEP_LABELS: Record<WizardStep, string> = { audience: 'Audience', message: 'Message', schedule: 'Schedule', review: 'Review' }

export default function MarketingCampaigns() {
  const { selectedRestaurant } = useRestaurant()
  const navigate = useNavigate()
  const [segments, setSegments] = useState<Segment[]>([])
  const [showWizard, setShowWizard] = useState(false)
  const [step, setStep] = useState<WizardStep>('audience')
  const [sending, setSending] = useState(false)
  const [statusFilter, setStatusFilter] = useState('All')

  const [confirmDelete, setConfirmDelete] = useState<{open: boolean, id: string, label: string}>({ open: false, id: '', label: '' })
  const [confirmCancel, setConfirmCancel] = useState<{open: boolean, id: string, label: string}>({ open: false, id: '', label: '' })

  // Wizard form state
  const [form, setForm] = useState({
    campaign_name: '',
    channel: 'WhatsApp',
    target_segment: '',
    message_template: '',
    email_subject: '',
    template_key: 'custom',
    include_coupon: false,
    coupon_code: '',
    scheduled_at: '',
    send_now: true,
  })

  // Data fetching for campaigns
  const {
      data: campaigns,
      isLoading,
      mutate,
      page,
      setPage,
      pageSize,
      setPageSize,
      totalCount,
      searchQuery,
      setSearchQuery
  } = useDataTable({
      customEndpoint: 'flamezo_backend.flamezo.api.marketing.get_campaigns',
      customParams: {
          restaurant_id: selectedRestaurant,
          status_filter: statusFilter !== 'All' ? statusFilter : undefined
      },
      paramNames: {
          page: 'page_num',
          pageSize: 'page_length',
          search: 'search_query'
      },
      initialPageSize: 10,
      debugId: `campaigns-${selectedRestaurant}`
  })

  const { call: fetchSegments } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.get_segments')
  const { call: createCampaignApi } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.create_campaign')
  const { call: sendCampaignApi } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.send_campaign')
  const { call: deleteCampaignApi } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.delete_campaign')
  const { call: cancelCampaignApi } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.cancel_campaign')

  useEffect(() => {
    if (selectedRestaurant) {
        fetchSegments({ restaurant_id: selectedRestaurant }).then((res: any) => {
            if (res.message?.success) setSegments(res.message.data || [])
        })
    }
  }, [selectedRestaurant, fetchSegments])

  const selectedSegment = segments.find(s => s.name === form.target_segment)
  const estimatedCoinCost = (selectedSegment?.estimated_reach ?? 0) * (form.channel === 'WhatsApp' ? 1.2 : form.channel === 'SMS' ? 0.25 : 0.05)

  const handleTemplateChange = (key: string) => {
    setForm(f => ({ ...f, template_key: key, message_template: TEMPLATES[key as keyof typeof TEMPLATES] ?? '' }))
  }

  const handleLaunch = async () => {
    if (!form.campaign_name || !form.target_segment || !form.message_template) {
      toast.error('Please fill all required fields')
      return
    }
    setSending(true)
    try {
      const createRes: any = await createCampaignApi({
        restaurant_id: selectedRestaurant,
        campaign_data: {
          campaign_name: form.campaign_name,
          channel: form.channel,
          target_segment: form.target_segment,
          message_template: form.message_template,
          email_subject: form.email_subject || null,
          include_coupon: form.include_coupon ? 1 : 0,
          coupon_code: form.coupon_code || null,
          scheduled_at: form.send_now ? null : form.scheduled_at,
        }
      })
      if (!createRes?.message?.success) throw new Error(createRes?.message?.error || 'Failed to create')

      if (form.send_now) {
        const sendRes: any = await sendCampaignApi({ campaign_id: createRes.message.data.name })
        if (!sendRes?.message?.success) throw new Error(sendRes?.message?.error || 'Failed to send')
        toast.success(`Campaign "${form.campaign_name}" is being sent!`)
      } else {
        toast.success(`Campaign "${form.campaign_name}" scheduled!`)
      }
      setShowWizard(false)
      setStep('audience')
      setForm({ campaign_name: '', channel: 'WhatsApp', target_segment: '', message_template: '', email_subject: '', template_key: 'custom', include_coupon: false, coupon_code: '', scheduled_at: '', send_now: true })
      mutate()
    } catch (e: any) {
      toast.error(e.message || 'Campaign failed')
    } finally {
      setSending(false)
    }
  }

  const handleDelete = async () => {
    try {
      const res: any = await deleteCampaignApi({ campaign_id: confirmDelete.id })
      if (res?.message?.success) {
        toast.success('Campaign deleted')
        mutate()
      } else {
        toast.error(res?.message?.error || 'Failed to delete')
      }
    } catch (e: any) { toast.error(e.message) }
  }

  const handleCancel = async () => {
    try {
      const res: any = await cancelCampaignApi({ campaign_id: confirmCancel.id })
      if (res?.message?.success) {
        toast.success('Campaign cancelled')
        mutate()
      } else {
        toast.error(res?.message?.error || 'Failed to cancel')
      }
    } catch (e: any) { toast.error(e.message) }
  }

  const stepIndex = STEPS.indexOf(step)
  const canProceed = step === 'audience'
    ? !!form.target_segment && !!form.campaign_name && !!form.channel
    : step === 'message' ? !!form.message_template
    : true

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1.5 text-[11px] font-bold tracking-widest uppercase text-muted-foreground/60 mb-2">
        <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
        <ChevronRight className="h-3 w-3" />
        <Link to="/marketing" className="hover:text-foreground transition-colors">Marketing</Link>
        <ChevronRight className="h-3 w-3" />
        <span className="text-foreground">Campaigns</span>
      </nav>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Campaigns</h1>
          <p className="text-sm text-muted-foreground">Create and manage marketing blasts</p>
        </div>
        <Button onClick={() => { setShowWizard(true); setStep('audience') }} className="gap-2 bg-gradient-to-r from-indigo-500 to-purple-600 text-white shadow-lg">
          <Plus className="h-4 w-4" /> New Campaign
        </Button>
      </div>

      {showWizard && (
        <Card className="border-indigo-200 shadow-xl animate-in zoom-in-95 duration-300 overflow-hidden">
          <div className="h-1.5 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500" />
          <CardHeader className="pb-3 border-b bg-muted/20">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-black uppercase tracking-widest text-indigo-600 dark:text-indigo-400">Campaign Wizard</CardTitle>
              <button onClick={() => setShowWizard(false)} className="p-1 hover:bg-muted rounded-full transition-colors"><X className="h-4 w-4 text-muted-foreground" /></button>
            </div>
            {/* Step bar */}
            <div className="flex gap-1 mt-4">
              {STEPS.map((s, i) => (
                <div key={s} className="flex items-center gap-1 flex-1">
                  <div className={`flex items-center gap-1.5 text-[10px] font-black uppercase tracking-tighter px-3 py-2 rounded-lg flex-1 justify-center transition-all
                    ${s === step 
                      ? 'bg-indigo-600 text-white shadow-md' 
                      : i < stepIndex 
                        ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400' 
                        : 'bg-muted text-muted-foreground'}`}>
                    {i < stepIndex ? <Check className="h-3 w-3" /> : <span>{i + 1}</span>}
                    {STEP_LABELS[s]}
                  </div>
                </div>
              ))}
            </div>
          </CardHeader>
          <CardContent className="pt-6 space-y-6">
            {/* Step 1: Audience */}
            {step === 'audience' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 scale-in-95 animate-in duration-300">
                <div className="space-y-2">
                  <Label className="text-xs font-bold uppercase tracking-wider">Campaign Name *</Label>
                  <Input placeholder="e.g. Weekend WhatsApp Blast" value={form.campaign_name} onChange={e => setForm(f => ({ ...f, campaign_name: e.target.value }))} className="bg-muted/30 focus-visible:ring-indigo-500" />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs font-bold uppercase tracking-wider">Channel *</Label>
                  <Select value={form.channel} onValueChange={v => setForm(f => ({ ...f, channel: v }))}>
                    <SelectTrigger className="bg-muted/30"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="WhatsApp">
                        <div className="flex items-center gap-2">
                          <MessageSquare className="h-3.5 w-3.5 text-green-500" />
                          <span>WhatsApp (₹1.20/msg)</span>
                        </div>
                      </SelectItem>
                      <SelectItem value="SMS">
                        <div className="flex items-center gap-2">
                          <Smartphone className="h-3.5 w-3.5 text-blue-500" />
                          <span>SMS (₹0.25/msg)</span>
                        </div>
                      </SelectItem>
                      <SelectItem value="Email">
                        <div className="flex items-center gap-2">
                          <Mail className="h-3.5 w-3.5 text-purple-500" />
                          <span>Email (₹0.05/msg)</span>
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label className="text-xs font-bold uppercase tracking-wider">Target Segment *</Label>
                  {segments.length === 0 ? (
                    <div className="p-4 border rounded-xl bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 text-sm flex gap-2">
                      <AlertCircle className="h-5 w-5 flex-shrink-0" />
                      <span>No segments found. Create a segment first.</span>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                      {segments.map(seg => (
                        <div key={seg.name} onClick={() => setForm(f => ({ ...f, target_segment: seg.name }))}
                            className={cn(
                                "group p-4 border rounded-xl cursor-pointer transition-all duration-300 relative overflow-hidden",
                                form.target_segment === seg.name 
                                    ? "border-indigo-600 bg-indigo-50/50 dark:bg-indigo-900/20 shadow-md ring-1 ring-indigo-600" 
                                    : "bg-muted/10 hover:border-indigo-300 hover:bg-muted/20"
                            )}>
                          <div className="flex justify-between items-start mb-2">
                            <p className="text-sm font-bold truncate">{seg.segment_name}</p>
                            {form.target_segment === seg.name && <Check className="h-4 w-4 text-indigo-600" />}
                          </div>
                          <p className="text-[10px] text-muted-foreground font-medium uppercase tracking-widest">{seg.criteria_type} · ~{seg.estimated_reach} users</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {selectedSegment && (
                  <div className="md:col-span-2 p-4 rounded-xl bg-indigo-600 text-white shadow-lg flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <Users className="h-5 w-5" />
                        <div>
                            <p className="text-[10px] font-black uppercase tracking-widest opacity-80">Estimated Reach</p>
                            <p className="text-lg font-bold">~{selectedSegment.estimated_reach.toLocaleString()} Customers</p>
                        </div>
                    </div>
                    <div className="text-right">
                        <p className="text-[10px] font-black uppercase tracking-widest opacity-80">Estimated Cost</p>
                        <p className="text-lg font-bold">{estimatedCoinCost.toFixed(1)} Coins</p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Step 2: Message */}
            {step === 'message' && (
              <div className="space-y-6 animate-in slide-in-from-right-4 duration-300">
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                  {[
                    { key: 'win_back', label: 'Win-Back', icon: HeartOff, color: 'text-red-500' },
                    { key: 'loyalty_nudge', label: 'Points Nudge', icon: Trophy, color: 'text-amber-500' },
                    { key: 'new_offer', label: 'Offer Blast', icon: Megaphone, color: 'text-blue-500' },
                    { key: 'birthday', label: 'Birthday', icon: Cake, color: 'text-pink-500' },
                    { key: 'custom', label: 'Custom', icon: Edit3, color: 'text-slate-500' }
                  ].map((tpl) => (
                    <button key={tpl.key} onClick={() => handleTemplateChange(tpl.key)}
                      className={cn(
                          "px-3 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-tighter border-2 transition-all flex flex-col items-center gap-1",
                          form.template_key === tpl.key 
                            ? "bg-indigo-600 text-white border-indigo-600 shadow-lg scale-105" 
                            : "bg-muted/20 border-transparent hover:border-muted-foreground"
                      )}>
                      <tpl.icon className={cn("h-4 w-4 mb-0.5", form.template_key === tpl.key ? "text-white" : tpl.color)} />
                      {tpl.label}
                    </button>
                  ))}
                </div>
                <div className="space-y-2">
                  <Label className="text-xs font-bold uppercase tracking-wider">Message Content *</Label>
                  <Textarea rows={6} placeholder="Type your message here..."
                    className="text-sm rounded-xl bg-muted/20 focus-visible:ring-indigo-500 font-medium"
                    value={form.message_template} onChange={e => setForm(f => ({ ...f, message_template: e.target.value, template_key: 'custom' }))} />
                  <div className="flex justify-between items-center text-[10px] font-bold uppercase tracking-widest">
                    <span className="text-indigo-500">Variables available: {'{{customer_name}}'}, {'{{coupon_code}}'}</span>
                    <span className={form.channel === 'SMS' && form.message_template.length > 160 ? 'text-red-500' : 'text-muted-foreground'}>
                      {form.message_template.length} Characters
                    </span>
                  </div>
                </div>
                {form.channel === 'Email' && (
                  <div className="space-y-2 animate-in fade-in duration-500">
                    <Label className="text-xs font-bold uppercase tracking-wider">Email Subject *</Label>
                    <Input placeholder="Subject line..." value={form.email_subject} onChange={e => setForm(f => ({ ...f, email_subject: e.target.value }))} className="bg-muted/20" />
                  </div>
                )}
                <div className="flex items-center gap-3 p-4 bg-muted/10 rounded-xl border border-dashed border-muted-foreground/30">
                  <input type="checkbox" id="inc_coupon" checked={form.include_coupon} onChange={e => setForm(f => ({ ...f, include_coupon: e.target.checked }))} className="w-4 h-4 rounded border-indigo-500 text-indigo-600 focus:ring-indigo-500" />
                  <Label htmlFor="inc_coupon" className="text-sm font-bold">Include a promotional coupon</Label>
                </div>
                {form.include_coupon && (
                  <Input 
                    placeholder="Enter coupon code..." 
                    value={form.coupon_code} 
                    onChange={e => setForm(f => ({ ...f, coupon_code: e.target.value }))} 
                    className="bg-indigo-50/30 dark:bg-indigo-900/10 border-indigo-200 dark:border-indigo-800 focus-visible:ring-indigo-500" 
                  />
                )}
              </div>
            )}

            {/* Step 3: Schedule */}
            {step === 'schedule' && (
              <div className="space-y-6 animate-in slide-in-from-right-4 duration-300">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {[
                    { label: 'Send Now', value: true, sub: 'Immediate dispatch', icon: Zap, color: 'text-amber-500' }, 
                    { label: 'Schedule', value: false, sub: 'Future date & time', icon: CalendarIcon, color: 'text-blue-500' }
                  ].map(opt => (
                    <div key={String(opt.value)} onClick={() => setForm(f => ({ ...f, send_now: opt.value }))}
                      className={cn(
                          "p-6 border-2 rounded-2xl cursor-pointer transition-all duration-300 flex flex-col items-center text-center gap-1",
                          form.send_now === opt.value 
                            ? "border-indigo-600 bg-indigo-50 dark:bg-indigo-900/20 shadow-md ring-1 ring-indigo-600" 
                            : "bg-muted/10 border-transparent hover:border-muted-foreground"
                      )}>
                      <opt.icon className={cn("h-6 w-6 mb-1", form.send_now === opt.value ? "text-indigo-600 dark:text-indigo-400" : opt.color)} />
                      <p className="font-black uppercase tracking-widest text-sm">{opt.label}</p>
                      <p className="text-[10px] text-muted-foreground font-medium">{opt.sub}</p>
                    </div>
                  ))}
                </div>
                 {!form.send_now && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 animate-in fade-in duration-500">
                    <div className="space-y-2">
                      <Label className="text-xs font-bold uppercase tracking-wider">Select Date</Label>
                      <DatePicker 
                        value={form.scheduled_at?.split('T')[0]} 
                        onChange={(val) => {
                          const time = form.scheduled_at?.split('T')[1] || '12:00:00'
                          setForm(f => ({ ...f, scheduled_at: val ? `${val}T${time}` : '' }))
                        }} 
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-xs font-bold uppercase tracking-wider">Select Time</Label>
                      <TimePicker 
                        value={form.scheduled_at?.split('T')[1] || '12:00:00'} 
                        onChange={(e) => {
                          const date = form.scheduled_at?.split('T')[0] || new Date().toISOString().split('T')[0]
                          setForm(f => ({ ...f, scheduled_at: `${date}T${e.target.value}` }))
                        }} 
                      />
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Step 4: Review */}
            {step === 'review' && (
              <div className="space-y-6 animate-in zoom-in-95 duration-300">
                <div className="grid grid-cols-2 gap-3">
                  {[
                    ['Goal', form.campaign_name],
                    ['Channel', form.channel],
                    ['Segment', selectedSegment?.segment_name ?? '—'],
                    ['Reach', `~${selectedSegment?.estimated_reach ?? 0} Users`],
                    ['Cost', `${estimatedCoinCost.toFixed(1)} Coins`],
                    ['Time', form.send_now ? 'ASAP' : (form.scheduled_at || '—')],
                  ].map(([k, v]) => (
                    <div key={k} className="p-3 bg-muted/20 rounded-xl border border-border/50">
                      <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">{k}</p>
                      <p className="text-xs font-bold truncate">{v}</p>
                    </div>
                  ))}
                </div>
                <div className="p-4 rounded-xl bg-slate-900 text-slate-100 font-mono text-xs relative overflow-hidden">
                   <div className="absolute top-0 right-0 p-2 opacity-10"><Send className="h-10 w-10 rotate-12" /></div>
                   <p className="text-[10px] text-indigo-400 font-black uppercase tracking-widest mb-2 flex items-center gap-1"><Check className="h-3 w-3" /> Preview Message</p>
                   <p className="whitespace-pre-wrap leading-relaxed opacity-90">{form.message_template}</p>
                </div>
              </div>
            )}

            {/* Navigation */}
            <div className="flex justify-between items-center pt-6 border-t">
              <Button variant="ghost" onClick={() => step === 'audience' ? setShowWizard(false) : setStep(STEPS[stepIndex - 1])} disabled={sending} className="text-xs font-bold uppercase tracking-widest">
                {step === 'audience' ? 'Cancel' : 'Back'}
              </Button>
              {step !== 'review' ? (
                <Button onClick={() => setStep(STEPS[stepIndex + 1])} disabled={!canProceed} className="bg-indigo-600 text-white hover:bg-indigo-700 px-8 rounded-xl shadow-lg shadow-indigo-500/20">
                  Next Step <ChevronRight className="h-4 w-4 ml-2" />
                </Button>
              ) : (
                <Button onClick={handleLaunch} disabled={sending} className="bg-gradient-to-r from-indigo-600 to-purple-600 text-white px-8 rounded-xl shadow-lg shadow-indigo-500/30 gap-2 scale-105 transition-transform active:scale-95">
                  {sending ? <><Loader2 className="h-4 w-4 animate-spin" /> Processing...</> : <><Send className="h-4 w-4" /> Finalize & Blast</>}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Campaign List */}
      <Card className="shadow-lg border-none overflow-hidden bg-card/50 backdrop-blur-sm">
        <CardHeader className="pb-3 border-b space-y-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-black uppercase tracking-widest text-muted-foreground">Manage History</CardTitle>
            <div className="flex items-center gap-3">
              <div className="relative">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Find campaign..."
                  className="pl-9 h-9 w-48 lg:w-64 text-xs bg-muted/20 border-none focus-visible:ring-indigo-500"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                />
              </div>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="h-9 w-32 bg-muted/20 border-none text-xs font-bold">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="All">All Status</SelectItem>
                  <SelectItem value="Sent">Sent</SelectItem>
                  <SelectItem value="Scheduled">Scheduled</SelectItem>
                  <SelectItem value="Draft">Draft</SelectItem>
                  <SelectItem value="Failed">Failed</SelectItem>
                  <SelectItem value="Cancelled">Cancelled</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
                <TableHeader className="bg-muted/30">
                    <TableRow>
                        <TableHead className="font-bold text-[10px] uppercase tracking-widest text-muted-foreground">Campaign Details</TableHead>
                        <TableHead className="font-bold text-[10px] uppercase tracking-widest text-muted-foreground">Channel</TableHead>
                        <TableHead className="font-bold text-[10px] uppercase tracking-widest text-muted-foreground">Performance</TableHead>
                        <TableHead className="font-bold text-[10px] uppercase tracking-widest text-muted-foreground">Status</TableHead>
                        <TableHead className="text-right pr-6 font-bold text-[10px] uppercase tracking-widest text-muted-foreground">Actions</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {isLoading && campaigns.length === 0 ? (
                        [1,2,3].map(i => <TableRow key={i}><TableCell colSpan={5}><Skeleton className="h-12 w-full" /></TableCell></TableRow>)
                    ) : campaigns.length === 0 ? (
                        <TableRow>
                            <TableCell colSpan={5} className="py-20 text-center">
                                <div className="flex flex-col items-center gap-3 text-muted-foreground opacity-40">
                                    <Send className="h-12 w-12" />
                                    <p className="text-sm font-bold">No campaigns found matching criteria.</p>
                                </div>
                            </TableCell>
                        </TableRow>
                    ) : (
                        campaigns.map((c: Campaign) => (
                            <TableRow key={c.name} className="group hover:bg-muted/20 transition-colors">
                                <TableCell>
                                    <div className="flex flex-col">
                                        <p className="font-black text-sm text-foreground mb-0.5 group-hover:text-indigo-600 transition-colors">{c.campaign_name}</p>
                                        <div className="flex items-center gap-2 text-[10px] font-bold text-muted-foreground">
                                            <span className="flex items-center gap-1 uppercase tracking-tight"><Users className="h-3 w-3" /> {c.target_segment}</span>
                                            <span>·</span>
                                            <span>{new Date(c.creation).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}</span>
                                        </div>
                                    </div>
                                </TableCell>
                                <TableCell>
                                    <Badge variant="secondary" className="bg-muted font-bold text-[10px] uppercase tracking-tighter flex items-center gap-1.5 w-fit">
                                        {c.channel === 'WhatsApp' ? <><MessageSquare className="h-3 w-3 text-green-500" /> WhatsApp</> : c.channel === 'SMS' ? <><Smartphone className="h-3 w-3 text-blue-500" /> SMS</> : <><Mail className="h-3 w-3 text-purple-500" /> Email</>}
                                    </Badge>
                                </TableCell>
                                <TableCell>
                                    <div className="flex items-center gap-4 text-xs font-bold tabular-nums">
                                        <div className="flex flex-col">
                                            <span className="text-[9px] uppercase tracking-widest text-muted-foreground">Sent</span>
                                            <span>{c.total_sent?.toLocaleString() || 0}</span>
                                        </div>
                                        {c.total_conversions > 0 && (
                                            <div className="flex flex-col text-emerald-600">
                                                <span className="text-[9px] uppercase tracking-widest opacity-70">Conv.</span>
                                                <span>{c.total_conversions}</span>
                                            </div>
                                        )}
                                        <div className="flex flex-col text-indigo-500">
                                            <span className="text-[9px] uppercase tracking-widest opacity-70">Cost</span>
                                            <span>{c.total_cost_coins.toFixed(1)}</span>
                                        </div>
                                    </div>
                                </TableCell>
                                <TableCell>
                                    <span className={cn(
                                        "text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md",
                                        STATUS_COLORS[c.status] || 'bg-muted'
                                    )}>
                                        {c.status}
                                    </span>
                                </TableCell>
                                <TableCell className="text-right pr-6">
                                    <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                        {c.status === 'Sent' && (
                                            <Button variant="ghost" size="icon" className="h-8 w-8 text-indigo-500" onClick={() => navigate(`/marketing/analytics?campaign=${c.name}`)}>
                                                <BarChart3 className="h-4 w-4" />
                                            </Button>
                                        )}
                                        {c.status === 'Draft' && (
                                            <Button variant="ghost" size="icon" className="h-8 w-8 text-red-400 hover:text-red-500" onClick={() => setConfirmDelete({ open: true, id: c.name, label: c.campaign_name })}>
                                                <Trash2 className="h-4 w-4" />
                                            </Button>
                                        )}
                                        {c.status === 'Scheduled' && (
                                            <Button variant="ghost" size="icon" className="h-8 w-8 text-amber-500" onClick={() => setConfirmCancel({ open: true, id: c.name, label: c.campaign_name })}>
                                                <XCircle className="h-4 w-4" />
                                            </Button>
                                        )}
                                        <ChevronRight className="h-4 w-4 text-muted-foreground/30" />
                                    </div>
                                </TableCell>
                            </TableRow>
                        ))
                    )}
                </TableBody>
            </Table>
          </div>
          
          <div className="p-4 border-t">
              <DataPagination
                currentPage={page}
                totalCount={totalCount}
                pageSize={pageSize}
                onPageChange={setPage}
                onPageSizeChange={setPageSize}
                isLoading={isLoading}
              />
          </div>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmDelete.open}
        onOpenChange={(open) => setConfirmDelete(d => ({ ...d, open }))}
        title="Delete Draft Campaign?"
        description={`This will permanently remove "${confirmDelete.label}".`}
        confirmText="Confirm Delete"
        variant="destructive"
        onConfirm={handleDelete}
      />

      <ConfirmDialog
        open={confirmCancel.open}
        onOpenChange={(open) => setConfirmCancel(d => ({ ...d, open }))}
        title="Stop Scheduled Blast?"
        description={`Prevent "${confirmCancel.label}" from being sent?`}
        confirmText="Stop Campaign"
        variant="warning"
        onConfirm={handleCancel}
      />
    </div>
  )
}
