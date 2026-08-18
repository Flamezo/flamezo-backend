import {
  Home,
  TrendingUp,
  Package,
  Calculator,
  Layers,
  FolderTree,
  Users,
  Tag,
  PartyPopper,
  Wallet,
  Settings,
  BarChart3,
  Megaphone,
  CheckCircle2,
  Globe,
  Sparkles,
  Star,
  Zap,
  Plus,
  QrCode,
  Store,
  CreditCard,
  Landmark,
  Shield,
  Send,
  Calendar,
  Dumbbell,
  Scissors,
  ShoppingBag,
  Trophy,
  Gamepad2,
  ClipboardList,
  Wrench,
  Wand2,
  Film,
  Upload,
  Play,
  Flame,
} from 'lucide-react'

export type OutletType =
  | 'dining'
  | 'cafe'
  | 'wellness'
  | 'fitness'
  | 'sports_court'
  | 'sports_venue'
  | 'fashion'

export interface NavLink {
  type: 'link'
  name: string
  href: string
  icon: any
  feature?: string
  adminOnly?: boolean
  badgeHref?: string
}

export interface NavGroup {
  type: 'group'
  id: string
  name: string
  icon: any
  feature?: string
  adminOnly?: boolean
  children: Omit<NavLink, 'type'>[]
}

export type NavItem = NavLink | NavGroup

export function getIndustryLabel(outletType: string): string {
  const labels: Record<string, string> = {
    dining: 'Restaurant',
    cafe: 'Café',
    wellness: 'Wellness Studio',
    fitness: 'Fitness Studio',
    sports_court: 'Sports Court',
    sports_venue: 'Sports Venue',
    fashion: 'Fashion Store',
  }
  return labels[outletType] || 'Outlet'
}

export function getCatalogueLabel(outletType: string): { singular: string; plural: string } {
  const map: Record<string, { singular: string; plural: string }> = {
    wellness: { singular: 'Service', plural: 'Services' },
    fitness: { singular: 'Class', plural: 'Classes' },
    sports_venue: { singular: 'Activity', plural: 'Activities' },
    fashion: { singular: 'Product', plural: 'Products' },
  }
  return map[outletType] || { singular: 'Item', plural: 'Items' }
}

// Shared nav items present for every industry
function sharedItems(isAdmin: boolean): NavItem[] {
  return [
    { type: 'link', name: 'Dashboard', href: '/dashboard', icon: Home },
    { type: 'link', name: 'Growth Dashboard', href: '/growth-dashboard', icon: TrendingUp },
  ]
}

function sharedBottomItems(isAdmin: boolean): NavItem[] {
  return [
    { type: 'link', name: 'Customers', href: '/customers', icon: Users, feature: 'customer' },
    { type: 'link', name: 'Manage Offer/Coupons', href: '/coupons', icon: Tag, feature: 'coupons' },
    { type: 'link', name: 'Hot Drops', href: '/hot-drops', icon: Flame, feature: 'coupons' },
    {
      type: 'group',
      id: 'loyalty-growth',
      name: 'Loyalty & Growth',
      icon: Wallet,
      feature: 'loyalty',
      children: [
        { name: 'Loyalty Settings', href: '/loyalty-settings', icon: Settings, feature: 'loyalty' },
        { name: 'Analytics', href: '/loyalty-analytics', icon: BarChart3, feature: 'loyalty' },
      ],
    },
    {
      type: 'group',
      id: 'ugc-cashback',
      name: 'UGC Cashback',
      icon: Megaphone,
      children: [
        { name: 'Configure Offer', href: '/ugc-cashback/config', icon: Settings },
        { name: 'Story Approvals', href: '/ugc-cashback/approvals', icon: CheckCircle2, badgeHref: '/ugc-cashback/approvals' },
        { name: 'Analytics', href: '/ugc-cashback/analytics', icon: BarChart3 },
      ],
    },
    {
      type: 'group',
      id: 'chills',
      name: 'Chills',
      icon: Film,
      children: [
        { name: 'Upload Video', href: '/chills/upload', icon: Upload },
        { name: 'My Videos', href: '/chills/videos', icon: Play },
        { name: 'Analytics', href: '/chills/analytics', icon: BarChart3 },
      ],
    },
    {
      type: 'group',
      id: 'google-growth',
      name: 'Google Growth',
      icon: Globe,
      feature: 'google_growth',
      children: [
        { name: 'Discovery Loop', href: '/google-growth', icon: Sparkles, feature: 'google_growth' },
        { name: 'Reviews & AI Reply', href: '/google-growth/reviews', icon: Star, feature: 'google_growth_ai' },
      ],
    },
    {
      type: 'group',
      id: 'boost',
      name: 'Boost',
      icon: Zap,
      children: [
        { name: 'Overview', href: '/boost', icon: Megaphone },
        { name: 'New Campaign', href: '/boost/new', icon: Plus },
        { name: 'Redeem Coupon', href: '/boost/redeem', icon: Tag },
      ],
    },
    {
      type: 'group',
      id: 'setup-config',
      name: 'Setup & Config',
      icon: Wrench,
      children: [
        { name: 'Setup Wizard', href: '/setup', icon: Wand2 },
        { name: 'Team Management', href: '/team', icon: Users, adminOnly: true },
        { name: 'Manage QR Code', href: '/qr-codes', icon: QrCode },
        { name: 'Gallery Management', href: '/gallery-management', icon: Star },
      ],
    },
    { type: 'link', name: 'Customer pay & Usage', href: '/billing', icon: CreditCard, feature: 'customer_pay_and_usage' },
    { type: 'link', name: 'Direct Bank Payouts', href: '/route-kyc', icon: Landmark },
    { type: 'link', name: 'Merchant Management', href: '/admin/merchants', icon: Shield, adminOnly: true },
    { type: 'link', name: 'Customer Management', href: '/admin/customers', icon: Users, adminOnly: true },
    {
      type: 'group',
      id: 'marketing-studio',
      name: 'Marketing Studio',
      icon: Megaphone,
      feature: 'marketing_studio',
      adminOnly: true,
      children: [
        { name: 'Performance', href: '/marketing', icon: BarChart3, feature: 'marketing_studio' },
        { name: 'Campaigns', href: '/marketing/campaigns', icon: Send, feature: 'marketing_studio', adminOnly: true },
        { name: 'Automation', href: '/marketing/automation', icon: Zap, feature: 'marketing_studio', adminOnly: true },
        { name: 'Segments', href: '/marketing/segments', icon: Users, feature: 'marketing_studio', adminOnly: true },
        { name: 'Analytics', href: '/marketing/analytics', icon: TrendingUp, feature: 'marketing_studio' },
      ],
    },
  ]
}

// Per-industry product management + bookings groups
function industryProductGroup(outletType: string): NavItem {
  switch (outletType) {
    case 'wellness':
      return {
        type: 'group',
        id: 'manage-product',
        name: 'Manage Services',
        icon: Scissors,
        children: [
          { name: 'Services Catalogue', href: '/catalogue', icon: ClipboardList },
          { name: 'Add-on Groups', href: '/addon-groups', icon: Layers },
          { name: 'Recommendations', href: '/recommendations-engine', icon: FolderTree, feature: 'ai_recommendations' },
        ],
      }
    case 'fitness':
      return {
        type: 'group',
        id: 'manage-product',
        name: 'Manage Classes',
        icon: Dumbbell,
        children: [
          { name: 'Class Catalogue', href: '/catalogue', icon: ClipboardList },
          { name: 'Add-on Groups', href: '/addon-groups', icon: Layers },
          { name: 'Recommendations', href: '/recommendations-engine', icon: FolderTree, feature: 'ai_recommendations' },
        ],
      }
    case 'sports_court':
      return {
        type: 'group',
        id: 'manage-product',
        name: 'Manage Courts',
        icon: Trophy,
        children: [
          { name: 'Courts Setup', href: '/courts', icon: Trophy },
          { name: 'Add-on Groups', href: '/addon-groups', icon: Layers },
        ],
      }
    case 'sports_venue':
      return {
        type: 'group',
        id: 'manage-product',
        name: 'Manage Activities',
        icon: Gamepad2,
        children: [
          { name: 'Activities Catalogue', href: '/catalogue', icon: ClipboardList },
          { name: 'Add-on Groups', href: '/addon-groups', icon: Layers },
          { name: 'Recommendations', href: '/recommendations-engine', icon: FolderTree, feature: 'ai_recommendations' },
        ],
      }
    case 'fashion':
      return {
        type: 'group',
        id: 'manage-product',
        name: 'Manage Products',
        icon: ShoppingBag,
        children: [
          { name: 'Product Catalogue', href: '/catalogue', icon: ClipboardList },
          { name: 'Add-on Groups', href: '/addon-groups', icon: Layers },
          { name: 'Recommendations', href: '/recommendations-engine', icon: FolderTree, feature: 'ai_recommendations' },
        ],
      }
    // dining | cafe (default)
    default:
      return {
        type: 'group',
        id: 'manage-product',
        name: 'Manage Product',
        icon: Package,
        children: [
          { name: 'Menu Management', href: '/menu', icon: Package },
          { name: 'Food Cost & Margins', href: '/menu-costing', icon: Calculator },
          { name: 'Addon Groups', href: '/addon-groups', icon: Layers },
          { name: 'Recommendations Engine', href: '/recommendations-engine', icon: FolderTree, feature: 'ai_recommendations' },
        ],
      }
  }
}

function industryBookingsItems(outletType: string): NavItem[] {
  switch (outletType) {
    case 'wellness':
    case 'fitness': {
      const label = outletType === 'fitness' ? 'Class Bookings' : 'Appointments'
      return [
        { type: 'link', name: label, href: '/appointments', icon: Calendar, feature: 'tableBooking' },
        { type: 'link', name: 'Events', href: '/events', icon: PartyPopper, feature: 'events' },
      ]
    }
    case 'sports_court':
      return [
        { type: 'link', name: 'Court Bookings', href: '/courts', icon: Trophy, feature: 'tableBooking' },
      ]
    case 'sports_venue':
      return [
        { type: 'link', name: 'Slot Bookings', href: '/appointments', icon: Calendar, feature: 'tableBooking' },
        { type: 'link', name: 'Events', href: '/events', icon: PartyPopper, feature: 'events' },
      ]
    case 'fashion':
      return [
        { type: 'link', name: 'Events', href: '/events', icon: PartyPopper, feature: 'events' },
      ]
    default:
      return [
        { type: 'link', name: 'Table Bookings', href: '/bookings', icon: Calendar, feature: 'tableBooking' },
        { type: 'link', name: 'Events', href: '/events', icon: PartyPopper, feature: 'events' },
      ]
  }
}

function industryAIItems(outletType: string): NavItem[] {
  if (outletType === 'dining' || outletType === 'cafe') {
    return [
      {
        type: 'group',
        id: 'ai-tools',
        name: 'AI Tools',
        icon: Sparkles,
        children: [
          { name: 'AI Enhancements', href: '/ai-enhancements', icon: Sparkles },
          { name: 'AI Gallery', href: '/ai-gallery', icon: Star },
          { name: 'AI Menu Background', href: '/ai-menu-theme-background', icon: Sparkles },
        ],
      },
    ]
  }
  return [
    {
      type: 'group',
      id: 'ai-tools',
      name: 'AI Tools',
      icon: Sparkles,
      children: [
        { name: 'AI Enhancements', href: '/ai-enhancements', icon: Sparkles },
        { name: 'AI Gallery', href: '/ai-gallery', icon: Star },
      ],
    },
  ]
}

export function buildNavigation(outletType: string): NavItem[] {
  const type = outletType || 'dining'
  return [
    ...sharedItems(false),
    industryProductGroup(type),
    ...industryBookingsItems(type),
    ...sharedBottomItems(false),
    ...industryAIItems(type),
  ]
}
