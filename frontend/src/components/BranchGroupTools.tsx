import { useEffect, useState } from 'react'
import { Users, Copy, X, Loader2, Plus, ArrowRight } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { BranchOfPicker, type BranchRef } from '@/components/BranchOfPicker'
import { GroupPicker } from '@/components/GroupPicker'
import { OptionPicker } from '@/components/OptionPicker'
import { useFrappePostCall } from '@/lib/frappe'

/**
 * Admin group tools for Merchant Management (standalone, not on a merchant page):
 *   • Create Group  — name a group + pick its branches
 *   • Copy to Branches — pick a group, copy FROM one branch TO many
 */

interface Branch { id: string; restaurant_name?: string; city?: string }

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
  const [createOpen, setCreateOpen] = useState(false)
  const [copyOpen, setCopyOpen] = useState(false)

  // ── Create Group ──────────────────────────────────────────────
  const [groupName, setGroupName] = useState('')
  const [picked, setPicked] = useState<BranchRef[]>([])
  const [creating, setCreating] = useState(false)
  const { call: createGroup } = useFrappePostCall<{ success: boolean; error?: string }>(
    'flamezo_backend.flamezo.api.branch_clone.create_group',
  )

  const submitCreate = async () => {
    if (!groupName.trim()) { toast.error('Enter a group name'); return }
    setCreating(true)
    try {
      const res: any = await createGroup({ group_name: groupName.trim(), restaurant_ids: JSON.stringify(picked.map((p) => p.id)) })
      const data = res?.message ?? res
      if (data?.success) {
        toast.success(`Group "${groupName.trim()}" created${picked.length ? ` with ${picked.length} branch(es)` : ''}`)
        setCreateOpen(false); setGroupName(''); setPicked([])
        onGroupsChanged?.()
      } else {
        toast.error(data?.error || 'Could not create group')
      }
    } catch (e: any) {
      toast.error(e?.message || 'Could not create group')
    } finally {
      setCreating(false)
    }
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

  const { call: listGroupBranches } = useFrappePostCall<{ success: boolean; branches?: Branch[] }>(
    'flamezo_backend.flamezo.api.branch_clone.list_group_branches',
  )
  const { call: cloneToBranches } = useFrappePostCall<{ success: boolean; results?: CloneResult[]; error?: string }>(
    'flamezo_backend.flamezo.api.branch_clone.clone_content_to_branches',
  )

  useEffect(() => {
    if (!group) { setBranches([]); setCopyFrom(null); setCopyTo(new Set()); return }
    setLoadingBranches(true)
    listGroupBranches({ group_id: group })
      .then((res: any) => {
        const data = res?.message ?? res
        setBranches(data?.success ? (data.branches || []) : [])
      })
      .catch(() => setBranches([]))
      .finally(() => setLoadingBranches(false))
  }, [group])

  const doCopy = async () => {
    if (!copyFrom || copyTo.size === 0) return
    setCopying(true); setResults(null)
    try {
      const res: any = await cloneToBranches({
        source_restaurant_id: copyFrom,
        target_restaurant_ids: JSON.stringify([...copyTo]),
      })
      const data = res?.message ?? res
      if (data?.success) setResults(data.results || [])
      else toast.error(data?.error || 'Copy failed')
    } catch (e: any) {
      toast.error(e?.message || 'Copy failed')
    } finally {
      setCopying(false)
    }
  }

  const resetCopy = () => { setCopyOpen(false); setGroup(null); setGroupLabel(''); setCopyFrom(null); setCopyTo(new Set()); setResults(null) }

  const branchOptions = branches.map((b) => ({ value: b.id, label: b.restaurant_name || b.id }))
  const targetOptions = branchOptions.filter((o) => o.value !== copyFrom)

  return (
    <>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => setCreateOpen(true)} className="gap-2 h-9">
          <Users className="h-4 w-4" /> New Group
        </Button>
        <Button size="sm" onClick={() => setCopyOpen(true)} className="bg-emerald-600 hover:bg-emerald-700 shadow-emerald-500/20 shadow-lg gap-2 text-white h-9">
          <Copy className="h-4 w-4" /> Copy Menu
        </Button>
      </div>

      {/* ── Create Group modal ── */}
      {createOpen && (
        <Overlay onClose={() => setCreateOpen(false)}>
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-lg font-semibold">Create Group</h2>
            <button onClick={() => setCreateOpen(false)} className="text-muted-foreground hover:text-foreground"><X className="h-5 w-5" /></button>
          </div>
          <p className="text-sm text-muted-foreground mb-4">Name the group and pick the branches that belong to the same merchant.</p>

          <label className="text-sm font-medium">Group name</label>
          <input
            className="mt-1 mb-4 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none"
            value={groupName}
            onChange={(e) => setGroupName(e.target.value)}
            placeholder="e.g. Chocolate Fiers"
          />

          <label className="text-sm font-medium">Branches</label>
          <div className="mt-1 mb-4">
            <BranchOfPicker value={picked} onChange={setPicked} placeholder="Search outlets to add…" />
          </div>

          <Button className="w-full gap-2" disabled={creating || !groupName.trim()} onClick={submitCreate}>
            {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Create group{picked.length ? ` with ${picked.length}` : ''}
          </Button>
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
                    {/* Copy FROM — searchable single-select dropdown */}
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

                    {/* Copy TO — searchable multi-select dropdown + Select all */}
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
    </>
  )
}
