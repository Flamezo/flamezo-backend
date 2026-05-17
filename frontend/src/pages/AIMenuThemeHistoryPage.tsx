import { useEffect, useMemo, useState } from 'react'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall } from '@/lib/frappe'
import { toast } from 'sonner'
import { Loader2, Image as ImageIcon, Download, Eye, ArrowLeft, Calendar, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Link } from 'react-router-dom'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { format } from 'date-fns'

interface ThemeHistoryItem {
  id: string
  image_url: string
  source_images?: string[]
  created_on?: string
  active?: boolean
}

interface ThemeStatusResponse {
  success: boolean
  status: 'Idle' | 'Pending' | 'Processing' | 'Completed' | 'Failed'
  active_image?: string | null
  preview_image?: string | null
  source_images?: string[]
  history?: ThemeHistoryItem[]
  error_message?: string | null
}

export default function AIMenuThemeHistoryPage() {
  const { selectedRestaurant, restaurantConfig } = useRestaurant()
  const [showPreviewModal, setShowPreviewModal] = useState(false)
  const [selectedImage, setSelectedImage] = useState<string | null>(null)
  const { call: getThemeStatus } = useFrappePostCall<ThemeStatusResponse>('flamezo_backend.flamezo.api.ai_media.get_menu_theme_background_status')
  const { call: activateThemeBackground, loading: isActivating } = useFrappePostCall('flamezo_backend.flamezo.api.ai_media.activate_menu_theme_background')

  const [status, setStatus] = useState<ThemeStatusResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      if (!selectedRestaurant) {
        setIsLoading(false)
        return
      }
      setIsLoading(true)
      try {
        const res: any = await getThemeStatus({ restaurant: selectedRestaurant })
        const payload = res?.message || res
        if (!cancelled && payload?.success) {
          setStatus(payload)
        }
      } catch (error: any) {
        if (!cancelled) {
          toast.error('Failed to load theme history', { description: error?.message })
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [getThemeStatus, selectedRestaurant])

  const history = useMemo(
    () => status?.history || restaurantConfig?.branding?.menuThemeBackgroundHistory || [],
    [status, restaurantConfig]
  )

  const handleDownload = (url: string, name: string) => {
    const proxyUrl = `/api/method/flamezo_backend.flamezo.api.ai_media.download_proxy?file_url=${encodeURIComponent(url)}&filename=${encodeURIComponent(name)}`
    const link = document.createElement('a')
    link.href = proxyUrl
    link.download = name
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    toast.success('Download started!')
  }

  const handlePreview = (url: string) => {
    setSelectedImage(url)
    setShowPreviewModal(true)
  }

  const handleActivate = async (imageUrl: string) => {
    if (!selectedRestaurant || !imageUrl) return
    try {
      await activateThemeBackground({ restaurant: selectedRestaurant, image_url: imageUrl })
      toast.success('Theme background activated')
      const res: any = await getThemeStatus({ restaurant: selectedRestaurant })
      const payload = res?.message || res
      if (payload?.success) {
        setStatus(payload)
      }
    } catch (error: any) {
      toast.error('Failed to activate background', { description: error?.message })
    }
  }

  if (!selectedRestaurant) {
    return <div className="p-8 text-center text-muted-foreground">Please select a restaurant</div>
  }

  return (
    <div className="container mx-auto p-6 max-w-7xl animate-in fade-in duration-500">
      <div className="flex items-center justify-between mb-8">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Link to="/ai-menu-theme-background">
              <Button variant="ghost" size="icon" className="h-8 w-8 -ml-2 hover:bg-primary/5 hover:text-primary">
                <ArrowLeft className="h-4 w-4" />
              </Button>
            </Link>
            <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
              Menu Theme History
            </h1>
          </div>
          <p className="text-muted-foreground text-sm pl-8">
            Browse and reuse your generated menu theme backgrounds.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center min-h-[400px] gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary opacity-50" />
          <p className="text-sm text-muted-foreground animate-pulse">Curating your theme history...</p>
        </div>
      ) : history && history.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {history.map((item: ThemeHistoryItem) => (
            <Card key={item.id} className="group overflow-hidden border-muted/60 hover:border-primary/30 transition-all hover:shadow-lg hover:shadow-primary/5">
              <div className="relative aspect-[9/16] overflow-hidden bg-muted/20">
                <img
                  src={item.image_url}
                  className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                  alt={item.id}
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                  <div className="absolute bottom-4 left-4 right-4 flex justify-between items-center">
                    <div className="flex gap-2">
                      <Button
                        size="icon"
                        variant="secondary"
                        className="h-8 w-8 rounded-full bg-white/10 hover:bg-white/20 backdrop-blur-md border-white/10 text-white"
                        onClick={() => handlePreview(item.image_url)}
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="secondary"
                        className="h-8 w-8 rounded-full bg-white/10 hover:bg-white/20 backdrop-blur-md border-white/10 text-white"
                        onClick={() => handleDownload(item.image_url, `menu-theme-${item.id}.png`)}
                      >
                        <Download className="h-4 w-4" />
                      </Button>
                    </div>
                    <Button
                      size="sm"
                      className="h-8 rounded-full bg-primary text-primary-foreground hover:bg-primary/90"
                      disabled={item.active || isActivating}
                      onClick={() => handleActivate(item.image_url)}
                    >
                      {item.active ? 'Active' : 'Activate'}
                    </Button>
                  </div>
                </div>
                {item.active && (
                  <Badge variant="outline" className="absolute top-3 left-3 text-[9px] h-5 px-2 border-primary/20 bg-white/90 text-primary font-medium">
                    ACTIVE
                  </Badge>
                )}
              </div>
              <CardContent className="p-3">
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-bold text-foreground leading-tight truncate" title={item.id}>
                      Menu Theme Preview
                    </h3>
                    <div className="shrink-0">
                      <Badge variant="outline" className="text-[9px] h-4 px-1.5 border-primary/20 bg-primary/5 text-primary font-medium">
                        STUDIO
                      </Badge>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 text-[10px] text-muted-foreground/70">
                    <Calendar className="h-3 w-3" />
                    {item.created_on ? format(new Date(item.created_on), 'MMM dd, yyyy • hh:mm a') : 'Recently generated'}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center min-h-[400px] border-2 border-dashed rounded-xl bg-muted/5">
          <div className="bg-primary/5 p-4 rounded-full mb-4">
            <ImageIcon className="h-10 w-10 text-primary opacity-20" />
          </div>
          <h3 className="text-lg font-semibold text-foreground/80">Theme history is empty</h3>
          <p className="text-sm text-muted-foreground mb-6">Generate menu background previews to populate this gallery.</p>
          <Link to="/ai-menu-theme-background">
            <Button variant="default" className="shadow-lg shadow-primary/20">
              Go to AI Menu Background
            </Button>
          </Link>
        </div>
      )}

      <Dialog open={showPreviewModal} onOpenChange={setShowPreviewModal}>
        <DialogContent className="max-w-4xl p-0 border-none bg-transparent shadow-none overflow-visible">
          <DialogHeader className="sr-only">
            <DialogTitle>Generated menu theme background preview</DialogTitle>
            <DialogDescription>Preview the generated restaurant menu theme background image.</DialogDescription>
          </DialogHeader>
          <div className="relative group overflow-hidden rounded-xl shadow-2xl ring-1 ring-white/20">
            {selectedImage && (
              <img src={selectedImage} alt="Generated menu theme background" className="w-full h-auto max-h-[85vh] object-contain rounded-xl" />
            )}
            <div className="absolute top-4 left-4 flex items-center gap-2 bg-primary/90 text-white text-[10px] px-3 py-1.5 rounded-full font-bold shadow-lg backdrop-blur-md">
              <Sparkles className="h-3 w-3" />
              STUDIO PREVIEW
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
