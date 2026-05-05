import { useState, useEffect } from 'react'
import { useFrappeGetDoc, useFrappeGetDocList, useFrappePostCall, useFrappeUpdateDoc, useFrappeDeleteDoc } from '@/lib/frappe'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Plus, Edit2, Trash2, Users, Camera, Image, Star as StarIcon, Loader2, Instagram } from 'lucide-react'
import { toast } from 'sonner'
import { uploadToR2 } from '@/lib/r2Upload'

interface LegacyContentStepProps {
  selectedRestaurant: string
  onComplete: () => void
}

interface MenuProduct {
  name: string
  product_name: string
  image?: string
  category_name?: string
  main_category?: string
}

export default function LegacyContentStep({ selectedRestaurant, onComplete }: LegacyContentStepProps) {
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<any>(null)
  const [currentSection, setCurrentSection] = useState<string>('')
  const [uploading, setUploading] = useState(false)
  const [reelsToAdd, setReelsToAdd] = useState<string[]>([''])
  const [heroData, setHeroData] = useState({
    hero_media_type: 'image',
    hero_title: '',
    opening_text: '',
    paragraph_1: '',
    paragraph_2: ''
  })

  // Get the main legacy content document
  const { data: legacyContent, isLoading: contentLoading, mutate: mutateContent } = useFrappeGetDoc(
    'Legacy Content',
    selectedRestaurant,
    { enabled: !!selectedRestaurant }
  )

  // Child table data is derived from the main legacyContent document
  const signatureDishes = legacyContent?.signature_dishes || []
  const members = legacyContent?.members || []
  const galleryImages = legacyContent?.gallery_featured_images || []
  const instagramReels = legacyContent?.instagram_reels || []

  // Get all menu products for signature dishes selection
  const { data: allMenuProducts } = useFrappeGetDocList('Menu Product', {
    filters: selectedRestaurant ? ({ restaurant: selectedRestaurant, is_active: 1 } as any) : undefined,
    fields: ['name', 'product_name', 'category_name', 'main_category'],
    orderBy: { field: 'product_name', order: 'asc' } as any
  })

  const { call: createDoc, loading: isCreating } = useFrappePostCall('frappe.client.insert')
  const { updateDoc, loading: isUpdating } = useFrappeUpdateDoc()
  const { deleteDoc } = useFrappeDeleteDoc()
  const { call: updateLegacyContent } = useFrappePostCall('dinematters.dinematters.api.legacy.update_legacy_content')

  const refreshAll = () => {
    mutateContent()
  }

  // Unified Sync Engine: Handles both re-fetch and state migration
  useEffect(() => {
    // 1. Force a refresh if the restaurant context changes
    if (selectedRestaurant && mutateContent) {
      void (mutateContent() as any)
    }

    // 2. Only sync to local state if the data from server matches our selected restaurant
    // This prevents "flickering" or syncing stale data from the previous step/restaurant
    if (legacyContent && legacyContent.name === selectedRestaurant) {
      
      setHeroData({
        hero_media_type: legacyContent.hero_media_type || 'image',
        hero_title: legacyContent.hero_title || '',
        opening_text: legacyContent.opening_text || '',
        paragraph_1: legacyContent.paragraph_1 || '',
        paragraph_2: legacyContent.paragraph_2 || ''
      })
    } else if (legacyContent) {
      
    }
  }, [selectedRestaurant, legacyContent, mutateContent])

  const handleSaveChild = async (data: any, type: string, doctype: string) => {
    try {
      if (editingItem?.name) {
        await updateDoc(doctype, editingItem.name, data)
        toast.success(`${type} updated successfully`)
      } else {
        await createDoc({
          ...data,
          doctype: doctype,
          parent: selectedRestaurant,
          parenttype: 'Legacy Content',
          parentfield: getChildTableField(doctype)
        })
        toast.success(`${type} added successfully`)
      }
      
      setIsDialogOpen(false)
      setEditingItem(null)
      refreshAll()
    } catch (error) {
      toast.error(`Failed to save ${type}`)
    }
  }

  const handleDelete = async (doctype: string, name: string, type: string) => {
    try {
      await deleteDoc(doctype, name)
      toast.success(`${type} deleted successfully`)
      refreshAll()
    } catch (error) {
      toast.error(`Failed to delete ${type}`)
    }
  }

  const handleLegacyContentSave = async (data: any) => {
    try {
      await updateLegacyContent({
        restaurant_id: selectedRestaurant,
        ...data
      })
      toast.success('Legacy content updated successfully')
      mutateContent()
    } catch (error) {
      toast.error('Failed to update legacy content')
    }
  }

  const handleFileUpload = async (file: File, mediaRole: string): Promise<string> => {
    setUploading(true)
    try {
      const result = await uploadToR2({
        ownerDoctype: 'Legacy Content',
        ownerName: selectedRestaurant,
        mediaRole,
        file
      })
      return result.primary_url
    } catch (error) {
      console.error('Upload failed:', error)
      throw error
    } finally {
      setUploading(false)
    }
  }

  const getChildTableField = (doctype: string) => {
    const mapping: Record<string, string> = {
      'Legacy Signature Dish': 'signature_dishes',
      'Legacy Testimonial': 'testimonials',
      'Legacy Member': 'members',
      'Legacy Gallery Image': 'gallery_featured_images',
      'Legacy Instagram Reel': 'instagram_reels'
    }
    return mapping[doctype] || ''
  }

  const renderSignatureDishesSection = () => (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <StarIcon className="h-5 w-5" />
            Signature Dishes
            <Badge variant="secondary">{signatureDishes?.length || 0}/3</Badge>
          </CardTitle>
          <Button 
            size="sm" 
            onClick={() => {
              setEditingItem({ type: 'Signature Dish', doctype: 'Legacy Signature Dish' })
              setCurrentSection('Signature Dish')
              setIsDialogOpen(true)
            }}
            disabled={(signatureDishes?.length || 0) >= 3}
          >
            <Plus className="h-4 w-4 mr-1" />
            Add Signature Dish
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {signatureDishes && signatureDishes.length > 0 ? (
          <div className="space-y-4">
            {signatureDishes.map((item: any) => (
              <div key={item.name} className="flex items-center justify-between p-4 border rounded-lg">
                <div>
                  <h4 className="font-semibold">{item.dish_name || item.dish}</h4>
                  <p className="text-sm text-muted-foreground">Order: {item.display_order}</p>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => {
                    setEditingItem({ ...item, type: 'Signature Dish', doctype: 'Legacy Signature Dish' })
                    setCurrentSection('Signature Dish')
                    setIsDialogOpen(true)
                  }}>
                    <Edit2 className="h-4 w-4" />
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => handleDelete('Legacy Signature Dish', item.name, 'Signature Dish')}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            No signature dishes yet. Add up to 3 signature dishes from your menu.
          </div>
        )}
      </CardContent>
    </Card>
  )

  const renderMembersSection = () => (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" />
            Team Members
            <Badge variant="secondary">{members?.length || 0}/3</Badge>
          </CardTitle>
          <Button 
            size="sm" 
            onClick={() => {
              setEditingItem({ type: 'Member', doctype: 'Legacy Member' })
              setCurrentSection('Member')
              setIsDialogOpen(true)
            }}
            disabled={(members?.length || 0) >= 3}
          >
            <Plus className="h-4 w-4 mr-1" />
            Add Team Member
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {members && members.length > 0 ? (
          <div className="space-y-4">
            {members.map((item: any) => (
              <div key={item.name} className="flex items-center justify-between p-4 border rounded-lg">
                <div className="flex items-center gap-3">
                  {item.image && (
                    <div className="h-12 w-12 rounded-full overflow-hidden border">
                      <img src={item.image} alt={item.member_name} className="h-full w-full object-cover" />
                    </div>
                  )}
                  <div>
                    <h4 className="font-semibold">{item.member_name}</h4>
                    <p className="text-sm text-muted-foreground">{item.role}</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => {
                    setEditingItem({ ...item, type: 'Member', doctype: 'Legacy Member' })
                    setCurrentSection('Member')
                    setIsDialogOpen(true)
                  }}>
                    <Edit2 className="h-4 w-4" />
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => handleDelete('Legacy Member', item.name, 'Member')}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            No team members yet. Add up to 3 team members with photos.
          </div>
        )}
      </CardContent>
    </Card>
  )

  const renderGallerySection = () => (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Camera className="h-5 w-5" />
            Gallery Images
            <Badge variant="secondary">{galleryImages?.length || 0}</Badge>
          </CardTitle>
          <Button size="sm" onClick={() => {
            setEditingItem({ type: 'Gallery Image', doctype: 'Legacy Gallery Image' })
            setCurrentSection('Gallery Image')
            setIsDialogOpen(true)
          }}>
            <Plus className="h-4 w-4 mr-1" />
            Add Gallery Image
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {galleryImages && galleryImages.length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {galleryImages.map((item: any) => (
              <div key={item.name} className="relative group">
                <div className="aspect-square rounded-lg overflow-hidden border">
                  <img src={item.image} alt={item.title || 'Gallery image'} className="h-full w-full object-cover" />
                </div>
                <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg flex items-center justify-center gap-2">
                  <Button size="sm" variant="secondary" onClick={() => {
                    setEditingItem({ ...item, type: 'Gallery Image', doctype: 'Legacy Gallery Image' })
                    setCurrentSection('Gallery Image')
                    setIsDialogOpen(true)
                  }}>
                    <Edit2 className="h-4 w-4" />
                  </Button>
                  <Button size="sm" variant="destructive" onClick={() => handleDelete('Legacy Gallery Image', item.name, 'Gallery Image')}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                {item.title && (
                  <p className="mt-2 text-sm font-medium truncate">{item.title}</p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            No gallery images yet. Upload images to showcase your restaurant.
          </div>
        )}
      </CardContent>
    </Card>
  )

  const renderInstagramReelsSection = () => (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Instagram className="h-5 w-5" />
            Moments We Treasure
            <Badge variant="secondary">{instagramReels?.length || 0}/3</Badge>
          </CardTitle>
          <Button 
            size="sm" 
            onClick={() => {
              setEditingItem({ type: 'Instagram Reel', doctype: 'Legacy Instagram Reel' })
              setCurrentSection('Instagram Reel')
              setIsDialogOpen(true)
            }}
            disabled={(instagramReels?.length || 0) >= 3}
          >
            <Plus className="h-4 w-4 mr-1" />
            Add Reel
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {instagramReels && instagramReels.length > 0 ? (
          <div className="space-y-4">
            {instagramReels.map((item: any) => (
              <div key={item.name} className="flex items-center justify-between p-4 border rounded-lg">
                <div className="flex-1 min-w-0 mr-4">
                  <h4 className="font-semibold truncate">{item.title || 'Instagram Reel'}</h4>
                  <p className="text-sm text-muted-foreground truncate">{item.reel_link}</p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <Button size="sm" variant="outline" onClick={() => {
                    setEditingItem({ ...item, type: 'Instagram Reel', doctype: 'Legacy Instagram Reel' })
                    setCurrentSection('Instagram Reel')
                    setIsDialogOpen(true)
                  }}>
                    <Edit2 className="h-4 w-4" />
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => handleDelete('Legacy Instagram Reel', item.name, 'Instagram Reel')}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            No reels yet. Add up to 3 Instagram Reels to showcase "Moments We Treasure".
          </div>
        )}
      </CardContent>
    </Card>
  )

  const renderFormDialogContent = () => {
    const handleSubmit = async (e: React.FormEvent) => {
      e.preventDefault()
      const formData = new FormData(e.target as HTMLFormElement)
      const data: any = {}
      
      try {
        switch (currentSection) {
          case 'Signature Dish':
            data.dish = formData.get('dish')
            data.display_order = parseInt(formData.get('display_order') as string) || 0
            break
          case 'Member':
            data.member_name = formData.get('member_name')
            data.role = formData.get('role')
            data.display_order = parseInt(formData.get('display_order') as string) || 0
            
            // Handle member photo upload
            const memberPhotoFile = (formData.get('member_photo') as File)
            if (memberPhotoFile && memberPhotoFile.size > 0) {
              data.image = await handleFileUpload(memberPhotoFile, 'legacy_member_image')
            } else if (!editingItem?.image) {
              toast.error('Member photo is required')
              return
            }
            break
          case 'Gallery Image':
            data.title = formData.get('title')
            data.display_order = parseInt(formData.get('display_order') as string) || 0
            
            // Handle gallery image upload
            const galleryFile = (formData.get('gallery_image') as File)
            if (galleryFile && galleryFile.size > 0) {
              data.image = await handleFileUpload(galleryFile, 'legacy_gallery_image')
            } else if (!editingItem?.image) {
              toast.error('Gallery image is required')
              return
            }
            break
          case 'Instagram Reel':
            if (editingItem?.name) {
              // Edit mode
              data.reel_link = formData.get('reel_link')
              data.title = formData.get('title')
              data.display_order = parseInt(formData.get('display_order') as string) || 0
            } else {
              // Add mode - multiple reels
              const links = reelsToAdd.filter(link => link.trim() !== '')
              if (links.length === 0) {
                toast.error('At least one reel link is required')
                return
              }
              
              for (const link of links) {
                await createDoc({
                  reel_link: link,
                  title: 'Instagram Reel',
                  doctype: 'Legacy Instagram Reel',
                  parent: selectedRestaurant,
                  parenttype: 'Legacy Content',
                  parentfield: 'instagram_reels'
                })
              }
              
              toast.success(`${links.length} reel(s) added successfully`)
              setIsDialogOpen(false)
              setEditingItem(null)
              setReelsToAdd([''])
              refreshAll()
              return // Already handled
            }
            break
        }
        
        await handleSaveChild(data, currentSection, editingItem.doctype)
      } catch (error: any) {
        toast.error(error.message || `Failed to save ${currentSection}`)
      }
    }

    if (currentSection === 'Signature Dish') {
      return (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="dish">Select Dish from Menu</Label>
            <Select name="dish" defaultValue={editingItem?.dish} required>
              <SelectTrigger>
                <SelectValue placeholder="Select a dish from your menu" />
              </SelectTrigger>
              <SelectContent>
                {allMenuProducts?.map((product: MenuProduct) => (
                  <SelectItem key={product.name} value={product.name}>
                    <div className="flex items-center gap-2">
                      {product.image && (
                        <img 
                          src={product.image} 
                          alt={product.product_name} 
                          className="h-4 w-4 rounded object-cover" 
                        />
                      )}
                      <span>{product.product_name}</span>
                      <span className="text-xs text-muted-foreground ml-2">
                        ({product.category_name || 'Uncategorised'})
                      </span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {allMenuProducts && allMenuProducts.length === 0 && (
              <p className="text-sm text-muted-foreground mt-2">
                No menu products found. Please add menu products first.
              </p>
            )}
          </div>
          <div>
            <Label htmlFor="display_order">Display Order</Label>
            <NumberInput  name="display_order" defaultValue={editingItem?.display_order || 0} />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isCreating || isUpdating}>
              {editingItem?.name ? 'Update' : 'Create'}
            </Button>
          </div>
        </form>
      )
    }

    if (currentSection === 'Member') {
      return (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="member_name">Member Name</Label>
            <Input name="member_name" defaultValue={editingItem?.member_name} required />
          </div>
          <div>
            <Label htmlFor="role">Role</Label>
            <Input name="role" defaultValue={editingItem?.role} placeholder="e.g. Head Chef, Manager, etc." />
          </div>
          <div>
            <Label htmlFor="member_photo">Member Photo (Required)</Label>
            <Input
              type="file"
              name="member_photo"
              accept="image/*"
              required={!editingItem?.image}
              className="cursor-pointer"
            />
            {editingItem?.image && (
              <div className="mt-2">
                <p className="text-sm text-muted-foreground mb-2">Current photo:</p>
                <img src={editingItem.image} alt="Current member photo" className="h-20 w-20 rounded-full object-cover border" />
              </div>
            )}
          </div>
          <div>
            <Label htmlFor="display_order">Display Order</Label>
            <NumberInput  name="display_order" defaultValue={editingItem?.display_order || 0} />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isCreating || isUpdating || uploading}>
              {uploading ? <Loader2 className="animate-spin h-4 w-4 mr-2" /> : null}
              {uploading ? 'Uploading...' : (editingItem?.name ? 'Update' : 'Create')}
            </Button>
          </div>
        </form>
      )
    }

    if (currentSection === 'Gallery Image') {
      return (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="gallery_image">Gallery Image (Required)</Label>
            <Input
              type="file"
              name="gallery_image"
              accept="image/*"
              required={!editingItem?.image}
              className="cursor-pointer"
            />
            {editingItem?.image && (
              <div className="mt-2">
                <p className="text-sm text-muted-foreground mb-2">Current image:</p>
                <img src={editingItem.image} alt="Current gallery image" className="h-32 w-full max-w-xs object-cover rounded-lg border" />
              </div>
            )}
          </div>
          <div>
            <Label htmlFor="title">Title (Optional)</Label>
            <Input name="title" defaultValue={editingItem?.title} placeholder="Enter image title" />
          </div>
          <div>
            <Label htmlFor="display_order">Display Order</Label>
            <NumberInput  name="display_order" defaultValue={editingItem?.display_order || 0} />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isCreating || isUpdating || uploading}>
              {uploading ? <Loader2 className="animate-spin h-4 w-4 mr-2" /> : null}
              {uploading ? 'Uploading...' : (editingItem?.name ? 'Update' : 'Create')}
            </Button>
          </div>
        </form>
      )
    }

    if (currentSection === 'Instagram Reel') {
      const remainingSlots = 3 - (instagramReels?.length || 0)
      
      return (
        <form onSubmit={handleSubmit} className="space-y-4">
          {editingItem?.name ? (
            <>
              <div>
                <Label htmlFor="reel_link">Reel Link</Label>
                <Input name="reel_link" defaultValue={editingItem?.reel_link} required placeholder="https://www.instagram.com/reels/..." />
              </div>
              <div>
                <Label htmlFor="title">Title (Optional)</Label>
                <Input name="title" defaultValue={editingItem?.title} placeholder="e.g. Grandma's Recipe" />
              </div>
              <div>
                <Label htmlFor="display_order">Display Order</Label>
                <NumberInput  name="display_order" defaultValue={editingItem?.display_order || 0} />
              </div>
            </>
          ) : (
            <div className="space-y-4">
              {reelsToAdd.map((link, index) => (
                <div key={index} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label>Reel Link {index + 1}</Label>
                    {index > 0 && (
                      <Button 
                        type="button" 
                        variant="ghost" 
                        size="sm" 
                        className="h-6 text-destructive"
                        onClick={() => setReelsToAdd(reelsToAdd.filter((_, i) => i !== index))}
                      >
                        Remove
                      </Button>
                    )}
                  </div>
                  <Input 
                    value={link} 
                    onChange={(e) => {
                      const newReels = [...reelsToAdd]
                      newReels[index] = e.target.value
                      setReelsToAdd(newReels)
                    }} 
                    placeholder="https://www.instagram.com/reels/..."
                    required={index === 0}
                  />
                </div>
              ))}
              
              {reelsToAdd.length < remainingSlots && (
                <Button 
                  type="button" 
                  variant="outline" 
                  size="sm" 
                  className="w-full"
                  onClick={() => setReelsToAdd([...reelsToAdd, ''])}
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Add another Reel
                </Button>
              )}
            </div>
          )}
          
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isCreating || isUpdating}>
              {editingItem?.name ? 'Update' : 'Add Reels'}
            </Button>
          </div>
        </form>
      )
    }

    return null
  }

  if (contentLoading) {
    return (
      <div className="space-y-6 py-8 animate-pulse">
        <div className="space-y-2">
          <div className="h-8 w-48 bg-muted rounded" />
          <div className="h-4 w-96 bg-muted/60 rounded" />
        </div>
        <div className="grid gap-6">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-48 rounded-xl bg-muted border border-muted-foreground/10" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Legacy Content</h1>
        <p className="text-muted-foreground">Configure your restaurant's story, heritage, and featured content</p>
      </div>

      {/* Hero Section Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Image className="h-5 w-5" />
            Hero Section
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form 
            key={legacyContent?.name || 'loading'}
            onSubmit={(e) => {
            e.preventDefault()
            handleLegacyContentSave(heroData)
          }} className="space-y-4">
            <div>
              <Label htmlFor="hero_media_type">Hero Media Type</Label>
              <Select 
                name="hero_media_type" 
                value={heroData.hero_media_type}
                onValueChange={(val) => setHeroData(prev => ({ ...prev, hero_media_type: val }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select media type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="image">Image</SelectItem>
                  <SelectItem value="video">Video</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="hero_title">Hero Title</Label>
              <Input 
                name="hero_title" 
                value={heroData.hero_title} 
                onChange={(e) => setHeroData(prev => ({ ...prev, hero_title: e.target.value }))}
                placeholder="Enter your restaurant's story title" 
              />
            </div>
            <div>
              <Label htmlFor="opening_text">Opening Text</Label>
              <Textarea 
                name="opening_text" 
                value={heroData.opening_text} 
                onChange={(e) => setHeroData(prev => ({ ...prev, opening_text: e.target.value }))}
                placeholder="Welcome text for your restaurant" 
              />
            </div>
            <div>
              <Label htmlFor="paragraph_1">First Paragraph</Label>
              <Textarea 
                name="paragraph_1" 
                value={heroData.paragraph_1} 
                onChange={(e) => setHeroData(prev => ({ ...prev, paragraph_1: e.target.value }))}
                placeholder="Tell your restaurant's story" 
              />
            </div>
            <div>
              <Label htmlFor="paragraph_2">Second Paragraph (Optional)</Label>
              <Textarea 
                name="paragraph_2" 
                value={heroData.paragraph_2} 
                onChange={(e) => setHeroData(prev => ({ ...prev, paragraph_2: e.target.value }))}
                placeholder="Continue your story" 
              />
            </div>
            <Button type="submit" disabled={isUpdating}>
              {isUpdating ? <Loader2 className="animate-spin h-4 w-4 mr-2" /> : null}
              Save Hero Section
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="grid gap-6">
        {renderSignatureDishesSection()}
        {renderMembersSection()}
        {renderGallerySection()}
        {renderInstagramReelsSection()}
      </div>

      <div className="flex justify-end gap-4 pt-6">
        <Button onClick={onComplete} size="lg" className="px-10">
          Complete Legacy Setup
        </Button>
      </div>

      {/* Dialog for forms */}
      <Dialog open={isDialogOpen} onOpenChange={(open) => {
        setIsDialogOpen(open)
        if (!open) {
          setEditingItem(null)
          setCurrentSection('')
        }
      }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {editingItem?.name && !editingItem.doctype?.includes('Signature') ? `Edit ${currentSection}` : `Add ${currentSection}`}
            </DialogTitle>
          </DialogHeader>
          {renderFormDialogContent()}
        </DialogContent>
      </Dialog>
    </div>
  )
}
