import { useState, useEffect } from 'react'
import { Calendar, Users, Clock, CheckCircle, XCircle, AlertCircle, Search, ChevronLeft, ChevronRight, Phone, StickyNote, ChevronDown } from 'lucide-react'
import { useFrappePostCall } from '@/lib/frappe'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { toast } from 'sonner'
import CalendarPicker from '@/components/CalendarPicker'
import { LockedFeature } from '@/components/FeatureGate/LockedFeature'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { History, LayoutDashboard } from 'lucide-react'

interface Booking {
  id: string
  bookingNumber: string
  numberOfDiners: number
  date: string
  timeSlot: string
  status: 'pending' | 'confirmed' | 'rejected' | 'cancelled' | 'completed' | 'no-show'
  customerName?: string
  customerPhone?: string
  customerEmail?: string
  notes?: string
  assignedTable?: string
  createdAt: string
  confirmedAt?: string
}

const SELECTED_DATE_KEY = 'flamezo_backend-bookings-selected-date'

export default function Bookings() {
  const { selectedRestaurant, isGold, isSilver } = useRestaurant()
  const [bookings, setBookings] = useState<Booking[]>([])
  const [loading, setLoading] = useState(true)
  const [showPastBookings, setShowPastBookings] = useState(false)
  const [selectedBooking, setSelectedBooking] = useState<Booking | null>(null)
  const [selectedDate, setSelectedDate] = useState(() => {
    // Initialize from localStorage if available
    try {
      const saved = localStorage.getItem(SELECTED_DATE_KEY)
      return saved ? new Date(saved) : new Date()
    } catch {
      return new Date()
    }
  })
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [showCalendarPicker, setShowCalendarPicker] = useState(false)
  const [monthlyBookings, setMonthlyBookings] = useState<{[key: string]: number}>({})

  const { call: fetchBookings } = useFrappePostCall('flamezo_backend.flamezo.api.bookings.get_admin_bookings')
  const { call: confirmBookingAPI } = useFrappePostCall('flamezo_backend.flamezo.api.bookings.confirm_booking')
  const { call: rejectBookingAPI } = useFrappePostCall('flamezo_backend.flamezo.api.bookings.reject_booking')
  const { call: markCompletedAPI } = useFrappePostCall('flamezo_backend.flamezo.api.bookings.mark_completed')
  const { call: markNoShowAPI } = useFrappePostCall('flamezo_backend.flamezo.api.bookings.mark_no_show')

  // Save selected date to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(SELECTED_DATE_KEY, selectedDate.toISOString())
    } catch {
      // Ignore errors
    }
  }, [selectedDate])

  useEffect(() => {
    if (selectedRestaurant) {
      loadBookings()
      if (!searchQuery) loadMonthlyBookings()
    }
  }, [selectedRestaurant, selectedDate, statusFilter, showPastBookings, searchQuery])

  // Format date without timezone conversion
  const formatDateForAPI = (date: Date): string => {
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }

  const loadBookings = async () => {
    if (!selectedRestaurant) return
    
    try {
      setLoading(true)
      const dateStr = formatDateForAPI(selectedDate)
      let date_from = dateStr
      let date_to = dateStr

      if (showPastBookings) {
        // Show last 30 days plus any future bookings
        const thirtyDaysAgo = new Date()
        thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30)
        date_from = formatDateForAPI(thirtyDaysAgo)
        
        const nextYear = new Date()
        nextYear.setFullYear(nextYear.getFullYear() + 1)
        date_to = formatDateForAPI(nextYear)
      }

      const response = await fetchBookings({
        restaurant_id: selectedRestaurant,
        date_from,
        date_to,
        status: statusFilter === 'all' ? undefined : statusFilter,
        search_query: searchQuery || undefined,
        limit: 200
      })
      
      
      
      // Handle Frappe's response wrapper - response can be wrapped in 'message'
      const data = response?.message?.data || response?.data
      
      if (data?.bookings) {
        setBookings(data.bookings)
      } else {
        setBookings([])
      }
    } catch (error) {
      toast.error('Failed to load bookings')
      setBookings([])
    } finally {
      setLoading(false)
    }
  }

  const loadMonthlyBookings = async () => {
    if (!selectedRestaurant) return
    
    try {
      const startOfMonth = new Date(selectedDate.getFullYear(), selectedDate.getMonth(), 1)
      const endOfMonth = new Date(selectedDate.getFullYear(), selectedDate.getMonth() + 1, 0)
      
      const response = await fetchBookings({
        restaurant_id: selectedRestaurant,
        date_from: formatDateForAPI(startOfMonth),
        date_to: formatDateForAPI(endOfMonth),
        limit: 1000
      })
      
      // Handle Frappe's response wrapper
      const data = response?.message?.data || response?.data
      
      if (data?.bookings) {
        const bookingsByDate: {[key: string]: number} = {}
        data.bookings.forEach((booking: Booking) => {
          const dateKey = booking.date
          bookingsByDate[dateKey] = (bookingsByDate[dateKey] || 0) + 1
        })
        setMonthlyBookings(bookingsByDate)
      }
    } catch (error) {
      console.error('Failed to load monthly bookings:', error)
    }
  }

  // Parse time slot to minutes for sorting
  const parseTimeSlot = (timeSlot: string): number => {
    const match = timeSlot.match(/(\d+):(\d+)\s*(AM|PM)/i)
    if (!match) return 0
    let hours = parseInt(match[1])
    const minutes = parseInt(match[2])
    const period = match[3].toUpperCase()
    if (period === 'PM' && hours !== 12) hours += 12
    if (period === 'AM' && hours === 12) hours = 0
    return hours * 60 + minutes
  }

  const filteredBookings = [...bookings].sort((a, b) => {
      // Sort by time slot (earliest first)
      const timeA = parseTimeSlot(a.timeSlot)
      const timeB = parseTimeSlot(b.timeSlot)
      return timeA - timeB
    })

  const changeDate = (days: number) => {
    const newDate = new Date(selectedDate)
    newDate.setDate(newDate.getDate() + days)
    setSelectedDate(newDate)
  }

  const formatDate = (date: Date) => {
    return date.toLocaleDateString('en-US', { 
      weekday: 'long', 
      year: 'numeric', 
      month: 'long', 
      day: 'numeric' 
    })
  }

  const handleStatusChange = async (bookingId: string, newStatus: string) => {
    if (!selectedRestaurant) return

    try {
      let response
      
      switch (newStatus) {
        case 'confirmed':
          response = await confirmBookingAPI({
            booking_id: bookingId,
            restaurant_id: selectedRestaurant
          })
          break
        case 'rejected':
          response = await rejectBookingAPI({
            booking_id: bookingId,
            restaurant_id: selectedRestaurant,
            reason: 'Rejected by staff'
          })
          break
        case 'completed':
          response = await markCompletedAPI({
            booking_id: bookingId,
            restaurant_id: selectedRestaurant
          })
          break
        case 'no-show':
          response = await markNoShowAPI({
            booking_id: bookingId,
            restaurant_id: selectedRestaurant
          })
          break
        default:
          return
      }

      const data = response?.message?.data || response?.data
      
      if (data || response?.success) {
        toast.success(`Booking status updated to ${newStatus}`)
        // Reload bookings to reflect the change
        await loadBookings()
        await loadMonthlyBookings()
      } else {
        toast.error('Failed to update booking status')
      }
    } catch (error) {
      console.error('Error updating status:', error)
      toast.error('Failed to update booking status')
    }
  }

  const stats = {
    total: filteredBookings.length,
    pending: filteredBookings.filter(b => b.status === 'pending').length,
    confirmed: filteredBookings.filter(b => b.status === 'confirmed').length,
    totalDiners: filteredBookings.reduce((sum, b) => sum + b.numberOfDiners, 0)
  }

  if (!selectedRestaurant) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground">Please select a restaurant to view bookings</p>
        </div>
      </div>
    )
  }

  if (isSilver) {
    return <LockedFeature feature="table_booking" requiredPlan={['GOLD', 'GOLD']} />
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Table Bookings</h1>
        <p className="text-muted-foreground mt-1">Manage and track all restaurant reservations</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg p-4 border border-blue-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-blue-600">Total Bookings</p>
              <p className="text-2xl font-bold text-blue-900 mt-1">{stats.total}</p>
            </div>
            <Calendar className="w-8 h-8 text-blue-500" />
          </div>
        </div>
        <div className="bg-gradient-to-br from-yellow-50 to-yellow-100 rounded-lg p-4 border border-yellow-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-yellow-600">Pending</p>
              <p className="text-2xl font-bold text-yellow-900 mt-1">{stats.pending}</p>
            </div>
            <Clock className="w-8 h-8 text-yellow-500" />
          </div>
        </div>
        <div className="bg-gradient-to-br from-green-50 to-green-100 rounded-lg p-4 border border-green-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-green-600">Confirmed</p>
              <p className="text-2xl font-bold text-green-900 mt-1">{stats.confirmed}</p>
            </div>
            <CheckCircle className="w-8 h-8 text-green-500" />
          </div>
        </div>
        <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-lg p-4 border border-purple-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-purple-600">Total Diners</p>
              <p className="text-2xl font-bold text-purple-900 mt-1">{stats.totalDiners}</p>
            </div>
            <Users className="w-8 h-8 text-purple-500" />
          </div>
        </div>
      </div>

      {/* Filters and Date Navigation */}
      <div className="bg-card rounded-lg border p-4">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button 
                variant={showPastBookings ? "default" : "outline"} 
                className="gap-2"
                onClick={() => setShowPastBookings(!showPastBookings)}
              >
                {showPastBookings ? (
                  <LayoutDashboard className="w-4 h-4" />
                ) : (
                  <History className="w-4 h-4" />
                )}
                {showPastBookings ? "Show Daily View" : "Past Bookings"}
              </Button>

            {!showPastBookings && (
              <div className="flex items-center gap-3">
                <Button variant="outline" size="icon" onClick={() => changeDate(-1)}>
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <Button
                  variant="outline"
                  className="min-w-[280px] justify-center"
                  onClick={() => setShowCalendarPicker(true)}
                >
                  <Calendar className="w-4 h-4 mr-2" />
                  <span className="font-semibold">{formatDate(selectedDate)}</span>
                </Button>
                <Button variant="outline" size="icon" onClick={() => changeDate(1)}>
                  <ChevronRight className="w-4 h-4" />
                </Button>
                <Button variant="outline" onClick={() => setSelectedDate(new Date())}>
                  Today
                </Button>
              </div>
            )}
          </div>

          <div className="flex items-center gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Search bookings..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Filter by status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="confirmed">Confirmed</SelectItem>
                <SelectItem value="rejected">Rejected</SelectItem>
                <SelectItem value="completed">Completed</SelectItem>
                <SelectItem value="no-show">No Show</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* Bookings Display */}
      <div>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
          </div>
        ) : filteredBookings.length === 0 ? (
          <div className="bg-card rounded-lg border p-12 text-center">
            <Calendar className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground text-lg">No bookings found for this date</p>
            <p className="text-sm text-muted-foreground mt-2">
              Try selecting a different date or adjusting your filters
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredBookings.map((booking) => (
              <div 
                key={booking.id} 
                className="bg-card rounded-lg border p-4 hover:shadow-md transition-shadow cursor-pointer border-l-4 border-l-primary/30"
                onClick={() => setSelectedBooking(booking)}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <div className="flex flex-col">
                        <h3 className="font-bold text-lg text-foreground">{booking.customerName || 'Guest'}</h3>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-xs font-mono text-muted-foreground uppercase tracking-wider bg-muted px-1.5 py-0.5 rounded">#{booking.bookingNumber}</span>
                          {showPastBookings && (
                             <span className="text-xs font-medium text-primary/80">{booking.date}</span>
                          )}
                        </div>
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                          <button className={`px-3 py-1.5 rounded-md text-sm font-semibold flex items-center gap-1.5 hover:opacity-80 transition-opacity ${
                            booking.status === 'confirmed' ? 'bg-green-100 text-green-800' :
                            booking.status === 'pending' ? 'bg-yellow-100 text-yellow-800' :
                            booking.status === 'rejected' ? 'bg-red-100 text-red-800' :
                            booking.status === 'completed' ? 'bg-blue-100 text-blue-800' :
                            booking.status === 'no-show' ? 'bg-orange-100 text-orange-800' :
                            'bg-gray-100 text-gray-800'
                          }`}>
                            {booking.status}
                            <ChevronDown className="w-4 h-4" />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start">
                          {booking.status === 'pending' && (
                            <>
                              <DropdownMenuItem onClick={() => handleStatusChange(booking.id, 'confirmed')}>
                                <CheckCircle className="w-4 h-4 mr-2 text-green-600" />
                                Confirm
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => handleStatusChange(booking.id, 'rejected')}>
                                <XCircle className="w-4 h-4 mr-2 text-red-600" />
                                Reject
                              </DropdownMenuItem>
                            </>
                          )}
                          {booking.status === 'confirmed' && (
                            <>
                              <DropdownMenuItem onClick={() => handleStatusChange(booking.id, 'completed')}>
                                <CheckCircle className="w-4 h-4 mr-2 text-blue-600" />
                                Mark Completed
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => handleStatusChange(booking.id, 'no-show')}>
                                <AlertCircle className="w-4 h-4 mr-2 text-orange-600" />
                                Mark No-Show
                              </DropdownMenuItem>
                            </>
                          )}
                          {(booking.status === 'rejected' || booking.status === 'completed' || booking.status === 'no-show') && (
                            <DropdownMenuItem disabled className="text-muted-foreground">
                              No actions available
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <Clock className="w-4 h-4" />
                        <span>{booking.timeSlot}</span>
                      </div>
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <Users className="w-4 h-4" />
                        <span>{booking.numberOfDiners} diners</span>
                      </div>
                      {booking.customerPhone && (
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <Phone className="w-4 h-4" />
                          <span>{booking.customerPhone}</span>
                        </div>
                      )}
                    </div>
                    {booking.notes && (
                      <div className="mt-2 flex items-start gap-2 text-sm text-muted-foreground">
                        <StickyNote className="w-4 h-4 mt-0.5" />
                        <span>{booking.notes}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Booking Details Modal */}
      <Dialog open={!!selectedBooking} onOpenChange={(open) => !open && setSelectedBooking(null)}>
        <DialogContent className="sm:max-w-[450px] p-0 overflow-hidden border-none shadow-2xl">
          <div className="bg-primary/5 p-6 border-b border-primary/10">
            <DialogHeader>
              <div className="flex items-center justify-between">
                <DialogTitle className="text-2xl font-bold flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                    <Users className="w-5 h-5 text-primary" />
                  </div>
                  Booking Details
                </DialogTitle>
                <Badge variant="outline" className={`px-2.5 py-0.5 uppercase text-[10px] font-bold tracking-widest ${
                  selectedBooking?.status === 'confirmed' ? 'bg-green-50 text-green-700 border-green-200' :
                  selectedBooking?.status === 'pending' ? 'bg-yellow-50 text-yellow-700 border-yellow-200' :
                  'bg-muted text-muted-foreground border-muted'
                }`}>
                  {selectedBooking?.status}
                </Badge>
              </div>
            </DialogHeader>
          </div>
          
          <div className="p-6 space-y-6">
            <div className="grid grid-cols-2 gap-6">
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Customer Name</p>
                <p className="text-base font-semibold">{selectedBooking?.customerName || 'Guest'}</p>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Phone Number</p>
                <p className="text-base font-semibold flex items-center gap-2">
                  <Phone className="w-3.5 h-3.5 text-primary/60" />
                  {selectedBooking?.customerPhone || 'Not provided'}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Reservation</p>
                <p className="text-base font-semibold flex items-center gap-2">
                  <Calendar className="w-3.5 h-3.5 text-primary/60" />
                  {selectedBooking?.date}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Time Slot</p>
                <p className="text-base font-semibold flex items-center gap-2">
                  <Clock className="w-3.5 h-3.5 text-primary/60" />
                  {selectedBooking?.timeSlot}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Party Size</p>
                <p className="text-base font-semibold flex items-center gap-2">
                  <Users className="w-3.5 h-3.5 text-primary/60" />
                  {selectedBooking?.numberOfDiners} Diners
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Booking ID</p>
                <p className="font-mono text-sm text-muted-foreground">#{selectedBooking?.bookingNumber}</p>
              </div>
            </div>

            {selectedBooking?.notes && (
              <div className="space-y-2 pt-4 border-t border-muted">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider flex items-center gap-1.5">
                  <StickyNote className="w-3 h-3" />
                  Special Notes
                </p>
                <div className="bg-muted/50 p-3 rounded-lg text-sm italic text-muted-foreground leading-relaxed">
                  "{selectedBooking.notes}"
                </div>
              </div>
            )}
          </div>
          
          <div className="p-4 bg-muted/20 flex justify-end">
            <Button variant="ghost" size="sm" onClick={() => setSelectedBooking(null)}>
              Close Details
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Calendar Picker Modal */}
      <CalendarPicker
        isOpen={showCalendarPicker}
        onClose={() => setShowCalendarPicker(false)}
        selectedDate={selectedDate}
        onSelectDate={(date) => {
          setSelectedDate(date)
          setShowCalendarPicker(false)
        }}
        bookingsByDate={monthlyBookings}
      />
    </div>
  )
}
