import { useState, useEffect } from 'react'
import { Trophy, Calendar, Clock, CheckCircle, XCircle, AlertCircle, Search, ChevronLeft, ChevronRight, Phone, Plus, Trash2, Edit2, ChevronDown } from 'lucide-react'
import { useFrappePostCall } from '@/lib/frappe'
import { useOutlet } from '@/contexts/OutletContext'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'
import CalendarPicker from '@/components/CalendarPicker'
import { useConfirm } from '@/hooks/useConfirm'
import { History, LayoutDashboard } from 'lucide-react'

interface Court {
  id: string
  name: string
  sport_type: string
  slot_duration_minutes: number
  price_per_slot: number
  consumer_fee: number
  opening_time: string
  closing_time: string
  available_days: string
  advance_booking_days: number
}

interface CourtBooking {
  id: string
  restaurant: string
  court: string
  court_name: string
  sport_type: string
  booking_date: string
  start_time: string
  end_time: string
  customer_name: string
  customer_phone: string
  notes: string
  slot_price: number
  consumer_fee: number
  payment_status: string
  status: string
  completed_at: string | null
}

const COURT_SPORTS = ['Badminton', 'Futsal', 'Football', 'Basketball', 'Tennis', 'Squash', 'Cricket Net', 'Volleyball', 'Pickleball', 'Table Tennis']
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const SELECTED_DATE_KEY = 'flamezo_backend-court-bookings-selected-date'

const DEFAULT_COURT_DATA = {
  court_name: '',
  sport_type: 'Badminton',
  slot_duration_minutes: 60,
  price_per_slot: 0,
  consumer_fee: 20,
  opening_time: '06:00',
  closing_time: '22:00',
  available_days: 'Mon,Tue,Wed,Thu,Fri,Sat,Sun',
  advance_booking_days: 7,
  is_active: 1,
}

export default function CourtsPage() {
  const { selectedOutlet } = useOutlet()
  const { confirm, ConfirmDialogComponent } = useConfirm()

  const [activeTab, setActiveTab] = useState<'bookings' | 'courts'>('bookings')

  // ── Courts state ─────────────────────────────────────────────────────────
  const [courts, setCourts] = useState<Court[]>([])
  const [courtsLoading, setCourtsLoading] = useState(true)
  const [courtFormOpen, setCourtFormOpen] = useState(false)
  const [editingCourt, setEditingCourt] = useState<Court | null>(null)
  const [courtData, setCourtData] = useState({ ...DEFAULT_COURT_DATA })
  const [courtSaving, setCourtSaving] = useState(false)

  // ── Bookings state ───────────────────────────────────────────────────────
  const [bookings, setBookings] = useState<CourtBooking[]>([])
  const [bookingsLoading, setBookingsLoading] = useState(true)
  const [selectedBooking, setSelectedBooking] = useState<CourtBooking | null>(null)
  const [showPast, setShowPast] = useState(false)
  const [selectedDate, setSelectedDate] = useState(() => {
    try {
      const s = localStorage.getItem(SELECTED_DATE_KEY)
      return s ? new Date(s) : new Date()
    } catch {
      return new Date()
    }
  })
  const [courtFilter, setCourtFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [showCalendarPicker, setShowCalendarPicker] = useState(false)
  const [monthlyBookings, setMonthlyBookings] = useState<{ [key: string]: number }>({})

  // ── API calls ────────────────────────────────────────────────────────────
  const { call: fetchCourts } = useFrappePostCall('flamezo_backend.flamezo.api.courts.get_courts')
  const { call: saveCourt } = useFrappePostCall('flamezo_backend.flamezo.api.courts.save_court')
  const { call: deleteCourt } = useFrappePostCall('flamezo_backend.flamezo.api.courts.delete_court')
  const { call: fetchBookings } = useFrappePostCall('flamezo_backend.flamezo.api.courts.get_court_bookings')
  const { call: completeBookingAPI } = useFrappePostCall('flamezo_backend.flamezo.api.courts.mark_court_completed')
  const { call: noShowAPI } = useFrappePostCall('flamezo_backend.flamezo.api.courts.mark_court_no_show')

  useEffect(() => {
    if (selectedOutlet) {
      loadCourts()
      loadBookings()
      if (!searchQuery) loadMonthlyBookings()
    }
  }, [selectedOutlet])

  useEffect(() => {
    if (selectedOutlet) {
      loadBookings()
      if (!searchQuery) loadMonthlyBookings()
    }
  }, [selectedDate, statusFilter, courtFilter, showPast, searchQuery])

  useEffect(() => {
    try { localStorage.setItem(SELECTED_DATE_KEY, selectedDate.toISOString()) } catch {}
  }, [selectedDate])

  const formatDateAPI = (date: Date) => {
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const d = String(date.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  }

  const loadCourts = async () => {
    if (!selectedOutlet) return
    try {
      setCourtsLoading(true)
      const res = await fetchCourts({ outlet_id: selectedOutlet })
      const data = res?.message?.data || res?.data
      setCourts(Array.isArray(data) ? data : [])
    } catch {
      toast.error('Failed to load courts')
      setCourts([])
    } finally {
      setCourtsLoading(false)
    }
  }

  const loadBookings = async () => {
    if (!selectedOutlet) return
    try {
      setBookingsLoading(true)
      const params: any = { outlet_id: selectedOutlet, limit: 200 }
      if (!showPast) params.date = formatDateAPI(selectedDate)
      if (courtFilter !== 'all') params.court_id = courtFilter
      if (statusFilter !== 'all') params.status = statusFilter
      const res = await fetchBookings(params)
      const data = res?.message?.data || res?.data
      let list: CourtBooking[] = data?.bookings || []
      if (searchQuery) {
        const q = searchQuery.toLowerCase()
        list = list.filter(
          (b) =>
            b.customer_name?.toLowerCase().includes(q) ||
            b.customer_phone?.includes(q) ||
            b.court_name?.toLowerCase().includes(q)
        )
      }
      setBookings(list)
    } catch {
      toast.error('Failed to load bookings')
      setBookings([])
    } finally {
      setBookingsLoading(false)
    }
  }

  const loadMonthlyBookings = async () => {
    if (!selectedOutlet) return
    try {
      const res = await fetchBookings({ outlet_id: selectedOutlet, limit: 1000 })
      const data = res?.message?.data || res?.data
      const byDate: { [key: string]: number } = {}
      ;(data?.bookings || []).forEach((b: CourtBooking) => {
        if (b.booking_date) byDate[b.booking_date] = (byDate[b.booking_date] || 0) + 1
      })
      setMonthlyBookings(byDate)
    } catch {}
  }

  const handleBookingAction = async (id: string, action: 'complete' | 'no_show') => {
    if (!selectedOutlet) return
    try {
      const base = { booking_id: id, outlet_id: selectedOutlet }
      const res = action === 'complete' ? await completeBookingAPI(base) : await noShowAPI(base)
      const ok = res?.message?.success ?? res?.success ?? (res?.message?.data || res?.data)
      if (ok) {
        toast.success(action === 'complete' ? 'Marked as completed' : 'Marked as no-show')
        await loadBookings()
        await loadMonthlyBookings()
        if (selectedBooking?.id === id) setSelectedBooking(null)
      } else {
        toast.error('Failed to update booking')
      }
    } catch {
      toast.error('Failed to update booking')
    }
  }

  const openCourtForm = (court?: Court) => {
    if (court) {
      setEditingCourt(court)
      setCourtData({
        court_name: court.name,
        sport_type: court.sport_type,
        slot_duration_minutes: court.slot_duration_minutes,
        price_per_slot: court.price_per_slot,
        consumer_fee: court.consumer_fee,
        opening_time: court.opening_time,
        closing_time: court.closing_time,
        available_days: court.available_days,
        advance_booking_days: court.advance_booking_days,
        is_active: 1,
      })
    } else {
      setEditingCourt(null)
      setCourtData({ ...DEFAULT_COURT_DATA })
    }
    setCourtFormOpen(true)
  }

  const handleSaveCourt = async () => {
    if (!selectedOutlet || !courtData.court_name || !courtData.sport_type) {
      toast.error('Court name and sport type are required')
      return
    }
    try {
      setCourtSaving(true)
      const res = await saveCourt({
        outlet_id: selectedOutlet,
        court_id: editingCourt?.id || null,
        court_data: JSON.stringify(courtData),
      })
      const ok = res?.message?.success ?? res?.success ?? (res?.message?.data || res?.data)
      if (ok) {
        toast.success(editingCourt ? 'Court updated' : 'Court added')
        setCourtFormOpen(false)
        await loadCourts()
      } else {
        toast.error(res?.message?.error?.message || 'Failed to save court')
      }
    } catch (e: any) {
      toast.error('Failed to save court')
    } finally {
      setCourtSaving(false)
    }
  }

  const handleDeleteCourt = async (court: Court) => {
    const ok = await confirm({
      title: `Delete "${court.name}"?`,
      description: 'This will remove the court. Existing bookings will not be affected.',
      confirmLabel: 'Delete',
      confirmVariant: 'destructive',
    })
    if (!ok) return
    try {
      const res = await deleteCourt({ outlet_id: selectedOutlet, court_id: court.id })
      const success = res?.message?.success ?? res?.success
      if (success) {
        toast.success('Court deleted')
        await loadCourts()
      } else {
        toast.error(res?.message?.error?.message || 'Failed to delete court')
      }
    } catch {
      toast.error('Failed to delete court')
    }
  }

  const toggleDay = (day: string) => {
    const days = courtData.available_days ? courtData.available_days.split(',') : []
    const next = days.includes(day) ? days.filter((d) => d !== day) : [...days, day]
    setCourtData({ ...courtData, available_days: next.join(',') })
  }

  const changeDate = (days: number) => {
    const d = new Date(selectedDate)
    d.setDate(d.getDate() + days)
    setSelectedDate(d)
  }

  const formatDate = (date: Date) =>
    date.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })

  const stats = {
    total: bookings.length,
    confirmed: bookings.filter((b) => b.status === 'Confirmed').length,
    completed: bookings.filter((b) => b.status === 'Completed').length,
    revenue: bookings.filter((b) => b.payment_status === 'Paid').reduce((s, b) => s + b.slot_price, 0),
  }

  const statusColor = (status: string) => {
    if (status === 'Confirmed') return 'bg-green-100 text-green-800'
    if (status === 'Pending Payment') return 'bg-yellow-100 text-yellow-800'
    if (status === 'Cancelled') return 'bg-red-100 text-red-800'
    if (status === 'Completed') return 'bg-blue-100 text-blue-800'
    if (status === 'No Show') return 'bg-orange-100 text-orange-800'
    return 'bg-gray-100 text-gray-800'
  }

  if (!selectedOutlet) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground">Please select an outlet to manage courts</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {ConfirmDialogComponent}

      <div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Courts</h1>
        <p className="text-muted-foreground mt-1">Manage your courts and track all bookings</p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border">
        <button
          onClick={() => setActiveTab('bookings')}
          className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'bookings'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Calendar className="w-4 h-4 inline mr-2" />
          Bookings
        </button>
        <button
          onClick={() => setActiveTab('courts')}
          className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'courts'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Trophy className="w-4 h-4 inline mr-2" />
          Courts Setup
        </button>
      </div>

      {/* ── BOOKINGS TAB ───────────────────────────────────────────────────── */}
      {activeTab === 'bookings' && (
        <>
          {/* Stats */}
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
                  <p className="text-sm font-medium text-purple-600">Completed</p>
                  <p className="text-2xl font-bold text-purple-900 mt-1">{stats.completed}</p>
                </div>
                <Trophy className="w-8 h-8 text-purple-500" />
              </div>
            </div>
            <div className="bg-gradient-to-br from-emerald-50 to-emerald-100 rounded-lg p-4 border border-emerald-200">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-emerald-600">Revenue (Paid)</p>
                  <p className="text-2xl font-bold text-emerald-900 mt-1">₹{stats.revenue.toFixed(0)}</p>
                </div>
                <Trophy className="w-8 h-8 text-emerald-500" />
              </div>
            </div>
          </div>

          {/* Filters */}
          <div className="bg-card rounded-lg border p-4">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
              <div className="flex items-center gap-3">
                <Button
                  variant={showPast ? 'default' : 'outline'}
                  className="gap-2"
                  onClick={() => setShowPast(!showPast)}
                >
                  {showPast ? <LayoutDashboard className="w-4 h-4" /> : <History className="w-4 h-4" />}
                  {showPast ? 'Show Daily View' : 'All Bookings'}
                </Button>

                {!showPast && (
                  <div className="flex items-center gap-3">
                    <Button variant="outline" size="icon" onClick={() => changeDate(-1)}>
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="outline"
                      className="w-full sm:min-w-[280px] sm:w-auto justify-center"
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
                    placeholder="Search by name, phone..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-10"
                  />
                </div>
                {courts.length > 0 && (
                  <Select value={courtFilter} onValueChange={setCourtFilter}>
                    <SelectTrigger className="w-[160px]">
                      <SelectValue placeholder="All Courts" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Courts</SelectItem>
                      {courts.map((c) => (
                        <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-[160px]">
                    <SelectValue placeholder="All Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Status</SelectItem>
                    <SelectItem value="Pending Payment">Pending Payment</SelectItem>
                    <SelectItem value="Confirmed">Confirmed</SelectItem>
                    <SelectItem value="Completed">Completed</SelectItem>
                    <SelectItem value="Cancelled">Cancelled</SelectItem>
                    <SelectItem value="No Show">No Show</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          {/* Bookings List */}
          {bookingsLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary" />
            </div>
          ) : bookings.length === 0 ? (
            <div className="bg-card rounded-lg border p-12 text-center">
              <Trophy className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground text-lg">No court bookings found</p>
              <p className="text-sm text-muted-foreground mt-2">Try a different date or filter</p>
            </div>
          ) : (
            <div className="space-y-3">
              {bookings.map((booking) => (
                <div
                  key={booking.id}
                  className="bg-card rounded-lg border p-4 hover:shadow-md transition-shadow cursor-pointer border-l-4 border-l-primary/30"
                  onClick={() => setSelectedBooking(booking)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <div className="flex flex-col">
                          <h3 className="font-bold text-lg text-foreground">{booking.customer_name || 'Guest'}</h3>
                          {showPast && (
                            <span className="text-xs font-medium text-primary/80">{booking.booking_date}</span>
                          )}
                        </div>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                            <button className={`px-3 py-1.5 rounded-md text-sm font-semibold flex items-center gap-1.5 hover:opacity-80 ${statusColor(booking.status)}`}>
                              {booking.status}
                              <ChevronDown className="w-4 h-4" />
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="start">
                            {booking.status === 'Confirmed' && (
                              <>
                                <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleBookingAction(booking.id, 'complete') }}>
                                  <CheckCircle className="w-4 h-4 mr-2 text-blue-600" />
                                  Mark Completed
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleBookingAction(booking.id, 'no_show') }}>
                                  <AlertCircle className="w-4 h-4 mr-2 text-orange-600" />
                                  Mark No-Show
                                </DropdownMenuItem>
                              </>
                            )}
                            {['Completed', 'Cancelled', 'No Show', 'Pending Payment'].includes(booking.status) && (
                              <DropdownMenuItem disabled className="text-muted-foreground">
                                No actions available
                              </DropdownMenuItem>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <Trophy className="w-4 h-4" />
                          <span>{booking.court_name}</span>
                        </div>
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <Clock className="w-4 h-4" />
                          <span>{booking.start_time} – {booking.end_time}</span>
                        </div>
                        {booking.customer_phone && (
                          <div className="flex items-center gap-2 text-muted-foreground">
                            <Phone className="w-4 h-4" />
                            <span>{booking.customer_phone}</span>
                          </div>
                        )}
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <span className="text-xs font-semibold">₹{booking.slot_price}</span>
                          <Badge variant="outline" className="text-[10px]">{booking.payment_status}</Badge>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* ── COURTS SETUP TAB ──────────────────────────────────────────────── */}
      {activeTab === 'courts' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Add courts, set pricing and availability. Customers book slots directly from the Flamezo app.
            </p>
            <Button onClick={() => openCourtForm()} className="gap-2">
              <Plus className="w-4 h-4" />
              Add Court
            </Button>
          </div>

          {courtsLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary" />
            </div>
          ) : courts.length === 0 ? (
            <div className="bg-card rounded-lg border p-12 text-center">
              <Trophy className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground text-lg">No courts added yet</p>
              <p className="text-sm text-muted-foreground mt-2 mb-4">Add your first court to start accepting bookings</p>
              <Button onClick={() => openCourtForm()} className="gap-2">
                <Plus className="w-4 h-4" />
                Add First Court
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {courts.map((court) => (
                <div key={court.id} className="bg-card rounded-lg border p-5 hover:shadow-md transition-shadow">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="font-bold text-lg">{court.name}</h3>
                      <p className="text-sm text-muted-foreground">{court.sport_type}</p>
                    </div>
                    <div className="flex gap-2">
                      <Button variant="ghost" size="icon" onClick={() => openCourtForm(court)}>
                        <Edit2 className="w-4 h-4" />
                      </Button>
                      <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive" onClick={() => handleDeleteCourt(court)}>
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Slot Duration</p>
                      <p className="font-medium">{court.slot_duration_minutes} min</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Price / Slot</p>
                      <p className="font-medium">₹{court.price_per_slot}</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Timings</p>
                      <p className="font-medium">{court.opening_time} – {court.closing_time}</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Available Days</p>
                      <p className="font-medium text-xs">{court.available_days}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Booking Detail Modal ─────────────────────────────────────────── */}
      <Dialog open={!!selectedBooking} onOpenChange={(open) => !open && setSelectedBooking(null)}>
        <DialogContent className="sm:max-w-[450px] p-0 overflow-hidden border-none shadow-2xl">
          <div className="bg-primary/5 p-6 border-b border-primary/10">
            <DialogHeader>
              <div className="flex items-center justify-between">
                <DialogTitle className="text-2xl font-bold flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                    <Trophy className="w-5 h-5 text-primary" />
                  </div>
                  Booking Details
                </DialogTitle>
                <Badge variant="outline" className={`px-2.5 py-0.5 uppercase text-[10px] font-bold tracking-widest ${statusColor(selectedBooking?.status || '')}`}>
                  {selectedBooking?.status}
                </Badge>
              </div>
            </DialogHeader>
          </div>
          <div className="p-6 space-y-6">
            <div className="grid grid-cols-2 gap-6">
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Customer</p>
                <p className="text-base font-semibold">{selectedBooking?.customer_name || 'Guest'}</p>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Phone</p>
                <p className="text-base font-semibold flex items-center gap-2">
                  <Phone className="w-3.5 h-3.5 text-primary/60" />
                  {selectedBooking?.customer_phone || 'N/A'}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Court</p>
                <p className="text-base font-semibold">{selectedBooking?.court_name}</p>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Date</p>
                <p className="text-base font-semibold">{selectedBooking?.booking_date}</p>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Time Slot</p>
                <p className="text-base font-semibold">{selectedBooking?.start_time} – {selectedBooking?.end_time}</p>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Amount</p>
                <p className="text-base font-semibold">₹{selectedBooking?.slot_price}</p>
              </div>
            </div>
          </div>
          <div className="p-4 bg-muted/20 flex justify-end">
            <Button variant="ghost" size="sm" onClick={() => setSelectedBooking(null)}>Close</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── Court Form Modal ─────────────────────────────────────────────── */}
      <Dialog open={courtFormOpen} onOpenChange={(open) => !open && setCourtFormOpen(false)}>
        <DialogContent className="sm:max-w-[540px]">
          <DialogHeader>
            <DialogTitle>{editingCourt ? 'Edit Court' : 'Add New Court'}</DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2 space-y-1.5">
                <Label>Court Name *</Label>
                <Input
                  placeholder="e.g. Court 1 — Badminton"
                  value={courtData.court_name}
                  onChange={(e) => setCourtData({ ...courtData, court_name: e.target.value })}
                />
              </div>

              <div className="space-y-1.5">
                <Label>Sport *</Label>
                <Select
                  value={courtData.sport_type}
                  onValueChange={(v) => setCourtData({ ...courtData, sport_type: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {COURT_SPORTS.map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label>Slot Duration (minutes) *</Label>
                <Select
                  value={String(courtData.slot_duration_minutes)}
                  onValueChange={(v) => setCourtData({ ...courtData, slot_duration_minutes: Number(v) })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {[30, 45, 60, 90, 120].map((m) => (
                      <SelectItem key={m} value={String(m)}>{m} min</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label>Price per Slot (₹) *</Label>
                <Input
                  type="number"
                  min={0}
                  value={courtData.price_per_slot}
                  onChange={(e) => setCourtData({ ...courtData, price_per_slot: Number(e.target.value) })}
                />
              </div>

              <div className="space-y-1.5">
                <Label>Consumer Booking Fee (₹)</Label>
                <Input
                  type="number"
                  min={0}
                  value={courtData.consumer_fee}
                  onChange={(e) => setCourtData({ ...courtData, consumer_fee: Number(e.target.value) })}
                />
                <p className="text-xs text-muted-foreground">Flamezo platform fee charged to the customer</p>
              </div>

              <div className="space-y-1.5">
                <Label>Opening Time *</Label>
                <Input
                  type="time"
                  value={courtData.opening_time}
                  onChange={(e) => setCourtData({ ...courtData, opening_time: e.target.value })}
                />
              </div>

              <div className="space-y-1.5">
                <Label>Closing Time *</Label>
                <Input
                  type="time"
                  value={courtData.closing_time}
                  onChange={(e) => setCourtData({ ...courtData, closing_time: e.target.value })}
                />
              </div>

              <div className="space-y-1.5">
                <Label>Advance Booking (days)</Label>
                <Input
                  type="number"
                  min={1}
                  max={60}
                  value={courtData.advance_booking_days}
                  onChange={(e) => setCourtData({ ...courtData, advance_booking_days: Number(e.target.value) })}
                />
              </div>

              <div className="col-span-2 space-y-2">
                <Label>Available Days *</Label>
                <div className="flex gap-2 flex-wrap">
                  {DAYS.map((day) => {
                    const active = courtData.available_days?.includes(day)
                    return (
                      <button
                        key={day}
                        type="button"
                        onClick={() => toggleDay(day)}
                        className={`px-3 py-1.5 rounded-md text-sm font-medium border transition-colors ${
                          active
                            ? 'bg-primary text-primary-foreground border-primary'
                            : 'bg-background border-border text-muted-foreground hover:border-primary'
                        }`}
                      >
                        {day}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setCourtFormOpen(false)}>Cancel</Button>
            <Button onClick={handleSaveCourt} disabled={courtSaving}>
              {courtSaving ? 'Saving...' : editingCourt ? 'Update Court' : 'Add Court'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
