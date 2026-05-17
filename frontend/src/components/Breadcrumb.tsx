import { Link, useLocation, useParams } from 'react-router-dom'
import { ChevronRight, Home } from 'lucide-react'
import { cn } from '@/lib/utils'

interface BreadcrumbItem {
  label: string
  href?: string
}

export default function Breadcrumb() {
  const location = useLocation()
  const params = useParams()

  // If page already contains a server-rendered breadcrumb/header (Frappe website),
  // don't render the SPA breadcrumb to avoid duplicate headers.
  if (typeof window !== 'undefined') {
    const serverHeader = document.querySelector('.page-head, .page-title, .page-header, .breadcrumb, header.page-head')
    if (serverHeader) return null
  }

  // Decode URL-encoded strings
  const decodeLabel = (label: string): string => {
    try {
      return decodeURIComponent(label)
    } catch {
      return label
    }
  }

  // Generate breadcrumb items based on current path
  const getBreadcrumbs = (): BreadcrumbItem[] => {
    const path = location.pathname.replace('/flamezo_backend', '') || '/dashboard'
    const segments = path.split('/').filter(Boolean)
    
    const breadcrumbs: BreadcrumbItem[] = [
      { label: 'Home', href: '/dashboard' }
    ]

    if (segments.length === 0 || (segments.length === 1 && segments[0] === 'dashboard')) {
      return breadcrumbs
    }

    // Map route segments to readable labels
    const routeLabels: Record<string, string> = {
      'dashboard': 'Dashboard',
      'setup': 'Setup Wizard',
      'orders': 'Orders',
      'past-orders': 'Past and Billed Orders',
      'customers': 'Customers',
      'products': 'Products',
      'categories': 'Categories',
      'Restaurant': 'Restaurants',
      'qr-codes': 'QR Codes',
    }

    // Special handling for Setup Wizard page - add restaurant name if available
    if (segments[0] === 'setup' && segments.length > 1) {
      breadcrumbs.push({
        label: 'Setup Wizard',
        href: '/setup'
      })
      
      // Get restaurant name from URL (second segment)
      const restaurantNameFromUrl = decodeLabel(segments[1])
      // Convert URL-friendly name back to readable format (replace hyphens with spaces, capitalize)
      const restaurantName = restaurantNameFromUrl
        .replace(/-/g, ' ')
        .split(' ')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ')
      
      breadcrumbs.push({
        label: `${restaurantName} wizard`
      })
      return breadcrumbs
    }



    let currentPath = ''
    
    segments.forEach((segment, index) => {
      // Decode the segment to handle URL encoding
      const decodedSegment = decodeLabel(segment)
      currentPath += `/${segment}`
      const isLast = index === segments.length - 1
      
      // Handle special cases
      if (segment === 'new') {
        const parent = segments[index - 1]
        const parentLabel = routeLabels[parent] || decodeLabel(parent).charAt(0).toUpperCase() + decodeLabel(parent).slice(1).replace(/-/g, ' ')
        breadcrumbs.push({
          label: `New ${parentLabel}`,
        })
        return
      }
      
      if (segment === 'edit' && segments[index - 1]) {
        const parent = segments[index - 2]
        const docName = segments[index - 1]
        const parentLabel = routeLabels[parent] || decodeLabel(parent)?.charAt(0).toUpperCase() + decodeLabel(parent)?.slice(1).replace(/-/g, ' ') || 'Item'
        breadcrumbs.push({
          label: parentLabel,
          href: `/${parent}/${docName}`
        })
        breadcrumbs.push({
          label: `Edit`,
        })
        return
      }

      // Check if it's a document ID (UUID or alphanumeric) - check params first
      const isDocId = params.docname === segment || params.orderId === segment || 
          params.productId === segment || params.categoryId === segment ||
          (segment.length > 10 && /^[a-zA-Z0-9-]+$/.test(segment) && index > 0)
      
      if (isDocId && index > 0) {
        const parent = segments[index - 1]
        const parentLabel = routeLabels[parent] || decodeLabel(parent)?.charAt(0).toUpperCase() + decodeLabel(parent)?.slice(1).replace(/-/g, ' ') || 'Detail'
        breadcrumbs.push({
          label: parentLabel,
          href: `/${parent}`
        })
        // Truncate long document IDs
        const displayName = decodedSegment.length > 20 ? `${decodedSegment.substring(0, 20)}...` : decodedSegment
        breadcrumbs.push({
          label: displayName,
        })
        return
      }

      // Regular route segment - decode and format
      let label = routeLabels[segment]
      if (!label) {
        // Decode URL-encoded characters and format
        label = decodeLabel(segment)
          .replace(/_/g, ' ')
          .replace(/-/g, ' ')
          .split(' ')
          .map(word => word.charAt(0).toUpperCase() + word.slice(1))
          .join(' ')
      }
      
      breadcrumbs.push({
        label: label,
        href: isLast ? undefined : currentPath
      })
    })

    return breadcrumbs
  }

  const breadcrumbs = getBreadcrumbs()

  // Don't show breadcrumb on dashboard (only Home)
  if (breadcrumbs.length <= 1) {
    return null
  }

  return (
    <nav className="flex items-center gap-1.5 text-sm mb-4 overflow-hidden" aria-label="Breadcrumb">
      <ol className="flex items-center gap-1.5 flex-nowrap overflow-x-auto no-scrollbar py-1">
        {breadcrumbs.map((crumb, index) => {
          const isLast = index === breadcrumbs.length - 1
          
          return (
            <li key={index} className="flex items-center gap-1.5">
              {index > 0 && (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
              )}
              {isLast ? (
                <span className="text-foreground font-medium truncate max-w-[200px]">
                  {crumb.label}
                </span>
              ) : (
                <Link
                  to={crumb.href || '#'}
                  className={cn(
                    "text-muted-foreground hover:text-foreground transition-colors truncate max-w-[200px]",
                    "hover:underline"
                  )}
                >
                  {index === 0 ? (
                    <span className="flex items-center gap-1">
                      <Home className="h-3.5 w-3.5" />
                      <span>{crumb.label}</span>
                    </span>
                  ) : (
                    crumb.label
                  )}
                </Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

