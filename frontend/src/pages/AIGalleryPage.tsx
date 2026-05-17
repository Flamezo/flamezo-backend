import { useState } from 'react'
import { useFrappeGetDocList } from 'frappe-react-sdk'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { toast } from 'sonner'
import { Loader2, Image as ImageIcon, Download, Eye, ArrowLeft, Calendar, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Link } from 'react-router-dom'
import {
  Dialog,
  DialogContent,
} from '@/components/ui/dialog'
import { format } from 'date-fns'

export default function AIGalleryPage() {
  const { selectedRestaurant } = useRestaurant()
  const [showPreviewModal, setShowPreviewModal] = useState(false)
  const [selectedImage, setSelectedImage] = useState<string | null>(null)

  const { data: generations, isLoading } = useFrappeGetDocList('AI Image Generation', {
    fields: ['name', 'creation', 'owner_name', 'original_image_url', 'enhanced_image_url'],
    filters: [['restaurant', '=', selectedRestaurant || ''], ['status', '=', 'Completed']],
    orderBy: { field: 'creation', order: 'desc' },
    limit: 50
  }, selectedRestaurant ? undefined : null)

  const handleDownload = async (url: string, name: string) => {
    // Use the backend proxy to bypass CORS and force download
    const proxyUrl = `/api/method/flamezo_backend.flamezo.api.ai_media.download_proxy?file_url=${encodeURIComponent(url)}&filename=ai-gen-${name}.png`
    
    const link = document.createElement('a')
    link.href = proxyUrl
    link.download = `ai-gen-${name}.png`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    toast.success('Download started!')
  }

  const handlePreview = (url: string) => {
    setSelectedImage(url)
    setShowPreviewModal(true)
  }

  if (!selectedRestaurant) {
    return <div className="p-8 text-center text-muted-foreground">Please select a restaurant</div>
  }

  return (
    <div className="container mx-auto p-6 max-w-7xl animate-in fade-in duration-500">
      <div className="flex items-center justify-between mb-8">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Link to="/ai-enhancements">
              <Button variant="ghost" size="icon" className="h-8 w-8 -ml-2 hover:bg-primary/5 hover:text-primary">
                <ArrowLeft className="h-4 w-4" />
              </Button>
            </Link>
            <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
              My Generative Gallery
            </h1>
          </div>
          <p className="text-muted-foreground text-sm pl-8">
            Manage and rediscover your AI-enhanced masterpieces
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center min-h-[400px] gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary opacity-50" />
          <p className="text-sm text-muted-foreground animate-pulse">Curating your collection...</p>
        </div>
      ) : generations && generations.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {generations.map((gen) => (
            <Card key={gen.name} className="group overflow-hidden border-muted/60 hover:border-primary/30 transition-all hover:shadow-lg hover:shadow-primary/5">
              <div className="relative aspect-square overflow-hidden bg-muted/20">
                <img 
                  src={gen.enhanced_image_url} 
                  className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110" 
                  alt={gen.owner_name} 
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                  <div className="absolute bottom-4 left-4 right-4 flex justify-between items-center">
                    <div className="flex gap-2">
                       <Button 
                         size="icon" 
                         variant="secondary" 
                         className="h-8 w-8 rounded-full bg-white/10 hover:bg-white/20 backdrop-blur-md border-white/10 text-white"
                         onClick={() => handlePreview(gen.enhanced_image_url)}
                       >
                         <Eye className="h-4 w-4" />
                       </Button>
                       <Button 
                         size="icon" 
                         variant="secondary" 
                         className="h-8 w-8 rounded-full bg-white/10 hover:bg-white/20 backdrop-blur-md border-white/10 text-white"
                         onClick={() => handleDownload(gen.enhanced_image_url, gen.name)}
                       >
                         <Download className="h-4 w-4" />
                       </Button>
                    </div>
                  </div>
                </div>
              </div>
              <CardContent className="p-3">
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-bold text-foreground leading-tight truncate" title={gen.owner_name}>
                      {gen.owner_name}
                    </h3>
                    <div className="shrink-0">
                      <Badge variant="outline" className="text-[9px] h-4 px-1.5 border-primary/20 bg-primary/5 text-primary font-medium">
                        STUDIO
                      </Badge>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 text-[10px] text-muted-foreground/70">
                    <Calendar className="h-3 w-3" />
                    {format(new Date(gen.creation), 'MMM dd, yyyy • hh:mm a')}
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
           <h3 className="text-lg font-semibold text-foreground/80">Gallery is empty</h3>
           <p className="text-sm text-muted-foreground mb-6">Start enhancing your menu images to populate your gallery.</p>
           <Link to="/ai-enhancements">
             <Button variant="default" className="shadow-lg shadow-primary/20">
               Go to AI Enhancements
             </Button>
           </Link>
        </div>
      )}

      {/* Preview Modal */}
      <Dialog open={showPreviewModal} onOpenChange={setShowPreviewModal}>
        <DialogContent className="max-w-3xl p-0 border-none bg-transparent shadow-none overflow-visible">
          <div className="relative group overflow-hidden rounded-xl shadow-2xl ring-1 ring-white/20">
             {selectedImage && (
               <img 
                 src={selectedImage} 
                 alt="Premium AI Enhancement" 
                 className="w-full h-auto max-h-[85vh] object-contain rounded-xl" 
               />
             )}
             
             {/* High-End Label */}
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
