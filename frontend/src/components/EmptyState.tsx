import { LucideIcon, BarChart3 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description: string
  action?: {
    label: string
    onClick: () => void
  }
  secondaryAction?: {
    label: string
    onClick: () => void
  }
  variant?: 'default' | 'compact' | 'chart'
  className?: string
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  secondaryAction,
  variant = 'default',
  className
}: EmptyStateProps) {
  if (variant === 'chart') {
    return (
      <div className={cn("flex flex-col items-center justify-center p-8 min-h-[200px] relative overflow-hidden group", className)}>
        <div className="absolute inset-0 opacity-[0.03] flex items-center justify-center pointer-events-none group-hover:opacity-[0.05] transition-opacity">
           <BarChart3 className="w-48 h-48 rotate-12 text-foreground" />
        </div>
        <div className="relative z-10 text-center space-y-2">
          <div className="h-12 w-12 bg-muted/40 rounded-full flex items-center justify-center mx-auto mb-2 border border-border/40">
            {Icon ? <Icon className="h-6 w-6 text-muted-foreground/50" /> : <BarChart3 className="h-6 w-6 text-muted-foreground/50" />}
          </div>
          <h4 className="text-sm font-bold text-muted-foreground/60 tracking-tight">{title}</h4>
          <p className="text-[11px] text-muted-foreground/40 italic max-w-[200px] mx-auto leading-relaxed">{description}</p>
        </div>
      </div>
    )
  }

  if (variant === 'compact') {
    return (
      <div className={cn("flex items-center gap-4 p-4 rounded-xl bg-muted/10 border border-border/20", className)}>
         <div className="h-10 w-10 bg-muted/30 rounded-full flex items-center justify-center shrink-0">
           {Icon && <Icon className="h-5 w-5 text-muted-foreground/60" />}
         </div>
         <div className="space-y-0.5">
           <p className="text-xs font-bold text-muted-foreground/70">{title}</p>
           <p className="text-[10px] text-muted-foreground/50 italic leading-tight">{description}</p>
         </div>
      </div>
    )
  }

  return (
    <div className={cn("flex flex-col items-center justify-center py-16 px-4", className)}>
      {Icon && (
        <div className="mb-4 rounded-full bg-gradient-to-br from-muted/50 to-muted p-6 shadow-inner border border-white/5">
          <Icon className="h-12 w-12 text-muted-foreground/70" />
        </div>
      )}
      <h3 className="text-lg font-bold text-foreground/80 mb-2 tracking-tight">{title}</h3>
      <p className="text-sm text-muted-foreground/60 text-center max-w-md mb-6 leading-relaxed">
        {description}
      </p>
      {(action || secondaryAction) && (
        <div className="flex flex-col sm:flex-row gap-3">
          {action && (
            <Button onClick={action.onClick} size="default" className="rounded-full px-6 shadow-lg shadow-primary/20">
              {action.label}
            </Button>
          )}
          {secondaryAction && (
            <Button onClick={secondaryAction.onClick} variant="outline" size="default" className="rounded-full px-6">
              {secondaryAction.label}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
