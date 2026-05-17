import { useState, useEffect, useMemo } from 'react'
import { useFrappeGetCall } from '@/lib/frappe'
import DynamicForm from '@/components/DynamicForm'
import StaffMembersList from '@/components/StaffMembersList'
import RestaurantDataList from '@/components/RestaurantDataList'
import LegacyContentStep from '@/components/LegacyContentStep'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Stepper } from '@/components/ui/stepper'
import { Badge } from '@/components/ui/badge'
import { ArrowLeft, ArrowRight, Check, Zap, Star, Loader2 } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { cn } from '@/lib/utils'
import { getHiddenFields } from '@/config/setupWizardFields'

interface WizardStep {
  id: string
  title: string
  description: string
  doctype: string
  required: boolean
  view_only?: boolean
  feature?: string
  customComponent?: string
}

// Map step IDs to URL-friendly slugs
const stepIdToSlug = (id: string) => {
  const map: Record<string, string> = {
    'restaurant': 'RestaurantProfile',
    'config': 'BrandingAndConfig',
    'categories': 'MenuCategories',
    'products': 'MenuProducts',
    'users': 'StaffMembers',
    'table_booking': 'TableBooking',
    'marketing': 'MarketingGrowth',
    'pos': 'POSIntegration',
    'ordering': 'OrderingSettings',
    'loyalty': 'LoyaltyProgram',
    'legacy': 'LegacyContent'
  }
  return map[id] || id
}

const slugToStepId = (slug: string) => {
  const map: Record<string, string> = {
    'RestaurantProfile': 'restaurant',
    'BrandingAndConfig': 'config',
    'StaffMembers': 'users',
    'LegacyContent': 'legacy'
  }
  return map[slug] || slug
}

interface SetupProgressResponse {
  message: Record<string, boolean>
}

export default function TieredSetupWizard() {
  const { stepId: urlSlug } = useParams<{ stepId?: string }>()
  const navigate = useNavigate()
  const { selectedRestaurant, setSelectedRestaurant, planType, isGold, isLoading: contextLoading, restaurants } = useRestaurant()

  // Define All Possible Steps
  const allPotentialSteps: WizardStep[] = [
    { id: 'restaurant', title: 'Restaurant Profile', description: 'Set up your restaurant basic information and contact details.', doctype: 'Restaurant', required: true },
    { id: 'config', title: 'Branding & Config', description: 'Configure your brand colors, logos, and operational settings.', doctype: 'Restaurant Config', required: true },
    { id: 'users', title: 'Staff Members', description: 'Invite your team members and assign roles.', doctype: 'Restaurant User', required: false, customComponent: 'StaffMembersList' },
    { id: 'legacy', title: 'Legacy Content', description: 'Tell your story and showcase your restaurant heritage.', doctype: 'Legacy Content', required: false, customComponent: 'LegacyContentStep' },
  ]

  // Filter steps based on current plan
  const steps = useMemo(() => {
    return allPotentialSteps
  }, [allPotentialSteps])

  // Get setup progress from backend
  const { data: progressData, mutate: refreshProgress } = useFrappeGetCall<SetupProgressResponse>(
    'flamezo_backend.flamezo.api.ui.get_restaurant_setup_progress',
    { restaurant_id: selectedRestaurant || '' },
    selectedRestaurant ? `restaurant-progress-${selectedRestaurant}` : null
  )

  const progress = progressData?.message || {}
  
  // Local State
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(0)
  const [showProgressModal, setShowProgressModal] = useState(false)
  const [formHasChanges, setFormHasChanges] = useState(false)
  const [triggerSave, setTriggerSave] = useState(0)

  // Sync currentStepIndex with URL and Plan Changes
  useEffect(() => {
    if (steps.length === 0) return

    const targetIdFromUrl = urlSlug ? slugToStepId(urlSlug) : null
    const foundIndex = targetIdFromUrl ? steps.findIndex(s => s.id === targetIdFromUrl) : -1

    if (foundIndex !== -1) {
      setCurrentStepIndex(foundIndex)
    } else {
      // Default to first step if URL is invalid for current plan
      const firstStepSlug = stepIdToSlug(steps[0].id)
      navigate(`/setup/${firstStepSlug}`, { replace: true })
      setCurrentStepIndex(0)
    }
  }, [urlSlug, steps, navigate])

  const currentStep = steps[currentStepIndex] || steps[0]

  const handleNext = () => {
    
    if (currentStepIndex < steps.length - 1) {
      const nextIndex = currentStepIndex + 1
      navigate(`/setup/${stepIdToSlug(steps[nextIndex].id)}`)
    } else {
      toast.success('Awesome! Setup completed.', {
        description: 'You can always return here to update your settings.'
      })
      navigate('/dashboard')
    }
  }

  const handlePrevious = () => {
    
    if (currentStepIndex > 0) {
      const prevIndex = currentStepIndex - 1
      navigate(`/setup/${stepIdToSlug(steps[prevIndex].id)}`)
    }
  }

  const handleStepClick = (index: number) => {
    navigate(`/setup/${stepIdToSlug(steps[index].id)}`)
    setShowProgressModal(false)
  }

  const completedCount = useMemo(() => {
    return steps.filter(s => progress[s.id] || (s.id === 'restaurant' && selectedRestaurant)).length
  }, [steps, progress, selectedRestaurant])

  const progressPercentage = (completedCount / steps.length) * 100

  // Plan Badge UI
  const PlanBadge = () => {
    if (isGold) return <Badge className="bg-gradient-to-r from-indigo-600 to-blue-600 text-white border-none shadow-lg gap-1 px-3 py-1"><Zap className="w-3.5 h-3.5" /> GOLD Growth</Badge>
    return <Badge className="bg-gradient-to-r from-amber-500 to-orange-500 text-white border-none shadow-lg gap-1 px-3 py-1"><Star className="w-3.5 h-3.5" /> SILVER Foundation</Badge>
  }

  if (contextLoading || !steps.length || (restaurants.length > 0 && !selectedRestaurant)) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <Loader2 className="w-10 h-10 animate-spin text-primary" />
        <p className="text-muted-foreground animate-pulse">Synchronizing your dashboard...</p>
      </div>
    )
  }

  if (!selectedRestaurant && currentStepIndex > 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-6 text-center max-w-md mx-auto">
        <div className="w-20 h-20 bg-muted rounded-full flex items-center justify-center">
          <ArrowLeft className="w-10 h-10 text-muted-foreground" />
        </div>
        <div className="space-y-2">
          <h2 className="text-2xl font-bold">Selection Required</h2>
          <p className="text-muted-foreground">Please select a restaurant to continue with the setup process.</p>
        </div>
        <Button onClick={() => navigate(`/setup/${stepIdToSlug('restaurant')}`)} variant="outline" className="rounded-full">Back to Restaurant Profile</Button>
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto space-y-8 pb-20">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 px-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-3">
             <h1 className="text-3xl sm:text-4xl font-black tracking-tight text-foreground">Setup Wizard</h1>
             <PlanBadge />
          </div>
          <p className="text-sm sm:text-base text-muted-foreground max-w-lg">
            Let's get your {planType.toLowerCase()} experience ready. Follow these steps to unlock full potential.
          </p>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="text-right hidden sm:block">
            <p className="text-sm font-bold">{Math.round(progressPercentage)}% Complete</p>
            <p className="text-[10px] text-muted-foreground uppercase tracking-widest">{completedCount} of {steps.length} steps</p>
          </div>
          <Button 
            variant="outline" 
            className="rounded-2xl border-primary/20 hover:bg-primary/5 transition-all shadow-sm h-14 px-6 flex flex-col items-center gap-0"
            onClick={() => setShowProgressModal(true)}
          >
            <div className="flex gap-1 mb-1">
              {steps.map((_, i) => (
                <div key={i} className={cn(
                  "w-1.5 h-1.5 rounded-full",
                  i < completedCount ? "bg-primary" : "bg-muted"
                )} />
              ))}
            </div>
            <span className="text-[10px] uppercase font-bold tracking-tight">View Journey</span>
          </Button>
        </div>
      </div>

      {/* Main Content Card */}
      <Card className="border-none shadow-2xl shadow-primary/5 overflow-hidden rounded-2xl sm:rounded-[2rem] bg-card/50 backdrop-blur-sm border border-white/10">
        <CardHeader className="p-4 sm:p-8 sm:pb-4 border-b border-white/5 space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold text-primary bg-primary/10 px-2 py-0.5 rounded-full uppercase tracking-wider">Step {currentStepIndex + 1}</span>
                <CardTitle className="text-xl sm:text-2xl font-bold">{currentStep.title}</CardTitle>
              </div>
              <CardDescription className="text-sm sm:text-base text-foreground/70">{currentStep.description}</CardDescription>
            </div>
            
            <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={handlePrevious} 
                disabled={currentStepIndex === 0}
                className="text-muted-foreground hover:text-foreground h-9"
              >
                <ArrowLeft className="w-4 h-4 mr-1 sm:mr-2" /> <span className="text-xs sm:text-sm">Prev</span>
              </Button>
              <Button variant="ghost" size="sm" onClick={() => handleNext()} className="text-muted-foreground hover:text-foreground h-9 text-xs sm:text-sm">Skip</Button>
              {formHasChanges ? (
                <Button 
                  onClick={() => setTriggerSave(prev => prev + 1)}
                  className="bg-primary hover:bg-primary/90 text-white rounded-xl shadow-lg shadow-primary/20 px-4 sm:px-6 h-9 sm:h-auto"
                >
                  <Check className="w-4 h-4 mr-1 sm:mr-2" /> <span className="text-xs sm:text-sm">Save</span>
                </Button>
              ) : (
                <Button 
                  onClick={handleNext}
                  className="rounded-xl shadow-md px-4 sm:px-6 h-9 sm:h-auto"
                >
                  <span className="text-xs sm:text-sm">{currentStepIndex === steps.length - 1 ? 'Finish' : 'Next'}</span> <ArrowRight className="w-4 h-4 ml-1 sm:mr-2" />
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        
        <CardContent className="p-0">
           {/* Minimalist Box-like Segmented Progress */}
           <div className="px-4 sm:px-8 pt-3 pb-0 flex gap-1 w-full">
             {steps.map((_, i) => (
                <div 
                  key={i} 
                  className={cn(
                    "h-1.5 flex-1 rounded-sm transition-all duration-500",
                    i <= currentStepIndex ? "bg-primary" : "bg-muted/10 border border-black/5"
                  )} 
                />
             ))}
           </div>
           <div className="p-4 sm:p-8">
              {/* Conditional Step Rendering */}
              {currentStep.customComponent === 'StaffMembersList' ? (
                <StaffMembersList 
                  key={`wizard-staff-${currentStep.id}-${selectedRestaurant}`}
                  restaurantId={selectedRestaurant || ''} 
                  onAdd={() => refreshProgress?.()} 
                />
              ) : currentStep.customComponent === 'LegacyContentStep' ? (
                <LegacyContentStep 
                  key={`wizard-legacy-${currentStep.id}-${selectedRestaurant}`}
                  selectedRestaurant={selectedRestaurant ?? ''} 
                  onComplete={() => {
                    refreshProgress?.()
                    handleNext()
                  }} 
                />
              ) : currentStep.view_only ? (
                <RestaurantDataList 
                  doctype={currentStep.doctype} 
                  restaurantId={selectedRestaurant || ''} 
                  titleField={currentStep.id === 'categories' ? 'category_name' : 'product_name'} 
                />
              ) : (
                <DynamicForm
                  key={`wizard-form-${selectedRestaurant}`}
                  doctype={currentStep.doctype}
                  docname={(currentStep.id === 'restaurant' || currentStep.id === 'config') ? (selectedRestaurant ?? undefined) : undefined}
                  initialData={{ restaurant: selectedRestaurant }}
                  readOnlyFields={['restaurant']}
                  mode={((currentStep.id === 'restaurant' || currentStep.id === 'config') && selectedRestaurant) ? 'edit' : 'create'}
                  onChange={setFormHasChanges}
                  onSave={(data) => {
                    if (currentStep.id === 'restaurant') {
                      setSelectedRestaurant(data.name || selectedRestaurant)
                    }
                    refreshProgress?.()
                    setFormHasChanges(false)
                    toast.success(`${currentStep.title} saved successfully!`)
                  }}
                  triggerSave={triggerSave}
                  showSaveButton={false}
                  hideFields={
                    (currentStep.id === 'restaurant' || currentStep.id === 'config')
                      ? getHiddenFields(currentStep.id, planType)
                      : []
                  }
                />
              )}
           </div>
        </CardContent>
      </Card>



      {/* Progress Journey Dialog */}
      <Dialog open={showProgressModal} onOpenChange={setShowProgressModal}>
        <DialogContent className="sm:max-w-2xl bg-background/95 backdrop-blur-xl border-white/10 rounded-[2.5rem] p-10 shadow-2xl">
          <div className="space-y-8">
            <div className="text-center space-y-2">
              <h1 className="text-6xl font-black text-primary tracking-tighter">{Math.round(progressPercentage)}%</h1>
              <p className="text-muted-foreground uppercase tracking-[0.3em] text-xs font-bold">Your Success Journey</p>
            </div>
            
            <div className="space-y-4">
              <div className="flex justify-between text-xs font-bold uppercase tracking-wider text-muted-foreground">
                <span>Progress</span>
                <span>{completedCount} / {steps.length} Steps</span>
              </div>
              <Progress value={progressPercentage} className="h-2 rounded-full bg-primary/10" />
            </div>

            <div className="pt-4">
              <Stepper 
                steps={steps.map((s, i) => ({ 
                  ...s, 
                  completed: !!(progress[s.id] || (s.id === 'restaurant' && selectedRestaurant)), 
                  active: i === currentStepIndex 
                }))} 
                currentStep={currentStepIndex} 
                onStepClick={handleStepClick} 
              />
            </div>

            <Button 
              className="w-full rounded-2xl h-14 text-lg font-bold shadow-xl shadow-primary/10"
              onClick={() => setShowProgressModal(false)}
            >
              Continue My Journey
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
