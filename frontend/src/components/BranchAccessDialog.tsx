import { useMemo, useState } from 'react'
import { useFrappeGetCall, useFrappePostCall } from '@/lib/frappe'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import { Search, Loader2, Store, CheckCircle2, Copy } from 'lucide-react'

/**
 * BranchAccessDialog — reusable "assign one user to many branches" modal.
 *
 * One owner logs in with ONE email and gets a branch-switcher across all the
 * branches ticked here. A single-branch manager is the same flow with one
 * branch ticked.
 *
 * After assigning, the dialog shows a result panel: the login email, the
 * generated password (for a NEW account), and exactly which/how many branches
 * the person can now access — so the admin can hand the credentials over
 * directly (the emailed copy may not arrive in every environment).
 *
 * Modular by design (per the Flamezo modular-components rule): it fetches its
 * own outlet list and owns all its state.
 */

interface OutletRow {
  name: string
  outlet_id?: string
  outlet_name?: string
  owner_email?: string
  city?: string
}

interface BranchAccessDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called after a successful assignment so the caller can refresh its data. */
  onAssigned?: () => void
}

type AssignResult = {
  branch: string
  status: 'assigned' | 'skipped' | 'not_found' | 'failed'
  error?: string
}

type AccessUser = {
  user: string
  count: number
  branches: { name: string; outlet_name: string; role: string }[]
}

type AssignSummary = {
  email: string
  password: string | null
  isNew: boolean
  assigned: number
  skipped: number
  failed: number
  /** Branch names the person can now access (assigned + already-had). */
  accessBranches: string[]
}

export function BranchAccessDialog({ open, onOpenChange, onAssigned }: BranchAccessDialogProps) {
  const [ownerEmail, setOwnerEmail] = useState('')
  const [ownerName, setOwnerName] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState('')
  const [submitting, setSubmitting] = useState(false)
  // When set, the dialog shows the result panel instead of the form.
  const [summary, setSummary] = useState<AssignSummary | null>(null)

  // Self-contained: pull the full outlet list once the dialog opens.
  const { data: outletsData, isLoading } = useFrappeGetCall<{
    message: { success: boolean; data?: { restaurants: OutletRow[] } }
  }>(
    'flamezo_backend.flamezo.api.admin.get_all_outlets',
    { page: 1, page_size: 500 },
    open ? 'branch-access-outlets' : null,
  )

  const { call: assignOwner } = useFrappePostCall(
    'flamezo_backend.flamezo.api.admin.admin_assign_owner_to_branches',
  )

  // Persistent overview: who has access to how many branches (refreshed each open).
  const { data: accessData, mutate: reloadAccess } = useFrappeGetCall<{
    message: { success: boolean; data?: { users: AccessUser[] } }
  }>(
    'flamezo_backend.flamezo.api.admin.admin_list_branch_access',
    {},
    open ? 'branch-access-list' : null,
  )
  const accessUsers = useMemo<AccessUser[]>(
    () => accessData?.message?.data?.users || [],
    [accessData],
  )

  const outlets = useMemo<OutletRow[]>(
    () => outletsData?.message?.data?.restaurants || [],
    [outletsData],
  )

  // Map docname -> display name so the result panel can show friendly labels.
  const nameOf = useMemo(() => {
    const m: Record<string, string> = {}
    for (const r of outlets) m[r.name] = r.outlet_name || r.name
    return m
  }, [outlets])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return outlets
    return outlets.filter(
      (r) =>
        (r.outlet_name || '').toLowerCase().includes(q) ||
        (r.outlet_id || '').toLowerCase().includes(q) ||
        (r.city || '').toLowerCase().includes(q),
    )
  }, [outlets, query])

  const toggle = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const reset = () => {
    setOwnerEmail('')
    setOwnerName('')
    setSelected(new Set())
    setQuery('')
    setSummary(null)
  }

  const closeAll = () => {
    reset()
    onOpenChange(false)
  }

  const copy = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast.success(`${label} copied`)
    } catch {
      toast.error('Could not copy')
    }
  }

  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(ownerEmail.trim())
  const canSubmit = emailValid && selected.size > 0 && !submitting

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    try {
      const res: any = await assignOwner({
        owner_email: ownerEmail.trim().toLowerCase(),
        owner_name: ownerName.trim(),
        branch_ids: JSON.stringify(Array.from(selected)),
        role: 'Restaurant Staff',
      })
      const data = res?.message ?? res
      if (data?.success) {
        const results: AssignResult[] = data?.data?.results || []
        const accessBranches = results
          .filter((r) => r.status === 'assigned' || r.status === 'skipped')
          .map((r) => nameOf[r.branch] || r.branch)
        onAssigned?.()
        reloadAccess()
        setSummary({
          email: ownerEmail.trim().toLowerCase(),
          password: data?.data?.generated_password || null,
          isNew: !!data?.data?.is_new_user,
          assigned: results.filter((r) => r.status === 'assigned').length,
          skipped: results.filter((r) => r.status === 'skipped').length,
          failed: results.filter((r) => r.status === 'failed' || r.status === 'not_found').length,
          accessBranches,
        })
        // Keep the dialog open on the result panel.
      } else {
        toast.error(data?.error || 'Could not assign branch access.')
      }
    } catch (e: any) {
      toast.error(e?.message || 'Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : closeAll())}>
      <DialogContent className="max-w-lg">
        {summary ? (
          // ── Result / credentials panel ─────────────────────────────────────
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-green-500" />
                Access granted
              </DialogTitle>
              <DialogDescription>
                {summary.email} can now access {summary.accessBranches.length} branch
                {summary.accessBranches.length === 1 ? '' : 'es'}.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-3">
              {/* Email */}
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Login email</Label>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded-lg border border-border/60 bg-muted/40 px-3 py-2 text-sm font-mono break-all">
                    {summary.email}
                  </code>
                  <Button variant="outline" size="icon" onClick={() => copy(summary.email, 'Email')}>
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              {/* Password (only for a newly-created account) */}
              {summary.isNew && summary.password ? (
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground">Temporary password</Label>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 rounded-lg border border-border/60 bg-muted/40 px-3 py-2 text-sm font-mono break-all">
                      {summary.password}
                    </code>
                    <Button variant="outline" size="icon" onClick={() => copy(summary.password!, 'Password')}>
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                  <p className="text-xs text-amber-600 dark:text-amber-500">
                    Save this now — it won't be shown again. Share it with the owner; they can change it after logging in.
                  </p>
                </div>
              ) : (
                <div className="rounded-lg border border-border/60 bg-muted/30 px-3 py-2.5 text-sm text-muted-foreground">
                  This email already had an account — they log in with their <strong>existing password</strong> (no new password generated).
                </div>
              )}

              {/* Branches the person can now access */}
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">
                  Branches accessible ({summary.accessBranches.length})
                </Label>
                <div className="flex flex-wrap gap-1.5">
                  {summary.accessBranches.map((b) => (
                    <Badge key={b} variant="secondary" className="text-xs">
                      {b}
                    </Badge>
                  ))}
                </div>
                {summary.accessBranches.length > 1 && (
                  <p className="text-xs text-muted-foreground">
                    They log in once and switch between these branches.
                  </p>
                )}
                {summary.failed > 0 && (
                  <p className="text-xs text-red-500">{summary.failed} branch(es) could not be assigned.</p>
                )}
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setSummary(null)}>
                Assign another
              </Button>
              <Button onClick={closeAll}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          // ── Assignment form ────────────────────────────────────────────────
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Store className="h-5 w-5 text-primary" />
                Assign Branch Access
              </DialogTitle>
              <DialogDescription>
                Give one person access to one or more branches. The same email is used across all
                ticked branches — they log in once and switch between them.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="ba-email">Email *</Label>
                  <Input
                    id="ba-email"
                    type="email"
                    placeholder="owner@example.com"
                    value={ownerEmail}
                    onChange={(e) => setOwnerEmail(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="ba-name">Name</Label>
                  <Input
                    id="ba-name"
                    placeholder="Owner / Manager name"
                    value={ownerName}
                    onChange={(e) => setOwnerName(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label>Branches</Label>
                  {selected.size > 0 && (
                    <Badge variant="secondary" className="text-xs">
                      {selected.size} selected
                    </Badge>
                  )}
                </div>
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    className="h-9 pl-8"
                    placeholder="Search branches…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>
                <div className="max-h-56 overflow-y-auto rounded-xl border border-border/60 divide-y divide-border/40">
                  {isLoading ? (
                    <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" /> Loading branches…
                    </div>
                  ) : filtered.length === 0 ? (
                    <div className="py-8 text-center text-sm text-muted-foreground">No branches found.</div>
                  ) : (
                    filtered.map((r) => (
                      <label
                        key={r.name}
                        className="flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-muted/50"
                      >
                        <Checkbox
                          checked={selected.has(r.name)}
                          onCheckedChange={() => toggle(r.name)}
                        />
                        <div className="min-w-0">
                          <div className="text-sm font-medium truncate">
                            {r.outlet_name || r.name}
                          </div>
                          <div className="text-xs text-muted-foreground truncate">
                            {[r.outlet_id, r.city].filter(Boolean).join(' · ')}
                          </div>
                        </div>
                      </label>
                    ))
                  )}
                </div>
              </div>

              {/* Who has access — persistent overview (email → branch count) */}
              {accessUsers.length > 0 && (
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">
                    Who has access ({accessUsers.length})
                  </Label>
                  <div className="max-h-40 overflow-y-auto rounded-xl border border-border/60 divide-y divide-border/40">
                    {accessUsers.map((u) => (
                      <div key={u.user} className="flex items-center justify-between gap-2 px-3 py-2">
                        <div className="min-w-0">
                          <div className="text-sm font-medium truncate">{u.user}</div>
                          <div className="text-xs text-muted-foreground truncate">
                            {u.branches.map((b) => b.outlet_name).join(', ')}
                          </div>
                        </div>
                        <Badge
                          variant={u.count > 1 ? 'default' : 'secondary'}
                          className="shrink-0 text-xs"
                        >
                          {u.count} branch{u.count === 1 ? '' : 'es'}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={closeAll} disabled={submitting}>
                Cancel
              </Button>
              <Button onClick={handleSubmit} disabled={!canSubmit}>
                {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Assign {selected.size > 0 ? `(${selected.size})` : ''}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default BranchAccessDialog
