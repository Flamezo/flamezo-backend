import { useState, useEffect, useCallback, useRef } from 'react'
import { useFrappeGetDoc, useFrappePostCall, useFrappeUpdateDoc } from '@/lib/frappe'
import { useRestaurant } from '@/contexts/RestaurantContext'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toast } from 'sonner'
import { getFrappeError } from '@/lib/utils'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import {
  QrCode,
  Download,
  Eye,
  Settings,
  Loader2,
  AlertCircle,
  Info,
  Trash2,
  ScanLine,
  BarChart3,
  TrendingUp,
  Grid,
  Layers,
  RefreshCw,
  ImageDown,
  Table2,
  Trophy,
  Activity,
  CalendarDays,
  ChevronDown,
  Upload,
  X,
} from 'lucide-react'
import QRCodeScanner from '@/components/QRCodeScanner'
import { cn } from '@/lib/utils'

// ─── Stat Card ───────────────────────────────────────────────────────────────
function AnalyticStatCard({
  label,
  value,
  sub,
  icon: Icon,
  accent = false,
}: {
  label: string
  value: string | number
  sub?: string
  icon: React.ElementType
  accent?: boolean
}) {
  return (
    <Card className={cn('transition-all hover:shadow-md', accent && 'border-primary/30 bg-primary/5')}>
      <CardContent className="pt-5 pb-4">
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-0.5">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
            <p className={cn('text-2xl font-bold tracking-tight', accent && 'text-primary')}>{value}</p>
            {sub && <p className="text-[11px] text-muted-foreground">{sub}</p>}
          </div>
          <div className={cn('rounded-xl p-2.5', accent ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground')}>
            <Icon className="h-4 w-4" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Per-table QR card with live canvas thumbnail ────────────────────────────
function TableQRCard({
  tableNumber,
  pngUrl,
  svgUrl: _svgUrl,
  qrData: _qrData,
  scanCount,
  onDownloadPng,
  onDownloadSvg,
  customLabel,
}: {
  tableNumber: number
  pngUrl: string
  svgUrl?: string
  qrData?: string
  scanCount?: number
  onDownloadPng: () => void
  onDownloadSvg: () => void
  customLabel?: string
}) {
  const [imgLoaded, setImgLoaded] = useState(false)
  const [showDownloads, setShowDownloads] = useState(false)

  return (
    <Card className="overflow-hidden group hover:shadow-lg transition-all duration-300 border-border/60">
      {/* QR preview */}
      <div className="relative bg-muted/40 aspect-[3/4] flex items-center justify-center overflow-hidden">
        {!imgLoaded && (
          <div className="absolute inset-0 flex items-center justify-center">
            <Skeleton className="w-full h-full" />
          </div>
        )}
        <img
          src={pngUrl}
          alt={customLabel || `Table ${tableNumber} QR code`}
          className={cn(
            'w-full h-full object-contain transition-opacity duration-300 p-2',
            imgLoaded ? 'opacity-100' : 'opacity-0',
          )}
          onLoad={() => setImgLoaded(true)}
          onError={() => setImgLoaded(true)}
        />
        {/* Overlay on hover */}
        <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-2 p-3">
          <Button variant="secondary" size="sm" className="w-full gap-1.5 text-xs" onClick={onDownloadPng}>
            <ImageDown className="h-3.5 w-3.5" />
            Download PNG
          </Button>
          <Button variant="outline" size="sm" className="w-full gap-1.5 text-xs bg-transparent text-white border-white/40 hover:bg-white/10" onClick={onDownloadSvg}>
            <Download className="h-3.5 w-3.5" />
            Download SVG
          </Button>
        </div>
        {/* Scan count badge */}
        {scanCount !== undefined && scanCount > 0 && (
          <div className="absolute top-2 right-2">
            <Badge variant="secondary" className="text-[10px] gap-0.5 px-1.5 py-0.5">
              <Activity className="h-2.5 w-2.5" />
              {scanCount}
            </Badge>
          </div>
        )}
      </div>
      {/* Footer */}
      <div className="px-3 py-2.5 border-t border-border/50 bg-card">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold">{customLabel || `Table ${tableNumber}`}</p>
            {scanCount !== undefined && (
              <p className="text-[11px] text-muted-foreground">{scanCount} scan{scanCount !== 1 ? 's' : ''}</p>
            )}
          </div>
          {/* Mobile download button */}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 relative sm:hidden"
            onClick={() => setShowDownloads((p) => !p)}
          >
            <ChevronDown className={cn('h-4 w-4 transition-transform', showDownloads && 'rotate-180')} />
          </Button>
        </div>
        {showDownloads && (
          <div className="flex gap-2 mt-2 sm:hidden">
            <Button variant="outline" size="sm" className="flex-1 text-xs gap-1" onClick={onDownloadPng}>
              PNG
            </Button>
            <Button variant="outline" size="sm" className="flex-1 text-xs gap-1" onClick={onDownloadSvg}>
              SVG
            </Button>
          </div>
        )}
      </div>
    </Card>
  )
}

// ─── Mini bar chart for daily trend ──────────────────────────────────────────
function MiniBarChart({ data }: { data: { date: string; scanCount: number }[] }) {
  if (!data.length) return <p className="text-sm text-muted-foreground text-center py-4">No scan data yet</p>
  const max = Math.max(...data.map((d) => d.scanCount), 1)
  return (
    <div className="flex items-end gap-1 h-20 w-full">
      {data.map((d) => (
        <div key={d.date} className="flex-1 flex flex-col items-center gap-0.5 group" title={`${d.date}: ${d.scanCount}`}>
          <div
            className="w-full bg-primary/80 rounded-t-sm group-hover:bg-primary transition-all"
            style={{ height: `${Math.max((d.scanCount / max) * 100, 4)}%` }}
          />
          <span className="text-[8px] text-muted-foreground hidden group-hover:block absolute -mt-4 bg-popover px-1 rounded shadow text-nowrap z-10">
            {d.scanCount}
          </span>
        </div>
      ))}
    </div>
  )
}
// ─── Main Page ────────────────────────────────────────────────────────────────
export default function QRCodes() {
  const { selectedRestaurant } = useRestaurant()
  const [baseUrl, setBaseUrl] = useState('')
  const [tables, setTables] = useState(0)
  const [qrCodeUrl, setQrCodeUrl] = useState<string | null>(null)
  const [pdfLayout, setPdfLayout] = useState<'2x2' | '1x1'>('2x2')
  const [isGenerating, setIsGenerating] = useState(false)
  const [isUpdating, setIsUpdating] = useState(false)
  const [showScanner, setShowScanner] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  // Background Upload States
  const [showGenModal, setShowGenModal] = useState(false)
  const [bgFile, setBgFile] = useState<File | null>(null)
  const [bgPreview, setBgPreview] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [isLoadingAssets, setIsLoadingAssets] = useState(false)
  const [tableAssets, setTableAssets] = useState<any[]>([])
  const [analyticsData, setAnalyticsData] = useState<any>(null)
  const [isLoadingAnalytics, setIsLoadingAnalytics] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [activeTab, setActiveTab] = useState('overview')
  const [qrMode, setQrMode] = useState<'dine_in' | 'takeaway'>('dine_in')

  // Fetch restaurant document
  const { data: restaurantDoc, mutate: refreshRestaurant } = useFrappeGetDoc('Restaurant', selectedRestaurant || '', {
    enabled: !!selectedRestaurant,
  })

  // API calls
  const { call: generateQrCodes } = useFrappePostCall('flamezo_backend.flamezo.doctype.restaurant.restaurant.generate_qr_codes_pdf')
  const { call: getQrCodeUrl } = useFrappePostCall('flamezo_backend.flamezo.doctype.restaurant.restaurant.get_qr_codes_pdf_url')
  const { call: deleteQrCodes } = useFrappePostCall('flamezo_backend.flamezo.doctype.restaurant.restaurant.delete_qr_codes_pdf')
  const { call: getTableAssets } = useFrappePostCall('flamezo_backend.flamezo.doctype.restaurant.restaurant.get_table_qr_assets')
  const { call: getSpecialAssets } = useFrappePostCall('flamezo_backend.flamezo.doctype.restaurant.restaurant.get_special_qr_assets')
  const { call: getAnalytics } = useFrappePostCall('flamezo_backend.flamezo.doctype.restaurant.restaurant.get_qr_scan_analytics')
  const { call: getAppSettings } = useFrappePostCall('flamezo_backend.flamezo.utils.config_helpers.get_app_settings')
  const { updateDoc: updateRestaurant } = useFrappeUpdateDoc()

  // Load restaurant + settings on mount
  useEffect(() => {
    if (!restaurantDoc || !selectedRestaurant) return
    async function loadSettings() {
      try {
        const settingsRes: any = await getAppSettings({})
        const globalBaseUrl = settingsRes?.message?.app_base_url
        setBaseUrl(globalBaseUrl || restaurantDoc.base_url || 'https://backend.flamezo.in/')
      } catch {
        setBaseUrl(restaurantDoc.base_url || 'https://backend.flamezo.in/')
      }
      setTables(restaurantDoc.tables || 0)
      if (restaurantDoc.qr_codes_pdf_url) {
        setQrCodeUrl(restaurantDoc.qr_codes_pdf_url)
      } else if (restaurantDoc.tables > 0) {
        loadQrCodeUrl()
      }
    }
    loadSettings()
  }, [restaurantDoc?.name, selectedRestaurant])

  const loadQrCodeUrl = async () => {
    if (!selectedRestaurant) return
    try {
      const response: any = await getQrCodeUrl({ restaurant: selectedRestaurant })
      const msg = response?.message
      const url = typeof msg === 'string' ? msg : msg?.pdf_url ?? null
      setQrCodeUrl(url)
    } catch {
      setQrCodeUrl(null)
    }
  }

  const loadTableAssets = useCallback(async () => {
    if (!selectedRestaurant) return
    setIsLoadingAssets(true)
    try {
      const response: any = qrMode === 'takeaway'
        ? await getSpecialAssets({ restaurant: selectedRestaurant, force: 0 })
        : await getTableAssets({ restaurant: selectedRestaurant, force: 0 })

      const items = response?.message?.items || []
      setTableAssets(items)
    } catch (e) {
      // silent — not fatal
    } finally {
      setIsLoadingAssets(false)
    }
  }, [selectedRestaurant, qrMode])

  const loadAnalytics = useCallback(async () => {
    if (!selectedRestaurant) return
    setIsLoadingAnalytics(true)
    try {
      const res: any = await getAnalytics({ restaurant: selectedRestaurant, days: 30 })
      if (res?.message?.success) {
        setAnalyticsData(res.message.data)
      }
    } catch {
      // silent
    } finally {
      setIsLoadingAnalytics(false)
    }
  }, [selectedRestaurant])

  // Load assets + analytics when switching to dedicated tabs
  useEffect(() => {
    if (activeTab === 'tables' && tableAssets.length === 0) loadTableAssets()
    if (activeTab === 'analytics') loadAnalytics()
  }, [activeTab, loadTableAssets, loadAnalytics])

  // Build per-table scan count map from analytics
  const scanCountMap: Record<string, number> = {}
  if (analyticsData?.perTable) {
    for (const row of analyticsData.perTable) {
      scanCountMap[`table-${row.tableNumber}`] = row.scanCount
    }
  }
  if (analyticsData?.perOrderType) {
    for (const [type, count] of Object.entries(analyticsData.perOrderType)) {
      scanCountMap[`special-${type}`] = count as number
    }
  }

  // ─── Handlers ──────────────────────────────────────────────────────────────
  const handleGenerateQrCodes = async () => {
    if (!selectedRestaurant) return toast.error('Select a restaurant first')
    if (qrMode === 'dine_in' && (!tables || tables <= 0)) {
      return toast.error('Set number of tables first')
    }

    setIsGenerating(true)
    try {
      let finalBgUrl = null

      // 1. Upload background file if provided
      if (bgFile) {
        toast.info('Uploading background image...', { id: 'qr-gen' })

        const formData = new FormData()
        formData.append('file', bgFile)
        formData.append('filename', bgFile.name)
        formData.append('doctype', 'Restaurant')
        formData.append('docname', selectedRestaurant)
        formData.append('is_private', '0')

        const csrf = (window as any).frappe?.csrf_token || (window as any).csrf_token
        const uploadResponse = await fetch('/api/method/upload_file', {
          method: 'POST',
          body: formData,
          headers: { 'X-Frappe-CSRF-Token': csrf },
        })

        if (!uploadResponse.ok) {
          throw new Error('Upload failed: ' + uploadResponse.statusText)
        }

        const uploadJson = await uploadResponse.json()
        finalBgUrl = uploadJson?.message?.file_url ?? null

        if (!finalBgUrl) throw new Error('Upload failed (no file URL returned)')
      }

      toast.info('Generating QR codes PDF...', { id: 'qr-gen' })
      const response: any = await generateQrCodes({
        restaurant: selectedRestaurant,
        layout: pdfLayout,
        background_image: finalBgUrl || undefined,
        qr_type: qrMode
      })

      const msg = response?.message
      const url: string | null = typeof msg === 'string' ? msg : msg?.pdf_url ?? null

      if (url) {
        const finalUrl = url.includes('?') ? `${url}&_t=${Date.now()}` : `${url}?_t=${Date.now()}`
        setQrCodeUrl(finalUrl)
        toast.success(`QR codes generated successfully!`, { id: 'qr-gen' })
        setShowGenModal(false)
        setBgFile(null)
        setBgPreview(null)

        await refreshRestaurant()
        setTableAssets([])
        if (activeTab === 'tables') {
          loadTableAssets()
        }
      }
    } catch (error: any) {
      toast.error('Failed to generate QR codes', {
        id: 'qr-gen',
        description: getFrappeError(error)
      })
    } finally {
      setIsGenerating(false)
    }
  }

  const handleUpdateTables = async () => {
    if (!selectedRestaurant) return
    if (!tables || tables <= 0) return toast.error('Number of tables must be > 0')
    setIsUpdating(true)
    try {
      await updateRestaurant('Restaurant', selectedRestaurant, { tables })
      toast.success('Tables count updated')
      await refreshRestaurant()
      setQrCodeUrl(null)
      setTableAssets([])
    } catch (error: any) {
      toast.error('Failed to update tables', { description: getFrappeError(error) })
    } finally {
      setIsUpdating(false)
    }
  }

  const handleViewQrCodes = () => {
    if (!qrCodeUrl) return
    const url = qrCodeUrl.includes('?') ? `${qrCodeUrl}&_t=${Date.now()}` : `${qrCodeUrl}?_t=${Date.now()}`
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  const handleDownloadQrCodes = () => {
    if (!qrCodeUrl) return
    const link = document.createElement('a')
    link.href = qrCodeUrl
    link.download = `${restaurantDoc?.restaurant_id || 'restaurant'}_qr_codes.pdf`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    toast.success('PDF download started')
  }

  const handleDownloadIndividual = async (asset: any, format: 'png' | 'svg') => {
    const url = format === 'png' ? asset.png_url : asset.svg_url
    if (!url) return toast.error(`${format.toUpperCase()} URL not available`)
    try {
      const response = await fetch(url)
      const blob = await response.blob()
      const objectUrl = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = `table_${asset.table_number}_qr.${format}`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(objectUrl)
      toast.success(`Table ${asset.table_number} QR downloaded (${format.toUpperCase()})`)
    } catch {
      toast.error('Download failed. Opening in new tab instead.')
      window.open(url, '_blank')
    }
  }

  const confirmDeleteQrCodes = async () => {
    if (!selectedRestaurant) return
    setShowDeleteDialog(false)
    setIsDeleting(true)
    try {
      const response: any = await deleteQrCodes({ restaurant: selectedRestaurant })
      const msg = response?.message
      const deleted = typeof msg === 'boolean' ? msg : msg?.status === 'success'
      if (deleted) {
        setQrCodeUrl(null)
        setTableAssets([])
        await refreshRestaurant()
        toast.success('QR codes PDF deleted')
      } else {
        toast.error('Deletion reported failure — check server logs')
      }
    } catch (error: any) {
      toast.error('Failed to delete', { description: getFrappeError(error) })
    } finally {
      setIsDeleting(false)
    }
  }

  // ─── Empty state ───────────────────────────────────────────────────────────
  if (!selectedRestaurant) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Card className="w-full max-w-md">
          <CardContent className="pt-6">
            <div className="flex flex-col items-start gap-4 text-left">
              <AlertCircle className="h-12 w-12 text-muted-foreground" />
              <div>
                <h3 className="text-lg font-semibold">No Restaurant Selected</h3>
                <p className="text-sm text-muted-foreground mt-1">Select a restaurant from the sidebar to manage QR codes</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  const tableCount = restaurantDoc?.tables || 0
  const tablesMatchSaved = tables === tableCount

  // ─── Main render ───────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Manage QR Codes</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Generate, download, and track QR codes for your restaurant tables
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowScanner(true)}
            className="gap-1.5"
          >
            <ScanLine className="h-4 w-4" />
            Scan QR
          </Button>
          {qrCodeUrl && (
            <>
              <Button variant="outline" size="sm" onClick={handleViewQrCodes} className="gap-1.5">
                <Eye className="h-4 w-4" />
                View PDF
              </Button>
              <Button variant="outline" size="sm" onClick={handleDownloadQrCodes} className="gap-1.5">
                <Download className="h-4 w-4" />
                Download PDF
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowDeleteDialog(true)}
                disabled={isDeleting}
                className="gap-1.5 text-destructive hover:text-destructive"
              >
                {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                {isDeleting ? 'Deleting…' : 'Delete PDF'}
              </Button>
            </>
          )}
        </div>
      </div>

      {/* ── Tabs ────────────────────────────────────────────────────────────── */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="overview" className="gap-1.5">
            <Settings className="h-4 w-4" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="tables" className="gap-1.5">
            <Grid className="h-4 w-4" />
            Per-Table
            {tableCount > 0 && (
              <Badge variant="secondary" className="ml-1 text-[10px] px-1.5 py-0">{tableCount}</Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="analytics" className="gap-1.5">
            <BarChart3 className="h-4 w-4" />
            Analytics
          </TabsTrigger>
        </TabsList>

        {/* ══ OVERVIEW TAB ═══════════════════════════════════════════════════ */}
        <TabsContent value="overview" className="space-y-6">
          {/* Quick stats row */}
          {restaurantDoc && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <AnalyticStatCard
                label="Total Tables"
                value={tableCount || '—'}
                sub={tableCount > 0 ? `1 → ${tableCount}` : 'Set below'}
                icon={Table2}
                accent={tableCount > 0}
              />
              <AnalyticStatCard
                label="QR Status"
                value={qrCodeUrl ? 'Ready' : 'Not generated'}
                sub={qrCodeUrl ? 'PDF available' : 'Click Generate'}
                icon={QrCode}
              />
              <AnalyticStatCard
                label="PDF Layout"
                value={pdfLayout === '2x2' ? '2×2 Grid' : 'Single'}
                sub={pdfLayout === '2x2' ? '4 cards / page' : '1 card / page'}
                icon={Layers}
              />
              <AnalyticStatCard
                label="Lifetime Scans"
                value={analyticsData?.lifetimeScans ?? '—'}
                sub="via QR codes"
                icon={Activity}
              />
            </div>
          )}

          {/* Settings card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                QR Code Settings
              </CardTitle>
              <CardDescription>Configure your QR code type and generation preferences</CardDescription>

              <div className="mt-4 inline-flex p-1 bg-muted rounded-lg border border-border/50">
                <Button
                  variant={qrMode === 'dine_in' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setQrMode('dine_in')}
                  className="h-8 rounded-md text-xs"
                >
                  Dine-In (Tables)
                </Button>
                <Button
                  variant={qrMode === 'takeaway' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setQrMode('takeaway')}
                  className="h-8 rounded-md text-xs"
                >
                  Takeaway/Delivery
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Base URL (read-only) */}
              <div className="space-y-1.5">
                <Label>QR Base URL</Label>
                <div className="flex items-center gap-2 px-3 py-2 bg-muted rounded-md text-sm text-muted-foreground font-mono border border-border/50">
                  {baseUrl || '—'}
                </div>
                <p className="text-xs text-muted-foreground">
                  QR codes encode: <code className="bg-muted px-1 rounded">
                    {(baseUrl || 'https://backend.flamezo.in').replace(/\/$/, '')}/restaurant-id
                    {qrMode === 'dine_in' ? '?table_no=N' : '?order_type=takeaway|delivery'}
                  </code>
                </p>
              </div>

              {/* Tables count - only for Dine-In */}
              {qrMode === 'dine_in' && (
                <div className="space-y-2">
                  <Label htmlFor="tables-input">Number of Tables</Label>
                  <div className="flex gap-2">
                    <NumberInput
                      id="tables-input"
                      min="1"
                      max="500"
                      value={tables}
                      onChange={(e: { target: { value: string } }) => setTables(parseInt(e.target.value) || 0)}
                      disabled={isUpdating}
                      className="flex-1 max-w-[140px]"
                    />
                    <Button
                      onClick={handleUpdateTables}
                      disabled={isUpdating || tablesMatchSaved || tables <= 0}
                      variant={tablesMatchSaved ? 'outline' : 'default'}
                    >
                      {isUpdating ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</> : 'Save Tables'}
                    </Button>
                  </div>
                  {/* Quick presets */}
                  <div className="flex gap-2 flex-wrap">
                    {[5, 10, 15, 20, 25, 30, 50].map((n) => (
                      <Button
                        key={n}
                        type="button"
                        variant={tables === n ? 'default' : 'outline'}
                        size="sm"
                        className="h-7 px-3 text-xs"
                        onClick={() => setTables(n)}
                        disabled={isUpdating}
                      >
                        {n}
                      </Button>
                    ))}
                  </div>
                  {!tablesMatchSaved && tables > 0 && (
                    <p className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
                      <AlertCircle className="h-3 w-3" />
                      Save table count before generating QR codes
                    </p>
                  )}
                </div>
              )}

              {/* PDF Layout selector */}
              <div className="space-y-2">
                <Label>PDF Layout</Label>
                <div className="grid grid-cols-2 gap-3 max-w-sm">
                  {(['2x2', '1x1'] as const).map((layout) => (
                    <button
                      key={layout}
                      onClick={() => setPdfLayout(layout)}
                      className={cn(
                        'flex flex-col items-center gap-2 p-3 rounded-xl border-2 text-sm font-medium transition-all',
                        pdfLayout === layout
                          ? 'border-primary bg-primary/5 text-primary'
                          : 'border-border hover:border-primary/40 text-muted-foreground hover:text-foreground',
                      )}
                    >
                      {layout === '2x2' ? (
                        <Grid className="h-6 w-6" />
                      ) : (
                        <Layers className="h-6 w-6" />
                      )}
                      <span className="text-xs">
                        {layout === '2x2' ? '2×2 Grid (4/page)' : 'Single card'}
                      </span>
                      {layout === '2x2' && (
                        <Badge variant="secondary" className="text-[9px] px-1.5">Recommended</Badge>
                      )}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  {pdfLayout === '2x2'
                    ? 'Landscape A4 — 4 QR cards per page. Best for mass printing (saves ~75% paper).'
                    : 'Portrait A4 — 1 QR card per page. Best when printing individual cards.'}
                </p>
              </div>

              {/* Generate button */}
              {(tableCount > 0 || qrMode === 'takeaway') && (
                <div className="pt-2 border-t space-y-3">
                  <Button
                    onClick={() => setShowGenModal(true)}
                    disabled={isGenerating || (qrMode === 'dine_in' && !tablesMatchSaved)}
                    size="lg"
                    className="w-full sm:w-auto gap-2"
                  >
                    {isGenerating ? (
                      <><Loader2 className="h-4 w-4 animate-spin" />Generating QR codes…</>
                    ) : (
                      <><QrCode className="h-4 w-4" />Generate QR Codes PDF</>
                    )}
                  </Button>
                  {(qrMode === 'dine_in' && !tablesMatchSaved) && tables > 0 && (
                    <p className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
                      <AlertCircle className="h-3 w-3" />
                      Save table count before generating table QR codes
                    </p>
                  )}
                  {qrCodeUrl && (qrMode !== 'dine_in' || tablesMatchSaved) && (
                    <p className="text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                      <Activity className="h-3 w-3" />
                      PDF ready — click View PDF or Download PDF in the toolbar above
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* How it works */}
          <Card className="border-primary/20 bg-primary/5">
            <CardContent className="pt-5">
              <div className="flex gap-3">
                <Info className="h-5 w-5 text-primary flex-shrink-0 mt-0.5" />
                <div className="space-y-1.5">
                  <h3 className="font-semibold text-sm">
                    {qrMode === 'dine_in' ? 'How Table QR Codes Work' : 'How Takeaway/Delivery QRs Work'}
                  </h3>
                  <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
                    {qrMode === 'dine_in' ? (
                      <>
                        <li>Each QR encodes a unique URL: <code className="bg-muted px-1 rounded">domain/restaurant-id?table_no=N</code></li>
                        <li>Customers scan → directly land on your full menu with the table pre-selected</li>
                        <li>Table number is auto-attached to every cart item and order</li>
                        <li>Use the <strong>Analytics</strong> tab to see which tables get scanned most</li>
                      </>
                    ) : (
                      <>
                        <li>Each QR encodes an order type: <code className="bg-muted px-1 rounded">domain/restaurant-id?order_type=X</code></li>
                        <li>Customers scan → land on mini-menu optimized for quick Takeaway or Delivery orders</li>
                        <li>Order type is pre-filled during checkout to speed up service</li>
                        <li>Use the <strong>Analytics</strong> tab to compare Takeaway vs Delivery scan volume</li>
                      </>
                    )}
                    <li><strong>2×2 grid PDF</strong> fits 4 cards per landscape A4 — recommended for mass printing</li>
                    <li>Use the <strong>Assets</strong> tab (above) to download individual codes as PNG / SVG</li>
                    <li>SILVER plan shows Flamezo branding; GOLD shows your logo</li>
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ══ PER-TABLE TAB ══════════════════════════════════════════════════ */}
        <TabsContent value="tables" className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold">QR Code Assets</h2>
              <p className="text-xs text-muted-foreground">Download table and order type QR codes as PNG or SVG</p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => { setTableAssets([]); loadTableAssets() }}
              disabled={isLoadingAssets}
              className="gap-1.5"
            >
              {isLoadingAssets ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              Refresh
            </Button>
          </div>

          <div className="space-y-4 pt-2">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className={cn(
                  "transition-all duration-300",
                  qrMode === 'dine_in' ? "bg-primary/5 text-primary border-primary/20" : "text-muted-foreground border-border"
                )}>
                  {qrMode === 'dine_in' ? 'Table-Specific QRs' : 'Takeaway & Delivery QRs'}
                </Badge>
                <div className="flex-1 w-24 h-px bg-border" />
              </div>

              <div className="flex p-0.5 bg-muted rounded-md border text-[10px]">
                <button
                  onClick={() => setQrMode('dine_in')}
                  className={cn("px-2 py-1 rounded-sm transition-all", qrMode === 'dine_in' ? "bg-background shadow-sm font-bold" : "text-muted-foreground")}
                >
                  Dine-In
                </button>
                <button
                  onClick={() => setQrMode('takeaway')}
                  className={cn("px-2 py-1 rounded-sm transition-all", qrMode === 'takeaway' ? "bg-background shadow-sm font-bold" : "text-muted-foreground")}
                >
                  Takeaway
                </button>
              </div>
            </div>

            {qrMode === 'dine_in' && !tables ? (
              <Card>
                <CardContent className="py-12 text-center text-muted-foreground text-sm">
                  <QrCode className="h-10 w-10 mx-auto mb-3 opacity-30" />
                  Set the number of tables in the Overview tab first
                </CardContent>
              </Card>
            ) : isLoadingAssets ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                {Array.from({ length: Math.min(tables || 1, 10) }).map((_, i) => (
                  <Card key={i} className="overflow-hidden">
                    <Skeleton className="aspect-[3/4] w-full" />
                    <div className="p-2"><Skeleton className="h-4 w-16" /></div>
                  </Card>
                ))}
              </div>
            ) : tableAssets.length === 0 ? (
              <Card>
                <CardContent className="py-12 text-center text-sm space-y-3">
                  <QrCode className="h-10 w-10 mx-auto opacity-30" />
                  <p className="text-muted-foreground">No table QR assets cached yet.</p>
                  <p className="text-xs text-muted-foreground">Generate the PDF first — assets are created automatically.</p>
                  <div className="flex gap-2 justify-center">
                    <Button
                      onClick={() => setShowGenModal(true)}
                      disabled={isGenerating || isDeleting}
                      className="shadow-sm"
                    >
                      {isGenerating ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <QrCode className="mr-2 h-4 w-4" />
                      )}
                      Generate QR Codes
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                {tableAssets.map((asset: any) => {
                  const assetKey = qrMode === 'dine_in'
                    ? `table-${asset.table_number}`
                    : `special-${asset.order_type || asset.table_number}`

                  return (
                    <TableQRCard
                      key={assetKey}
                      tableNumber={asset.table_number || 0}
                      pngUrl={asset.png_url}
                      svgUrl={asset.svg_url}
                      qrData={asset.qr_data}
                      scanCount={scanCountMap[assetKey] || 0}
                      onDownloadPng={() => handleDownloadIndividual(asset, 'png')}
                      onDownloadSvg={() => handleDownloadIndividual(asset, 'svg')}
                      customLabel={asset.label || (qrMode === 'takeaway' ? 'Order' : undefined)}
                    />
                  )
                })}
              </div>
            )}
          </div>
        </TabsContent>

        {/* ══ ANALYTICS TAB ══════════════════════════════════════════════════ */}
        <TabsContent value="analytics" className="space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold">QR Scan Analytics</h2>
              <p className="text-xs text-muted-foreground">Rolling 30-day window</p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={loadAnalytics}
              disabled={isLoadingAnalytics}
              className="gap-1.5"
            >
              {isLoadingAnalytics ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              Refresh
            </Button>
          </div>

          {isLoadingAnalytics ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
            </div>
          ) : analyticsData ? (
            <>
              {/* KPI row */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <AnalyticStatCard
                  label="Scans (30d)"
                  value={analyticsData.totalScans}
                  sub={`${analyticsData.avgDailyScans}/day avg`}
                  icon={ScanLine}
                  accent
                />
                <AnalyticStatCard
                  label="Lifetime Scans"
                  value={analyticsData.lifetimeScans}
                  sub="All time"
                  icon={TrendingUp}
                />
                <AnalyticStatCard
                  label="Top Table"
                  value={analyticsData.topTable ? `Table ${analyticsData.topTable.table_number}` : '—'}
                  sub={analyticsData.topTable ? `${analyticsData.topTable.scan_count} scans` : 'No data yet'}
                  icon={Trophy}
                />
                <AnalyticStatCard
                  label="Avg Daily"
                  value={analyticsData.avgDailyScans}
                  sub="Scans per day"
                  icon={CalendarDays}
                />
              </div>

              {/* Daily trend chart */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    <Activity className="h-4 w-4 text-primary" />
                    Daily Scan Trend (last 14 days)
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {analyticsData.dailyTrend?.length > 0 ? (
                    <MiniBarChart data={analyticsData.dailyTrend} />
                  ) : (
                    <p className="text-sm text-muted-foreground text-center py-6">No scan data in the last 14 days</p>
                  )}
                </CardContent>
              </Card>

              {/* Per-table breakdown */}
              {analyticsData.perTable?.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-semibold flex items-center gap-2">
                      <Table2 className="h-4 w-4 text-primary" />
                      Table Breakdown (Top 10)
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {analyticsData.perTable.slice(0, 10).map((row: any, idx: number) => {
                      const maxCount = analyticsData.perTable[0]?.scan_count || 1
                      const pct = Math.round((row.scan_count / maxCount) * 100)
                      return (
                        <div key={row.table_number} className="flex items-center gap-3">
                          <span className="text-xs font-medium w-5 text-muted-foreground">{idx + 1}</span>
                          <span className="text-xs font-medium w-16">Table {row.table_number}</span>
                          <div className="flex-1 bg-muted rounded-full h-2 overflow-hidden">
                            <div
                              className="h-full bg-primary rounded-full transition-all duration-500"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className="text-xs font-bold w-8 text-right">{row.scan_count}</span>
                        </div>
                      )
                    })}
                  </CardContent>
                </Card>
              )}
            </>
          ) : (
            <Card>
              <CardContent className="py-12 text-center space-y-2">
                <BarChart3 className="h-10 w-10 mx-auto opacity-30" />
                <p className="text-sm text-muted-foreground">No QR scan analytics yet.</p>
                <p className="text-xs text-muted-foreground">
                  Scan data is recorded as customers arrive via QR code links.
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* ─── Generate QR Codes Modal ────────────────────────────────────────── */}
      <Dialog open={showGenModal} onOpenChange={setShowGenModal}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Generate QR Codes PDF</DialogTitle>
            <DialogDescription>
              {qrMode === 'dine_in'
                ? 'Generating production-ready PDF for your restaurant tables.'
                : 'Generating special QRs for Takeaway and Delivery orders.'}
            </DialogDescription>
          </DialogHeader>

          <div className="flex justify-center p-1 bg-muted rounded-lg mb-4">
            <button
              className={cn("flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition-all", qrMode === 'dine_in' ? "bg-background shadow-sm" : "hover:bg-background/50")}
              onClick={() => setQrMode('dine_in')}
            >
              Dine-In
            </button>
            <button
              className={cn("flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition-all", qrMode === 'takeaway' ? "bg-background shadow-sm" : "hover:bg-background/50")}
              onClick={() => setQrMode('takeaway')}
            >
              Takeaway/Delivery
            </button>
          </div>

          <div className="grid gap-6 py-4">
            {/* Background Image Upload */}
            <div className="space-y-3">
              <Label className="text-sm font-semibold">Background Image (Optional)</Label>
              {!bgPreview ? (
                <div
                  className="relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-muted-foreground/20 bg-muted/30 py-10 transition-colors hover:bg-muted/50 cursor-pointer"
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault()
                    const file = e.dataTransfer.files[0]
                    if (file && file.type.startsWith('image/')) {
                      setBgFile(file)
                      setBgPreview(URL.createObjectURL(file))
                    }
                  }}
                >
                  <div className="mb-3 rounded-full bg-background p-3 shadow-sm">
                    <Upload className="h-6 w-6 text-primary" />
                  </div>
                  <p className="text-sm font-medium">Click or drag image to upload</p>
                  <p className="mt-1 text-xs text-muted-foreground">PNG, JPG or WEBP (Max 5MB)</p>
                  <input
                    type="file"
                    ref={fileInputRef}
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      if (file) {
                        setBgFile(file)
                        setBgPreview(URL.createObjectURL(file))
                      }
                    }}
                  />
                </div>
              ) : (
                <div className="relative overflow-hidden rounded-xl border group">
                  <img
                    src={bgPreview}
                    alt="Background Preview"
                    className="aspect-[4/3] w-full object-cover transition-transform group-hover:scale-105"
                  />
                  <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover:opacity-100">
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => {
                        setBgFile(null)
                        setBgPreview(null)
                      }}
                      className="h-8 rounded-full"
                    >
                      <X className="mr-2 h-3.5 w-3.5" />
                      Remove Image
                    </Button>
                  </div>
                  <div className="absolute bottom-3 left-3 right-3 rounded-lg bg-black/60 px-3 py-2 backdrop-blur-sm">
                    <p className="text-[10px] font-medium text-white/90">Custom background applied to all assets</p>
                  </div>
                </div>
              )}
              {!bgPreview && (
                <div className="flex items-center gap-2 rounded-lg bg-primary/5 px-3 py-2.5 text-[11px] text-primary/80">
                  <Info className="h-3.5 w-3.5" />
                  No background selected. QR codes will have a clean white background.
                </div>
              )}
            </div>

            {/* Layout Selection */}
            <div className="space-y-3">
              <Label className="text-sm font-semibold">Page Layout</Label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={() => setPdfLayout('2x2')}
                  className={cn(
                    'flex flex-col items-center gap-3 rounded-xl border-2 p-4 transition-all text-left group',
                    pdfLayout === '2x2' ? 'border-primary bg-primary/5 ring-2 ring-primary/20' : 'border-muted hover:border-muted-foreground/30'
                  )}
                >
                  <div className={cn('rounded-lg p-2.5', pdfLayout === '2x2' ? 'bg-primary text-primary-foreground' : 'bg-muted group-hover:bg-muted-foreground/10')}>
                    <Grid className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-sm font-bold">2×2 Grid</p>
                    <p className="text-[10px] leading-tight text-muted-foreground mt-0.5">4 cards per landscape page. Paper efficient.</p>
                  </div>
                </button>
                <button
                  onClick={() => setPdfLayout('1x1')}
                  className={cn(
                    'flex flex-col items-center gap-3 rounded-xl border-2 p-4 transition-all text-left group',
                    pdfLayout === '1x1' ? 'border-primary bg-primary/5 ring-2 ring-primary/20' : 'border-muted hover:border-muted-foreground/30'
                  )}
                >
                  <div className={cn('rounded-lg p-2.5', pdfLayout === '1x1' ? 'bg-primary text-primary-foreground' : 'bg-muted group-hover:bg-muted-foreground/10')}>
                    <Layers className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-sm font-bold">1×1 Centered</p>
                    <p className="text-[10px] leading-tight text-muted-foreground mt-0.5">One large card per portrait page.</p>
                  </div>
                </button>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowGenModal(false)} disabled={isGenerating}>
              Cancel
            </Button>
            <Button onClick={handleGenerateQrCodes} disabled={isGenerating}>
              {isGenerating ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating...</>
              ) : (
                <><QrCode className="mr-2 h-4 w-4" /> Generate PDF</>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── QR Code Scanner Dialog ─────────────────────────────────────────── */}
      <QRCodeScanner
        restaurantId={restaurantDoc?.restaurant_id || ''}
        open={showScanner}
        onOpenChange={setShowScanner}
        onScan={(tableNumber) => {
          toast.success(`Table ${tableNumber} scanned and validated!`)
          setShowScanner(false)
        }}
      />

      {/* ── Delete Confirmation ───────────────────────────────────────────── */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete QR Codes PDF?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the stored PDF. You can regenerate it at any time.
              Per-table QR assets on CDN will remain available.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDeleteQrCodes}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete PDF
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
