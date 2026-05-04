import { useState, useMemo, useEffect } from 'react'
import { useFrappePostCall, useFrappeUpdateDoc, useFrappeDeleteDoc } from '@/lib/frappe'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
// Removed unused Table imports
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Plus, Edit, Trash2, Calendar, Search, Zap, MapPin, Clock, ExternalLink } from 'lucide-react'
import { LockedFeature } from '@/components/FeatureGate/LockedFeature'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { toast } from 'sonner'
import { cn, getFrappeError } from '@/lib/utils'
import { useDataTable } from '@/hooks/useDataTable'
import { FilterCondition } from '@/components/ListFilters'
import { DataPagination } from '@/components/ui/DataPagination'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import { DatePicker } from '@/components/ui/date-picker'
import { TimePicker } from '@/components/ui/time-picker'
import { Textarea } from '@/components/ui/textarea'
import { uploadToR2 } from '@/lib/r2Upload'
import { Upload, X } from 'lucide-react'



export default function Events() {
  const { selectedRestaurant, isGold, isDiamond } = useRestaurant()
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [editingEvent, setEditingEvent] = useState<any>(null)
  const [filterType, setFilterType] = useState<string>('all')
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [eventToDelete, setEventToDelete] = useState<{ name: string; title: string } | null>(null)

  const initialFilters = useMemo(() => {
    if (!selectedRestaurant) return []
    const f: FilterCondition[] = [{ fieldname: 'restaurant', operator: '=', value: selectedRestaurant }]

    if (filterType === 'active') {
      f.push({ fieldname: 'is_active', operator: '=', value: 1 })
    } else if (filterType === 'inactive') {
      f.push({ fieldname: 'is_active', operator: '=', value: 0 })
    }

    return f
  }, [selectedRestaurant, filterType])

  const {
    data: events,
    isLoading,
    mutate,
    page,
    setPage,
    pageSize,
    setPageSize,
    totalCount,
    searchQuery,
    setSearchQuery
  } = useDataTable({
    doctype: 'Event',
    fields: ['name', 'title', 'description', 'category', 'is_active', 'date', 'time', 'location', 'image_src', 'repeat_this_event', 'repeat_till', 'google_maps_link', 'registration_link', 'featured', 'display_order', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'],
    initialFilters,
    searchFields: ['title', 'category', 'description', 'location'],
    orderBy: { field: 'creation', order: 'desc' },
    initialPageSize: 12,
    debugId: `events-${selectedRestaurant}-${filterType}`
  })

  const { call: createEvent } = useFrappePostCall('frappe.client.insert')
  const { updateDoc: updateEvent } = useFrappeUpdateDoc()
  const { deleteDoc: deleteEvent } = useFrappeDeleteDoc()

  const mapFormDataToBackend = (formData: any) => {
    const days = formData.recurring_days ? formData.recurring_days.split(',') : []
    return {
      ...formData,
      repeat_this_event: formData.repeat_this_event ? 1 : 0,
      repeat_on: formData.repeat_this_event ? 'Weekly' : '',
      monday: days.includes('Mon') ? 1 : 0,
      tuesday: days.includes('Tue') ? 1 : 0,
      wednesday: days.includes('Wed') ? 1 : 0,
      thursday: days.includes('Thu') ? 1 : 0,
      friday: days.includes('Fri') ? 1 : 0,
      saturday: days.includes('Sat') ? 1 : 0,
      sunday: days.includes('Sun') ? 1 : 0,
    }
  }

  const handleCreateEvent = async (formData: any) => {
    const mappedData = mapFormDataToBackend(formData)
    try {
      await createEvent({
        doc: {
          doctype: 'Event',
          ...mappedData,
          restaurant: selectedRestaurant,
        }
      })
      toast.success('Event created successfully')
      
      // Clear filters and search to show the new event instantly
      setSearchQuery('')
      setFilterType('all')
      
      mutate()
      setIsCreateDialogOpen(false)
    } catch (error: any) {
      toast.error('Failed to launch event', { description: getFrappeError(error) })
    }
  }

  const handleUpdateEvent = async (name: string, formData: any) => {
    const mappedData = mapFormDataToBackend(formData)
    try {
      await updateEvent('Event', name, mappedData)
      toast.success('Event details updated')
      mutate()
      setEditingEvent(null)
    } catch (error: any) {
      toast.error('Update failed', { description: getFrappeError(error) })
    }
  }

  const handleDeleteEvent = async () => {
    if (!eventToDelete) return
    try {
      await deleteEvent('Event', eventToDelete.name)
      toast.success('Event deleted successfully')
      mutate()
      setDeleteDialogOpen(false)
      setEventToDelete(null)
    } catch (error: any) {
      toast.error('Deletion failed', { description: getFrappeError(error) })
    }
  }

  const openDeleteDialog = (name: string, title: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setEventToDelete({ name, title })
    setDeleteDialogOpen(true)
  }


  if (!selectedRestaurant) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-center p-8">
        <div className="h-20 w-20 bg-muted rounded-full flex items-center justify-center mb-4">
          <Calendar className="h-10 w-10 text-muted-foreground/30" />
        </div>
        <h3 className="text-xl font-semibold mb-2">Select a Restaurant</h3>
        <p className="text-muted-foreground max-w-sm">Pick a restaurant to start managing floor events and special occasions.</p>
      </div>
    )
  }

  if (!isGold && !isDiamond) {
    return <LockedFeature feature="events" requiredPlan={['GOLD']} />
  }

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4">
        <div className="space-y-1">
          <h2 className="text-2xl font-bold tracking-tight">Events</h2>
          <p className="text-muted-foreground text-sm flex items-center gap-2">
            <Calendar className="h-3.5 w-3.5" />
            Manage your restaurant events and special occasions
          </p>
        </div>
        <Button onClick={() => setIsCreateDialogOpen(true)} className="rounded-xl h-11 px-6 shadow-lg shadow-primary/20 bg-black text-white hover:bg-black/90">
          <Plus className="h-4 w-4 mr-2" />
          Create Event
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <CardTitle>Events</CardTitle>
              <CardDescription>
                Manage your restaurant events and special occasions
              </CardDescription>
            </div>
            <div className="flex flex-col sm:flex-row items-center gap-3">
              <div className="relative w-full sm:w-64">
                <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search events..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 h-9"
                />
              </div>
              <Select value={filterType} onValueChange={setFilterType}>
                <SelectTrigger className="h-9 w-[120px]">
                  <SelectValue placeholder="All" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading && !events.length ? (
            <div className="py-20 flex justify-center">
              <div className="animate-spin h-6 w-6 border-2 border-primary border-t-transparent rounded-full" />
            </div>
          ) : !events || events.length === 0 ? (
            <div className="py-20 text-center text-muted-foreground flex flex-col items-center gap-4">
              <Calendar className="h-12 w-12 text-muted-foreground/20" />
              <div>
                <p className="font-medium text-foreground">No events found</p>
                <p className="text-sm">Try adjusting your search or filters</p>
              </div>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {events.map((event: any) => {
                  const eventDate = new Date(event.date)
                  const isRecurring = !!event.repeat_this_event
                  
                  return (
                    <div
                      key={event.name}
                      className={cn(
                        "group relative flex flex-col rounded-2xl border bg-card shadow-sm transition-all hover:shadow-md overflow-hidden",
                        !event.is_active && "opacity-75 grayscale-[0.5]"
                      )}
                    >
                      {/* Thumbnail Image */}
                      <div className="aspect-[16/9] w-full overflow-hidden bg-muted relative">
                        {event.image_src ? (
                          <img
                            src={event.image_src}
                            alt={event.title}
                            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                          />
                        ) : (
                          <div className="h-full w-full flex items-center justify-center text-muted-foreground/20">
                            <Calendar className="h-12 w-12" />
                          </div>
                        )}
                        
                        {/* Category Badge */}
                        <div className="absolute top-3 left-3">
                          <Badge className="bg-black/60 backdrop-blur-md text-white border-none hover:bg-black/70">
                            {event.category || 'Event'}
                          </Badge>
                        </div>

                        {/* Recurring Indicator */}
                        {isRecurring && (
                          <div className="absolute top-3 right-3">
                            <Badge variant="secondary" className="bg-primary/90 text-primary-foreground shadow-sm">
                              <Zap className="h-3 w-3 mr-1" /> Recurring
                            </Badge>
                          </div>
                        )}
                      </div>

                      <div className="flex flex-col flex-1 p-5 gap-4">
                        {/* Title + Toggle */}
                        <div className="flex items-start justify-between gap-3">
                          <div className="space-y-1 min-w-0">
                            <h3 className="font-bold text-lg leading-tight truncate group-hover:text-primary transition-colors">
                              {event.title}
                            </h3>
                            <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-medium">
                              <Calendar className="h-3.5 w-3.5" />
                              {eventDate.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
                            </div>
                          </div>
                          
                          <div className="flex flex-col items-end gap-1 shrink-0">
                            <Switch
                              checked={!!event.is_active}
                              onCheckedChange={async (checked) => {
                                try {
                                  await updateEvent('Event', event.name, { is_active: checked ? 1 : 0 })
                                  toast.success(`Event ${checked ? 'activated' : 'paused'}`)
                                  mutate()
                                } catch (e) {
                                  toast.error('Failed to update status')
                                }
                              }}
                              className="data-[state=checked]:bg-green-500"
                            />
                            <span className={cn(
                              "text-[10px] font-bold uppercase tracking-wider",
                              event.is_active ? "text-green-600" : "text-muted-foreground"
                            )}>
                              {event.is_active ? 'Active' : 'Inactive'}
                            </span>
                          </div>
                        </div>

                        {/* Description */}
                        {event.description && (
                          <p className="text-sm text-muted-foreground line-clamp-2 leading-relaxed">
                            {event.description}
                          </p>
                        )}

                        {/* Info Grid */}
                        <div className="grid grid-cols-1 gap-2 mt-auto">
                          <div className="flex items-center gap-2 text-sm text-foreground/80">
                            <Clock className="h-4 w-4 text-muted-foreground" />
                            <span className="font-medium">{event.time.split(':').slice(0, 2).join(':')}</span>
                          </div>
                          {event.location && (
                            <div className="flex items-center gap-2 text-sm text-foreground/80">
                              <MapPin className="h-4 w-4 text-muted-foreground" />
                              <span className="truncate">{event.location}</span>
                            </div>
                          )}
                        </div>

                        {/* Links if available */}
                        {(event.google_maps_link || event.registration_link) && (
                          <div className="flex gap-2">
                            {event.google_maps_link && (
                              <Button variant="outline" size="sm" className="h-8 px-2 text-[11px] rounded-lg" asChild>
                                <a href={event.google_maps_link} target="_blank" rel="noopener noreferrer">
                                  <MapPin className="h-3 w-3 mr-1" /> Maps
                                </a>
                              </Button>
                            )}
                            {event.registration_link && (
                              <Button variant="outline" size="sm" className="h-8 px-2 text-[11px] rounded-lg" asChild>
                                <a href={event.registration_link} target="_blank" rel="noopener noreferrer">
                                  <ExternalLink className="h-3 w-3 mr-1" /> Register
                                </a>
                              </Button>
                            )}
                          </div>
                        )}

                        <div className="pt-4 border-t flex items-center justify-between gap-2">
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => setEditingEvent(event)}
                            className="flex-1 h-9 rounded-xl font-semibold"
                          >
                            <Edit className="h-3.5 w-3.5 mr-2" />
                            Manage
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-9 w-9 rounded-xl text-destructive hover:bg-destructive/10"
                            onClick={(e) => openDeleteDialog(event.name, event.title, e)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>

              <div className="mt-8">
                <DataPagination
                  currentPage={page}
                  totalCount={totalCount}
                  pageSize={pageSize}
                  onPageChange={setPage}
                  onPageSizeChange={setPageSize}
                  isLoading={isLoading}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <EventDialog
        open={isCreateDialogOpen}
        onClose={() => setIsCreateDialogOpen(false)}
        onSave={handleCreateEvent}
      />

      <EventDialog
        open={!!editingEvent}
        onClose={() => setEditingEvent(null)}
        event={editingEvent}
        onSave={(data: any) => handleUpdateEvent(editingEvent.name, data)}
      />

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Event?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete <span className="font-bold text-foreground">"{eventToDelete?.title}"</span>? 
              This action is permanent and cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setEventToDelete(null)}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteEvent}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete Event
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function EventDialog({ open, onClose, event, onSave }: any) {
  const { selectedRestaurant } = useRestaurant()
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    category: '',
    is_active: true,
    date: '',
    repeat_till: '',
    time: '19:00:00',
    end_time: '23:00:00',
    location: '',
    image_src: '',
    repeat_this_event: false,
    recurring_days: '',
    google_maps_link: '',
    registration_link: '',
    featured: false,
    display_order: 0,
  })
  const [isUploading, setIsUploading] = useState(false)

  useEffect(() => {
    if (event) {
      // Map backend individual day flags back to the dashboard's comma-separated string for UI
      const days = []
      if (event.monday) days.push('Mon')
      if (event.tuesday) days.push('Tue')
      if (event.wednesday) days.push('Wed')
      if (event.thursday) days.push('Thu')
      if (event.friday) days.push('Fri')
      if (event.saturday) days.push('Sat')
      if (event.sunday) days.push('Sun')

      setFormData({
        title: event.title || '',
        description: event.description || '',
        category: event.category || '',
        is_active: event.is_active ?? true,
        date: event.date || '',
        repeat_till: event.repeat_till || '',
        time: event.time || '19:00:00',
        end_time: event.end_time || '23:00:00',
        location: event.location || '',
        image_src: event.image_src || '',
        repeat_this_event: !!event.repeat_this_event,
        recurring_days: days.join(','),
        google_maps_link: event.google_maps_link || '',
        registration_link: event.registration_link || '',
        featured: !!event.featured,
        display_order: event.display_order || 0,
      })
    } else {
      setFormData({
        title: '',
        description: '',
        category: '',
        is_active: true,
        date: '',
        repeat_till: '',
        time: '19:00:00',
        end_time: '23:00:00',
        location: '',
        image_src: '',
        repeat_this_event: false,
        recurring_days: '',
        google_maps_link: '',
        registration_link: '',
        featured: false,
        display_order: 0,
      })
    }
  }, [event, open])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave(formData)
  }

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !selectedRestaurant) return

    setIsUploading(true)
    try {
      const result = await uploadToR2({
        ownerDoctype: 'Restaurant',
        ownerName: selectedRestaurant,
        mediaRole: 'event_image',
        file,
      })
      setFormData({ ...formData, image_src: result.primary_url || '' })
      toast.success('Image uploaded successfully')
    } catch (error: any) {
      toast.error(error?.message || 'Failed to upload image')
    } finally {
      setIsUploading(false)
      if (e.target) e.target.value = ''
    }
  }

  const toggleDay = (day: string) => {
    const days = formData.recurring_days ? formData.recurring_days.split(',') : []
    const newDays = days.includes(day) ? days.filter(d => d !== day) : [...days, day]
    setFormData({ ...formData, recurring_days: newDays.join(',') })
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{event ? 'Edit Event' : 'Add New Event'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-6 py-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2 col-span-2">
              <Label htmlFor="title">Event Title</Label>
              <Input
                id="title"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                placeholder="Saturday Night Party"
                required
              />
            </div>

            <div className="space-y-2 col-span-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Describe the event details, activities, etc."
                className="min-h-[100px]"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="category">Category</Label>
              <Input
                id="category"
                value={formData.category}
                onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                placeholder="e.g. Live Music, Brunch..."
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="is_active">Status</Label>
              <Select
                value={formData.is_active ? 'active' : 'inactive'}
                onValueChange={(val) => setFormData({ ...formData, is_active: val === 'active' })}
              >
                <SelectTrigger id="is_active">
                  <SelectValue placeholder="Select Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="date">Start Date</Label>
              <DatePicker
                value={formData.date}
                onChange={(val) => setFormData({ ...formData, date: val })}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="repeat_till">End Date (Optional)</Label>
              <DatePicker
                value={formData.repeat_till}
                onChange={(val) => setFormData({ ...formData, repeat_till: val })}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="time">Start Time</Label>
              <TimePicker
                value={formData.time}
                onChange={(e) => setFormData({ ...formData, time: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="end_time">End Time</Label>
              <TimePicker
                value={formData.end_time}
                onChange={(e) => setFormData({ ...formData, end_time: e.target.value })}
              />
            </div>

            <div className="space-y-2 col-span-2">
              <Label htmlFor="location">Location</Label>
              <Input
                id="location"
                value={formData.location}
                onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                placeholder="Main Hall / Rooftop / Garden"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="google_maps_link">Google Maps URL</Label>
              <Input
                id="google_maps_link"
                value={formData.google_maps_link}
                onChange={(e) => setFormData({ ...formData, google_maps_link: e.target.value })}
                placeholder="https://maps.google.com/..."
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="registration_link">Registration Link (Optional)</Label>
              <Input
                id="registration_link"
                value={formData.registration_link}
                onChange={(e) => setFormData({ ...formData, registration_link: e.target.value })}
                placeholder="https://eventbrite.com/..."
              />
            </div>

            <div className="flex items-center gap-4 pt-2 col-span-2">
              <div className="flex items-center space-x-2">
                <Switch
                  id="featured"
                  checked={formData.featured}
                  onCheckedChange={(val) => setFormData({ ...formData, featured: val })}
                />
                <Label htmlFor="featured">Featured Event</Label>
              </div>

              <div className="flex items-center space-x-2 ml-auto">
                <Label htmlFor="display_order">Display Order</Label>
                <Input
                  id="display_order"
                  type="number"
                  className="w-20"
                  value={formData.display_order}
                  onChange={(e) => setFormData({ ...formData, display_order: parseInt(e.target.value) || 0 })}
                />
              </div>
            </div>

            <div className="space-y-2 col-span-2">
              <Label>Event Image</Label>
              {formData.image_src ? (
                <div className="relative group rounded-xl overflow-hidden aspect-video border bg-muted">
                  <img src={formData.image_src} alt="Preview" className="w-full h-full object-cover transition-transform group-hover:scale-105" />
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      onClick={() => setFormData({ ...formData, image_src: '' })}
                      className="rounded-full h-8 w-8 p-0"
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="relative">
                  <input
                    type="file"
                    id="event-image-upload"
                    accept="image/*"
                    onChange={handleImageUpload}
                    disabled={isUploading}
                    className="hidden"
                  />
                  <label
                    htmlFor="event-image-upload"
                    className={cn(
                      "flex flex-col items-center justify-center gap-3 py-10 border-2 border-dashed rounded-xl cursor-pointer transition-all hover:bg-accent hover:border-primary/50",
                      isUploading && "opacity-50 pointer-events-none"
                    )}
                  >
                    <div className="p-3 bg-primary/10 rounded-full">
                      {isUploading ? (
                        <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full" />
                      ) : (
                        <Upload className="h-5 w-5 text-primary" />
                      )}
                    </div>
                    <div className="text-center">
                      <p className="text-sm font-semibold">{isUploading ? 'Uploading Image...' : 'Upload Event Image'}</p>
                      <p className="text-xs text-muted-foreground mt-1">Recommended size: 1200x675 (16:9)</p>
                    </div>
                  </label>
                </div>
              )}
            </div>
          </div>

          {/* Recurring Section */}
          <div className="space-y-4 border-t pt-4">
            <div className="flex items-center justify-between col-span-2 pt-2">
              <div className="space-y-0.5">
                <Label>Recurring Event</Label>
                <p className="text-[10px] text-muted-foreground">Repeat this event weekly</p>
              </div>
              <Switch
                checked={formData.repeat_this_event}
                onCheckedChange={(val) => setFormData({ ...formData, repeat_this_event: val })}
              />
            </div>

            {formData.repeat_this_event && (
              <div className="animate-in fade-in slide-in-from-top-2 duration-300 space-y-4">
                <div className="space-y-2">
                  <Label>Days of the week</Label>
                  <div className="flex flex-wrap gap-3">
                    {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(day => (
                      <div key={day} className="flex items-center space-x-2">
                        <Checkbox
                          id={`day-${day}`}
                          checked={formData.recurring_days?.includes(day)}
                          onCheckedChange={() => toggleDay(day)}
                        />
                        <Label htmlFor={`day-${day}`} className="text-xs font-normal">{day}</Label>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="pt-4 border-t">
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit">
              {event ? 'Update Event' : 'Create Event'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
