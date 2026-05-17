import { useState, useCallback } from 'react'
import { useFrappeGetCall, useFrappePostCall } from '@/lib/frappe'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle
} from '@/components/ui/alert-dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select'
import {
  UserPlus, Shield, User, Trash2, Power, PowerOff, Crown,
  Zap, Star, Mail, AlertCircle, ChevronUp
} from 'lucide-react'
import { toast } from 'sonner'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { cn } from '@/lib/utils'

// ---------- Types ----------

interface StaffMember {
  name: string
  user: string
  full_name: string
  email: string
  user_image?: string
  role: 'Restaurant Admin' | 'Restaurant Staff'
  is_active: boolean
  is_default: boolean
  creation: string
}

interface StaffData {
  members: StaffMember[]
  seat_limit: number
  seats_used: number
  seats_remaining: number
  plan_type: string
  can_add_staff: boolean
}

interface StaffMembersListProps {
  restaurantId: string
  onAdd?: () => void
}

// ---------- Inline Avatar ----------

function StaffAvatar({ src, initials }: { src?: string; initials: string }) {
  const gradients = [
    'from-blue-500 to-indigo-600',
    'from-emerald-500 to-teal-600',
    'from-orange-500 to-rose-600',
    'from-purple-500 to-fuchsia-600',
  ]
  const gradient = gradients[initials.charCodeAt(0) % gradients.length]

  return (
    <div className={cn(
      "w-10 h-10 rounded-full flex-shrink-0 overflow-hidden flex items-center justify-center border-2 border-background shadow-sm ring-1 ring-border/30",
      !src && `bg-gradient-to-br ${gradient}`
    )}>
      {src ? (
        <img src={src} alt={initials} className="w-full h-full object-cover" />
      ) : (
        <span className="text-[13px] font-bold text-white tracking-tighter">{initials}</span>
      )}
    </div>
  )
}

// ---------- Main Component ----------

export default function StaffMembersList({ restaurantId, onAdd }: StaffMembersListProps) {
  const { isAdmin, planType } = useRestaurant()
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [removeTarget, setRemoveTarget] = useState<StaffMember | null>(null)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteFullName, setInviteFullName] = useState('')
  const [inviteRole, setInviteRole] = useState<'Restaurant Staff' | 'Restaurant Admin'>('Restaurant Staff')
  const [inviteLoading, setInviteLoading] = useState(false)

  const { data: staffDataRaw, isLoading, mutate } = useFrappeGetCall<{ message: { success: boolean; data: StaffData } }>(
    'flamezo_backend.flamezo.api.staff.get_staff_members',
    { restaurant_id: restaurantId },
    restaurantId ? `staff-members-${restaurantId}` : null
  )

  const { call: callPost } = useFrappePostCall('flamezo_backend.flamezo.api.staff.invite_staff_member')
  const { call: callRemove } = useFrappePostCall('flamezo_backend.flamezo.api.staff.remove_staff_member')
  const { call: callUpdate } = useFrappePostCall('flamezo_backend.flamezo.api.staff.update_staff_member')

  const staffData: StaffData | null = (staffDataRaw as any)?.message?.data ?? null
  const members = staffData?.members ?? []
  const seatLimit = staffData?.seat_limit ?? 0
  const seatsUsed = staffData?.seats_used ?? 0
  const seatsRemaining = staffData?.seats_remaining ?? 0
  const canAdd = staffData?.can_add_staff ?? false

  const handleInvite = useCallback(async () => {
    if (!inviteEmail.trim() || !inviteFullName.trim()) {
      toast.error('Please fill in all fields')
      return
    }
    setInviteLoading(true)
    try {
      const res = await callPost({
        restaurant_id: restaurantId,
        email: inviteEmail.trim(),
        full_name: inviteFullName.trim(),
        role: inviteRole,
      }) as any
      const payload = res?.message ?? res
      if (payload?.success) {
        toast.success(`${inviteFullName} invited successfully!`, {
          description: `An invite email has been sent to ${inviteEmail}.`
        })
        setShowInviteModal(false)
        setInviteEmail('')
        setInviteFullName('')
        setInviteRole('Restaurant Staff')
        mutate()
        onAdd?.()
      } else {
        toast.error(payload?.error || 'Failed to invite staff member')
      }
    } catch (e: any) {
      toast.error(e?.message || 'Something went wrong')
    } finally {
      setInviteLoading(false)
    }
  }, [inviteEmail, inviteFullName, inviteRole, restaurantId, callPost, mutate, onAdd])

  const handleRemove = useCallback(async () => {
    if (!removeTarget) return
    try {
      const res = await callRemove({
        restaurant_id: restaurantId,
        restaurant_user_name: removeTarget.name,
      }) as any
      const payload = res?.message ?? res
      if (payload?.success) {
        toast.success('Staff member removed')
        mutate()
      } else {
        toast.error(payload?.error || 'Failed to remove staff member')
      }
    } catch (e: any) {
      toast.error(e?.message || 'Something went wrong')
    } finally {
      setRemoveTarget(null)
    }
  }, [removeTarget, restaurantId, callRemove, mutate])

  const handleUpdateRole = useCallback(async (member: StaffMember, newRole: 'Restaurant Admin' | 'Restaurant Staff') => {
    try {
      const res = await callUpdate({
        restaurant_id: restaurantId,
        restaurant_user_name: member.name,
        role: newRole,
      }) as any
      const payload = res?.message ?? res
      if (payload?.success) {
        toast.success(`Role updated to ${newRole === 'Restaurant Admin' ? 'Admin' : 'Staff'}`)
        mutate()
      } else {
        toast.error(payload?.error || 'Failed to update role')
      }
    } catch (e: any) {
      toast.error(e?.message || 'Something went wrong')
    }
  }, [restaurantId, callUpdate, mutate])

  const handleToggleActive = useCallback(async (member: StaffMember) => {
    try {
      const res = await callUpdate({
        restaurant_id: restaurantId,
        restaurant_user_name: member.name,
        is_active: !member.is_active,
      }) as any
      const payload = res?.message ?? res
      if (payload?.success) {
        toast.success(member.is_active ? 'Staff member deactivated' : 'Staff member activated')
        mutate()
      } else {
        toast.error(payload?.error || 'Failed to update staff member')
      }
    } catch (e: any) {
      toast.error(e?.message || 'Something went wrong')
    }
  }, [restaurantId, callUpdate, mutate])

  const getInitials = (name: string) =>
    name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2) || '??'

  const planColor = planType === 'GOLD'
    ? 'from-fuchsia-600 to-purple-600'
    : planType === 'GOLD'
    ? 'from-amber-500 to-orange-500'
    : 'from-slate-500 to-slate-600'

  const PlanIcon = () => {
    if (planType === 'GOLD') return <Crown className="w-3.5 h-3.5" />
    if (planType === 'GOLD') return <Zap className="w-3.5 h-3.5" />
    return <Star className="w-3.5 h-3.5" />
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2].map(i => (
          <div key={i} className="h-16 rounded-xl bg-muted/40 animate-pulse" />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Seat Quota Bar */}
      {seatLimit > 0 && (
        <div className="rounded-2xl border border-border/50 bg-gradient-to-br from-card to-card/50 p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className={cn("flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full text-white bg-gradient-to-r", planColor)}>
                <PlanIcon />
                {planType} Plan
              </div>
              <span className="text-sm text-muted-foreground">Staff Seats</span>
            </div>
            <span className="text-sm font-semibold">
              <span className="text-foreground">{seatsUsed}</span>
              <span className="text-muted-foreground"> / {seatLimit} used</span>
            </span>
          </div>
          <div className="h-2 rounded-full bg-muted/50 overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500 bg-gradient-to-r",
                seatsUsed >= seatLimit ? 'from-red-500 to-red-600' : 'from-emerald-500 to-green-500'
              )}
              style={{ width: seatLimit > 0 ? `${Math.min(100, (seatsUsed / seatLimit) * 100)}%` : '0%' }}
            />
          </div>
          {seatsRemaining === 0 && planType !== 'GOLD' && (
            <div className="mt-3 flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
              <span>Seat limit reached. Upgrade to GOLD for 6 staff seats.</span>
            </div>
          )}
        </div>
      )}

      {/* Members Card */}
      <Card className="border-border/50 shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <CardTitle className="text-base">Team Members</CardTitle>
              <CardDescription>
                {members.length} member{members.length !== 1 ? 's' : ''} assigned
              </CardDescription>
            </div>
            {isAdmin && (
              <Button
                onClick={() => setShowInviteModal(true)}
                disabled={!canAdd && seatLimit > 0}
                size="sm"
                className="gap-2 rounded-xl"
                title={!canAdd && seatLimit > 0 ? 'Staff seat limit reached' : 'Invite a staff member'}
              >
                <UserPlus className="w-4 h-4" />
                Invite Staff
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          {members.length === 0 ? (
            <div className="flex flex-col items-center py-10 gap-3 text-center">
              <div className="w-14 h-14 rounded-full bg-muted/60 flex items-center justify-center">
                <User className="w-6 h-6 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground">No staff added yet.</p>
              <p className="text-xs text-muted-foreground/70 max-w-xs">
                The restaurant owner is automatically the Admin. Invite staff to let them handle orders.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-border/40">
              {members.map((member) => (
                <div key={member.name} className="flex items-center gap-3 py-3.5 first:pt-0 last:pb-0">
                  <StaffAvatar src={member.user_image} initials={getInitials(member.full_name || member.user)} />

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium truncate">{member.full_name || member.user}</span>
                      
                      {isAdmin ? (
                        <Select
                          value={member.role}
                          onValueChange={(val) => handleUpdateRole(member, val as any)}
                        >
                          <SelectTrigger className="h-6 w-auto border-none bg-transparent hover:bg-muted/50 px-2 rounded-full gap-1 shadow-none transition-colors">
                            <Badge
                              variant="outline"
                              className={cn(
                                "text-xs rounded-full gap-1 border-none pointer-events-none",
                                member.role === 'Restaurant Admin'
                                  ? 'bg-primary/10 text-primary'
                                  : 'bg-muted/60 text-muted-foreground'
                              )}
                            >
                              {member.role === 'Restaurant Admin'
                                ? <Shield className="w-3 h-3" />
                                : <User className="w-3 h-3" />}
                              {member.role === 'Restaurant Admin' ? 'Admin' : 'Staff'}
                            </Badge>
                          </SelectTrigger>
                          <SelectContent align="start" className="rounded-xl shadow-xl">
                            <SelectItem value="Restaurant Staff" className="rounded-lg">
                              <div className="flex items-center gap-2">
                                <User className="w-3.5 h-3.5" />
                                <span>Staff</span>
                              </div>
                            </SelectItem>
                            <SelectItem value="Restaurant Admin" className="rounded-lg">
                              <div className="flex items-center gap-2">
                                <Shield className="w-3.5 h-3.5" />
                                <span>Admin</span>
                              </div>
                            </SelectItem>
                          </SelectContent>
                        </Select>
                      ) : (
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-xs rounded-full gap-1 border-none",
                            member.role === 'Restaurant Admin'
                              ? 'bg-primary/10 text-primary'
                              : 'bg-muted/60 text-muted-foreground'
                          )}
                        >
                          {member.role === 'Restaurant Admin'
                            ? <Shield className="w-3 h-3" />
                            : <User className="w-3 h-3" />}
                          {member.role === 'Restaurant Admin' ? 'Admin' : 'Staff'}
                        </Badge>
                      )}

                      {!member.is_active && (
                        <Badge variant="outline" className="text-xs rounded-full bg-red-50 text-red-500 border-red-200 dark:bg-red-950/30 dark:text-red-400">
                          Inactive
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">{member.email}</p>
                  </div>

                  {/* Admin actions — not on self */}
                  {isAdmin && member.user !== (window as any).frappe?.session?.user && (
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-foreground"
                        title={member.is_active ? 'Deactivate' : 'Activate'}
                        onClick={() => handleToggleActive(member)}
                      >
                        {member.is_active
                          ? <PowerOff className="w-3.5 h-3.5" />
                          : <Power className="w-3.5 h-3.5" />}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        title="Remove"
                        onClick={() => setRemoveTarget(member)}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Upgrade CTA (SILVER plan) */}
      {seatLimit === 0 && isAdmin && (
        <div className="rounded-2xl border border-amber-200 dark:border-amber-800/40 bg-amber-50/60 dark:bg-amber-950/20 p-5 flex gap-3">
          <div className="w-9 h-9 rounded-xl bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center flex-shrink-0">
            <ChevronUp className="w-5 h-5 text-amber-600" />
          </div>
          <div>
            <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">Upgrade to Add Staff</p>
            <p className="text-xs text-amber-700 dark:text-amber-400 mt-0.5">
              GOLD plan includes 6 staff seats.
              Contact Flamezo to upgrade your plan.
            </p>
          </div>
        </div>
      )}

      {/* Invite Modal */}
      <Dialog open={showInviteModal} onOpenChange={setShowInviteModal}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Invite Staff Member</DialogTitle>
            <DialogDescription>
              They'll receive an email to join your team
              {seatLimit > 0 ? ` (${seatsRemaining} seat${seatsRemaining !== 1 ? 's' : ''} remaining)` : ''}.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="invite-name">Full Name</Label>
              <Input
                id="invite-name"
                placeholder="e.g. Ravi Kumar"
                value={inviteFullName}
                onChange={e => setInviteFullName(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="invite-email">Email Address</Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="invite-email"
                  type="email"
                  placeholder="staff@restaurant.com"
                  className="pl-9"
                  value={inviteEmail}
                  onChange={e => setInviteEmail(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleInvite()}
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="invite-role">Role</Label>
              <Select value={inviteRole} onValueChange={(v) => setInviteRole(v as 'Restaurant Staff' | 'Restaurant Admin')}>
                <SelectTrigger id="invite-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Restaurant Staff">
                    <div className="flex items-center gap-2 py-0.5">
                      <User className="w-4 h-4 flex-shrink-0" />
                      <div>
                        <p className="text-sm font-medium">Staff</p>
                        <p className="text-xs text-muted-foreground">Orders & bookings only</p>
                      </div>
                    </div>
                  </SelectItem>
                  <SelectItem value="Restaurant Admin">
                    <div className="flex items-center gap-2 py-0.5">
                      <Shield className="w-4 h-4 flex-shrink-0" />
                      <div>
                        <p className="text-sm font-medium">Admin</p>
                        <p className="text-xs text-muted-foreground">Full access</p>
                      </div>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowInviteModal(false)}>Cancel</Button>
            <Button onClick={handleInvite} disabled={inviteLoading} className="gap-2">
              {inviteLoading ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Mail className="w-4 h-4" />
              )}
              Send Invite
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Remove Confirmation */}
      <AlertDialog open={!!removeTarget} onOpenChange={() => setRemoveTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove Staff Member?</AlertDialogTitle>
            <AlertDialogDescription>
              <strong>{removeTarget?.full_name || removeTarget?.email}</strong> will lose access to this restaurant immediately.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={handleRemove}
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
