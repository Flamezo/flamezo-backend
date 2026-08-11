import { useState, useEffect } from 'react'
import { Calendar, Users, Clock, CheckCircle, XCircle, AlertCircle, Search, ChevronLeft, ChevronRight, Phone, StickyNote, ChevronDown, Scissors, Dumbbell } from 'lucide-react'
import { useFrappePostCall } from '@/lib/frappe'
import { useOutlet } from '@/contexts/OutletContext'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { toast } from 'sonner'
import CalendarPicker from '@/components/CalendarPicker'
import { History, LayoutDashboard } from 'lucide-react'

interface Appointment {
  id: string
  restaurant: string
  outlet_type: string
  catalogue_item: string
  catalogue_item_name: string
  sub_item_name: string
  sub_item_price: number | null
  customer_name: string
  customer_phone: string
  appointment_date: string
  appointment_time: string
  duration_minutes: number
  notes: string
  status: 'Pending' | 'Confirmed' | 'Cancelled' | 'Completed' | 'No Show'
  confirmed_at: string | null
  completed_at: string | null
}

const SELECTED_DATE_KEY = 'flamezo_backend-appointments-selected-date'

export default function AppointmentsPage() {
  const { selectedOutlet, outletType } = useOutlet()

  const isFitness = outletType === 'fitness'
  const pageTitle = isFitness ? 'Class Bookings' : 'Appointments'
  const pageSubtitle = isFitness
    ? 'Manage and track all class session bookings'
    : 'Manage and track all service appointments'
  const PageIcon = isFitness ? Dumbbell : Scissors

  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [loading, setLoading] = useState(true)
  const [showPastBookings, setShowPastBookings] = useState(false)
  const [selectedAppointment, setSelectedAppointment] = useState<Appointment | null>(null)
  const [selectedDate, setSelectedDate] = useState(() => {
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
  const [monthlyAppointments, setMonthlyAppointments] = useState<{ [key: string]: number }>({})

  const { call: fetchAppointments } = useFrappePostCall(
    'flamezo_backend.flamezo.api.appointments.get_appointment_requests'
  )
  const { call: confirmAPI } = useFrappePostCall(
    'flamezo_backend.flamezo.api.appointments.confirm_appointment'
  )
  const { call: rejectAPI } = useFrappePostCall(
    'flamezo_backend.flamezo.api.appointments.reject_appointment'
  )
  const { call: completeAPI } = useFrappePostCall(
    'flamezo_backend.flamezo.api.appointments.mark_appointment_completed'
  )
  const { call: noShowAPI } = useFrappePostCall(
    'flamezo_backend.flamezo.api.appointments.mark_appointment_no_show'
  )

  useEffect(() => {
    try {
      localStorage.setItem(SELECTED_DATE_KEY, selectedDate.toISOString())
    } catch {}
  }, [selectedDate])

  useEffect(() => {
    if (selectedOutlet) {
      loadAppointments()
      if (!searchQuery) loadMonthlyAppointments()
    }
  }, [selectedOutlet, selectedDate, statusFilter, showPastBookings, searchQuery])

  const formatDateForAPI = (date: Date): string => {
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const d = String(date.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  }

  const loadAppointments = async () => {
    if (!selectedOutlet) return
    try {
      setLoading(true)
      const dateStr = formatDateForAPI(selectedDate)
      let params: any = {
        outlet_id: selectedOutlet,
        status: statusFilter === 'all' ? undefined : statusFilter,
        limit: 200,
      }
      if (showPastBookings) {
        // No date filter — show all
      } else {
        params.date = dateStr
      }
      const response = await fetchAppointments(params)
      const data = response?.message?.data || response?.data
      if (data?.appointments) {
        let list: Appointment[] = data.appointments
        if (searchQuery) {
          const q = searchQuery.toLowerCase()
          list = list.filter(
            (a) =>
              a.customer_name?.toLowerCase().includes(q) ||
              a.customer_phone?.includes(q) ||
              a.catalogue_item_name?.toLowerCase().includes(q)
          )
        }
        setAppointments(list)
      } else {
        setAppointments([])
      }
    } catch {
      toast.error('Failed to load appointments')
      setAppointments([])
    } finally {
      setLoading(false)
    }
  }

  const loadMonthlyAppointments = async () => {
    if (!selectedOutlet) return
    try {
      const response = await fetchAppointments({
        outlet_id: selectedOutlet,
        limit: 1000,
      })
      const data = response?.message?.data || response?.data
      if (data?.appointments) {
        const byDate: { [key: string]: number } = {}
        data.appointments.forEach((a: Appointment) => {
          if (a.appointment_date) {
            byDate[a.appointment_date] = (byDate[a.appointment_date] || 0) + 1
          }
        })
        setMonthlyAppointments(byDate)
      }
    } catch {}
  }

  const handleStatusChange = async (id: string, newStatus: string) => {
    if (!selectedOutlet) return
    try {
      let response
      const base = { appointment_id: id, outlet_id: selectedOutlet }
      if (newStatus === 'Confirmed') response = await confirmAPI(base)
      else if (newStatus === 'Rejected') response = await rejectAPI({ ...base, reason: 'Rejected by staff' })
      else if (newStatus === 'Completed') response = await completeAPI(base)
      else if (newStatus === 'No Show') response = await noShowAPI(base)
      else return

      const ok = response?.message?.success ?? response?.success ?? (response?.message?.data || response?.data)
      if (ok) {
        toast.success(`Status updated to ${newStatus}`)
        await loadAppointments()
        await loadMonthlyAppointments()
        if (selectedAppointment?.id === id) setSelectedAppointment(null)
      } else {
        toast.error('Failed to update status')
      }
    } catch {
      toast.error('Failed to update status')
    }
  }

  const changeDate = (days: number) => {
    const d = new Date(selectedDate)
    d.setDate(d.getDate() + days)
    setSelectedDate(d)
  }

  const formatDate = (date: Date) =>
    date.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })

  const stats = {
    total: appointments.length,
    pending: appointments.filter((a) => a.status === 'Pending').length,
    confirmed: appointments.filter((a) => a.status === 'Confirmed').length,
    completed: appointments.filter((a) => a.status === 'Completed').length,
  }

  const statusColor = (status: string) => {
    if (status === 'Confirmed') return 'bg-green-100 text-green-800'
    if (status === 'Pending') return 'bg-yellow-100 text-yellow-800'
    if (status === 'Cancelled' || status === 'Rejected') return 'bg-red-100 text-red-800'
    if (status === 'Completed') return 'bg-blue-100 text-blue-800'
    if (status === 'No Show') return 'bg-orange-100 text-orange-800'
    return 'bg-gray-100 text-gray-800'
  }

  if (!selectedOutlet) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground">Please select an outlet to view appointments</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">{pageTitle}</h1>
        <p className="text-muted-foreground mt-1">{pageSubtitle}</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg p-4 border border-blue-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-blue-600">Total</p>
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
              <p className="text-sm font-medium text-purple-600">Completed</p>
              <p className="text-2xl font-bold text-purple-900 mt-1">{stats.completed}</p>
            </div>
            <PageIcon className="w-8 h-8 text-purple-500" />
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-card rounded-lg border p-4">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button
              variant={showPastBookings ? 'default' : 'outline'}
              className="gap-2"
              onClick={() => setShowPastBookings(!showPastBookings)}
            >
              {showPastBookings ? <LayoutDashboard className="w-4 h-4" /> : <History className="w-4 h-4" />}
              {showPastBookings ? 'Show Daily View' : 'All Appointments'}
            </Button>

            {!showPastBookings && (
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
                placeholder="Search by name, phone, service..."
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
                <SelectItem value="Pending">Pending</SelectItem>
                <SelectItem value="Confirmed">Confirmed</SelectItem>
                <SelectItem value="Completed">Completed</SelectItem>
                <SelectItem value="Cancelled">Cancelled</SelectItem>
                <SelectItem value="No Show">No Show</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* List */}
      <div>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary" />
          </div>
        ) : appointments.length === 0 ? (
          <div className="bg-card rounded-lg border p-12 text-center">
            <PageIcon className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground text-lg">
              No {pageTitle.toLowerCase()} found for this date
            </p>
            <p className="text-sm text-muted-foreground mt-2">
              Try selecting a different date or adjusting filters
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {appointments.map((appt) => (
              <div
                key={appt.id}
                className="bg-card rounded-lg border p-4 hover:shadow-md transition-shadow cursor-pointer border-l-4 border-l-primary/30"
                onClick={() => setSelectedAppointment(appt)}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <div className="flex flex-col">
                        <h3 className="font-bold text-lg text-foreground">
                          {appt.customer_name || 'Guest'}
                        </h3>
                        {showPastBookings && (
                          <span className="text-xs font-medium text-primary/80">{appt.appointment_date}</span>
                        )}
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                          <button
                            className={`px-3 py-1.5 rounded-md text-sm font-semibold flex items-center gap-1.5 hover:opacity-80 transition-opacity ${statusColor(appt.status)}`}
                          >
                            {appt.status}
                            <ChevronDown className="w-4 h-4" />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start">
                          {appt.status === 'Pending' && (
                            <>
                              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleStatusChange(appt.id, 'Confirmed') }}>
                                <CheckCircle className="w-4 h-4 mr-2 text-green-600" />
                                Confirm
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleStatusChange(appt.id, 'Rejected') }}>
                                <XCircle className="w-4 h-4 mr-2 text-red-600" />
                                Reject
                              </DropdownMenuItem>
                            </>
                          )}
                          {appt.status === 'Confirmed' && (
                            <>
                              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleStatusChange(appt.id, 'Completed') }}>
                                <CheckCircle className="w-4 h-4 mr-2 text-blue-600" />
                                Mark Completed
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleStatusChange(appt.id, 'No Show') }}>
                                <AlertCircle className="w-4 h-4 mr-2 text-orange-600" />
                                Mark No-Show
                              </DropdownMenuItem>
                            </>
                          )}
                          {['Cancelled', 'Completed', 'No Show', 'Rejected'].includes(appt.status) && (
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
                        <span>{appt.appointment_time}</span>
                      </div>
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <PageIcon className="w-4 h-4" />
                        <span>{appt.catalogue_item_name || '—'}</span>
                      </div>
                      {appt.sub_item_name && (
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <span className="text-xs text-primary/70">{appt.sub_item_name}</span>
                        </div>
                      )}
                      {appt.customer_phone && (
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <Phone className="w-4 h-4" />
                          <span>{appt.customer_phone}</span>
                        </div>
                      )}
                    </div>

                    {appt.notes && (
                      <div className="mt-2 flex items-start gap-2 text-sm text-muted-foreground">
                        <StickyNote className="w-4 h-4 mt-0.5" />
                        <span>{appt.notes}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Detail Modal */}
      <Dialog
        open={!!selectedAppointment}
        onOpenChange={(open) => !open && setSelectedAppointment(null)}
      >
        <DialogContent className="sm:max-w-[450px] p-0 overflow-hidden border-none shadow-2xl">
          <div className="bg-primary/5 p-6 border-b border-primary/10">
            <DialogHeader>
              <div className="flex items-center justify-between">
                <DialogTitle className="text-2xl font-bold flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                    <PageIcon className="w-5 h-5 text-primary" />
                  </div>
                  Appointment Details
                </DialogTitle>
                <Badge
                  variant="outline"
                  className={`px-2.5 py-0.5 uppercase text-[10px] font-bold tracking-widest ${statusColor(selectedAppointment?.status || '')}`}
                >
                  {selectedAppointment?.status}
                </Badge>
              </div>
            </DialogHeader>
          </div>

          <div className="p-6 space-y-6">
            <div className="grid grid-cols-2 gap-6">
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Customer</p>
                <p className="text-base font-semibold">{selectedAppointment?.customer_name || 'Guest'}</p>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Phone</p>
                <p className="text-base font-semibold flex items-center gap-2">
                  <Phone className="w-3.5 h-3.5 text-primary/60" />
                  {selectedAppointment?.customer_phone || 'Not provided'}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Date</p>
                <p className="text-base font-semibold flex items-center gap-2">
                  <Calendar className="w-3.5 h-3.5 text-primary/60" />
                  {selectedAppointment?.appointment_date}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Time</p>
                <p className="text-base font-semibold flex items-center gap-2">
                  <Clock className="w-3.5 h-3.5 text-primary/60" />
                  {selectedAppointment?.appointment_time}
                  {selectedAppointment?.duration_minutes ? ` (${selectedAppointment.duration_minutes} min)` : ''}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Service</p>
                <p className="text-base font-semibold">{selectedAppointment?.catalogue_item_name || '—'}</p>
              </div>
              {selectedAppointment?.sub_item_name && (
                <div className="space-y-1">
                  <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider">Variant</p>
                  <p className="text-base font-semibold">{selectedAppointment.sub_item_name}</p>
                </div>
              )}
            </div>

            {selectedAppointment?.notes && (
              <div className="space-y-2 pt-4 border-t border-muted">
                <p className="text-[10px] uppercase font-bold text-muted-foreground tracking-wider flex items-center gap-1.5">
                  <StickyNote className="w-3 h-3" />
                  Notes
                </p>
                <div className="bg-muted/50 p-3 rounded-lg text-sm italic text-muted-foreground leading-relaxed">
                  "{selectedAppointment.notes}"
                </div>
              </div>
            )}
          </div>

          <div className="p-4 bg-muted/20 flex justify-end">
            <Button variant="ghost" size="sm" onClick={() => setSelectedAppointment(null)}>
              Close
            </Button>
          </div>
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
        bookingsByDate={monthlyAppointments}
      />
    </div>
  )
}
