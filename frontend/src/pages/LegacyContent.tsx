import { useState } from 'react'
import * as React from 'react'
import { useFrappeGetDoc, useFrappeGetDocList, useFrappePostCall, useFrappeUpdateDoc, useFrappeDeleteDoc } from '@/lib/frappe'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Plus, Edit2, Trash2, Users, Star, Instagram, Image, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { uploadToR2 } from '@/lib/r2Upload'

export default function LegacyContentPage() {
  const { selectedRestaurant } = useRestaurant()
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<any>(null)

  const [uploading, setUploading] = useState(false)
  const [heroData, setHeroData] = useState({
    hero_media_type: 'image',
    hero_media_src: '',
    hero_fallback_image: '',
    hero_title: '',
    opening_text: '',
    paragraph_1: '',
    paragraph_2: ''
  })
  const [footerData, setFooterData] = useState({
    footer_media_src: '',
    footer_title: '',
    footer_description: '',
    footer_cta_text: '',
    footer_cta_route: ''
  })

  // Get the main legacy content document
  const { data: legacyContent, isLoading: contentLoading, mutate: mutateContent } = useFrappeGetDoc(
    'Legacy Content',
    selectedRestaurant || '',
    { enabled: !!selectedRestaurant }
  )

  React.useEffect(() => {
    if (legacyContent && legacyContent.name === selectedRestaurant) {
      setHeroData({
        hero_media_type: legacyContent.hero_media_type || 'image',
        hero_media_src: legacyContent.hero_media_src || '',
        hero_fallback_image: legacyContent.hero_fallback_image || '',
        hero_title: legacyContent.hero_title || '',
        opening_text: legacyContent.opening_text || '',
        paragraph_1: legacyContent.paragraph_1 || '',
        paragraph_2: legacyContent.paragraph_2 || ''
      })
      
      setFooterData({
        footer_media_src: legacyContent.footer_media_src || '',
        footer_title: legacyContent.footer_title || '',
        footer_description: legacyContent.footer_description || '',
        footer_cta_text: legacyContent.footer_cta_text || '',
        footer_cta_route: legacyContent.footer_cta_route || ''
      })
    }
  }, [legacyContent, selectedRestaurant])

  // Get child table data
  const { data: signatureDishes, mutate: mutateSignatureDishes } = useFrappeGetDocList('Legacy Signature Dish', {
    filters: [['parent', '=', selectedRestaurant]],
    fields: ['name', 'dish', 'display_order', 'dish_name'],
    orderBy: { field: 'display_order', order: 'asc' }
  })

  const { data: testimonials, mutate: mutateTestimonials } = useFrappeGetDocList('Legacy Testimonial', {
    filters: [['parent', '=', selectedRestaurant]],
    fields: ['name', 'customer_name', 'rating', 'text', 'location', 'avatar', 'display_order'],
    orderBy: { field: 'display_order', order: 'asc' }
  })

  const { data: members, mutate: mutateMembers } = useFrappeGetDocList('Legacy Member', {
    filters: [['parent', '=', selectedRestaurant]],
    fields: ['name', 'member_name', 'role', 'image', 'display_order'],
    orderBy: { field: 'display_order', order: 'asc' }
  })


  const { data: instagramReels, mutate: mutateReels } = useFrappeGetDocList('Legacy Instagram Reel', {
    filters: [['parent', '=', selectedRestaurant]],
    fields: ['name', 'reel_link', 'title', 'display_order'],
    orderBy: { field: 'display_order', order: 'asc' }
  })

  // Get menu products for signature dishes selection
  const { data: menuProducts } = useFrappeGetDocList('Menu Product', {
    filters: [['restaurant', '=', selectedRestaurant]],
    fields: ['name', 'product_name', 'image']
  })

  const { call: createDoc, loading: isCreating } = useFrappePostCall('frappe.client.insert')
  const { updateDoc, loading: isUpdating } = useFrappeUpdateDoc()
  const { deleteDoc } = useFrappeDeleteDoc()
  const { call: updateLegacyContent, loading: isUpdatingLegacy } = useFrappePostCall('flamezo_backend.flamezo.api.legacy.update_legacy_content')
  const { call: generateLegacyContent, loading: isGenerating } = useFrappePostCall('flamezo_backend.flamezo.api.legacy.generate_legacy_content')

  const handleGenerateLegacy = async () => {
    try {
      const res = await generateLegacyContent({ restaurant_id: selectedRestaurant })
      if (res?.message?.success) {
        toast.success('Legacy content generated successfully')
        mutateContent()
        mutateSignatureDishes()
        mutateTestimonials()
        mutateMembers()
      } else {
        toast.error(res?.message?.error?.message || 'Failed to generate legacy content')
      }
    } catch (error) {
      toast.error('Error generating legacy content')
    }
  }

  const handleFileUpload = async (file: File, mediaRole: string): Promise<string> => {
    setUploading(true)
    try {
      const result = await uploadToR2({
        ownerDoctype: 'Legacy Content',
        ownerName: selectedRestaurant || '',
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

  const handleHeroContentSave = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await updateLegacyContent({
        restaurant_id: selectedRestaurant,
        hero: {
          mediaType: heroData.hero_media_type,
          mediaSrc: heroData.hero_media_src,
          fallbackImage: heroData.hero_fallback_image,
          title: heroData.hero_title
        },
        content: {
          openingText: heroData.opening_text,
          paragraph1: heroData.paragraph_1,
          paragraph2: heroData.paragraph_2
        }
      })
      toast.success('Hero content updated successfully')
      mutateContent()
    } catch (error) {
      toast.error('Failed to update hero content')
    }
  }

  const handleFooterContentSave = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await updateLegacyContent({
        restaurant_id: selectedRestaurant,
        footer: {
          mediaSrc: footerData.footer_media_src,
          title: footerData.footer_title,
          description: footerData.footer_description,
          ctaButton: {
            text: footerData.footer_cta_text,
            route: footerData.footer_cta_route
          }
        }
      })
      toast.success('Footer content updated successfully')
      mutateContent()
    } catch (error) {
      toast.error('Failed to update footer content')
    }
  }

  const handleSave = async (data: any, type: string, doctype: string) => {
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
      
      // Refresh relevant data
      mutateSignatureDishes()
      mutateTestimonials()
      mutateMembers()
      mutateReels()
    } catch (error) {
      toast.error(`Failed to save ${type}`)
    }
  }

  const handleDelete = async (doctype: string, name: string, type: string) => {
    try {
      await deleteDoc(doctype, name)
      toast.success(`${type} deleted successfully`)
      
      // Refresh relevant data
      mutateSignatureDishes()
      mutateTestimonials()
      mutateMembers()
      mutateReels()
    } catch (error) {
      toast.error(`Failed to delete ${type}`)
    }
  }

  const getChildTableField = (doctype: string) => {
    const mapping: Record<string, string> = {
      'Legacy Signature Dish': 'signature_dishes',
      'Legacy Testimonial': 'testimonials',
      'Legacy Member': 'members',
      'Legacy Instagram Reel': 'instagram_reels'
    }
    return mapping[doctype] || ''
  }

  const renderSection = (title: string, icon: any, data: any[], type: string, doctype: string, renderItem: (item: any) => React.ReactNode) => (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            {icon}
            {title}
            <Badge variant="secondary">{data.length}</Badge>
          </CardTitle>
          <Dialog open={isDialogOpen && editingItem?.type === type} onOpenChange={(open) => {
            setIsDialogOpen(open)
            if (!open) setEditingItem(null)
          }}>
            <DialogTrigger asChild>
              <Button size="sm" onClick={() => setEditingItem({ type, doctype })}>
                <Plus className="h-4 w-4 mr-1" />
                Add {type}
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>
                  {editingItem?.name ? `Edit ${type}` : `Add ${type}`}
                </DialogTitle>
              </DialogHeader>
              {renderForm(type, doctype, editingItem)}
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No {title.toLowerCase()} yet. Click `Add {type}` to get started.
          </div>
        ) : (
          <div className="space-y-4">
            {data.map(renderItem)}
          </div>
        )}
      </CardContent>
    </Card>
  )

  const renderForm = (type: string, doctype: string, editingData: any) => {
    const handleSubmit = (e: React.FormEvent) => {
      e.preventDefault()
      const formData = new FormData(e.target as HTMLFormElement)
      const data: any = {}
      
      switch (type) {
        case 'Signature Dish':
          data.dish = formData.get('dish')
          data.display_order = parseInt(formData.get('display_order') as string) || 0
          break
        case 'Testimonial':
          data.customer_name = formData.get('customer_name')
          data.rating = parseInt(formData.get('rating') as string) || 5
          data.text = formData.get('text')
          data.location = formData.get('location')
          data.avatar = formData.get('avatar')
          data.display_order = parseInt(formData.get('display_order') as string) || 0
          break
        case 'Member':
          data.member_name = formData.get('member_name')
          data.role = formData.get('role')
          data.image = formData.get('image')
          data.display_order = parseInt(formData.get('display_order') as string) || 0
          break
        case 'Instagram Reel':
          data.reel_link = formData.get('reel_link')
          data.title = formData.get('title')
          data.display_order = parseInt(formData.get('display_order') as string) || 0
          break
      }
      
      handleSave(data, type, doctype)
    }

    return (
      <form onSubmit={handleSubmit} className="space-y-4">
        {type === 'Signature Dish' && (
          <>
            <div>
              <Label htmlFor="dish">Dish</Label>
              <Select key={editingData?.name || 'new'} name="dish" defaultValue={editingData?.dish} required>
                <SelectTrigger>
                  <SelectValue placeholder="Select a dish" />
                </SelectTrigger>
                <SelectContent>
                  {menuProducts?.map((product: any) => (
                    <SelectItem key={product.name} value={product.name}>
                      {product.product_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="display_order">Display Order</Label>
              <NumberInput  name="display_order" defaultValue={editingData?.display_order || 0} />
            </div>
          </>
        )}
        
        {type === 'Testimonial' && (
          <>
            <div>
              <Label htmlFor="customer_name">Customer Name</Label>
              <Input name="customer_name" defaultValue={editingData?.customer_name} required />
            </div>
            <div>
              <Label htmlFor="rating">Rating</Label>
              <Select name="rating" defaultValue={editingData?.rating?.toString() || '5'}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[1, 2, 3, 4, 5].map(rating => (
                    <SelectItem key={rating} value={rating.toString()}>
                      {rating} {rating === 1 ? 'Star' : 'Stars'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="text">Testimonial</Label>
              <Textarea name="text" defaultValue={editingData?.text} required />
            </div>
            <div>
              <Label htmlFor="location">Location (Optional)</Label>
              <Input name="location" defaultValue={editingData?.location} />
            </div>
            <div>
              <Label htmlFor="avatar">Avatar URL (Optional)</Label>
              <Input name="avatar" defaultValue={editingData?.avatar} />
            </div>
            <div>
              <Label htmlFor="display_order">Display Order</Label>
              <NumberInput  name="display_order" defaultValue={editingData?.display_order || 0} />
            </div>
          </>
        )}
        
        {type === 'Member' && (
          <>
            <div>
              <Label htmlFor="member_name">Member Name</Label>
              <Input name="member_name" defaultValue={editingData?.member_name} required />
            </div>
            <div>
              <Label htmlFor="role">Role</Label>
              <Input name="role" defaultValue={editingData?.role} />
            </div>
            <div>
              <Label htmlFor="image">Image URL (Optional)</Label>
              <Input name="image" defaultValue={editingData?.image} />
            </div>
            <div>
              <Label htmlFor="display_order">Display Order</Label>
              <NumberInput  name="display_order" defaultValue={editingData?.display_order || 0} />
            </div>
          </>
        )}
        
        
        {type === 'Instagram Reel' && (
          <>
            <div>
              <Label htmlFor="reel_link">Reel Link</Label>
              <Input name="reel_link" defaultValue={editingData?.reel_link} required />
            </div>
            <div>
              <Label htmlFor="title">Title (Optional)</Label>
              <Input name="title" defaultValue={editingData?.title} />
            </div>
            <div>
              <Label htmlFor="display_order">Display Order</Label>
              <NumberInput  name="display_order" defaultValue={editingData?.display_order || 0} />
            </div>
          </>
        )}
        
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>
            Cancel
          </Button>
          <Button type="submit" disabled={isCreating || isUpdating}>
            {editingData?.name ? 'Update' : 'Create'}
          </Button>
        </div>
      </form>
    )
  }

  if (!selectedRestaurant) {
    return (
      <div className="text-center py-8">
        <p>Please select a restaurant to manage legacy content.</p>
      </div>
    )
  }

  if (contentLoading) {
    return (
      <div className="text-center py-8">
        <p>Loading legacy content...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">Legacy Content Management</h1>
          <p className="text-muted-foreground">Manage your restaurant's story, heritage, and featured content</p>
        </div>
        <Button 
          onClick={handleGenerateLegacy} 
          disabled={isGenerating}
          variant="outline"
          className="gap-2 border-primary/50 hover:border-primary text-primary"
        >
          {isGenerating ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Star className="h-4 w-4 fill-primary" />
          )}
          Generate with AI
        </Button>
      </div>

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
            onSubmit={handleHeroContentSave} className="space-y-4">
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
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="hero_media_upload">Upload Hero Media</Label>
                <div className="flex gap-2 items-start mt-1">
                  <Input 
                    id="hero_media_upload"
                    type="file" 
                    accept={heroData.hero_media_type === 'video' ? 'video/*' : 'image/*'} 
                    onChange={async (e) => {
                      if (e.target.files && e.target.files[0]) {
                        try {
                          const url = await handleFileUpload(e.target.files[0], 'legacy_hero_media')
                          setHeroData(prev => ({ ...prev, hero_media_src: url }))
                          toast.success('Hero media uploaded')
                        } catch (err) {
                          toast.error('Failed to upload hero media')
                        }
                      }
                    }}
                  />
                </div>
                {heroData.hero_media_src && (
                  <p className="text-xs text-muted-foreground mt-2 truncate">Current: {heroData.hero_media_src}</p>
                )}
              </div>
              
              {heroData.hero_media_type === 'video' && (
                <div>
                  <Label htmlFor="hero_fallback_upload">Upload Fallback Image (Optional)</Label>
                  <div className="flex gap-2 items-start mt-1">
                    <Input 
                      id="hero_fallback_upload"
                      type="file" 
                      accept="image/*"
                      onChange={async (e) => {
                        if (e.target.files && e.target.files[0]) {
                          try {
                            const url = await handleFileUpload(e.target.files[0], 'legacy_hero_fallback')
                            setHeroData(prev => ({ ...prev, hero_fallback_image: url }))
                            toast.success('Fallback image uploaded')
                          } catch (err) {
                            toast.error('Failed to upload fallback image')
                          }
                        }
                      }}
                    />
                  </div>
                  {heroData.hero_fallback_image && (
                    <p className="text-xs text-muted-foreground mt-2 truncate">Current: {heroData.hero_fallback_image}</p>
                  )}
                </div>
              )}
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
            <Button type="submit" disabled={isUpdatingLegacy || uploading}>
              {uploading || isUpdatingLegacy ? <Loader2 className="animate-spin h-4 w-4 mr-2" /> : null}
              Save Hero Section
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="grid gap-6">
        {renderSection(
          'Signature Dishes',
          <Star className="h-5 w-5" />,
          signatureDishes || [],
          'Signature Dish',
          'Legacy Signature Dish',
          (item) => {
            const product = menuProducts?.find((p: any) => p.name === item.dish)
            return (
              <div key={item.name} className="flex items-center justify-between p-4 border rounded-lg">
                <div className="flex items-center gap-3">
                  {product?.image ? (
                    <img src={product.image} className="h-12 w-12 rounded-md object-cover" alt={item.dish_name} />
                  ) : (
                    <div className="h-12 w-12 rounded-md bg-muted flex items-center justify-center">
                      <Image className="h-6 w-6 text-muted-foreground" />
                    </div>
                  )}
                  <div>
                    <h4 className="font-semibold">{item.dish_name || product?.product_name || item.dish}</h4>
                    <p className="text-sm text-muted-foreground">Order: {item.display_order}</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => setEditingItem({ ...item, type: 'Signature Dish', doctype: 'Legacy Signature Dish' })}>
                    <Edit2 className="h-4 w-4" />
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => handleDelete('Legacy Signature Dish', item.name, 'Signature Dish')}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )
          }
        )}

        {renderSection(
          'Testimonials',
          <Users className="h-5 w-5" />,
          testimonials || [],
          'Testimonial',
          'Legacy Testimonial',
          (item) => (
            <div key={item.name} className="flex items-center justify-between p-4 border rounded-lg">
              <div>
                <h4 className="font-semibold">{item.customer_name}</h4>
                <div className="flex items-center gap-1 my-1">
                  {[...Array(5)].map((_, i) => (
                    <Star key={i} className={`h-3 w-3 ${i < item.rating ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300'}`} />
                  ))}
                </div>
                <p className="text-sm text-muted-foreground">{item.location}</p>
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setEditingItem({ ...item, type: 'Testimonial', doctype: 'Legacy Testimonial' })}>
                  <Edit2 className="h-4 w-4" />
                </Button>
                <Button size="sm" variant="outline" onClick={() => handleDelete('Legacy Testimonial', item.name, 'Testimonial')}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )
        )}

        {renderSection(
          'Members',
          <Users className="h-5 w-5" />,
          members || [],
          'Member',
          'Legacy Member',
          (item) => (
            <div key={item.name} className="flex items-center justify-between p-4 border rounded-lg">
              <div>
                <h4 className="font-semibold">{item.member_name}</h4>
                <p className="text-sm text-muted-foreground">{item.role}</p>
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setEditingItem({ ...item, type: 'Member', doctype: 'Legacy Member' })}>
                  <Edit2 className="h-4 w-4" />
                </Button>
                <Button size="sm" variant="outline" onClick={() => handleDelete('Legacy Member', item.name, 'Member')}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )
        )}


        {renderSection(
          'Instagram Reels',
          <Instagram className="h-5 w-5" />,
          instagramReels || [],
          'Instagram Reel',
          'Legacy Instagram Reel',
          (item) => (
            <div key={item.name} className="flex items-center justify-between p-4 border rounded-lg">
              <div>
                <h4 className="font-semibold">{item.title || 'Untitled'}</h4>
                <p className="text-sm text-muted-foreground truncate">{item.reel_link}</p>
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setEditingItem({ ...item, type: 'Instagram Reel', doctype: 'Legacy Instagram Reel' })}>
                  <Edit2 className="h-4 w-4" />
                </Button>
                <Button size="sm" variant="outline" onClick={() => handleDelete('Legacy Instagram Reel', item.name, 'Instagram Reel')}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Image className="h-5 w-5" />
            Footer Section
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form 
            key={legacyContent?.name ? `footer-${legacyContent.name}` : 'footer-loading'}
            onSubmit={handleFooterContentSave} className="space-y-4">
            <div>
              <Label htmlFor="footer_media_upload">Upload Footer Media (Image/Video)</Label>
              <div className="flex gap-2 items-start mt-1">
                <Input 
                  id="footer_media_upload"
                  type="file" 
                  accept="image/*,video/*"
                  onChange={async (e) => {
                    if (e.target.files && e.target.files[0]) {
                      try {
                        const url = await handleFileUpload(e.target.files[0], 'legacy_footer_media')
                        setFooterData(prev => ({ ...prev, footer_media_src: url }))
                        toast.success('Footer media uploaded')
                      } catch (err) {
                        toast.error('Failed to upload footer media')
                      }
                    }
                  }}
                />
              </div>
              {footerData.footer_media_src && (
                <p className="text-xs text-muted-foreground mt-2 truncate">Current: {footerData.footer_media_src}</p>
              )}
            </div>

            <div>
              <Label htmlFor="footer_title">Footer Title</Label>
              <Input 
                name="footer_title" 
                value={footerData.footer_title} 
                onChange={(e) => setFooterData(prev => ({ ...prev, footer_title: e.target.value }))}
                placeholder="Ready for Your Next Culinary Adventure?" 
              />
            </div>
            <div>
              <Label htmlFor="footer_description">Footer Description</Label>
              <Textarea 
                name="footer_description" 
                value={footerData.footer_description} 
                onChange={(e) => setFooterData(prev => ({ ...prev, footer_description: e.target.value }))}
                placeholder="Start exploring our menu today..." 
              />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="footer_cta_text">CTA Button Text</Label>
                <Input 
                  name="footer_cta_text" 
                  value={footerData.footer_cta_text} 
                  onChange={(e) => setFooterData(prev => ({ ...prev, footer_cta_text: e.target.value }))}
                  placeholder="Explore Our Menu" 
                />
              </div>
              <div>
                <Label htmlFor="footer_cta_route">CTA Button Route</Label>
                <Input 
                  name="footer_cta_route" 
                  value={footerData.footer_cta_route} 
                  onChange={(e) => setFooterData(prev => ({ ...prev, footer_cta_route: e.target.value }))}
                  placeholder="/main-menu" 
                />
              </div>
            </div>
            
            <Button type="submit" disabled={isUpdatingLegacy || uploading}>
              {uploading || isUpdatingLegacy ? <Loader2 className="animate-spin h-4 w-4 mr-2" /> : null}
              Save Footer Section
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
