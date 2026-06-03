import { useEffect, useState, useMemo } from 'react'
import { MapContainer, TileLayer, Marker, Circle, Tooltip, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

interface BoostRadiusMapProps {
  lat: number
  lng: number
  radius: number // in km
  restaurantName: string
}

function MapController({ center, radius }: { center: [number, number]; radius: number }) {
  const map = useMap()
  
  useEffect(() => {
    map.setView(center)
    const zoomLevel = radius === 5 ? 12 : radius === 7 ? 11 : 10
    map.setZoom(zoomLevel)
  }, [center, radius, map])

  return null
}

export default function BoostRadiusMap({ lat, lng, radius, restaurantName }: BoostRadiusMapProps) {
  const [isDark, setIsDark] = useState(false)

  useEffect(() => {
    if (typeof document !== 'undefined') {
      setIsDark(document.documentElement.classList.contains('dark'))
      const observer = new MutationObserver(() => {
        setIsDark(document.documentElement.classList.contains('dark'))
      })
      observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
      return () => observer.disconnect()
    }
  }, [])

  const customPinIcon = useMemo(() => L.divIcon({
    html: `
      <div class="relative flex items-center justify-center w-8 h-8">
        <div class="absolute w-8 h-8 bg-orange-500/25 rounded-full animate-ping"></div>
        <svg class="w-8 h-8 drop-shadow-md text-orange-500" viewBox="0 0 24 24" fill="currentColor" stroke="white" stroke-width="1.5">
          <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" />
        </svg>
      </div>
    `,
    className: 'custom-leaflet-pin',
    iconSize: [32, 32],
    iconAnchor: [16, 32],
  }), [])

  const center: [number, number] = [lat, lng]
  const tileUrl = isDark
    ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
    : 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png'

  return (
    <div className="w-full h-full relative">
      <MapContainer
        center={center}
        zoom={12}
        className="w-full h-full z-0"
        zoomControl={false}
        attributionControl={false}
      >
        <TileLayer
          url={tileUrl}
          attribution='&copy; CARTO'
        />
        <Circle
          center={center}
          radius={radius * 1000}
          pathOptions={{
            fillColor: '#f97316',
            fillOpacity: 0.12,
            color: '#f97316',
            weight: 1.5,
            dashArray: '5, 5',
          }}
        />
        <Marker position={center} icon={customPinIcon}>
          <Tooltip 
            permanent 
            direction="top" 
            offset={[0, -8]} 
            className="!bg-card !text-foreground !border-border/60 !shadow-md !rounded-lg !px-2.5 !py-1 !text-[10px] !font-black !uppercase !tracking-wider"
          >
            {restaurantName}
          </Tooltip>
        </Marker>
        <MapController center={center} radius={radius} />
      </MapContainer>
      
      {/* Floating km overlay badge */}
      <span className="absolute bottom-2 right-2 z-10 text-[9px] font-black uppercase tracking-wider bg-orange-500 text-white px-2 py-0.5 rounded shadow-md pointer-events-none">
        {radius === 15 ? 'Whole City' : `${radius} km`} Reach
      </span>
    </div>
  )
}
