import { useState, useEffect, useCallback, useRef } from 'react'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Trash2, Edit, Eye, CheckCircle2 } from 'lucide-react'
import { uploadToR2 } from '@/lib/r2Upload'

export default function HomeFeaturesManager() {
  const { selectedRestaurant, refreshConfig } = useRestaurant()
  const [features, setFeatures] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState<any | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const filteredFeatures = features.filter(f =>
    ['legacy', 'dine-play', 'offers-events', 'book-table'].includes(f.id)
  )

  const fetchFeatures = useCallback(async (): Promise<any[] | null> => {
    if (!selectedRestaurant) return null
    try {
      const response = await fetch(
        `/api/method/flamezo_backend.flamezo.api.config.get_home_features?restaurant_id=${encodeURIComponent(selectedRestaurant)}`
      )
      const json = await response.json()
      const payload = json?.message ?? json
      if (payload?.success) {
        const data = payload.data.features || []
        setFeatures(data)
        return data
      }
    } catch (error) {
      console.error(error)
    }
    return null
  }, [selectedRestaurant])

  // Always fetch fresh from API — never rely on the stale global restaurantConfig.homeFeatures
  // The global config is a snapshot taken at page-load; it becomes stale the moment the user edits.
  useEffect(() => {
    if (!selectedRestaurant) return
    setLoading(true)
    fetchFeatures().finally(() => setLoading(false))
  }, [selectedRestaurant, fetchFeatures])

  // Poll until a specific feature has the expected image URL reflected in the API.
  // This bridges the gap between the Media Asset being "uploaded" (processing) and "ready".
  const pollUntilImageReflected = useCallback(
    async (featureName: string, expectedUrl: string, maxAttempts = 10, intervalMs = 1500) => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)

      let attempt = 0
      const check = async () => {
        attempt++
        const data = await fetchFeatures()
        if (!data) return

        const found = data.find((f: any) => f.name === featureName)
        const reflected = found?.imageSrc && (
          found.imageSrc === expectedUrl ||
          // CDN URL may differ slightly from the raw object key URL — treat any non-empty image as success
          // after 3+ attempts (avoids infinite loops if URL transforms are applied)
          (attempt >= 3 && found.imageSrc !== '')
        )

        if (reflected || attempt >= maxAttempts) {
          // Final refresh to sync global context
          await refreshConfig()
          return
        }

        pollTimerRef.current = setTimeout(check, intervalMs)
      }

      // First check after a short delay to let the backend process
      pollTimerRef.current = setTimeout(check, intervalMs)
    },
    [fetchFeatures, refreshConfig]
  )

  // Cleanup poll on unmount
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    }
  }, [])

  const openEdit = (f: any) => {
    setEditing({ ...f, newImageFile: null })
  }

  const handleDelete = async (name: string) => {
    if (!confirm('Delete this feature?')) return
    try {
      const csrf = (window as any).frappe?.csrf_token || (window as any).csrf_token
      const resp = await fetch('/api/method/flamezo_backend.flamezo.api.documents.delete_doc', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'X-Frappe-CSRF-Token': csrf
        },
        body: JSON.stringify({ doctype: 'Home Feature', name })
      })
      const j = await resp.json()
      if (j?.message || j?.success) {
        setFeatures(prev => prev.filter(f => f.name !== name))
      } else {
        throw new Error(JSON.stringify(j))
      }
    } catch (e: any) {
      alert('Delete failed: ' + (e.message || e))
    }
  }

  const uploadFile = async (file: File) => {
    if (!editing?.name) throw new Error('Missing Home Feature id')

    return await uploadToR2({
      ownerDoctype: 'Home Feature',
      ownerName: editing.name,
      mediaRole: 'home_feature_image',
      file,
    })
  }

  const handleSave = async () => {
    if (!editing) return
    setSaving(true)
    try {
      const docData: any = {
        title: editing.title,
        subtitle: editing.subtitle,
      }

      let imageUrl = editing.imageSrc
      let imageChanged = false

      // ── Step 1: Upload new image if selected ──────────────────────────────
      if (editing.newImageFile) {
        try {
          // Primary path: direct R2 CDN upload
          const uploadResult: any = await uploadFile(editing.newImageFile)
          if (uploadResult?.primary_url) {
            imageUrl = uploadResult.primary_url
            docData.image_src = imageUrl
            imageChanged = true
          } else {
            throw new Error('CDN upload returned no URL')
          }
        } catch (uploadError: any) {
          console.error('CDN upload failed, trying fallback:', uploadError.message)

          // Fallback: regular Frappe /upload_file
          const formData = new FormData()
          formData.append('file', editing.newImageFile)
          formData.append('doctype', 'Home Feature')
          formData.append('docname', editing.name)
          formData.append('fieldname', 'image_src')

          const csrf = (window as any).frappe?.csrf_token || (window as any).csrf_token
          const uploadResponse = await fetch('/api/method/upload_file', {
            method: 'POST',
            body: formData,
            headers: { 'X-Frappe-CSRF-Token': csrf },
          })

          if (!uploadResponse.ok) {
            throw new Error('Fallback upload failed: ' + uploadResponse.statusText)
          }
          const uploadJson = await uploadResponse.json()
          const fileUrl = uploadJson?.message?.file_url
          if (!fileUrl) throw new Error('Fallback upload returned no file URL')

          imageUrl = fileUrl
          docData.image_src = imageUrl
          imageChanged = true
        }
      } else if (editing.imageSrc) {
        docData.image_src = editing.imageSrc
      }

      // ── Step 2: Persist doc changes ───────────────────────────────────────
      const csrf = (window as any).frappe?.csrf_token || (window as any).csrf_token
      const updateResp = await fetch('/api/method/flamezo_backend.flamezo.api.documents.update_document', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Frappe-CSRF-Token': csrf,
        },
        body: JSON.stringify({
          doctype: 'Home Feature',
          name: editing.name,
          doc_data: docData,
        }),
      })
      const json = await updateResp.json()
      if (!json.success && json.error) throw new Error(json.error.message || JSON.stringify(json))

      // ── Step 3: Optimistic UI update so user sees change immediately ──────
      const savedName = editing.name
      setFeatures(prev =>
        prev.map(p =>
          p.name === savedName
            ? { ...p, title: editing.title, subtitle: editing.subtitle, imageSrc: imageUrl }
            : p
        )
      )
      setEditing(null)
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 3000)

      // ── Step 4: Refresh from server ───────────────────────────────────────
      // Kick off an immediate fresh fetch so the list reflects the latest data.
      // If an image was changed, also start polling because the Media Asset
      // processing job runs asynchronously (status goes uploaded -> ready).
      if (imageChanged) {
        // Immediate fetch to update local list
        await fetchFeatures()
        // Then poll until the CDN URL is reflected through the Media Asset pipeline
        pollUntilImageReflected(savedName, imageUrl)
      } else {
        // No image change — a single fetch is enough
        await fetchFeatures()
        // Still refresh the global context so other pages don't show stale data
        refreshConfig()
      }
    } catch (e: any) {
      console.error('Save failed', e)
      alert('Save failed: ' + (e.message || e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-4">
      <h2 className="text-2xl font-semibold mb-4">Home Features</h2>
      {!selectedRestaurant && <div className="text-sm text-muted-foreground">Select a restaurant first</div>}

      {/* Save success toast */}
      {saveSuccess && (
        <div className="mb-4 flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg text-green-800 text-sm">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span>Feature saved successfully! Image will appear once processing completes.</span>
        </div>
      )}


      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <Button onClick={() => setViewMode('grid')} variant={viewMode==='grid' ? 'default' : 'ghost'}>Grid</Button>
          <Button onClick={() => setViewMode('list')} variant={viewMode==='list' ? 'default' : 'ghost'}>List</Button>
        </div>
        <div className="text-sm text-muted-foreground">
          {filteredFeatures.length} feature{filteredFeatures.length !== 1 ? 's' : ''} shown
        </div>
      </div>

      {loading ? <div>Loading…</div> : (
        viewMode === 'grid' ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {filteredFeatures.map(f => (
              <div key={f.id || f.name} className="p-4 bg-card rounded shadow-sm">
                {f.imageSrc ? <img src={f.imageSrc} alt={f.title} className="h-36 w-full object-cover rounded mb-2" /> : <div className="h-36 w-full bg-muted rounded mb-2 flex items-center justify-center text-xs">No image</div>}
                <div className="font-semibold">{f.title || f.id}</div>
                <div className="text-xs text-muted-foreground mb-2">{f.subtitle}</div>
                <div className="flex gap-2">
                  <Button onClick={() => openEdit(f)}><Edit className="h-4 w-4" /></Button>
                  <a className="inline-flex items-center px-3 py-1 rounded border text-sm" target="_blank" rel="noreferrer" href={`/app/home-feature/${encodeURIComponent(f.name)}`}><Eye className="h-4 w-4" /></a>
                  <Button variant="destructive" onClick={() => handleDelete(f.name)}><Trash2 className="h-4 w-4" /></Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="overflow-auto bg-card rounded p-4">
            <table className="w-full table-auto">
              <thead>
                <tr className="text-left text-sm text-muted-foreground">
                  <th className="p-2">Feature ID</th>
                  <th className="p-2">Title</th>
                  <th className="p-2">Subtitle</th>
                  <th className="p-2">Image</th>
                  <th className="p-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredFeatures.map(f => (
                  <tr key={f.id || f.name} className="border-t">
                    <td className="p-2">{f.id}</td>
                    <td className="p-2 font-semibold">{f.title}</td>
                    <td className="p-2 text-xs text-muted-foreground">{f.subtitle}</td>
                    <td className="p-2">{f.imageSrc ? <img src={f.imageSrc} alt={f.title} className="h-12 rounded object-cover" /> : '—'}</td>
                    <td className="p-2">
                      <div className="flex gap-2">
                        <Button onClick={() => openEdit(f)}><Edit className="h-4 w-4" /></Button>
                        <a className="inline-flex items-center px-3 py-1 rounded border text-sm" target="_blank" rel="noreferrer" href={`/app/home-feature/${encodeURIComponent(f.name)}`}><Eye className="h-4 w-4" /></a>
                        <Button variant="destructive" onClick={() => handleDelete(f.name)}><Trash2 className="h-4 w-4" /></Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      <Dialog open={!!editing} onOpenChange={(open) => { if (!open) setEditing(null) }}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>Edit Feature</DialogTitle>
            <DialogDescription>
              Update the feature details and image
            </DialogDescription>
          </DialogHeader>
          {editing && (
            <div className="space-y-4">
              <div>
                <Label>Title</Label>
                <Input value={editing.title} onChange={(e: any) => setEditing({ ...editing, title: e.target.value })} />
              </div>
              <div>
                <Label>Subtitle</Label>
                <Input value={editing.subtitle} onChange={(e: any) => setEditing({ ...editing, subtitle: e.target.value })} />
              </div>
              <div>
                <Label>Image</Label>
                <input type="file" accept="image/*" onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) setEditing({ ...editing, newImageFile: file })
                }} />
                {(editing.newImageFile || editing.imageSrc) && (
                  <img
                    src={editing.newImageFile ? URL.createObjectURL(editing.newImageFile) : editing.imageSrc}
                    alt="preview"
                    className="h-24 mt-2 rounded object-cover"
                  />
                )}
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
                <Button onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

