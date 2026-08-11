import { useState, useEffect, useRef } from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { MapPin, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useOutlet } from '@/contexts/OutletContext'

interface AddressAutocompleteProps {
  value: string
  onChange: (address: string) => void
  onLocationSelect?: (data: {
    address: string
    latitude: number | null
    longitude: number | null
    city?: string
    state?: string
    zipCode?: string
    googleMapUrl?: string
  }) => void
  label?: string
  required?: boolean
  readOnly?: boolean
  description?: string
  id?: string
}

declare global {
  interface Window {
    google: any
  }
}

// Default fallback key from build-time env
const ENV_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined

export default function AddressAutocomplete({
  value,
  onChange,
  onLocationSelect,
  label = 'Address',
  required = false,
  readOnly = false,
  description,
  id = 'address',
}: AddressAutocompleteProps) {
  const [suggestions, setSuggestions] = useState<any[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [autocompleteService, setAutocompleteService] = useState<any>(null)
  const [placesService, setPlacesService] = useState<any>(null)
  const [sessionToken, setSessionToken] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(false)
  const { googleMapsApiKey } = useOutlet()
  const activeMapsKey = googleMapsApiKey || ENV_MAPS_API_KEY
  const [isSelected, setIsSelected] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  // Only show suggestions after user explicitly types — prevents firing on load with saved data
  const hasUserTyped = useRef(false)

  // Close suggestions on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Load Google Maps Script & initialize Autocomplete
  useEffect(() => {
    if (!activeMapsKey || typeof window === 'undefined') return

    const initAutocomplete = async () => {
      const maps = window.google?.maps
      if (!maps) return

      try {
        let AutocompleteService: any
        let AutocompleteSessionToken: any

        if (typeof maps.importLibrary === 'function') {
          const places = await maps.importLibrary('places')
          AutocompleteService = places.AutocompleteService
          AutocompleteSessionToken = places.AutocompleteSessionToken
        } else if (maps.places) {
          AutocompleteService = maps.places.AutocompleteService
          AutocompleteSessionToken = maps.places.AutocompleteSessionToken
        } else {
          setTimeout(initAutocomplete, 500)
          return
        }

        if (AutocompleteService && AutocompleteSessionToken) {
          setAutocompleteService(new AutocompleteService())
          setSessionToken(new AutocompleteSessionToken())
        }
      } catch (error) {
        console.error('[AddressAutocomplete] Error initializing:', error)
      }
    }

    // If Google Maps is already loaded (e.g., from another component), just init
    if (window.google?.maps) {
      initAutocomplete()
      return
    }

    // If script tag already exists but not yet loaded, wait for it
    if (document.querySelector('script[src*="maps.googleapis.com"]')) {
      const checkInterval = setInterval(() => {
        if (window.google?.maps) {
          clearInterval(checkInterval)
          initAutocomplete()
        }
      }, 200)
      return
    }

    // Add the script tag
    const script = document.createElement('script')
    script.src = `https://maps.googleapis.com/maps/api/js?key=${activeMapsKey}&libraries=places&v=beta&loading=async`
    script.async = true
    script.defer = true
    script.onload = () => initAutocomplete()
    script.onerror = () => console.error('[AddressAutocomplete] Failed to load Google Maps script')
    document.head.appendChild(script)
  }, [activeMapsKey])

  // Fetch suggestions when value changes — only if user has actively typed
  useEffect(() => {
    if (!autocompleteService || !value || value.length < 2 || isSelected || !hasUserTyped.current) {
      setSuggestions([])
      setShowSuggestions(false)
      return
    }

    setIsLoading(true)
    const timer = setTimeout(async () => {
      const maps = window.google?.maps
      if (!maps) {
        setIsLoading(false)
        return
      }

      try {
        // Try new API first (v=beta)
        if (typeof maps.importLibrary === 'function') {
          const placesLib = await maps.importLibrary('places')
          if (placesLib?.AutocompleteSuggestion?.fetchAutocompleteSuggestions) {
            const { suggestions: newSugs } = await placesLib.AutocompleteSuggestion.fetchAutocompleteSuggestions({
              input: value,
              sessionToken: sessionToken,
              // No componentRestrictions - global search, no city restriction
            })
            setSuggestions(newSugs || [])
            setShowSuggestions((newSugs || []).length > 0)
            setIsLoading(false)
            return
          }
        }

        // Fallback legacy API
        autocompleteService.getPlacePredictions(
          {
            input: value,
            sessionToken: sessionToken,
            // No componentRestrictions - global search
          },
          (predictions: any, status: any) => {
            setIsLoading(false)
            if (status === 'OK' && predictions?.length) {
              setSuggestions(predictions)
              setShowSuggestions(true)
            } else {
              setSuggestions([])
              setShowSuggestions(false)
            }
          }
        )
      } catch (error) {
        console.error('[AddressAutocomplete] Error fetching predictions:', error)
        setIsLoading(false)
      }
    }, 350)

    return () => {
      clearTimeout(timer)
      setIsLoading(false)
    }
  }, [value, autocompleteService, isSelected, sessionToken])

  const handleSuggestionSelect = async (suggestion: any) => {
    const displayAddress = suggestion.placePrediction?.text?.text || suggestion.description
    onChange(displayAddress)
    setSuggestions([])
    setShowSuggestions(false)
    setIsSelected(true)

    const placeId = suggestion.placePrediction?.placeId || suggestion.place_id

    try {
      if (!window.google?.maps || !placeId) return

      let service = placesService
      if (!service) {
        const maps = window.google.maps
        let PlacesService: any

        if (typeof maps.importLibrary === 'function') {
          const places = await maps.importLibrary('places')
          PlacesService = places.PlacesService
        } else if (maps.places) {
          PlacesService = maps.places.PlacesService
        }

        if (PlacesService) {
          service = new PlacesService(document.createElement('div'))
          setPlacesService(service)
        }
      }

      if (service) {
        service.getDetails(
          {
            placeId,
            fields: ['formatted_address', 'geometry', 'address_components', 'url'],
            sessionToken,
          },
          (place: any, status: any) => {
            if (status === 'OK' && place) {
              const lat = place.geometry?.location?.lat?.() ?? null
              const lng = place.geometry?.location?.lng?.() ?? null
              const finalAddress = place.formatted_address || displayAddress
              
              // Extract city, state and zip code from address components
              let city = ''
              let state = ''
              let zipCode = ''
              
              if (place.address_components) {
                for (const component of place.address_components) {
                  const types = component.types
                  if (types.includes('locality')) {
                    city = component.long_name
                  } else if (types.includes('postal_code')) {
                    zipCode = component.long_name
                  } else if (types.includes('administrative_area_level_1')) {
                    state = component.long_name
                  } else if (!city && types.includes('administrative_area_level_2')) {
                    city = component.long_name
                  } else if (!city && types.includes('sublocality_level_1')) {
                    city = component.long_name
                  }
                }
              }

              onChange(finalAddress)

              onLocationSelect?.({ 
                address: finalAddress, 
                latitude: lat, 
                longitude: lng,
                city: city,
                state: state,
                zipCode: zipCode,
                googleMapUrl: place.url || `https://maps.google.com/?q=${encodeURIComponent(finalAddress)}`
              })

              // Refresh session token
              const maps = window.google?.maps
              if (maps?.places?.AutocompleteSessionToken) {
                setSessionToken(new maps.places.AutocompleteSessionToken())
              }
            }
          }
        )
      }
    } catch (error) {
      console.error('[AddressAutocomplete] Error fetching place details:', error)
    }
  }

  return (
    <div ref={containerRef} className="space-y-2 relative">
      <Label htmlFor={id}>
        {label}
        {required && <span className="text-destructive ml-1">*</span>}
      </Label>
      <div className="relative">
        <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none z-10" />
        <Input
          id={id}
          value={value}
          onChange={(e) => {
            setIsSelected(false)
            hasUserTyped.current = true
            onChange(e.target.value)
          }}
          onFocus={() => {
            if (suggestions.length > 0) setShowSuggestions(true)
          }}
          readOnly={readOnly}
          required={required}
          placeholder="Search for your restaurant address..."
          className={cn(
            'pl-9 pr-4',
            readOnly && 'opacity-60 cursor-not-allowed bg-muted'
          )}
          autoComplete="off"
        />
        {isLoading && !readOnly && (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground animate-spin" />
        )}
      </div>

      {/* Suggestions Dropdown */}
      {showSuggestions && suggestions.length > 0 && !readOnly && (
        <div className="absolute z-50 w-full bg-background border border-border rounded-xl shadow-xl mt-1 overflow-hidden">
          {suggestions.map((suggestion, index) => {
            const mainText =
              suggestion.placePrediction?.mainText?.text ||
              suggestion.structured_formatting?.main_text ||
              suggestion.description
            const secondaryText =
              suggestion.placePrediction?.secondaryText?.text ||
              suggestion.structured_formatting?.secondary_text ||
              ''
            return (
              <button
                key={index}
                type="button"
                className="w-full text-left px-4 py-3 hover:bg-primary/5 flex items-start gap-3 transition-colors border-b border-border/50 last:border-b-0 cursor-pointer"
                onMouseDown={(e) => {
                  e.preventDefault()
                  handleSuggestionSelect(suggestion)
                }}
              >
                <MapPin className="h-4 w-4 text-primary mt-0.5 shrink-0" />
                <div className="flex flex-col min-w-0">
                  <span className="text-sm font-medium text-foreground truncate">{mainText}</span>
                  {secondaryText && (
                    <span className="text-xs text-muted-foreground truncate">{secondaryText}</span>
                  )}
                </div>
              </button>
            )
          })}
          <div className="px-4 py-2 bg-muted/30 flex items-center justify-end gap-1">
            <span className="text-[10px] text-muted-foreground">Powered by Google</span>
          </div>
        </div>
      )}

      {description && (
        <p className="text-xs text-muted-foreground">{description}</p>
      )}
    </div>
  )
}
