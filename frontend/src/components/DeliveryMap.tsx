import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { useOutlet } from '@/contexts/OutletContext'

interface DeliveryMapProps {
  pickupLocation?: { lat: number; lng: number }
  dropLocation?: { lat: number; lng: number }
  riderLocation?: { lat: number; lng: number }
  riderLastUpdated?: string
  outletName?: string
}

declare global {
  interface Window {
    google: any
  }
}

export default function DeliveryMap({ 
  pickupLocation, 
  dropLocation, 
  riderLocation, 
  riderLastUpdated,
  outletName 
}: DeliveryMapProps) {
  const mapRef = useRef<HTMLDivElement>(null)
  const [map, setMap] = useState<any>(null)
  const [markers, setMarkers] = useState<{ [key: string]: any }>({})
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const { googleMapsApiKey } = useOutlet()
  const activeMapsKey = googleMapsApiKey || (import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined)

  useEffect(() => {
    if (!activeMapsKey) return

    const loadGoogleMaps = () => {
      if (window.google && window.google.maps) {
        initMap()
        return
      }

      const script = document.createElement('script')
      script.src = `https://maps.googleapis.com/maps/api/js?key=${activeMapsKey}&libraries=places&v=beta`
      script.async = true
      script.defer = true
      script.onload = initMap
      script.onerror = () => setError('Failed to load Google Maps')
      document.head.appendChild(script)
    }

    const initMap = () => {
      if (!mapRef.current || !window.google) return

      const center = riderLocation || dropLocation || pickupLocation || { lat: 21.1702, lng: 72.8311 } // Surat fallback
      
      const newMap = new window.google.maps.Map(mapRef.current, {
        center,
        zoom: 14,
        mapId: 'DELIVERY_MAP_ID', // Optional: requires Cloud Console setup
        disableDefaultUI: true,
        zoomControl: true,
      })

      setMap(newMap)
      setIsLoading(false)
    }

    loadGoogleMaps()
  }, [activeMapsKey])

  useEffect(() => {
    if (!map || !window.google) return

    const google = window.google
    const currentMarkers: { [key: string]: any } = { ...markers }

    const updateMarker = (id: string, position: { lat: number; lng: number }, title: string, color: string) => {
      if (currentMarkers[id]) {
        currentMarkers[id].setPosition(position)
      } else {
        // Simple circle marker for now, can be improved with SVG icons
        const marker = new google.maps.Marker({
          position,
          map,
          title,
          icon: {
            path: google.maps.SymbolPath.CIRCLE,
            fillColor: color,
            fillOpacity: 1,
            strokeWeight: 2,
            strokeColor: '#FFFFFF',
            scale: 10,
          }
        })
        currentMarkers[id] = marker
      }
    }

    if (pickupLocation) {
      updateMarker('pickup', pickupLocation, outletName || 'Restaurant', '#3B82F6')
    }

    if (dropLocation) {
      updateMarker('drop', dropLocation, 'Customer', '#10B981')
    }

    if (riderLocation) {
      updateMarker('rider', riderLocation, 'Delivery Rider', '#F59E0B')
    }

    // Auto-fit bounds if we have multiple points
    const bounds = new google.maps.LatLngBounds()
    let pointsCount = 0
    if (pickupLocation) { bounds.extend(pickupLocation); pointsCount++ }
    if (dropLocation) { bounds.extend(dropLocation); pointsCount++ }
    if (riderLocation) { bounds.extend(riderLocation); pointsCount++ }

    if (pointsCount > 1) {
      map.fitBounds(bounds, 50) // 50px padding
    } else if (pointsCount === 1) {
      map.setCenter(riderLocation || dropLocation || pickupLocation)
    }

    setMarkers(currentMarkers)
  }, [map, pickupLocation, dropLocation, riderLocation])

  if (error) {
    return (
      <div className="h-64 flex items-center justify-center bg-muted rounded-lg border border-dashed text-destructive text-sm p-4 text-center">
        {error}
      </div>
    )
  }

  return (
    <div className="relative w-full h-[400px] rounded-xl overflow-hidden border shadow-inner bg-muted">
      {isLoading && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-muted/80 backdrop-blur-sm">
          <Loader2 className="h-8 w-8 animate-spin text-primary mb-2" />
          <p className="text-xs font-medium text-muted-foreground tracking-wide uppercase">Initializing Live Map...</p>
        </div>
      )}
      <div ref={mapRef} className="w-full h-full" />
      
      {/* Legend / Overlay */}
      {!isLoading && (
        <div className="absolute top-4 left-4 bg-background/90 backdrop-blur-md p-3 rounded-lg border shadow-lg flex flex-col gap-2 pointer-events-none">
          {pickupLocation && (
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-blue-500 border border-white" />
              <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">{outletName || 'Restaurant'}</span>
            </div>
          )}
          {dropLocation && (
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-green-500 border border-white" />
              <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Drop Location</span>
            </div>
          )}
          {riderLocation && (
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-amber-500 border border-white animate-pulse" />
              <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Rider (Live)</span>
            </div>
          )}
        </div>
      )}

      {riderLastUpdated && (
        <div className="absolute bottom-4 right-4 bg-background/90 backdrop-blur-md px-2 py-1 rounded text-[9px] font-mono text-muted-foreground border shadow-sm">
          Last updated: {new Date(riderLastUpdated).toLocaleTimeString()}
        </div>
      )}
    </div>
  )
}
