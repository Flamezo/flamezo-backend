/**
 * ChillsLocationPicker
 *
 * Inline location selector for the Chills upload and edit flows.
 * Uses Google Places API v1 (New) REST endpoints — same as the mobile app.
 * No Maps JS SDK required; works purely with fetch().
 *
 * Auto-radius logic (mirrors flamezo-app/lib/places.ts):
 *   specific venue (restaurant/establishment) → 300 m
 *   neighbourhood / sublocality              → 3 km
 *   city / locality                          → 20 km
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useOutlet } from '@/contexts/OutletContext'
import { MapPin, Navigation, Building2, X, Search, Loader2 } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

// ── Types ──────────────────────────────────────────────────────────────────────

export interface ChillsLocationValue {
  name: string
  lat: number
  lng: number
  radius: number
}

interface Props {
  value: ChillsLocationValue | null
  onChange: (loc: ChillsLocationValue | null) => void
  /** Optional outlet coords for the "Use outlet location" shortcut */
  outletName?: string
  outletLat?: number | null
  outletLng?: number | null
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const SURAT_CENTER = { lat: 21.1702, lng: 72.8311 }
const AUTOCOMPLETE_URL = 'https://places.googleapis.com/v1/places:autocomplete'
const PLACE_DETAILS_BASE = 'https://places.googleapis.com/v1/places'

interface Prediction {
  placeId: string
  primaryText: string
  secondaryText: string
}

function radiusFromTypes(types: string[]): number {
  const s = new Set(types)
  if (s.has('locality') || s.has('administrative_area_level_2')) return 20_000
  if (s.has('neighborhood') || s.has('sublocality') || s.has('sublocality_level_1')) return 3_000
  return 300
}

function radiusLabel(m: number): string {
  if (m >= 10_000) return 'City-wide'
  if (m >= 1_000) return 'Neighbourhood'
  return 'Venue pin'
}

function formatRadius(m: number): string {
  return m >= 1000 ? `${m / 1000} km` : `${m} m`
}

async function fetchPredictions(query: string, apiKey: string, signal?: AbortSignal): Promise<Prediction[]> {
  if (!query.trim() || !apiKey) return []
  try {
    const res = await fetch(AUTOCOMPLETE_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': apiKey,
        'X-Goog-FieldMask': 'suggestions.placePrediction.placeId,suggestions.placePrediction.structuredFormat',
      },
      body: JSON.stringify({
        input: query,
        locationBias: {
          circle: { center: { latitude: SURAT_CENTER.lat, longitude: SURAT_CENTER.lng }, radius: 25_000 },
        },
        includedRegionCodes: ['in'],
      }),
      signal,
    })
    if (!res.ok) return []
    const json = await res.json()
    return (json.suggestions ?? []).flatMap((s: any) => {
      const p = s.placePrediction
      if (!p?.placeId) return []
      return [{
        placeId: p.placeId,
        primaryText: p.structuredFormat?.mainText?.text ?? '',
        secondaryText: p.structuredFormat?.secondaryText?.text ?? '',
      }]
    })
  } catch {
    return []
  }
}

async function fetchPlaceDetails(placeId: string, apiKey: string, signal?: AbortSignal): Promise<ChillsLocationValue | null> {
  if (!apiKey) return null
  try {
    const res = await fetch(`${PLACE_DETAILS_BASE}/${placeId}`, {
      headers: {
        'X-Goog-Api-Key': apiKey,
        'X-Goog-FieldMask': 'id,displayName,location,addressComponents,types',
      },
      signal,
    })
    if (!res.ok) return null
    const p = await res.json()
    if (!p.location) return null

    const city =
      p.addressComponents?.find((c: any) => c.types?.includes('locality'))?.longText ??
      p.addressComponents?.find((c: any) => c.types?.includes('administrative_area_level_2'))?.longText ??
      'Surat'

    return {
      name: p.displayName?.text ?? city,
      lat: p.location.latitude,
      lng: p.location.longitude,
      radius: radiusFromTypes(p.types ?? []),
    }
  } catch {
    return null
  }
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function ChillsLocationPicker({ value, onChange, outletName, outletLat, outletLng }: Props) {
  const { googleMapsApiKey } = useOutlet()
  const apiKey = (googleMapsApiKey || import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '') as string

  const [query, setQuery] = useState('')
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [resolvingId, setResolvingId] = useState<string | null>(null)
  const [showDropdown, setShowDropdown] = useState(false)

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const hasOutletCoords = !!(outletLat && outletLng && outletLat !== 0 && outletLng !== 0)

  // ── Debounced autocomplete ────────────────────────────────────────────────────

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    abortRef.current?.abort()

    if (!query.trim()) {
      setPredictions([])
      setIsSearching(false)
      return
    }

    debounceRef.current = setTimeout(() => {
      const ac = new AbortController()
      abortRef.current = ac
      setIsSearching(true)
      fetchPredictions(query, apiKey, ac.signal)
        .then((p) => { if (!ac.signal.aborted) { setPredictions(p); setShowDropdown(true) } })
        .finally(() => { if (!ac.signal.aborted) setIsSearching(false) })
    }, 300)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      abortRef.current?.abort()
    }
  }, [query, apiKey])

  const handleSelect = useCallback(async (pred: Prediction) => {
    setResolvingId(pred.placeId)
    setShowDropdown(false)
    setQuery('')
    try {
      const details = await fetchPlaceDetails(pred.placeId, apiKey)
      if (details) {
        // Prepend the primary text to give a human-readable name
        onChange({
          ...details,
          name: pred.primaryText + (pred.secondaryText ? `, ${pred.secondaryText.split(',')[0]}` : ''),
        })
      }
    } finally {
      setResolvingId(null)
    }
  }, [apiKey, onChange])

  const handleOutletLocation = useCallback(() => {
    if (!hasOutletCoords) return
    onChange({
      name: outletName ?? 'Outlet',
      lat: outletLat!,
      lng: outletLng!,
      radius: 300,
    })
  }, [hasOutletCoords, outletName, outletLat, outletLng, onChange])

  const handleClear = useCallback(() => {
    onChange(null)
    setQuery('')
  }, [onChange])

  // ── Render ────────────────────────────────────────────────────────────────────

  if (value) {
    return (
      <div className="rounded-xl border border-border bg-muted/30 p-3 flex items-center gap-3 group">
        <a 
          href={`https://www.google.com/maps/search/?api=1&query=${value.lat},${value.lng}`}
          target="_blank"
          rel="noopener noreferrer"
          className="h-9 w-9 rounded-lg bg-primary flex items-center justify-center shrink-0 hover:bg-primary/90 transition-colors"
          title="View on Google Maps"
        >
          <MapPin className="h-4 w-4 text-primary-foreground" />
        </a>
        <div className="flex-1 min-w-0">
          <a 
            href={`https://www.google.com/maps/search/?api=1&query=${value.lat},${value.lng}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium truncate hover:underline"
            title="View on Google Maps"
          >
            {value.name}
          </a>
          <p className="text-xs text-muted-foreground mt-0.5">
            {formatRadius(value.radius)} · {radiusLabel(value.radius)}
          </p>
        </div>
        <button
          type="button"
          onClick={handleClear}
          className="p-1 rounded-md text-muted-foreground hover:text-foreground transition-colors"
          title="Remove location"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {/* Search input */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
        <Input
          ref={inputRef}
          value={query}
          onChange={(e) => { setQuery(e.target.value); if (!e.target.value) { setPredictions([]); setShowDropdown(false) } }}
          onFocus={() => predictions.length > 0 && setShowDropdown(true)}
          placeholder="Search for a place, area, or city…"
          className="pl-9 pr-9"
        />
        {isSearching || resolvingId ? (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground animate-spin" />
        ) : query ? (
          <button
            type="button"
            onClick={() => { setQuery(''); setPredictions([]); setShowDropdown(false) }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        ) : null}

        {/* Dropdown predictions */}
        {showDropdown && predictions.length > 0 && (
          <div className="absolute z-50 w-full mt-1 rounded-xl border border-border bg-popover shadow-lg overflow-hidden">
            {predictions.map((p, i) => (
              <button
                key={p.placeId}
                type="button"
                className={cn(
                  'w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-accent/50 transition-colors',
                  i < predictions.length - 1 && 'border-b border-border',
                )}
                onClick={() => handleSelect(p)}
              >
                <MapPin className="h-4 w-4 text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{p.primaryText}</p>
                  {p.secondaryText && (
                    <p className="text-xs text-muted-foreground truncate">{p.secondaryText}</p>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Quick actions */}
      <div className="flex gap-2">
        {hasOutletCoords && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="flex-1 text-xs"
            onClick={handleOutletLocation}
          >
            <Building2 className="h-3.5 w-3.5 mr-1.5" />
            Use outlet location
          </Button>
        )}
        <p className="flex-1 text-xs text-muted-foreground self-center leading-relaxed">
          Radius is auto-set by place type — venue 300 m, area 3 km, city 20 km.
        </p>
      </div>
    </div>
  )
}
