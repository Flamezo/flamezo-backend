import { useCallback, useEffect, useState } from 'react'
import { useFrappePostCall } from '@/lib/frappe'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { toast } from 'sonner'
import { getFrappeError } from '@/lib/utils'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Loader2, Upload, Trash2, CheckCircle2, Image as ImageIcon, Power, Eye, Info } from 'lucide-react'

interface ThemeStatusResponse {
  success: boolean
  enabled?: boolean
  wallpapers: string[]
  main_index: number
  active_image?: string | null
}

export default function AIMenuThemeBackgroundPage() {
  const { selectedRestaurant } = useRestaurant()
  const [status, setStatus] = useState<ThemeStatusResponse | null>(null)
  const [isTogglingEnabled, setIsTogglingEnabled] = useState(false)
  const [uploadingIndex, setUploadingIndex] = useState<number | null>(null)
  const [deletingIndex, setDeletingIndex] = useState<number | null>(null)
  const [settingMainIndex, setSettingMainIndex] = useState<number | null>(null)
  
  const [showPreviewModal, setShowPreviewModal] = useState(false)
  const [previewImage, setPreviewImage] = useState<string | null>(null)

  const { call: getThemeStatus } = useFrappePostCall<ThemeStatusResponse>('flamezo_backend.flamezo.api.ai_media.get_menu_theme_background_status')
  const { call: setThemeBackgroundEnabled } = useFrappePostCall('flamezo_backend.flamezo.api.ai_media.set_menu_theme_background_enabled')
  const { call: uploadWallpaper } = useFrappePostCall('flamezo_backend.flamezo.api.ai_media.upload_menu_theme_wallpaper')
  const { call: deleteWallpaper } = useFrappePostCall('flamezo_backend.flamezo.api.ai_media.delete_menu_theme_wallpaper')
  const { call: setMainWallpaper } = useFrappePostCall('flamezo_backend.flamezo.api.ai_media.set_main_menu_theme_wallpaper')

  const fetchStatus = useCallback(async () => {
    if (!selectedRestaurant) return
    try {
      const res: any = await getThemeStatus({ restaurant: selectedRestaurant })
      const payload = res?.message || res
      if (payload?.success) {
        setStatus(payload)
      }
    } catch (error: any) {
      toast.error('Failed to load background status', { description: getFrappeError(error) })
    }
  }, [getThemeStatus, selectedRestaurant])

  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  const handleToggleBackground = async () => {
    if (!selectedRestaurant || isTogglingEnabled) return
    const isEnabled = status?.enabled ?? true
    const nextEnabled = !isEnabled
    setIsTogglingEnabled(true)
    try {
      await setThemeBackgroundEnabled({ restaurant: selectedRestaurant, enabled: nextEnabled ? 1 : 0 })
      toast.success(nextEnabled ? 'Menu background enabled' : 'Menu background disabled')
      await fetchStatus()
    } catch (error: any) {
      toast.error('Failed to update setting', { description: getFrappeError(error) })
    } finally {
      setIsTogglingEnabled(false)
    }
  }

  const handleFileUpload = async (index: number, e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !selectedRestaurant) return

    if (file.size > 5 * 1024 * 1024) {
      toast.error('Image too large (max 5MB)')
      return
    }

    setUploadingIndex(index)
    const reader = new FileReader()
    reader.onloadend = async () => {
      try {
        const base64 = reader.result as string
        await uploadWallpaper({
          restaurant: selectedRestaurant,
          filedata: base64,
          filename: file.name,
          index: index
        })
        toast.success(`Wallpaper ${index + 1} uploaded`)
        await fetchStatus()
      } catch (error: any) {
        toast.error('Upload failed', { description: getFrappeError(error) })
      } finally {
        setUploadingIndex(null)
      }
    }
    reader.readAsDataURL(file)
  }

  const handleDelete = async (index: number) => {
    if (!selectedRestaurant) return
    setDeletingIndex(index)
    try {
      await deleteWallpaper({ restaurant: selectedRestaurant, index })
      toast.success(`Wallpaper ${index + 1} removed`)
      await fetchStatus()
    } catch (error: any) {
      toast.error('Delete failed', { description: getFrappeError(error) })
    } finally {
      setDeletingIndex(null)
    }
  }

  const handleSetMain = async (index: number) => {
    if (!selectedRestaurant || status?.wallpapers[index] === '') return
    setSettingMainIndex(index)
    try {
      await setMainWallpaper({ restaurant: selectedRestaurant, index })
      toast.success(`Wallpaper ${index + 1} set as main`)
      await fetchStatus()
    } catch (error: any) {
      toast.error('Failed to set main', { description: getFrappeError(error) })
    } finally {
      setSettingMainIndex(null)
    }
  }

  if (!selectedRestaurant) {
    return <div className="p-8 text-center text-muted-foreground">Please select a restaurant</div>
  }

  const isEnabled = status?.enabled ?? true

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Menu Theme Wallpapers</h1>
          <p className="text-muted-foreground mt-2">
            Upload up to 3 wallpapers for your menu splash page. The "Main" wallpaper will also serve as the blurred background for your entire application.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            role="switch"
            aria-checked={isEnabled}
            onClick={handleToggleBackground}
            disabled={isTogglingEnabled}
            className={`group inline-flex items-center gap-3 rounded-2xl border px-3 py-2 shadow-sm transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:pointer-events-none disabled:opacity-60 ${
              isEnabled
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300'
                : 'border-border bg-background text-muted-foreground hover:bg-accent/50'
            }`}
          >
            <div className="flex items-center gap-2">
              <span
                className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors duration-200 ${
                  isEnabled ? 'bg-emerald-500' : 'bg-muted-foreground/25'
                }`}
              >
                <span
                  className={`inline-block h-5 w-5 rounded-full bg-white shadow-md transition-transform duration-200 ${
                    isEnabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </span>
              <div className="text-left leading-tight">
                <p className="text-sm font-semibold text-foreground">Background Layer</p>
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  {isEnabled ? 'Global On' : 'Global Off'}
                </p>
              </div>
            </div>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {[0, 1, 2].map((index) => {
          const url = status?.wallpapers?.[index]
          const isMain = status?.main_index === index
          const isUploading = uploadingIndex === index
          const isDeleting = deletingIndex === index
          const isSettingMain = settingMainIndex === index

          return (
            <Card key={index} className={`overflow-hidden border-2 transition-all ${isMain ? 'border-primary ring-1 ring-primary/20' : 'border-muted'}`}>
              <CardHeader className="p-4 flex flex-row items-center justify-between space-y-0">
                <CardTitle className="text-sm font-medium">Slot {index + 1}</CardTitle>
                {isMain && (
                  <Badge className="bg-primary text-white gap-1 px-1.5 py-0.5">
                    <CheckCircle2 className="h-3 w-3" />
                    Main
                  </Badge>
                )}
              </CardHeader>
              <CardContent className="p-0">
                <div className="relative aspect-[9/16] bg-muted flex flex-col items-center justify-center group">
                  {url ? (
                    <div className="w-full h-full bg-black relative">
                      <img src={url} alt={`Wallpaper ${index + 1}`} className="w-full h-full object-cover" />
                      <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                         <Button size="icon" variant="secondary" className="rounded-full" onClick={() => { setPreviewImage(url); setShowPreviewModal(true) }}>
                            <Eye className="h-4 w-4" />
                         </Button>
                         <Button size="icon" variant="destructive" className="rounded-full" onClick={() => handleDelete(index)} disabled={isDeleting}>
                            {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                         </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="p-6 text-center space-y-3">
                      <div className="w-12 h-12 rounded-full border-2 border-dashed border-muted-foreground/30 flex items-center justify-center mx-auto">
                        {isUploading ? <Loader2 className="h-6 w-6 animate-spin text-primary" /> : <ImageIcon className="h-6 w-6 text-muted-foreground/40" />}
                      </div>
                      <div>
                        <p className="text-sm font-medium">No Image</p>
                        <p className="text-xs text-muted-foreground">9:16 portrait ratio recommended</p>
                      </div>
                      <Button size="sm" variant="outline" className="gap-2 relative" disabled={isUploading}>
                        <Upload className="h-3.5 w-3.5" />
                        {isUploading ? 'Uploading...' : 'Upload'}
                        <input 
                          type="file" 
                          accept="image/*" 
                          className="absolute inset-0 opacity-0 cursor-pointer"
                          onChange={(e) => handleFileUpload(index, e)}
                          disabled={isUploading}
                        />
                      </Button>
                    </div>
                  )}
                </div>
                <div className="p-4 border-t bg-muted/30">
                  <Button 
                    className="w-full gap-2" 
                    variant={isMain ? "default" : "outline"} 
                    disabled={!url || isMain || isSettingMain}
                    onClick={() => handleSetMain(index)}
                  >
                    {isSettingMain ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                    {isMain ? 'Currently Main' : 'Set as Main'}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <div className="rounded-xl border border-blue-100 bg-blue-50/50 p-4 flex gap-3 text-blue-800">
        <Info className="h-5 w-5 shrink-0" />
        <div className="text-sm space-y-1">
          <p className="font-semibold">Quick Tip</p>
          <p>
            The wallpaper set as <strong>"Main"</strong> is highly visible as it serves as the blurred background for your customers as they navigate through category and product pages. For the best look, choose high-quality imagery with vibrant colors.
          </p>
        </div>
      </div>

      <Dialog open={showPreviewModal} onOpenChange={setShowPreviewModal}>
        <DialogContent className="max-w-md p-0 border-none bg-transparent shadow-none">
          <DialogHeader className="sr-only">
            <DialogTitle>Wallpaper Preview</DialogTitle>
            <DialogDescription>Full view of the uploaded wallpaper.</DialogDescription>
          </DialogHeader>
          {previewImage && (
            <div className="relative aspect-[9/16] rounded-2xl overflow-hidden shadow-2xl">
              <img src={previewImage} alt="Wallpaper Preview" className="w-full h-full object-cover" />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
