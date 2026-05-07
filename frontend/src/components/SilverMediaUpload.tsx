import { useState } from 'react'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { 
  Upload, 
  Image as ImageIcon, 
  Video, 
  Lock, 
  Crown, 
  Star,
  AlertCircle,
  ArrowUp,
  Check
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

interface SilverMediaUploadProps {
  onUpload: (files: File[]) => Promise<void>
  currentImageCount?: number
  maxImages?: number
  disabled?: boolean
  className?: string
}

export default function SilverMediaUpload({ 
  onUpload, 
  currentImageCount = 0, 
  maxImages = 200, 
  disabled = false,
  className 
}: SilverMediaUploadProps) {
  const { isSilver, isGold, isDiamond, selectedRestaurant } = useRestaurant()
  const [uploading, setUploading] = useState(false)
  const [dragActive, setDragActive] = useState(false)

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return

    const fileArray = Array.from(files)
    
    // Silver restrictions
    if (isSilver) {
      // Check for video files (not allowed in Silver)
      const videoFiles = fileArray.filter(file => 
        file.type.startsWith('video/') || 
        ['.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv', '.flv', '.wmv'].some(ext => 
          file.name.toLowerCase().endsWith(ext)
        )
      )

      if (videoFiles.length > 0) {
        toast.error('Video uploads require Gold plan. Upgrade to unlock video features.', {
          duration: 5000,
          action: {
            label: 'Upgrade',
            onClick: () => {
              // TODO: Navigate to upgrade page
            }
          }
        })
        return
      }

      // Check image limit
      const imageFiles = fileArray.filter(file => file.type.startsWith('image/'))
      const totalImages = currentImageCount + imageFiles.length

      if (totalImages > maxImages) {
        toast.error(`Image limit exceeded. You can upload ${maxImages - currentImageCount} more images.`, {
          duration: 5000,
          action: {
            label: 'Upgrade to Gold',
            onClick: () => {
              // TODO: Navigate to upgrade page
            }
          }
        })
        return
      }
    }

    setUploading(true)
    
    try {
      await onUpload(fileArray)
      toast.success(`${fileArray.length} file(s) uploaded successfully`)
    } catch (error: any) {
      toast.error(error?.message || 'Failed to upload files')
    } finally {
      setUploading(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(false)
    handleFileSelect(e.dataTransfer.files)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(false)
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    handleFileSelect(e.target.files)
    // Clear input to allow selecting the same file again
    e.target.value = ''
  }

  if (!selectedRestaurant) {
    return (
      <Card className={cn("border-dashed border-muted-foreground/25", className)}>
        <CardContent className="flex items-center justify-center py-8">
          <div className="text-center text-muted-foreground">
            <AlertCircle className="h-8 w-8 mx-auto mb-2" />
            <p>Please select a restaurant first</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className={cn("space-y-4", className)}>
      {/* Usage indicator for Silver restaurants */}
      {isSilver && (
        <Card className="border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-950/20">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Star className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                <div className="text-sm">
                  <span className="font-semibold text-blue-900 dark:text-blue-100">Silver Plan Usage:</span>
                  <span className="text-blue-700 dark:text-blue-300 ml-2">
                    {currentImageCount}/{maxImages} images
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Progress 
                  value={(currentImageCount / maxImages) * 100} 
                  className="w-20 h-2" 
                />
                <Badge 
                  variant={currentImageCount >= maxImages ? "destructive" : "secondary"}
                  className="text-xs"
                >
                  {maxImages - currentImageCount} left
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Upload area */}
      <Card className={cn(
        "border-dashed transition-colors",
        dragActive && "border-primary bg-primary/5",
        disabled && "opacity-50 pointer-events-none",
        className
      )}>
        <CardContent 
          className="p-8"
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
        >
          <input
            type="file"
            id="media-upload"
            multiple
            accept="image/*,video/*"
            onChange={handleFileInput}
            disabled={disabled || uploading}
            className="hidden"
          />
          
          <div className="text-center space-y-4">
            {/* Upload icon */}
            <div className="mx-auto w-12 h-12 rounded-full bg-muted flex items-center justify-center">
              {uploading ? (
                <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full" />
              ) : (
                <Upload className="h-5 w-5 text-muted-foreground" />
              )}
            </div>

            {/* Main text */}
            <div className="space-y-2">
              <h3 className="font-semibold text-foreground">
                {uploading ? 'Uploading...' : 'Upload Media'}
              </h3>
              <p className="text-sm text-muted-foreground">
                {isSilver ? (
                  <>Drag and drop images here, or <label htmlFor="media-upload" className="text-primary hover:underline cursor-pointer">browse files</label></>
                ) : (
                  <>Drag and drop images and videos here, or <label htmlFor="media-upload" className="text-primary hover:underline cursor-pointer">browse files</label></>
                )}
              </p>
            </div>

            {/* Plan-specific information */}
            <div className="flex flex-col gap-2 text-xs">
              {isSilver ? (
                <div className="flex items-center justify-center gap-2 text-blue-600 dark:text-blue-400">
                  <Star className="h-3 w-3" />
                  <span>Images only • {maxImages - currentImageCount} remaining</span>
                </div>
              ) : (
                <div className="flex items-center justify-center gap-2 text-green-600 dark:text-green-400">
                  <Crown className="h-3 w-3" />
                  <span>Images & videos • Unlimited storage</span>
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div className="flex items-center justify-center gap-2">
              <Button 
                variant="outline" 
                size="sm"
                disabled={disabled || uploading || (isSilver && currentImageCount >= maxImages)}
                onClick={() => document.getElementById('media-upload')?.click()}
              >
                <ImageIcon className="h-4 w-4 mr-2" />
                Choose Images
              </Button>
              
              {(isGold || isDiamond) && (
                <Button 
                  variant="outline" 
                  size="sm"
                  disabled={disabled || uploading}
                  onClick={() => {
                    const input = document.getElementById('media-upload') as HTMLInputElement
                    if (input) {
                      input.accept = 'video/*'
                      input.click()
                      input.accept = 'image/*,video/*' // Reset accept
                    }
                  }}
                >
                  <Video className="h-4 w-4 mr-2" />
                  Choose Videos
                </Button>
              )}
            </div>

            {/* Upgrade prompt for Silver users at limit */}
            {isSilver && currentImageCount >= maxImages && (
              <Card className="border-orange-200 dark:border-orange-800 bg-orange-50/50 dark:bg-orange-950/20 mt-4">
                <CardContent className="p-3">
                  <div className="flex items-center gap-3">
                    <Lock className="h-4 w-4 text-orange-600 dark:text-orange-400" />
                    <div className="text-sm">
                      <span className="font-semibold text-orange-900 dark:text-orange-100">Image limit reached</span>
                      <span className="text-orange-700 dark:text-orange-300 block">
                        Upgrade to Gold for unlimited images and video uploads
                      </span>
                    </div>
                  </div>
                  <Button 
                    size="sm" 
                    className="w-full mt-2 bg-gradient-to-r from-orange-600 to-red-600 hover:from-orange-700 hover:to-red-700"
                    onClick={() => {
                      // TODO: Navigate to upgrade page
                    }}
                  >
                    <ArrowUp className="h-4 w-4 mr-2" />
                    Upgrade to Gold
                  </Button>
                </CardContent>
              </Card>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Feature comparison */}
      {isSilver && (
        <Card className="border-muted">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2">
              <Crown className="h-4 w-4" />
              Gold Features
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs">
            <div className="flex items-center gap-2">
              <Check className="h-3 w-3 text-green-600" />
              <span>Unlimited image uploads</span>
            </div>
            <div className="flex items-center gap-2">
              <Check className="h-3 w-3 text-green-600" />
              <span>Video uploads for menu items</span>
            </div>
            <div className="flex items-center gap-2">
              <Check className="h-3 w-3 text-green-600" />
              <span>Advanced media management</span>
            </div>
            <Button 
              variant="outline" 
              size="sm" 
              className="w-full mt-3"
              onClick={() => {
                // TODO: Navigate to upgrade page
              }}
            >
              Upgrade to Unlock All Features
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
