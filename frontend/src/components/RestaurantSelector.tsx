import * as React from "react"
import { Check, ChevronsUpDown, Search } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Input } from "@/components/ui/input"

interface RestaurantOption {
  value: string
  label: string
}

interface RestaurantSelectorProps {
  options: RestaurantOption[]
  value: string
  onSelect: (value: string) => void
  placeholder?: string
  disabled?: boolean
}

export function RestaurantSelector({
  options,
  value,
  onSelect,
  placeholder = "Select restaurant...",
  disabled = false
}: RestaurantSelectorProps) {
  const [open, setOpen] = React.useState(false)
  const [searchQuery, setSearchQuery] = React.useState("")

  const filteredOptions = options.filter((option) =>
    option.label.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const selectedOption = options.find((option) => option.value === value)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className="w-full justify-between h-10 rounded-xl px-4 font-medium border-muted/60"
        >
          {selectedOption ? selectedOption.label : placeholder}
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0 rounded-2xl border border-white/5 shadow-2xl overflow-hidden bg-[#1c1c1c] text-white">
        <div className="flex items-center px-3 border-b border-white/5 bg-white/5">
          <Search className="mr-2 h-4 w-4 shrink-0 text-muted-foreground" />
          <Input
            placeholder="Search restaurants..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex h-11 w-full border-none bg-transparent py-3 text-sm text-white outline-none placeholder:text-muted-foreground focus-visible:ring-0"
          />
        </div>
        <div 
          className="max-h-[300px] overflow-y-auto p-1 bg-[#1c1c1c] custom-scrollbar touch-pan-y"
          onWheel={(e) => e.stopPropagation()}
        >
          {filteredOptions.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No restaurant found.
            </div>
          ) : (
            filteredOptions.map((option) => (
              <div
                key={option.value}
                onClick={() => {
                  onSelect(option.value)
                  setOpen(false)
                  setSearchQuery("")
                }}
                className={cn(
                  "relative flex cursor-pointer select-none items-center rounded-lg px-3 py-2.5 text-sm outline-none transition-colors",
                  "hover:bg-primary/20 hover:text-white",
                  value === option.value ? "bg-primary/20 text-white font-bold" : "text-white/80"
                )}
              >
                <Check
                  className={cn(
                    "mr-2 h-4 w-4",
                    value === option.value ? "opacity-100" : "opacity-0"
                  )}
                />
                <span className="truncate">{option.label}</span>
              </div>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
