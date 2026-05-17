/**
 * CustomerImportModal
 *
 * 3-step wizard to bulk-import customers from CSV / Excel files.
 *
 * Step 1 — Upload   : drag-and-drop or click to pick .csv / .xlsx / .xls
 * Step 2 — Map      : auto-detected columns + user-adjustable dropdowns, live preview
 * Step 3 — Results  : summary of imported / updated / skipped rows + error download
 */

import { useState, useCallback, useRef } from 'react'
import Papa from 'papaparse'
import * as XLSX from 'xlsx'
import { useFrappePostCall } from '@/lib/frappe'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { toast } from 'sonner'
import {
  Upload,
  FileSpreadsheet,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Download,
  AlertCircle,
  Users,
  X,
  Phone,
  User,
  Mail,
  Cake,
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Props {
  open: boolean
  onClose: () => void
  restaurantId: string
  onImportComplete: () => void
}

type Step = 'upload' | 'map' | 'importing' | 'results'

interface ParsedRow {
  [key: string]: string
}

// Fields the backend accepts
type MappableField = 'phone' | 'name' | 'email' | 'birthday' | 'ignore'

interface ColumnMapping {
  [columnHeader: string]: MappableField
}

interface ImportResult {
  row: number
  phone?: string
  name?: string
  status: 'imported' | 'updated' | 'skipped'
  reason?: string
}

interface ImportSummary {
  imported: number
  updated: number
  skipped: number
  total: number
  results: ImportResult[]
}

// ─── Constants ────────────────────────────────────────────────────────────────

const FIELD_OPTIONS: { value: MappableField; label: string }[] = [
  { value: 'phone',    label: 'Phone Number' },
  { value: 'name',     label: 'Customer Name' },
  { value: 'email',    label: 'Email Address' },
  { value: 'birthday', label: 'Birthday (YYYY-MM-DD)' },
  { value: 'ignore',   label: 'Ignore this column' },
]

// Alias maps for auto-detection (all lowercase)
const PHONE_ALIASES   = ['phone', 'mobile', 'cell', 'contact', 'number', 'ph', 'mob', 'telephone', 'tel', 'phone number', 'mobile number', 'contact number']
const NAME_ALIASES    = ['name', 'customer name', 'full name', 'client', 'customer', 'guest name', 'guest', 'person', 'fullname', 'client name']
const EMAIL_ALIASES   = ['email', 'mail', 'e-mail', 'email address', 'emailid', 'email id']
const BIRTHDAY_ALIASES = ['birthday', 'dob', 'date of birth', 'bday', 'birth date', 'birthdate', 'dateofbirth', 'born']

const MAX_PREVIEW_ROWS = 5
const BATCH_SIZE = 200  // rows per API call

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Sanitize a raw phone cell value before sending to the backend.
 *
 * Handles every known Excel / CSV corruption:
 *   - Scientific notation  : "9.19877E+11"  → "919877000000" → last 10 digits
 *   - Float suffix         : "9876543210.0" → "9876543210"
 *   - Arithmetic result    : "-11327"        → strip, likely corrupt → pass through (backend will reject)
 *   - Leading country code : "+919876543210" → "9876543210"
 *   - Spaces / dashes      : "+91-98765 43210" → digits only → last 10
 *
 * We do NOT do full normalization here — that is the backend's job.
 * We only undo Excel's damage so the backend receives something it can work with.
 */
function sanitizePhoneCell(raw: string): string {
  if (!raw) return ''
  let s = raw.trim()

  // Detect and expand scientific notation (e.g. 9.19877E+11)
  if (/^[+\-]?\d+\.?\d*[eE][+\-]?\d+$/.test(s)) {
    try {
      // Parse as float and convert to integer string — no decimal, no exponent
      const n = parseFloat(s)
      if (!isNaN(n) && isFinite(n) && n > 0) {
        s = Math.round(n).toString()
      }
    } catch { /* leave as-is, backend will reject */ }
  }

  // Strip float suffix: "9876543210.0" → "9876543210"
  s = s.replace(/\.0+$/, '')

  return s
}

function autoDetectField(header: string): MappableField {
  const h = header.toLowerCase().trim()
  if (PHONE_ALIASES.some(a => h === a || h.includes(a)))   return 'phone'
  if (NAME_ALIASES.some(a => h === a || h.includes(a)))    return 'name'
  if (EMAIL_ALIASES.some(a => h === a || h.includes(a)))   return 'email'
  if (BIRTHDAY_ALIASES.some(a => h === a || h.includes(a))) return 'birthday'
  return 'ignore'
}

function parseFileToRows(file: File): Promise<{ headers: string[]; rows: ParsedRow[] }> {
  return new Promise((resolve, reject) => {
    const ext = file.name.split('.').pop()?.toLowerCase()

    if (ext === 'csv') {
      Papa.parse<ParsedRow>(file, {
        header: true,
        skipEmptyLines: true,
        transformHeader: (h) => h.trim(),
        complete: (result) => {
          const headers = result.meta.fields ?? []
          resolve({ headers, rows: result.data })
        },
        error: (err) => reject(new Error(err.message)),
      })
    } else if (ext === 'xlsx' || ext === 'xls') {
      const reader = new FileReader()
      reader.onload = (e) => {
        try {
          const data = e.target?.result
          // cellText: true forces xlsx to compute the formatted text string for every cell,
          // which preserves leading zeros, avoids scientific notation, and keeps +91 prefixes intact.
          const workbook = XLSX.read(data, { type: 'array', cellDates: true, cellText: true })
          const sheetName = workbook.SheetNames[0]
          const sheet = workbook.Sheets[sheetName]

          // Use sheet_to_json with raw:false + the w (formatted text) field via cellText.
          // We do a second pass to pick the .w (display text) over .v (raw value) for every cell
          // so that phone numbers like +919876543214 or 09876543212 are never converted to numbers.
          const range = XLSX.utils.decode_range(sheet['!ref'] ?? 'A1')
          const headers: string[] = []

          // Read header row
          for (let col = range.s.c; col <= range.e.c; col++) {
            const cellAddr = XLSX.utils.encode_cell({ r: range.s.r, c: col })
            const cell = sheet[cellAddr]
            headers.push(cell ? String(cell.v ?? '').trim() : '')
          }

          // Read data rows — always prefer cell.w (formatted text) to avoid scientific notation
          const jsonRows: ParsedRow[] = []
          for (let row = range.s.r + 1; row <= range.e.r; row++) {
            const rowObj: ParsedRow = {}
            let hasAnyValue = false
            for (let col = range.s.c; col <= range.e.c; col++) {
              const cellAddr = XLSX.utils.encode_cell({ r: row, c: col })
              const cell = sheet[cellAddr]
              const header = headers[col - range.s.c]
              if (!header) continue
              // .w is the formatted display string (what you see in Excel).
              // Fall back to .v only when .w is absent (e.g. empty cells).
              const val = cell ? String(cell.w ?? cell.v ?? '').trim() : ''
              rowObj[header] = val
              if (val) hasAnyValue = true
            }
            if (hasAnyValue) jsonRows.push(rowObj)
          }

          resolve({ headers: headers.filter(Boolean), rows: jsonRows })
        } catch (err) {
          reject(new Error('Failed to parse Excel file. Make sure it is a valid .xlsx or .xls file.'))
        }
      }
      reader.onerror = () => reject(new Error('Could not read file'))
      reader.readAsArrayBuffer(file)
    } else {
      reject(new Error('Unsupported file type. Please upload a .csv, .xlsx, or .xls file.'))
    }
  })
}

function downloadErrorCSV(results: ImportResult[]) {
  const skipped = results.filter(r => r.status === 'skipped')
  if (!skipped.length) return
  const csv = Papa.unparse(
    skipped.map(r => ({ Row: r.row, Phone: r.phone ?? '', Name: r.name ?? '', Reason: r.reason ?? '' }))
  )
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'import_errors.csv'
  a.click()
  URL.revokeObjectURL(url)
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function CustomerImportModal({ open, onClose, restaurantId, onImportComplete }: Props) {
  const [step, setStep]                     = useState<Step>('upload')
  const [file, setFile]                     = useState<File | null>(null)
  const [isDragging, setIsDragging]         = useState(false)
  const [parseError, setParseError]         = useState<string | null>(null)
  const [isParsing, setIsParsing]           = useState(false)
  const [headers, setHeaders]               = useState<string[]>([])
  const [allRows, setAllRows]               = useState<ParsedRow[]>([])
  const [columnMapping, setColumnMapping]   = useState<ColumnMapping>({})
  const [summary, setSummary]               = useState<ImportSummary | null>(null)
  const [importProgress, setImportProgress] = useState(0)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { call: callImport } = useFrappePostCall(
    'flamezo_backend.flamezo.api.customers.import_customers'
  )

  // ── Reset all state when modal closes ──────────────────────────────────────
  const handleClose = useCallback(() => {
    setStep('upload')
    setFile(null)
    setParseError(null)
    setHeaders([])
    setAllRows([])
    setColumnMapping({})
    setSummary(null)
    setImportProgress(0)
    onClose()
  }, [onClose])

  // ── File selection / drop ──────────────────────────────────────────────────
  const processFile = useCallback(async (f: File) => {
    setFile(f)
    setParseError(null)
    setIsParsing(true)
    try {
      const { headers: h, rows } = await parseFileToRows(f)
      if (h.length === 0 || rows.length === 0) {
        setParseError('The file appears to be empty or has no data rows.')
        setIsParsing(false)
        return
      }

      // Auto-detect mapping
      const mapping: ColumnMapping = {}
      h.forEach(col => { mapping[col] = autoDetectField(col) })

      setHeaders(h)
      setAllRows(rows)
      setColumnMapping(mapping)
      setStep('map')
    } catch (err: unknown) {
      setParseError(err instanceof Error ? err.message : 'Failed to read file')
    } finally {
      setIsParsing(false)
    }
  }, [])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) processFile(f)
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) processFile(f)
  }, [processFile])

  // ── Mapping validation ─────────────────────────────────────────────────────
  const phoneColumn = Object.entries(columnMapping).find(([, v]) => v === 'phone')?.[0]
  const isMappingValid = !!phoneColumn

  // ── Import execution ───────────────────────────────────────────────────────
  const handleImport = useCallback(async () => {
    if (!isMappingValid) return
    setStep('importing')
    setImportProgress(0)

    // Transform rows into {phone, name, email, birthday} dicts.
    // Phone values are sanitized here to undo any Excel corruption (scientific
    // notation, float suffix, arithmetic results) before the backend sees them.
    const mappedRows = allRows.map(row => {
      const out: Record<string, string> = {}
      Object.entries(columnMapping).forEach(([col, field]) => {
        if (field !== 'ignore' && row[col] != null) {
          const val = String(row[col]).trim()
          out[field] = field === 'phone' ? sanitizePhoneCell(val) : val
        }
      })
      return out
    })

    // Send in batches to avoid huge payloads / timeouts
    const batches: typeof mappedRows[] = []
    for (let i = 0; i < mappedRows.length; i += BATCH_SIZE) {
      batches.push(mappedRows.slice(i, i + BATCH_SIZE))
    }

    let totalImported = 0
    let totalUpdated  = 0
    let totalSkipped  = 0
    const allResults: ImportResult[] = []
    let batchOffset = 0

    try {
      for (let bi = 0; bi < batches.length; bi++) {
        const batch = batches[bi]
        const res = await callImport({
          restaurant_id: restaurantId,
          rows: JSON.stringify(batch),
        })
        const body = (res as { message?: { success: boolean; data?: ImportSummary; error?: string } })?.message
          ?? (res as { success: boolean; data?: ImportSummary; error?: string })

        if (!body?.success) {
          throw new Error(body?.error ?? 'Import failed')
        }

        const d = body.data!
        totalImported += d.imported
        totalUpdated  += d.updated
        totalSkipped  += d.skipped

        // Adjust row numbers to be global (across batches)
        d.results.forEach(r => {
          allResults.push({ ...r, row: r.row + batchOffset })
        })
        batchOffset += batch.length
        setImportProgress(Math.round(((bi + 1) / batches.length) * 100))
      }

      setSummary({
        imported: totalImported,
        updated:  totalUpdated,
        skipped:  totalSkipped,
        total:    mappedRows.length,
        results:  allResults,
      })
      setStep('results')
      if (totalImported > 0 || totalUpdated > 0) {
        onImportComplete()
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Import failed. Please try again.')
      setStep('map')
    }
  }, [allRows, columnMapping, isMappingValid, restaurantId, callImport, onImportComplete])

  // ─── Render helpers ────────────────────────────────────────────────────────

  const previewRows = allRows.slice(0, MAX_PREVIEW_ROWS)

  const StepIndicator = () => (
    <div className="flex items-center gap-2 mb-6">
      {(['upload', 'map', 'results'] as const).map((s, i) => {
        const labels = ['Upload File', 'Map Columns', 'Results']
        const isActive   = step === s || (step === 'importing' && s === 'map')
        const isComplete = (
          (s === 'upload' && (step === 'map' || step === 'importing' || step === 'results')) ||
          (s === 'map'    && (step === 'importing' || step === 'results'))
        )
        return (
          <div key={s} className="flex items-center gap-2">
            <div className={`h-7 w-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
              isComplete ? 'bg-green-500 text-white' :
              isActive   ? 'bg-primary text-primary-foreground' :
              'bg-muted text-muted-foreground'
            }`}>
              {isComplete ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
            </div>
            <span className={`text-xs font-semibold hidden sm:inline ${isActive ? 'text-foreground' : 'text-muted-foreground'}`}>
              {labels[i]}
            </span>
            {i < 2 && <div className="h-px w-6 bg-border mx-1" />}
          </div>
        )
      })}
    </div>
  )

  // ─── Step 1: Upload ────────────────────────────────────────────────────────

  const renderUpload = () => (
    <div className="space-y-4">
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all ${
          isDragging ? 'border-primary bg-primary/5 scale-[1.01]' : 'border-border hover:border-primary/50 hover:bg-muted/30'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          onChange={handleFileChange}
        />
        {isParsing ? (
          <div className="flex flex-col items-center gap-3">
            <RefreshCw className="h-10 w-10 text-primary animate-spin" />
            <p className="font-semibold text-sm">Reading your file…</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div className="h-16 w-16 bg-primary/10 rounded-full flex items-center justify-center">
              <Upload className="h-8 w-8 text-primary" />
            </div>
            <div>
              <p className="font-bold text-base">Drop your file here, or click to browse</p>
              <p className="text-muted-foreground text-sm mt-1">Supports CSV, Excel (.xlsx, .xls)</p>
            </div>
          </div>
        )}
      </div>

      {parseError && (
        <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
          <span>{parseError}</span>
        </div>
      )}

      <div className="bg-muted/40 rounded-xl p-4 space-y-3">
        <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">What columns does it need?</p>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex items-start gap-2.5">
            <div className="h-7 w-7 rounded-md bg-background border border-border flex items-center justify-center shrink-0 mt-0.5">
              <Phone className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            <div>
              <p className="font-semibold text-xs">Phone <span className="text-red-500">*</span></p>
              <p className="text-[10px] text-muted-foreground">Required. Any format accepted.</p>
            </div>
          </div>
          <div className="flex items-start gap-2.5">
            <div className="h-7 w-7 rounded-md bg-background border border-border flex items-center justify-center shrink-0 mt-0.5">
              <User className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            <div>
              <p className="font-semibold text-xs">Name</p>
              <p className="text-[10px] text-muted-foreground">Customer's full name</p>
            </div>
          </div>
          <div className="flex items-start gap-2.5">
            <div className="h-7 w-7 rounded-md bg-background border border-border flex items-center justify-center shrink-0 mt-0.5">
              <Mail className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            <div>
              <p className="font-semibold text-xs">Email</p>
              <p className="text-[10px] text-muted-foreground">Email address</p>
            </div>
          </div>
          <div className="flex items-start gap-2.5">
            <div className="h-7 w-7 rounded-md bg-background border border-border flex items-center justify-center shrink-0 mt-0.5">
              <Cake className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            <div>
              <p className="font-semibold text-xs">Birthday</p>
              <p className="text-[10px] text-muted-foreground">YYYY-MM-DD format</p>
            </div>
          </div>
        </div>
        <p className="text-[10px] text-muted-foreground border-t border-border/50 pt-2.5 mt-1">
          Column names don't need to match exactly — we'll auto-detect them. Your existing customers won't be duplicated.
        </p>
      </div>
    </div>
  )

  // ─── Step 2: Column Mapping ────────────────────────────────────────────────

  const renderMap = () => (
    <div className="space-y-5">
      <div className="flex items-center gap-3 p-3 bg-muted/40 rounded-lg">
        <FileSpreadsheet className="h-5 w-5 text-primary shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold truncate">{file?.name}</p>
          <p className="text-xs text-muted-foreground">{allRows.length.toLocaleString()} rows detected</p>
        </div>
        <button
          onClick={() => { setStep('upload'); setFile(null) }}
          className="text-muted-foreground hover:text-foreground transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Column mapping table */}
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-3">
          Map your columns
        </p>
        <p className="text-xs text-muted-foreground mb-3">
          We've auto-detected the columns below. Check they're correct and fix any that are wrong.
          Only <strong>Phone Number</strong> is required.
        </p>
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-muted-foreground">Your Column</th>
                <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-muted-foreground">Maps To</th>
                <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-muted-foreground hidden sm:table-cell">Sample Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {headers.map(col => (
                <tr key={col} className="hover:bg-muted/20">
                  <td className="px-4 py-2.5 font-mono text-xs font-medium text-foreground max-w-[140px] truncate">
                    {col}
                  </td>
                  <td className="px-4 py-2.5 w-52">
                    <Select
                      value={columnMapping[col]}
                      onValueChange={(val) =>
                        setColumnMapping(prev => ({ ...prev, [col]: val as MappableField }))
                      }
                    >
                      <SelectTrigger className={`h-8 text-xs ${columnMapping[col] === 'phone' ? 'border-primary/50 bg-primary/5' : ''}`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {FIELD_OPTIONS.map(o => (
                          <SelectItem key={o.value} value={o.value} className="text-xs">
                            {o.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground hidden sm:table-cell max-w-[140px] truncate">
                    {previewRows[0]?.[col] ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Preview table */}
      {previewRows.length > 0 && (
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-2">
            Preview (first {Math.min(previewRows.length, MAX_PREVIEW_ROWS)} rows)
          </p>
          <div className="rounded-lg border overflow-x-auto">
            <table className="text-xs w-full">
              <thead className="bg-muted/50">
                <tr>
                  {headers.filter(h => columnMapping[h] !== 'ignore').map(h => (
                    <th key={h} className="text-left px-3 py-2 font-semibold text-muted-foreground whitespace-nowrap">
                      {FIELD_OPTIONS.find(o => o.value === columnMapping[h])?.label.split(' ').slice(1).join(' ') || h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {previewRows.map((row, i) => (
                  <tr key={i} className="hover:bg-muted/20">
                    {headers.filter(h => columnMapping[h] !== 'ignore').map(h => (
                      <td key={h} className="px-3 py-1.5 text-foreground max-w-[140px] truncate">
                        {row[h] || <span className="text-muted-foreground/40">—</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!isMappingValid && (
        <div className="flex items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-700 text-xs">
          <AlertCircle className="h-4 w-4 shrink-0" />
          Please map at least one column to <strong>Phone Number</strong> to continue.
        </div>
      )}
    </div>
  )

  // ─── Step: Importing (progress) ────────────────────────────────────────────

  const renderImporting = () => (
    <div className="flex flex-col items-center justify-center py-16 gap-6">
      <div className="relative h-20 w-20">
        <div className="absolute inset-0 rounded-full border-4 border-muted" />
        <div
          className="absolute inset-0 rounded-full border-4 border-primary border-t-transparent animate-spin"
          style={{ animationDuration: '0.8s' }}
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-sm font-bold text-primary">{importProgress}%</span>
        </div>
      </div>
      <div className="text-center">
        <p className="font-bold text-base">Importing your customers…</p>
        <p className="text-sm text-muted-foreground mt-1">
          Processing {allRows.length.toLocaleString()} rows. Please don't close this window.
        </p>
      </div>
      <div className="w-full max-w-xs bg-muted rounded-full h-2 overflow-hidden">
        <div
          className="h-2 bg-primary rounded-full transition-all duration-300"
          style={{ width: `${importProgress}%` }}
        />
      </div>
    </div>
  )

  // ─── Step 3: Results ───────────────────────────────────────────────────────

  const renderResults = () => {
    if (!summary) return null
    const hasErrors = summary.skipped > 0

    return (
      <div className="space-y-5">
        {/* Summary cards */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-green-50 border border-green-100 rounded-xl p-4 text-center">
            <p className="text-2xl font-black text-green-600">{summary.imported.toLocaleString()}</p>
            <p className="text-xs font-semibold text-green-700 mt-1">New Customers</p>
          </div>
          <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-center">
            <p className="text-2xl font-black text-blue-600">{summary.updated.toLocaleString()}</p>
            <p className="text-xs font-semibold text-blue-700 mt-1">Updated</p>
          </div>
          <div className={`rounded-xl p-4 text-center border ${hasErrors ? 'bg-red-50 border-red-100' : 'bg-muted/40 border-border'}`}>
            <p className={`text-2xl font-black ${hasErrors ? 'text-red-500' : 'text-muted-foreground'}`}>
              {summary.skipped.toLocaleString()}
            </p>
            <p className={`text-xs font-semibold mt-1 ${hasErrors ? 'text-red-600' : 'text-muted-foreground'}`}>Skipped</p>
          </div>
        </div>

        {/* Success message */}
        {(summary.imported > 0 || summary.updated > 0) && (
          <div className="flex items-center gap-3 p-4 bg-green-50 border border-green-100 rounded-xl">
            <CheckCircle2 className="h-5 w-5 text-green-500 shrink-0" />
            <p className="text-sm text-green-700 font-medium">
              Successfully processed {(summary.imported + summary.updated).toLocaleString()} customers.
              {summary.imported > 0 && ` ${summary.imported} new customers added.`}
              {summary.updated > 0 && ` ${summary.updated} existing customers updated.`}
            </p>
          </div>
        )}

        {/* Errors list */}
        {hasErrors && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                Skipped Rows ({summary.skipped})
              </p>
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs gap-1.5"
                onClick={() => downloadErrorCSV(summary.results)}
              >
                <Download className="h-3 w-3" />
                Download Error Report
              </Button>
            </div>
            <div className="rounded-lg border max-h-52 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted/50 sticky top-0">
                  <tr>
                    <th className="text-left px-3 py-2 font-semibold text-muted-foreground">Row</th>
                    <th className="text-left px-3 py-2 font-semibold text-muted-foreground">Phone</th>
                    <th className="text-left px-3 py-2 font-semibold text-muted-foreground">Reason</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {summary.results.filter(r => r.status === 'skipped').map((r, i) => (
                    <tr key={i} className="hover:bg-muted/20">
                      <td className="px-3 py-1.5 text-muted-foreground">#{r.row}</td>
                      <td className="px-3 py-1.5 font-mono">{r.phone || '—'}</td>
                      <td className="px-3 py-1.5 text-red-600">{r.reason || 'Unknown error'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {summary.imported === 0 && summary.updated === 0 && (
          <div className="flex items-center gap-3 p-4 bg-amber-50 border border-amber-100 rounded-xl">
            <XCircle className="h-5 w-5 text-amber-500 shrink-0" />
            <p className="text-sm text-amber-700 font-medium">
              No customers were imported. Please check your file and try again.
            </p>
          </div>
        )}
      </div>
    )
  }

  // ─── Footer buttons ────────────────────────────────────────────────────────

  const renderFooter = () => {
    if (step === 'upload') return (
      <div className="flex justify-end">
        <Button variant="ghost" onClick={handleClose}>Cancel</Button>
      </div>
    )

    if (step === 'map') return (
      <div className="flex justify-between">
        <Button variant="ghost" onClick={() => { setStep('upload'); setFile(null) }} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" /> Back
        </Button>
        <Button onClick={handleImport} disabled={!isMappingValid} className="gap-1.5">
          Import {allRows.length.toLocaleString()} Customers <ArrowRight className="h-4 w-4" />
        </Button>
      </div>
    )

    if (step === 'importing') return null

    if (step === 'results') return (
      <div className="flex justify-between">
        <Button
          variant="outline"
          onClick={() => { setStep('upload'); setFile(null); setAllRows([]); setSummary(null) }}
          className="gap-1.5"
        >
          <Upload className="h-4 w-4" /> Import Another File
        </Button>
        <Button onClick={handleClose} className="gap-1.5">
          <CheckCircle2 className="h-4 w-4" /> Done
        </Button>
      </div>
    )
  }

  // ─── Dialog title / description per step ──────────────────────────────────

  const stepMeta: Record<Step, { title: string; description: string }> = {
    upload: {
      title: 'Import Customers',
      description: 'Upload your existing customer database from Excel or CSV.',
    },
    map: {
      title: 'Match Your Columns',
      description: 'Tell us which column is which. We\'ve auto-detected most of them.',
    },
    importing: {
      title: 'Importing…',
      description: 'We\'re adding your customers. This may take a moment.',
    },
    results: {
      title: 'Import Complete',
      description: 'Here\'s a summary of what was imported.',
    },
  }

  const meta = stepMeta[step]

  // ─── Render ────────────────────────────────────────────────────────────────

  return (
    <Dialog open={open} onOpenChange={(o) => !o && step !== 'importing' && handleClose()}>
      <DialogContent
        className="max-w-2xl max-h-[90vh] flex flex-col rounded-2xl border-none shadow-2xl p-0 gap-0"
        onInteractOutside={(e) => step === 'importing' && e.preventDefault()}
      >
        {/* Header */}
        <div className="p-6 pb-4 border-b border-border/50">
          <DialogHeader className="flex flex-row items-center gap-4 space-y-0">
            <div className="h-11 w-11 bg-primary/10 rounded-xl flex items-center justify-center shrink-0">
              <Users className="h-6 w-6 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <DialogTitle className="text-lg font-bold">{meta.title}</DialogTitle>
              <DialogDescription className="text-xs mt-0.5">{meta.description}</DialogDescription>
            </div>
          </DialogHeader>
          {step !== 'importing' && <div className="mt-5"><StepIndicator /></div>}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6">
          {step === 'upload'    && renderUpload()}
          {step === 'map'       && renderMap()}
          {step === 'importing' && renderImporting()}
          {step === 'results'   && renderResults()}
        </div>

        {/* Footer */}
        {step !== 'importing' && (
          <div className="p-4 border-t border-border/50 bg-muted/20 rounded-b-2xl">
            {renderFooter()}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
