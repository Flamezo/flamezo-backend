import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall } from '@/lib/frappe'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Zap, Plus, Trash2, Loader2, Edit2, X, Check, Search, BellRing, ChevronRight } from 'lucide-react'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { toast } from 'sonner'

interface Trigger {
  name: string; trigger_name: string; trigger_event: string; channel: string
  is_active: number; delay_hours: number; days_since_visit: number
  loyalty_milestone_points: number; total_fired: number; message_template: string
  include_coupon: number; coupon_code: string
}

const PRESET_TEMPLATES = [
  {
    id: 'review',
    emoji: '⭐',
    label: 'Post-Visit Review Nudge',
    description: 'WhatsApp sent 2h after a completed order, asking for a Google Review.',
    trigger_event: 'On Order Complete',
    channel: 'WhatsApp',
    delay_hours: 2,
    message_template: "Hi {{customer_name}}! 🙏 Thank you for dining at {{restaurant_name}}. We'd love your feedback — it helps us improve!\n\nLeave us a Google Review here: {{review_link}}\n\nSee you again soon! 😊"
  },
  {
    id: 'winback',
    emoji: '💔',
    label: 'Win-Back Campaign',
    description: 'SMS sent 30 days after a customer\'s last visit.',
    trigger_event: 'X Days After Last Visit',
    channel: 'SMS',
    delay_hours: 0,
    days_since_visit: 30,
    message_template: "Hi {{customer_name}}, we miss you at {{restaurant_name}}! 🍽️ Come back and enjoy {{coupon_code}} on your next visit. Limited time offer!"
  },
  {
    id: 'birthday',
    emoji: '🎂',
    label: 'Birthday Surprise',
    description: 'WhatsApp sent on the customer\'s birthday.',
    trigger_event: 'On Birthday',
    channel: 'WhatsApp',
    delay_hours: 0,
    message_template: "🎂 Happy Birthday {{customer_name}}! The team at {{restaurant_name}} wishes you a wonderful day. Enjoy a special birthday gift: {{coupon_code}} ❤️ See you soon!"
  },
  {
    id: 'milestone',
    emoji: '🏆',
    label: 'Points Milestone',
    description: 'SMS when a customer crosses 500 loyalty points.',
    trigger_event: 'On Loyalty Milestone',
    channel: 'SMS',
    delay_hours: 0,
    loyalty_milestone_points: 500,
    message_template: "Congrats {{customer_name}}! You've earned 500+ loyalty points at {{restaurant_name}} 🏆 Redeem them on your next visit for a FREE reward!"
  },
  {
    id: 'referral',
    emoji: '📣',
    label: 'Referral Thank You',
    description: 'Email sent when someone signs up via your referral link.',
    trigger_event: 'On Referral Signup',
    channel: 'Email',
    delay_hours: 0,
    message_template: "Hi {{customer_name}},\n\nThank you for sharing {{restaurant_name}} with your friends! 🎉\n\nYour referral bonus points are ready to use on your next order. Keep sharing and keep earning!\n\nSee you at {{restaurant_name}} soon."
  },
]



export default function MarketingAutomation() {
  const { selectedRestaurant } = useRestaurant()
  const [triggers, setTriggers] = useState<Trigger[]>([])
  const [loading, setLoading] = useState(true)
  const [editTrigger, setEditTrigger] = useState<Partial<Trigger> | null>(null)
  const [saving, setSaving] = useState(false)

  // Management states
  const [searchQuery, setSearchQuery] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<{open: boolean, name: string, label: string}>({
    open: false, name: '', label: ''
  })

  const { call: fetchTriggers } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.get_triggers')
  const { call: saveTriggerApi } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.save_trigger')
  const { call: deleteTriggerApi } = useFrappePostCall('flamezo_backend.flamezo.api.marketing.delete_trigger')

  const load = () => {
    if (!selectedRestaurant) return
    setLoading(true)
    fetchTriggers({ restaurant_id: selectedRestaurant }).then((res: any) => {
      if (res?.message?.success) {
        setTriggers(res.message.data || [])
      }
    })
    .catch((err) => console.error("Failed to load triggers:", err))
    .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [selectedRestaurant])

  const handleToggle = async (trigger: Trigger) => {
    try {
      await saveTriggerApi({
        restaurant_id: selectedRestaurant,
        trigger_data: { name: trigger.name, is_active: trigger.is_active ? 0 : 1 }
      })
      toast.success(trigger.is_active ? 'Trigger paused' : 'Trigger activated')
      load()
    } catch (e: any) { toast.error(e.message) }
  }

  const handleSave = async () => {
    if (!editTrigger?.trigger_name || !editTrigger?.trigger_event || !editTrigger?.message_template) {
      toast.error('Fill all required fields')
      return
    }
    setSaving(true)
    try {
      await saveTriggerApi({ restaurant_id: selectedRestaurant, trigger_data: editTrigger })
      toast.success('Trigger saved!')
      setEditTrigger(null)
      load()
    } catch (e: any) { toast.error(e.message) } finally { setSaving(false) }
  }

  const handleDelete = async () => {
    try {
      await deleteTriggerApi({ trigger_name: confirmDelete.name })
      toast.success('Trigger deleted')
      load()
    } catch (e: any) { toast.error(e.message) }
  }

  const filteredTriggers = triggers.filter(t => 
    t.trigger_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    t.trigger_event.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const usePreset = (preset: typeof PRESET_TEMPLATES[0]) => {
    setEditTrigger({
      trigger_name: preset.label,
      trigger_event: preset.trigger_event,
      channel: preset.channel,
      delay_hours: preset.delay_hours,
      days_since_visit: (preset as any).days_since_visit ?? 30,
      loyalty_milestone_points: (preset as any).loyalty_milestone_points ?? 500,
      is_active: 1,
      message_template: preset.message_template,
      include_coupon: 0,
    })
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1.5 text-[11px] font-bold tracking-widest uppercase text-muted-foreground/60 mb-2">
        <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
        <ChevronRight className="h-3 w-3" />
        <Link to="/marketing" className="hover:text-foreground transition-colors">Marketing</Link>
        <ChevronRight className="h-3 w-3" />
        <span className="text-foreground">Automation</span>
      </nav>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2 font-bold tracking-tight"><Zap className="h-6 w-6 text-yellow-500" /> Automation</h1>
          <p className="text-sm text-muted-foreground">Set-and-forget triggers that run automatically</p>
        </div>
        <Button onClick={() => setEditTrigger({ is_active: 1, delay_hours: 2, channel: 'WhatsApp', trigger_event: 'On Order Complete' })} className="gap-2">
          <Plus className="h-4 w-4" /> New Trigger
        </Button>
      </div>

      {/* Preset Templates */}
      {!editTrigger && (
        <div>
          <p className="text-sm font-medium mb-3 text-muted-foreground">Quick-start templates</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {PRESET_TEMPLATES.map(preset => {
              const alreadyAdded = triggers.some(t => t.trigger_name === preset.label)
              return (
                <div key={preset.id} className="p-4 border rounded-xl hover:border-yellow-400 transition-colors group">
                  <div className="text-2xl mb-2">{preset.emoji}</div>
                  <p className="text-sm font-semibold">{preset.label}</p>
                  <p className="text-xs text-muted-foreground mt-1 mb-3">{preset.description}</p>
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-muted font-mono">{preset.channel}</span>
                    {alreadyAdded ? (
                      <span className="text-xs text-green-600 flex items-center gap-1"><Check className="h-3 w-3" /> Added</span>
                    ) : (
                      <Button size="sm" variant="outline" className="text-xs h-6 px-2" onClick={() => usePreset(preset)}>
                        Use Template
                      </Button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Editor */}
      {editTrigger && (
        <Card className="border-yellow-200 shadow-sm">
          <CardHeader className="pb-3 border-b flex flex-row items-center justify-between">
            <CardTitle className="text-base">{editTrigger.name ? 'Edit Trigger' : 'New Trigger'}</CardTitle>
            <button onClick={() => setEditTrigger(null)}><X className="h-4 w-4 text-muted-foreground" /></button>
          </CardHeader>
          <CardContent className="pt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Trigger Name *</Label>
              <Input value={editTrigger.trigger_name ?? ''} onChange={e => setEditTrigger(t => ({ ...t, trigger_name: e.target.value }))} placeholder="e.g. Post-Visit Review" />
            </div>
            <div className="space-y-2">
              <Label>Channel *</Label>
              <Select value={editTrigger.channel ?? 'WhatsApp'} onValueChange={v => setEditTrigger(t => ({ ...t, channel: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="WhatsApp">💬 WhatsApp</SelectItem>
                  <SelectItem value="SMS">📱 SMS</SelectItem>
                  <SelectItem value="Email">📧 Email</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Trigger Event *</Label>
              <Select value={editTrigger.trigger_event ?? 'On Order Complete'} onValueChange={v => setEditTrigger(t => ({ ...t, trigger_event: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="On Order Complete">On Order Complete</SelectItem>
                  <SelectItem value="On Referral Signup">On Referral Signup</SelectItem>
                  <SelectItem value="On Birthday">On Birthday</SelectItem>
                  <SelectItem value="X Days After Last Visit">X Days After Last Visit</SelectItem>
                  <SelectItem value="On Loyalty Milestone">On Loyalty Milestone</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Delay (Hours after event)</Label>
              <NumberInput  min={0} value={editTrigger.delay_hours ?? 2} onChange={e => setEditTrigger(t => ({ ...t, delay_hours: parseInt(e.target.value) }))} />
            </div>
            {editTrigger.trigger_event === 'X Days After Last Visit' && (
              <div className="space-y-2">
                <Label>Days Inactive</Label>
                <NumberInput  min={1} value={editTrigger.days_since_visit ?? 30} onChange={e => setEditTrigger(t => ({ ...t, days_since_visit: parseInt(e.target.value) }))} />
              </div>
            )}
            {editTrigger.trigger_event === 'On Loyalty Milestone' && (
              <div className="space-y-2">
                <Label>Milestone (₹)</Label>
                <NumberInput  min={1} value={editTrigger.loyalty_milestone_points ?? 500} onChange={e => setEditTrigger(t => ({ ...t, loyalty_milestone_points: parseInt(e.target.value) }))} />
              </div>
            )}
            <div className="space-y-2 md:col-span-2">
              <Label>Message Body * <span className="text-muted-foreground text-xs">(supports {'{{customer_name}}'}, {'{{restaurant_name}}'}, {'{{loyalty_balance}}'}, {'{{coupon_code}}'})</span></Label>
              <Textarea rows={4} value={editTrigger.message_template ?? ''} onChange={e => setEditTrigger(t => ({ ...t, message_template: e.target.value }))} />
            </div>
            <div className="md:col-span-2 flex items-center justify-between border-t pt-3">
              <div className="flex items-center gap-2">
                <Switch checked={!!editTrigger.is_active} onCheckedChange={v => setEditTrigger(t => ({ ...t, is_active: v ? 1 : 0 }))} />
                <Label>Active</Label>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setEditTrigger(null)}>Cancel</Button>
                <Button onClick={handleSave} disabled={saving} className="gap-2 bg-yellow-500 text-white hover:bg-yellow-600">
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Save Trigger
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Active Triggers List */}
      <Card>
        <CardHeader className="pb-3 border-b flex flex-row items-center justify-between">
          <CardTitle className="text-base font-bold flex items-center gap-2">
            <BellRing className="h-4 w-4 text-muted-foreground" /> Your Triggers ({triggers.length})
          </CardTitle>
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search triggers..."
              className="pl-9 h-9 w-64 text-sm bg-muted/20 border-none"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          {loading ? <div className="space-y-3 pt-4">{[1, 2, 3].map(i => <Skeleton key={i} className="h-16 w-full rounded-xl" />)}</div>
            : filteredTriggers.length === 0 ? (
              <div className="flex flex-col items-center py-16 gap-2 text-muted-foreground">
                <Zap className="h-12 w-12 opacity-15" />
                <p className="text-sm">
                  {searchQuery ? "No triggers match your search." : "No triggers yet. Use a template above to get started."}
                </p>
              </div>
            ) : (
              <div className="divide-y">
                {filteredTriggers.map(t => (
                  <div key={t.name} className="py-4 flex items-center gap-4 hover:bg-muted/10 -mx-2 px-2 rounded-lg transition-colors group">
                    <Switch checked={!!t.is_active} onCheckedChange={() => handleToggle(t)} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <p className="text-sm font-bold truncate">{t.trigger_name}</p>
                        {!t.is_active && <span className="text-[10px] font-black uppercase text-muted-foreground px-1.5 py-0.5 rounded bg-muted">Paused</span>}
                      </div>
                      <p className="text-xs text-muted-foreground font-medium">
                        {t.trigger_event} · {t.channel} · <span className="text-indigo-600 font-bold">{t.total_fired} fired</span>
                      </p>
                    </div>
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => setEditTrigger(t)} title="Edit">
                        <Edit2 className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                      </Button>
                      <Button size="icon" variant="ghost" className="h-8 w-8 hover:bg-red-50" onClick={() => setConfirmDelete({ open: true, name: t.name, label: t.trigger_name })} title="Delete">
                        <Trash2 className="h-4 w-4 text-red-400" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmDelete.open}
        onOpenChange={(open) => setConfirmDelete(d => ({ ...d, open }))}
        title="Delete Trigger?"
        description={`This will permanently delete the automation trigger "${confirmDelete.label}". Messages will no longer be sent automatically.`}
        confirmText="Delete Trigger"
        variant="destructive"
        onConfirm={handleDelete}
      />
    </div>

  )
}
