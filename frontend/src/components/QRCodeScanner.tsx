import { useState, useRef, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { QrCode, Camera, X, CheckCircle2, Loader2, ZapOff, Hash } from 'lucide-react'
import { toast } from 'sonner'
import { useFrappePostCall } from '@/lib/frappe'

interface QRCodeScannerProps {
  onScan: (tableNumber: number, restaurantId: string) => void
  restaurantId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

type ScanState = 'idle' | 'scanning' | 'success' | 'error'

export default function QRCodeScanner({ onScan, restaurantId, open, onOpenChange }: QRCodeScannerProps) {
  const [manualInput, setManualInput] = useState('')
  const [scanState, setScanState] = useState<ScanState>('idle')
  const [scanMessage, setScanMessage] = useState('')
  const [detectedCode, setDetectedCode] = useState('')
  const [cameraError, setCameraError] = useState<string | null>(null)

  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const animFrameRef = useRef<number | null>(null)
  const processingRef = useRef(false)

  const { call: parseQrCode } = useFrappePostCall('flamezo_backend.flamezo.api.cart.parse_qr_code')

  // Full cleanup on close
  const stopCamera = useCallback(() => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
    if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop())
    animFrameRef.current = null
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    setScanState('idle')
    processingRef.current = false
  }, [])

  useEffect(() => {
    if (!open) {
      stopCamera()
      setManualInput('')
      setScanMessage('')
      setDetectedCode('')
      setCameraError(null)
    }
  }, [open, stopCamera])

  useEffect(() => () => stopCamera(), [stopCamera])

  // ─── Real QR decode loop using jsQR ────────────────────────────────────────
  const tickScan = useCallback(async () => {
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas || video.readyState < 2 || processingRef.current) {
      animFrameRef.current = requestAnimationFrame(tickScan)
      return
    }

    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx) {
      animFrameRef.current = requestAnimationFrame(tickScan)
      return
    }

    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)

    // Dynamically import jsQR to avoid SSR issues
    try {
      const jsQR = (await import('jsqr')).default
      const qrResult = jsQR(imageData.data, imageData.width, imageData.height, {
        inversionAttempts: 'dontInvert',
      })

      if (qrResult && !processingRef.current) {
        processingRef.current = true
        setDetectedCode(qrResult.data)
        setScanState('scanning')
        setScanMessage('QR code detected — validating…')
        await handleParseQrCode(qrResult.data)
        return // stop loop after successful scan
      }
    } catch {
      // jsQR decode error — continue scanning
    }

    animFrameRef.current = requestAnimationFrame(tickScan)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const startCamera = async () => {
    setCameraError(null)
    setScanState('scanning')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      // Start the decode loop
      animFrameRef.current = requestAnimationFrame(tickScan)
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Camera access denied'
      setCameraError(msg)
      setScanState('error')
      toast.error('Camera Error', { description: msg })
    }
  }

  const handleParseQrCode = async (qrDataValue: string) => {
    if (!qrDataValue.trim()) return
    try {
      const response: any = await parseQrCode({ qr_data: qrDataValue.trim() })

      if (response?.message?.success && response?.message?.data) {
        const { restaurantId: parsedId, tableNumber } = response.message.data

        if (parsedId !== restaurantId) {
          setScanState('error')
          setScanMessage(`QR code belongs to a different restaurant (${parsedId})`)
          toast.error('Wrong Restaurant', {
            description: `This QR code is for "${parsedId}", not your current restaurant.`,
          })
          processingRef.current = false
          // Resume scanning
          animFrameRef.current = requestAnimationFrame(tickScan)
          return
        }

        setScanState('success')
        setScanMessage(`✓ Table ${tableNumber} validated`)
        onScan(tableNumber, parsedId)
        onOpenChange(false)
        toast.success(`Table ${tableNumber} scanned!`)
      } else {
        const errMsg = response?.message?.error?.message || 'Invalid QR code'
        setScanState('error')
        setScanMessage(errMsg)
        toast.error('Invalid QR Code', { description: errMsg })
        processingRef.current = false
        // Resume scanning loop after brief pause
        setTimeout(() => {
          if (streamRef.current) animFrameRef.current = requestAnimationFrame(tickScan)
        }, 1500)
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Parse failed'
      setScanState('error')
      setScanMessage(msg)
      processingRef.current = false
      setTimeout(() => {
        if (streamRef.current) animFrameRef.current = requestAnimationFrame(tickScan)
      }, 1500)
    }
  }

  const handleManualSubmit = () => {
    if (!manualInput.trim()) return
    const input = manualInput.trim()
    // If just a number, treat as table number for this restaurant
    const asNum = parseInt(input, 10)
    if (!isNaN(asNum) && String(asNum) === input) {
      handleParseQrCode(`${restaurantId}/${asNum}`)
    } else {
      handleParseQrCode(input)
    }
  }

  const handleClose = () => {
    stopCamera()
    onOpenChange(false)
    setManualInput('')
    setScanMessage('')
    setDetectedCode('')
    setCameraError(null)
  }

  const isStreaming = !!streamRef.current

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <QrCode className="h-5 w-5 text-primary" />
            Scan Table QR Code
          </DialogTitle>
          <DialogDescription>
            Point your camera at a table QR code, or enter the table number manually
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Camera viewport */}
          <div className="relative bg-black rounded-xl overflow-hidden aspect-video border border-border">
            {/* Hidden canvas for jsQR pixel extraction */}
            <canvas ref={canvasRef} className="hidden" />

            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className={`w-full h-full object-cover transition-opacity duration-300 ${isStreaming ? 'opacity-100' : 'opacity-0'}`}
            />

            {/* Scanning overlay with animated finder frame */}
            {isStreaming && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="relative w-48 h-48">
                  {/* Corner brackets */}
                  <div className="absolute top-0 left-0 w-8 h-8 border-t-4 border-l-4 border-primary rounded-tl-md" />
                  <div className="absolute top-0 right-0 w-8 h-8 border-t-4 border-r-4 border-primary rounded-tr-md" />
                  <div className="absolute bottom-0 left-0 w-8 h-8 border-b-4 border-l-4 border-primary rounded-bl-md" />
                  <div className="absolute bottom-0 right-0 w-8 h-8 border-b-4 border-r-4 border-primary rounded-br-md" />
                  {/* Scan line */}
                  <div className="absolute inset-x-0 top-1/2 h-0.5 bg-primary/70 animate-pulse" />
                </div>
              </div>
            )}

            {/* Status badge overlay */}
            {isStreaming && scanState !== 'idle' && (
              <div className="absolute bottom-3 inset-x-3 flex justify-center">
                <Badge
                  variant={scanState === 'success' ? 'default' : scanState === 'error' ? 'destructive' : 'secondary'}
                  className="gap-1.5 text-xs px-3 py-1.5"
                >
                  {scanState === 'scanning' && <Loader2 className="h-3 w-3 animate-spin" />}
                  {scanState === 'success' && <CheckCircle2 className="h-3 w-3" />}
                  {scanState === 'error' && <ZapOff className="h-3 w-3" />}
                  {scanMessage || 'Scanning…'}
                </Badge>
              </div>
            )}

            {/* Idle / start state */}
            {!isStreaming && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/80">
                {cameraError ? (
                  <div className="text-center px-4 space-y-2">
                    <ZapOff className="h-10 w-10 text-destructive mx-auto" />
                    <p className="text-sm text-white/80">{cameraError}</p>
                    <Button size="sm" variant="outline" onClick={startCamera} className="mt-1">
                      Retry Camera
                    </Button>
                  </div>
                ) : (
                  <>
                    <Camera className="h-10 w-10 text-white/50" />
                    <p className="text-sm text-white/60">Camera not started</p>
                    <Button size="sm" onClick={startCamera} className="gap-2">
                      <Camera className="h-4 w-4" />
                      Start Camera
                    </Button>
                  </>
                )}
              </div>
            )}

            {/* Stop button */}
            {isStreaming && (
              <Button
                variant="destructive"
                size="icon"
                className="absolute top-2 right-2 h-8 w-8 rounded-full opacity-80 hover:opacity-100"
                onClick={stopCamera}
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>

          {/* Detected raw value (debug/info) */}
          {detectedCode && (
            <p className="text-[11px] text-muted-foreground truncate px-1">
              <span className="font-medium">Detected:</span> {detectedCode}
            </p>
          )}

          {/* Divider */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-border" />
            <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">or enter manually</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          {/* Manual table number input */}
          <div className="space-y-2">
            <Label htmlFor="table-manual-input" className="flex items-center gap-1.5">
              <Hash className="h-3.5 w-3.5 text-muted-foreground" />
              Table Number
            </Label>
            <div className="flex gap-2">
              <NumberInput
                id="table-manual-input"
                
                min="1"
                placeholder="e.g. 5"
                value={manualInput}
                onChange={(e) => setManualInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleManualSubmit() }}
                className="flex-1"
              />
              <Button
                onClick={handleManualSubmit}
                disabled={!manualInput.trim() || scanState === 'scanning'}
              >
                {scanState === 'scanning' && processingRef.current ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  'Submit'
                )}
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Enter just the table number (e.g. <code className="bg-muted px-1 rounded">5</code>) — or paste a full QR URL
            </p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
