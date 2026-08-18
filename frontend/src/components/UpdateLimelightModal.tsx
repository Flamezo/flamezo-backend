import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'

interface UpdateLimelightModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  merchantName: string
  onConfirm: (startDate: string, endDate: string | null) => void | Promise<void>
}

export function UpdateLimelightModal({
  open,
  onOpenChange,
  merchantName,
  onConfirm,
}: UpdateLimelightModalProps) {
  const [startDate, setStartDate] = useState<string>('')
  const [endDate, setEndDate] = useState<string>('')

  // Reset state when opened
  useEffect(() => {
    if (open) {
      const today = new Date().toISOString().split('T')[0]
      setStartDate(today)
      setEndDate('')
    }
  }, [open])

  const handleConfirm = () => {
    const finalEndDate = endDate || null
    onConfirm(startDate, finalEndDate)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Limelight Schedule</DialogTitle>
          <DialogDescription>
            {merchantName} is being added to the Limelight. Specify the duration for this promotion.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="start-date">Start Date</Label>
            <Input
              id="start-date"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="end-date">End Date</Label>
            <Input
              id="end-date"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
            <p className="text-xs text-muted-foreground mt-1">
              Leave End Date blank for an indefinite Limelight promotion.
            </p>
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0 mt-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleConfirm} disabled={!startDate}>
            Set Schedule
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
