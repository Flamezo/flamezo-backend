import { useFrappeGetDoc, useFrappeAuth } from '@/lib/frappe'
import { useOutlet } from '@/contexts/OutletContext'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { User, Mail, Globe, MapPin, AlertCircle, Clock, CheckCircle2, ShieldAlert } from 'lucide-react'

export default function MyAccount() {
  const { currentUser } = useFrappeAuth()
  const { isActive } = useOutlet()

  // Fetch user data securely
  const { data: userDoc, isLoading, error } = useFrappeGetDoc('User', currentUser || '', {
    enabled: !!currentUser && currentUser !== 'Guest'
  })

  // Fallbacks if data loading
  const email = userDoc?.email || currentUser || ''
  const firstName = userDoc?.first_name || ''
  const lastName = userDoc?.last_name || ''
  const fullName = userDoc?.full_name || `${firstName} ${lastName}`.trim() || email.split('@')[0]
  const username = userDoc?.username || fullName
  const timeZone = userDoc?.time_zone || 'Asia/Kolkata'

  const userInitial = (firstName?.charAt(0) || fullName?.charAt(0) || email?.charAt(0) || 'U').toUpperCase()

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    )
  }

  return (
    <div className="space-y-8 pb-10 max-w-6xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Top Banner */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="text-3xl font-bold tracking-tight text-foreground">My Account</h1>
          </div>
          <p className="text-muted-foreground text-sm flex items-center gap-1.5">
            <User className="h-4 w-4 text-primary" />
            Manage your personal profile and preferences
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">

        {/* Left Column: Profile Card */}
        <div className="lg:col-span-4 space-y-6">
          <Card className="border-none shadow-sm bg-card overflow-hidden">
            <div className="h-32 bg-gradient-to-br from-primary/30 to-background w-full border-b border-border/40" />
            <CardContent className="px-6 pb-6 relative">
              <div className="absolute -top-16 left-6 h-28 w-28 rounded-2xl bg-background border border-border shadow-md flex items-center justify-center text-5xl font-bold text-primary">
                {userInitial}
              </div>
              <div className="pt-16">
                <h2 className="text-xl font-bold">{fullName}</h2>
                <div className="text-sm text-muted-foreground mt-1 flex items-center gap-2">
                  <Mail className="h-4 w-4" />
                  {email}
                </div>

                <div className="mt-8 pt-6 border-t border-border space-y-4">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground font-medium">Status</span>
                    {isActive ? (
                      <span className="flex items-center text-emerald-600 bg-emerald-100 dark:bg-emerald-950/30 px-2.5 py-0.5 rounded-full font-bold text-xs">
                        <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
                        Enabled
                      </span>
                    ) : (
                      <span className="flex items-center text-rose-600 bg-rose-100 dark:bg-rose-950/30 px-2.5 py-0.5 rounded-full font-bold text-xs">
                        <ShieldAlert className="h-3.5 w-3.5 mr-1" />
                        Deactivated
                      </span>
                    )}
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground font-medium">System Role</span>
                    <span className="text-foreground font-medium capitalize bg-muted px-2.5 py-0.5 rounded-full text-xs">
                      {currentUser === 'Administrator' ? 'Administrator' : 'System User'}
                    </span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Details Tabs */}
        <div className="lg:col-span-8">
          <Card className="border-none shadow-sm bg-card overflow-hidden">
            <Tabs defaultValue="details" className="w-full">
              <CardHeader className="border-b border-border p-0 bg-muted/20">
                <TabsList className="w-full justify-start h-14 bg-transparent p-0 rounded-none overflow-x-auto">
                  <TabsTrigger
                    value="details"
                    className="data-[state=active]:border-b-2 data-[state=active]:border-primary data-[state=active]:shadow-none rounded-none h-14 px-6 font-medium data-[state=active]:bg-transparent"
                  >
                    User Details
                  </TabsTrigger>
                  <TabsTrigger
                    value="settings"
                    className="data-[state=active]:border-b-2 data-[state=active]:border-primary data-[state=active]:shadow-none rounded-none h-14 px-6 font-medium data-[state=active]:bg-transparent"
                  >
                    Settings
                  </TabsTrigger>
                </TabsList>
              </CardHeader>

              <CardContent className="p-6">
                <TabsContent value="details" className="mt-0 space-y-6">

                  {error && (
                    <div className="p-4 bg-rose-50 dark:bg-rose-950/30 text-rose-600 dark:text-rose-400 rounded-xl flex items-center gap-3 text-sm border border-rose-100 dark:border-rose-900/30">
                      <AlertCircle className="h-5 w-5 flex-shrink-0" />
                      <p>Could not fully load administrative profile data. Some fields are reconstructed dynamically.</p>
                    </div>
                  )}

                  <div>
                    <h3 className="text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground mb-6">Basic Info</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-6">
                      <div className="space-y-2">
                        <Label className="text-xs font-bold text-muted-foreground">Email</Label>
                        <Input value={email} readOnly className="bg-muted/30 border-transparent focus-visible:ring-0 focus-visible:ring-offset-0 cursor-default" />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-bold text-muted-foreground">Full Name</Label>
                        <Input value={fullName} readOnly className="bg-muted/30 border-transparent focus-visible:ring-0 focus-visible:ring-offset-0 cursor-default" />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-bold text-muted-foreground">First Name</Label>
                        <Input value={firstName} readOnly className="bg-muted/30 border-transparent focus-visible:ring-0 focus-visible:ring-offset-0 cursor-default" />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-bold text-muted-foreground">Last Name</Label>
                        <Input value={lastName} readOnly className="bg-muted/30 border-transparent focus-visible:ring-0 focus-visible:ring-offset-0 cursor-default" />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-bold text-muted-foreground">Username</Label>
                        <Input value={username} readOnly className="bg-muted/30 border-transparent focus-visible:ring-0 focus-visible:ring-offset-0 cursor-default" />
                      </div>
                      <div className="space-y-2 border-t border-border/40 mt-2 pt-6 md:border-none md:mt-0 md:pt-0">
                        <Label className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                          <Globe className="h-3 w-3" /> Language
                        </Label>
                        <Input value={userDoc?.language || 'English'} readOnly className="bg-muted/30 border-transparent focus-visible:ring-0 focus-visible:ring-offset-0 cursor-default" />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                          <Clock className="h-3 w-3" /> Time Zone
                        </Label>
                        <Input value={timeZone} readOnly className="bg-muted/30 border-transparent focus-visible:ring-0 focus-visible:ring-offset-0 cursor-default" />
                      </div>
                    </div>
                  </div>
                </TabsContent>

                <TabsContent value="settings" className="mt-0">
                  <div className="text-center py-16 px-6">
                    <div className="h-16 w-16 bg-muted/50 rounded-2xl flex items-center justify-center mx-auto mb-5 border border-border/40">
                      <User className="h-8 w-8 text-muted-foreground opacity-40" />
                    </div>
                    <h4 className="text-sm font-bold text-foreground mb-2">Preferences Managed Administratively</h4>
                    <p className="text-sm text-muted-foreground/80 max-w-sm mx-auto leading-relaxed">
                      For platform security, direct profile edits, password resets, and critical role assignments must be performed by your system administrator.
                    </p>
                  </div>
                </TabsContent>
              </CardContent>
            </Tabs>
          </Card>
        </div>
      </div>
    </div>
  )
}
