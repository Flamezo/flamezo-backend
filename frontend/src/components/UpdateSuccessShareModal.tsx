import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { NumberInput } from '@/components/ui/number-input'
import { Label } from '@/components/ui/label'

/**
 * Shown after flipping a merchant's Signature toggle (either direction) in
 * the Merchant Management table or the merchant details page. Signature
 * status and Success Share rate are related but separate decisions — the
 * toggle no longer auto-changes the rate, this modal is the explicit,
 * visible prompt to update it, defaulting to "leave it as-is" (Skip).
 */
interface UpdateSuccessShareModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  merchantName: string
  currentRate: number
  onConfirm: (newRate: number) => void | Promise<void>
  isSaving?: boolean
}

export function UpdateSuccessShareModal({
  open,
  onOpenChange,
  merchantName,
  currentRate,
  onConfirm,
  isSaving = false,
}: UpdateSuccessShareModalProps) {
  const [rate, setRate] = useState(currentRate)

  // Reset to the current rate every time the modal opens for a (possibly
  // different) merchant — never carry over a stale draft value.
  useEffect(() => {
    if (open) setRate(currentRate)
  }, [open, currentRate])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Update Success Share?</DialogTitle>
          <DialogDescription>
            {merchantName}'s Signature status just changed. Current Success Share is <strong>{currentRate}%</strong>.
            Set a new rate below, or skip to leave it unchanged.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 py-2">
          <Label htmlFor="update-success-share-rate">Success Share (%)</Label>
          <NumberInput
            id="update-success-share-rate"
            value={rate}
            onChange={(e) => setRate(parseFloat(e.target.value) || 0)}
            disabled={isSaving}
          />
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>
            Skip
          </Button>
          <Button onClick={() => onConfirm(rate)} disabled={isSaving || rate === currentRate}>
            {isSaving ? 'Saving…' : 'Update rate'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
