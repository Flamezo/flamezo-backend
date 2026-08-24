import { useEffect, useState, useCallback } from 'react'
import { Users, Copy, X, Loader2, Plus, ArrowRight, Pencil, Trash2, Check, UserPlus, Search } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { BranchOfPicker, type BranchRef } from '@/components/BranchOfPicker'
import { GroupPicker } from '@/components/GroupPicker'
import { OptionPicker } from '@/components/OptionPicker'
import { useFrappePostCall } from '@/lib/frappe'

/**
 * Admin group tools for Merchant Management (standalone, not on a merchant page):
 *   • Manage Groups — full CRUD: create, rename, delete groups + assign branches
 *   • Copy to Branches — pick a group, copy FROM one branch TO many
 */

interface Branch { id: string; restaurant_name?: string; city?: string }
interface GroupRow { id: string; group_name: string; branch_count?: number }

interface CloneResult {
  branch: string
  status: string
  products_copied?: number
  categories?: number
  addon_groups?: number
  offers_copied?: number
  coupons_copied?: number
  gallery_copied?: number
  branding_copied?: boolean
  message?: string
}

function Overlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-xl bg-background p-5 shadow-xl border border-border max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )
}

export function BranchGroupTools({ onGroupsChanged }: { onGroupsChanged?: () => void }) {
  const [manageOpen, setManageOpen] = useState(false)
  const [copyOpen, setCopyOpen] = useState(false)

  // ── Manage Groups (CRUD) ──────────────────────────────────────
  const [groups, setGroups] = useState<GroupRow[]>([])
  const [loadingGroups, setLoadingGroups] = useState(false)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameVal, setRenameVal] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [groupQuery, setGroupQuery] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<GroupRow | null>(null)
  // Add existing merchants to an existing group
  const [addingToId, setAddingToId] = useState<string | null>(null)
  const [addPicked, setAddPicked] = useState<BranchRef[]>([])
  const [addBusy, setAddBusy] = useState(false)

  // Create new group
  const [groupName, setGroupName] = useState('')
  const [picked, setPicked] = useState<BranchRef[]>([])
  const [creating, setCreating] = useState(false)

  const { call: listGroups } = useFrappePostCall<{ success: boolean; groups?: GroupRow[] }>('flamezo_backend.flamezo.api.branch_clone.list_groups')
  const { call: createGroup } = useFrappePostCall<{ success: boolean; error?: string }>('flamezo_backend.flamezo.api.branch_clone.create_group')
  const { call: renameGroup } = useFrappePostCall<{ success: boolean; error?: string }>('flamezo_backend.flamezo.api.branch_clone.rename_group')
  const { call: deleteGroup } = useFrappePostCall<{ success: boolean; error?: string; detached?: number }>('flamezo_backend.flamezo.api.branch_clone.delete_group')
  const { call: addToGroup } = useFrappePostCall<{ success: boolean; error?: string; assigned?: number }>('flamezo_backend.flamezo.api.branch_clone.add_to_group')

  const fetchGroups = useCallback(async () => {
    setLoadingGroups(true)
    try {
      const res: any = await listGroups({})
      const data = res?.message ?? res
      setGroups(data?.success ? (data.groups || []) : [])
    } catch { setGroups([]) } finally { setLoadingGroups(false) }
  }, [listGroups])

  useEffect(() => { if (manageOpen) fetchGroups() }, [manageOpen, fetchGroups])

  const afterChange = () => { fetchGroups(); onGroupsChanged?.() }

  const filteredGroups = groups.filter((g) => g.group_name.toLowerCase().includes(groupQuery.trim().toLowerCase()))

  const submitCreate = async () => {
    if (!groupName.trim()) { toast.error('Enter a group name'); return }
    setCreating(true)
    try {
      const res: any = await createGroup({ group_name: groupName.trim(), outlet_ids: JSON.stringify(picked.map((p) => p.id)) })
      const data = res?.message ?? res
      if (data?.success) {
        toast.success(`Group "${groupName.trim()}" created${picked.length ? ` with ${picked.length} branch(es)` : ''}`)
        setGroupName(''); setPicked([]); setGroupQuery('')
        onGroupsChanged?.()
        setManageOpen(false)   // close after creating; reopen to create another
      } else {
        toast.error(data?.error || 'Could not create group')
      }
    } catch (e: any) {
      toast.error(e?.message || 'Could not create group')
    } finally {
      setCreating(false)
    }
  }

  const submitRename = async (id: string) => {
    if (!renameVal.trim()) { toast.error('Enter a group name'); return }
    setBusyId(id)
    try {
      const res: any = await renameGroup({ group_id: id, group_name: renameVal.trim() })
      const data = res?.message ?? res
      if (data?.success) { toast.success('Group renamed'); setRenamingId(null); setRenameVal(''); afterChange() }
      else toast.error(data?.error || 'Could not rename')
    } catch (e: any) { toast.error(e?.message || 'Could not rename') } finally { setBusyId(null) }
  }

  const doDelete = async () => {
    const g = deleteTarget
    if (!g) return
    setBusyId(g.id)
    try {
      const res: any = await deleteGroup({ group_id: g.id })
      const data = res?.message ?? res
      if (data?.success) { toast.success(`Group deleted${data.detached ? ` — ${data.detached} branch(es) detached` : ''}`); setDeleteTarget(null); afterChange() }
      else toast.error(data?.error || 'Could not delete')
    } catch (e: any) { toast.error(e?.message || 'Could not delete') } finally { setBusyId(null) }
  }

  const submitAddMerchants = async (id: string) => {
    if (!addPicked.length) { toast.error('Pick at least one merchant'); return }
    setAddBusy(true)
    try {
      const res: any = await addToGroup({ group_id: id, outlet_ids: JSON.stringify(addPicked.map((p) => p.id)) })
      const data = res?.message ?? res
      if (data?.success) {
        toast.success(`${data.assigned ?? addPicked.length} merchant(s) added`)
        setAddingToId(null); setAddPicked([])
        onGroupsChanged?.()
        setManageOpen(false)   // close after adding; reopen when needed
      } else toast.error(data?.error || 'Could not add merchants')
    } catch (e: any) { toast.error(e?.message || 'Could not add merchants') } finally { setAddBusy(false) }
  }

  // ── Copy to Branches ──────────────────────────────────────────
  const [group, setGroup] = useState<string | null>(null)
  const [groupLabel, setGroupLabel] = useState('')
  const [branches, setBranches] = useState<Branch[]>([])
  const [loadingBranches, setLoadingBranches] = useState(false)
  const [copyFrom, setCopyFrom] = useState<string | null>(null)
  const [copyTo, setCopyTo] = useState<Set<string>>(new Set())
  const [copying, setCopying] = useState(false)
  const [results, setResults] = useState<CloneResult[] | null>(null)

  const { call: listGroupBranches } = useFrappePostCall<{ success: boolean; branches?: Branch[] }>('flamezo_backend.flamezo.api.branch_clone.list_group_branches')
  const { call: cloneToBranches } = useFrappePostCall<{ success: boolean; results?: CloneResult[]; error?: string }>('flamezo_backend.flamezo.api.branch_clone.clone_content_to_branches')

  useEffect(() => {
    if (!group) { setBranches([]); setCopyFrom(null); setCopyTo(new Set()); return }
    setLoadingBranches(true)
    listGroupBranches({ group_id: group })
      .then((res: any) => { const data = res?.message ?? res; setBranches(data?.success ? (data.branches || []) : []) })
      .catch(() => setBranches([]))
      .finally(() => setLoadingBranches(false))
  }, [group])

  const doCopy = async () => {
    if (!copyFrom || copyTo.size === 0) return
    setCopying(true); setResults(null)
    try {
      const res: any = await cloneToBranches({ source_outlet_id: copyFrom, target_outlet_ids: JSON.stringify([...copyTo]) })
      const data = res?.message ?? res
      if (data?.success) setResults(data.results || [])
      else toast.error(data?.error || 'Copy failed')
    } catch (e: any) { toast.error(e?.message || 'Copy failed') } finally { setCopying(false) }
  }

  const resetCopy = () => { setCopyOpen(false); setGroup(null); setGroupLabel(''); setCopyFrom(null); setCopyTo(new Set()); setResults(null) }

  const branchOptions = branches.map((b) => ({ value: b.id, label: b.restaurant_name || b.id }))
  const targetOptions = branchOptions.filter((o) => o.value !== copyFrom)

  return (
    <>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setManageOpen(true)}
          className="gap-2 h-9 rounded-lg font-medium border-border/70 bg-muted/30 text-foreground/80 hover:bg-muted/60 hover:text-foreground transition-colors"
        >
          <Users className="h-4 w-4 opacity-70" /> Manage Groups
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setCopyOpen(true)}
          className="gap-2 h-9 rounded-lg font-medium border-primary/20 bg-primary/[0.07] text-primary hover:bg-primary/[0.12] hover:text-primary transition-colors"
        >
          <Copy className="h-4 w-4" /> Copy Menu
        </Button>
      </div>

      {/* ── Manage Groups modal (CRUD) ── */}
      {manageOpen && (
        <Overlay onClose={() => setManageOpen(false)}>
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-lg font-semibold">Manage Groups</h2>
            <button onClick={() => setManageOpen(false)} className="text-muted-foreground hover:text-foreground"><X className="h-5 w-5" /></button>
          </div>
          <p className="text-sm text-muted-foreground mb-4">Create, rename or delete merchant groups. Deleting a group detaches its branches — it never deletes a merchant.</p>

          {/* Existing groups — searchable (scales to many groups) */}
          <div className="relative mb-2">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              className="w-full rounded-lg border border-border bg-background pl-8 pr-3 py-2 text-sm outline-none"
              value={groupQuery}
              onChange={(e) => setGroupQuery(e.target.value)}
              placeholder="Search groups…"
            />
          </div>
          <div className="space-y-1.5 mb-5 max-h-72 overflow-y-auto pr-1">
            {loadingGroups ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground py-4 justify-center"><Loader2 className="h-4 w-4 animate-spin" /> Loading groups…</div>
            ) : filteredGroups.length === 0 ? (
              <p className="text-sm text-muted-foreground py-2">{groupQuery.trim() ? 'No matching groups.' : 'No groups yet. Create one below.'}</p>
            ) : filteredGroups.map((g) => (
              <div key={g.id} className="rounded-lg border border-border/70 transition-colors hover:border-primary/40 hover:bg-muted/30">
                <div className="flex items-center gap-2 px-3 py-2">
                  {renamingId === g.id ? (
                    <>
                      <input
                        autoFocus
                        className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-sm outline-none"
                        value={renameVal}
                        onChange={(e) => setRenameVal(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') submitRename(g.id); if (e.key === 'Escape') setRenamingId(null) }}
                      />
                      <button className="text-green-600 hover:text-green-700 disabled:opacity-50" disabled={busyId === g.id} onClick={() => submitRename(g.id)}>
                        {busyId === g.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                      </button>
                      <button className="text-muted-foreground hover:text-foreground" onClick={() => { setRenamingId(null); setRenameVal('') }}><X className="h-4 w-4" /></button>
                    </>
                  ) : (
                    <>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{g.group_name}</p>
                        <p className="text-[11px] text-muted-foreground">{g.branch_count || 0} branch{g.branch_count === 1 ? '' : 'es'}</p>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button className="p-1.5 rounded-md text-muted-foreground hover:bg-primary/10 hover:text-primary transition-colors" title="Add merchants to this group"
                          onClick={() => { setAddingToId(addingToId === g.id ? null : g.id); setAddPicked([]) }}><UserPlus className="h-4 w-4" /></button>
                        <button className="p-1.5 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors" title="Rename" onClick={() => { setRenamingId(g.id); setRenameVal(g.group_name) }}><Pencil className="h-4 w-4" /></button>
                        <button className="p-1.5 rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors disabled:opacity-50" title="Delete group" disabled={busyId === g.id} onClick={() => setDeleteTarget(g)}>
                          {busyId === g.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                        </button>
                      </div>
                    </>
                  )}
                </div>

                {/* Add existing merchants to this group */}
                {addingToId === g.id && (
                  <div className="border-t px-3 py-3 space-y-2 bg-muted/20">
                    <p className="text-xs text-muted-foreground">Add existing merchants to <span className="font-medium text-foreground">{g.group_name}</span>.</p>
                    <BranchOfPicker value={addPicked} onChange={setAddPicked} placeholder="Search merchants to add…" />
                    <div className="flex gap-2">
                      <Button size="sm" className="gap-1.5" disabled={addBusy || !addPicked.length} onClick={() => submitAddMerchants(g.id)}>
                        {addBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
                        Add{addPicked.length ? ` ${addPicked.length}` : ''}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => { setAddingToId(null); setAddPicked([]) }}>Cancel</Button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Create new group */}
          <div className="border-t pt-4">
            <p className="text-sm font-semibold mb-2">Create a new group</p>
            <label className="text-sm font-medium">Group name</label>
            <input
              className="mt-1 mb-3 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none"
              value={groupName}
              onChange={(e) => setGroupName(e.target.value)}
              placeholder="e.g. Chocolate Fiers"
            />
            <label className="text-sm font-medium">Branches (optional)</label>
            <div className="mt-1 mb-3">
              <BranchOfPicker value={picked} onChange={setPicked} placeholder="Search outlets to add…" />
            </div>
            <Button className="w-full gap-2" disabled={creating || !groupName.trim()} onClick={submitCreate}>
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Create group{picked.length ? ` with ${picked.length}` : ''}
            </Button>
          </div>
        </Overlay>
      )}

      {/* ── Copy to Branches modal ── */}
      {copyOpen && (
        <Overlay onClose={resetCopy}>
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-lg font-semibold">Copy to Branches</h2>
            <button onClick={resetCopy} className="text-muted-foreground hover:text-foreground"><X className="h-5 w-5" /></button>
          </div>

          {results ? (
            <div className="space-y-2 mt-3">
              {results.map((r) => (
                <div key={r.branch} className="rounded-lg border border-border p-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{r.branch}</span>
                    <span className={r.status === 'ok' ? 'text-green-600' : r.status === 'error' ? 'text-red-600' : 'text-amber-600'}>
                      {r.status === 'ok' ? 'Done' : r.status.replace(/_/g, ' ')}
                    </span>
                  </div>
                  {r.status === 'ok' && (
                    <div className="text-muted-foreground mt-1">
                      {r.products_copied} products, {r.categories} categories, {r.addon_groups} add-on groups
                      {(r.offers_copied || r.coupons_copied) ? ` · ${(r.offers_copied || 0) + (r.coupons_copied || 0)} offers` : ''}
                      {r.gallery_copied ? ` · ${r.gallery_copied} gallery` : ''}
                      {r.branding_copied ? ' · branding' : ''}
                    </div>
                  )}
                  {r.message && <div className="text-red-600 mt-1">{r.message}</div>}
                </div>
              ))}
              <Button className="w-full mt-2" onClick={resetCopy}>Close</Button>
            </div>
          ) : (
            <>
              <p className="text-sm text-muted-foreground my-3">Pick a group, then copy the full menu/branding from one branch to the others.</p>

              <label className="text-sm font-medium">Group</label>
              <div className="mt-1 mb-4">
                <GroupPicker value={group} valueLabel={groupLabel} onChange={(id, label) => { setGroup(id); setGroupLabel(label || ''); }} />
              </div>

              {group && (
                loadingBranches ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground py-4 justify-center"><Loader2 className="h-4 w-4 animate-spin" /> Loading branches…</div>
                ) : branches.length < 2 ? (
                  <div className="text-sm text-muted-foreground py-3">This group needs at least 2 branches to copy between.</div>
                ) : (
                  <div className="space-y-4">
                    <div>
                      <label className="text-sm font-medium">Copy from <span className="text-muted-foreground">(one source)</span></label>
                      <div className="mt-1">
                        <OptionPicker
                          options={branchOptions}
                          value={copyFrom ? [copyFrom] : []}
                          onChange={(vals) => {
                            const src = vals[0] || null
                            setCopyFrom(src)
                            if (src) setCopyTo((prev) => { const n = new Set(prev); n.delete(src); return n })
                          }}
                          placeholder="Select source branch…"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="text-sm font-medium">Copy to <span className="text-muted-foreground">(one or more targets)</span></label>
                      <div className="mt-1">
                        <OptionPicker
                          options={targetOptions}
                          value={[...copyTo]}
                          onChange={(vals) => setCopyTo(new Set(vals))}
                          multiple
                          selectAll
                          placeholder="Select target branches…"
                        />
                      </div>
                    </div>

                    <Button className="w-full gap-2" disabled={!copyFrom || copyTo.size === 0 || copying} onClick={doCopy}>
                      {copying ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                      {copying ? 'Copying…' : `Copy to ${copyTo.size || ''} branch${copyTo.size === 1 ? '' : 'es'}`}
                    </Button>
                  </div>
                )
              )}
            </>
          )}
        </Overlay>
      )}

      {/* ── Delete group confirmation ── */}
      {deleteTarget && (
        <Overlay onClose={() => busyId ? null : setDeleteTarget(null)}>
          <div className="flex items-start gap-3">
            <div className="rounded-full bg-destructive/10 p-2.5 shrink-0"><Trash2 className="h-5 w-5 text-destructive" /></div>
            <div className="min-w-0">
              <h2 className="text-lg font-semibold">Delete “{deleteTarget.group_name}”?</h2>
              <p className="text-sm text-muted-foreground mt-1">
                This deletes <span className="font-medium text-foreground">only the group</span>. Its{' '}
                <span className="font-medium text-foreground">{deleteTarget.branch_count || 0} merchant{deleteTarget.branch_count === 1 ? '' : 's'}</span>{' '}
                will be detached and become standalone — <span className="font-medium text-foreground">no merchant is deleted</span>. This can't be undone.
              </p>
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-5">
            <Button variant="outline" size="sm" disabled={!!busyId} onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" size="sm" className="gap-1.5" disabled={!!busyId} onClick={doDelete}>
              {busyId ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />} Delete group
            </Button>
          </div>
        </Overlay>
      )}
    </>
  )
}
