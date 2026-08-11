import { useOutlet } from '@/contexts/OutletContext'
import StaffMembersList from '@/components/StaffMembersList'
import { Badge } from '@/components/ui/badge'
import { Crown, Users, Lock } from 'lucide-react'

export default function TeamManagement() {
  const { selectedOutlet, isAdmin } = useOutlet()

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 text-center max-w-sm mx-auto">
        <div className="w-16 h-16 rounded-2xl bg-muted/60 flex items-center justify-center">
          <Lock className="w-7 h-7 text-muted-foreground" />
        </div>
        <div className="space-y-1">
          <h2 className="text-lg font-bold">Admin Access Required</h2>
          <p className="text-sm text-muted-foreground">
            Only Outlet Admins can manage team members.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto space-y-8 pb-20">
      <div className="space-y-3">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-amber-500 to-yellow-600">
            <Users className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Team Management</h1>
            <p className="text-sm text-muted-foreground">
              Invite staff to manage bookings, and more.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Badge
            className="text-white border-none gap-1"
            style={{ background: 'linear-gradient(135deg, #F59E0B, #B45309)', boxShadow: '0 1px 4px rgba(180,83,9,0.3)' }}
          >
            <Crown className="w-3 h-3" /> 6 Staff Seats
          </Badge>
          <span className="text-xs text-muted-foreground">
            Staff can view and manage bookings. Admins have full dashboard access.
          </span>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-border/50 bg-card p-4 space-y-2">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
              <svg className="w-4 h-4 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
            </div>
            <span className="text-sm font-semibold">Outlet Admin</span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Full access: bookings, catalogue, billing, settings, staff management.
            <br /><span className="font-medium text-foreground/70">That's you.</span>
          </p>
        </div>
        <div className="rounded-2xl border border-border/50 bg-card p-4 space-y-2">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-muted/60 flex items-center justify-center">
              <svg className="w-4 h-4 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
              </svg>
            </div>
            <span className="text-sm font-semibold">Outlet Staff</span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Limited access: reservations.
            <br /><span className="font-medium text-foreground/70">Billing and settings are hidden.</span>
          </p>
        </div>
      </div>

      {selectedOutlet ? (
        <StaffMembersList outletId={selectedOutlet} />
      ) : (
        <div className="text-center text-muted-foreground py-10">
          Select an outlet to manage its team.
        </div>
      )}
    </div>
  )
}
