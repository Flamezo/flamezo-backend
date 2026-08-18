import * as React from "react"
import { Clock } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

interface TimePickerProps {
  id?: string
  value?: string // HH:mm:ss
  onChange?: (e: { target: { value: string } }) => void
  label?: string
  required?: boolean
  disabled?: boolean
  className?: string
}

type View = "hours" | "minutes"

export function TimePicker({
  id,
  value = "",
  onChange,
  label,
  required,
  disabled,
  className
}: TimePickerProps) {
  const [isOpen, setIsOpen] = React.useState(false)
  const [view, setView] = React.useState<View>("hours")

  // Parse value (format: HH:mm:ss)
  const { hour, minute, period } = React.useMemo(() => {
    if (!value) return { hour: 12, minute: 0, period: "AM" }
    const [h, m] = value.split(":")
    const hNum = parseInt(h)
    const period = hNum >= 12 ? "PM" : "AM"
    const displayHour = hNum % 12 || 12
    return {
      hour: displayHour,
      minute: parseInt(m) || 0,
      period
    }
  }, [value])

  const updateTime = (h: number, m: number, p: string) => {
    let finalH = h
    if (p === "PM" && h < 12) finalH += 12
    if (p === "AM" && h === 12) finalH = 0
    
    const formattedTime = `${String(finalH).padStart(2, "0")}:${String(m).padStart(2, "0")}:00`
    onChange?.({ target: { value: formattedTime } } as any)
  }

  const handleSelect = (val: number) => {
    if (view === "hours") {
      updateTime(val, minute, period)
      setView("minutes")
    } else {
      updateTime(hour, val, period)
    }
  }

  const togglePeriod = (p: string) => {
    updateTime(hour, minute, p)
  }

  return (
    <div className={cn("space-y-2 w-full", className)}>
      {label && (
        <Label htmlFor={id} className="text-sm font-medium">
          {label}
          {required && <span className="text-destructive ml-1">*</span>}
        </Label>
      )}
      <Popover open={isOpen} onOpenChange={(open) => {
        setIsOpen(open)
        if (open) setView("hours")
      }}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            className={cn(
              "w-full justify-start text-left font-normal h-9 px-3 transition-all",
              "hover:border-primary/50 focus:ring-1 focus:ring-primary/20",
              !value && "text-muted-foreground",
              disabled && "opacity-50 cursor-not-allowed"
            )}
            disabled={disabled}
          >
            <Clock className="mr-2 h-4 w-4 text-primary" />
            <span className="font-medium">
              {value ? `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")} ${period}` : "Select time"}
            </span>
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[248px] p-0 rounded-xl overflow-hidden shadow-2xl border-primary/10" align="start" collisionPadding={12}>
          <div className="bg-primary text-primary-foreground p-3 flex flex-col items-center gap-1">
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setView("hours")}
                className={cn(
                  "text-3xl font-bold transition-opacity",
                  view === "hours" ? "opacity-100" : "opacity-50 hover:opacity-80"
                )}
              >
                {String(hour).padStart(2, "0")}
              </button>
              <span className="text-3xl font-light opacity-50">:</span>
              <button
                type="button"
                onClick={() => setView("minutes")}
                className={cn(
                  "text-3xl font-bold transition-opacity",
                  view === "minutes" ? "opacity-100" : "opacity-50 hover:opacity-80"
                )}
              >
                {String(minute).padStart(2, "0")}
              </button>
              <div className="ml-3 flex flex-col gap-1">
                <button
                  type="button"
                  onClick={() => togglePeriod("AM")}
                  className={cn(
                    "text-sm font-bold px-3 py-1 rounded-md transition-colors",
                    period === "AM" ? "bg-white text-primary shadow-sm" : "bg-white/15 text-white/80 hover:bg-white/25"
                  )}
                >
                  AM
                </button>
                <button
                  type="button"
                  onClick={() => togglePeriod("PM")}
                  className={cn(
                    "text-sm font-bold px-3 py-1 rounded-md transition-colors",
                    period === "PM" ? "bg-white text-primary shadow-sm" : "bg-white/15 text-white/80 hover:bg-white/25"
                  )}
                >
                  PM
                </button>
              </div>
            </div>
          </div>

          <div className="p-4 bg-background">
            <ClockDial
              view={view}
              value={view === "hours" ? hour : minute}
              onSelect={handleSelect}
            />
          </div>

          <div className="px-4 py-3 bg-muted/50 border-t flex justify-end gap-2">
             <Button type="button" variant="ghost" size="sm" onClick={() => setIsOpen(false)} className="font-semibold text-primary">OK</Button>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}

function ClockDial({ view, value, onSelect }: { view: View, value: number, onSelect: (val: number) => void }) {
  const dialRef = React.useRef<HTMLDivElement>(null)
  const isDragging = React.useRef(false)

  const items = React.useMemo(() => {
    if (view === "hours") {
      return Array.from({ length: 12 }, (_, i) => i + 1)
    }
    return Array.from({ length: 12 }, (_, i) => i * 5)
  }, [view])

  const calculateValueFromCoords = (x: number, y: number) => {
    if (!dialRef.current) return
    const rect = dialRef.current.getBoundingClientRect()
    const centerX = rect.width / 2
    const centerY = rect.height / 2
    const dx = x - rect.left - centerX
    const dy = y - rect.top - centerY
    
    // Angle in degrees (0 is top, 90 is right)
    let angle = (Math.atan2(dy, dx) * 180) / Math.PI + 90
    if (angle < 0) angle += 360

    if (view === "hours") {
      const h = Math.round(angle / 30) || 12
      return h > 12 ? 12 : h
    } else {
      const m = Math.round(angle / 6) % 60
      return m
    }
  }

  const handleInteraction = (e: React.MouseEvent | React.TouchEvent) => {
    const clientX = "touches" in e ? e.touches[0].clientX : e.clientX
    const clientY = "touches" in e ? e.touches[0].clientY : e.clientY
    const val = calculateValueFromCoords(clientX, clientY)
    if (val !== undefined) onSelect(val)
  }

  const handleMouseDown = (e: React.MouseEvent) => {
    isDragging.current = true
    handleInteraction(e)
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging.current) handleInteraction(e)
  }

  const handleMouseUp = () => {
    isDragging.current = false
  }

  // Calculate rotation for the hand
  const rotation = view === "hours" 
    ? (value % 12) * 30 
    : value * 6

  return (
    <div 
      ref={dialRef}
      className="relative w-[176px] h-[176px] rounded-full bg-muted/30 mx-auto select-none touch-none"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onTouchStart={handleInteraction}
      onTouchMove={handleInteraction}
    >
      {/* Center Dot */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-primary z-20" />
      
      {/* Hand */}
      <div 
        className="absolute top-1/2 left-1/2 w-0.5 bg-primary origin-bottom transition-transform duration-200 ease-out pointer-events-none"
        style={{
          height: "62px",
          transform: `translate(-50%, -100%) rotate(${rotation}deg)`
        }}
      >
        <div className="absolute -top-4 left-1/2 -translate-x-1/2 w-8 h-8 rounded-full bg-primary opacity-20" />
        <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-primary" />
      </div>

      {/* Numbers */}
      {items.map((item, i) => {
        const angle = (view === "hours" ? item * 30 : (i * 5) * 6) - 90
        const radian = (angle * Math.PI) / 180
        const radius = 62 // Optimized radius for better alignment
        const x = Math.cos(radian) * radius
        const y = Math.sin(radian) * radius
        
        const isSelected = value === item

        return (
          <div
            key={item}
            className={cn(
              "absolute w-8 h-8 flex items-center justify-center rounded-full text-sm font-medium transition-colors cursor-default z-10",
              isSelected ? "text-primary-foreground font-bold" : "text-muted-foreground hover:text-foreground"
            )}
            style={{ 
              left: `calc(50% + ${x}px)`,
              top: `calc(50% + ${y}px)`,
              transform: "translate(-50%, -50%)"
            }}
          >
            {view === "hours" ? item : String(item).padStart(2, "0")}
          </div>
        )
      })}
    </div>
  )
}
