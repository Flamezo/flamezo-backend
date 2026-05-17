import React from 'react'
import { ShieldAlert, Mail, Phone, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface SuspendedOverlayProps {
  restaurantName: string
  reason?: string
}

export const SuspendedOverlay: React.FC<SuspendedOverlayProps> = ({ 
  restaurantName, 
  reason = "Your account has been suspended due to a security reason. Please contact support for reactivation." 
}) => {
  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-background/80 backdrop-blur-md animate-in fade-in duration-500">
      <div className="max-w-md w-full px-4 animate-in zoom-in-95 duration-500">
        <Card className="border-destructive/50 shadow-2xl overflow-hidden">
          <div className="h-2 bg-destructive w-full" />
          <CardHeader className="text-center pt-8">
            <div className="mx-auto w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center mb-4">
              <ShieldAlert className="h-8 w-8 text-destructive" />
            </div>
            <CardTitle className="text-2xl font-black tracking-tight uppercase">Account Suspended</CardTitle>
            <CardDescription className="text-base font-medium">
              {restaurantName}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6 pb-8">
            <div className="bg-muted p-4 rounded-xl text-sm text-muted-foreground border border-border/50 text-center leading-relaxed">
              {reason}
              <p className="mt-2 font-bold text-foreground italic">
                All customer orders and dashboard features are locked until reactivation.
              </p>
            </div>

            <div className="space-y-3">
              <p className="text-xs font-black uppercase tracking-widest text-muted-foreground text-center mb-2">Next Steps</p>
              
              <div className="grid gap-2">
                <Button className="w-full gap-2 bg-foreground hover:bg-foreground/90 text-background h-11" asChild>
                   <a href="mailto:support@flamezo_backend.ono.menu">
                      <Mail className="h-4 w-4" />
                      Contact Billing Support
                   </a>
                </Button>
                
                <div className="grid grid-cols-2 gap-2">
                   <Button variant="outline" className="gap-2 h-11" asChild>
                      <a href="tel:+91-SUPPORT-PH">
                         <Phone className="h-4 w-4" />
                         Call Support
                      </a>
                   </Button>
                   <Button variant="outline" className="gap-2 h-11" onClick={() => window.location.reload()}>
                      <ExternalLink className="h-4 w-4" />
                      Check Again
                   </Button>
                </div>
              </div>
            </div>

            <p className="text-[10px] text-muted-foreground text-center uppercase tracking-tighter opacity-70">
              Only a Flamezo Systems Administrator can reactivate this account.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
