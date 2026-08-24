import {
  Home,
  Package,
  Calculator,
  Layers,
  FolderTree,
  Users,
  Tag,
  PartyPopper,
  Settings,
  Megaphone,
  Sparkles,
  Star,
  Zap,
  QrCode,
  CreditCard,
  Landmark,
  Shield,
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
  /** Short one-line subtitle shown under the name (top-level items only) —
   * tells a merchant what's inside before they click, since the sidebar is
   * now organized by job-to-be-done (e.g. "Grow & Promote") rather than by
   * feature name, so the label alone is less self-explanatory than before. */
  description?: string
  href: string
  icon: any
  feature?: string
  adminOnly?: boolean
  badgeHref?: string
  exactMatch?: boolean
  /** Shows a small "BETA" tag next to this item — was previously shown on
   * the whole Google Growth / Boost group header before those became
   * children of "Grow & Promote"; now marked per-item instead. */
  beta?: boolean
  /** Prefix used to decide if this row highlights as active — falls back to
   * `href` when unset. Needed for links that now point at one tab of a
   * multi-tab hub page (e.g. href '/chills/videos') but should still show
   * active on the hub's other tabs too (e.g. '/chills/upload'), which don't
   * share a literal path prefix with `href` itself. Purely a matching
   * string — it doesn't need to be a real route on its own. */
  activeMatch?: string
}

export interface NavGroup {
  type: 'group'
  id: string
  name: string
  description?: string
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

// ─────────────────────────────────────────────────────────────────────────
// Navigation — reorganized around what a merchant is trying to DO (Instagram
// Professional Dashboard / Swiggy Partner style: a handful of top-level
// destinations, each expanding to the same underlying pages) rather than by
// internal feature name. Every href below is unchanged from before this
// reorganization — this file only regroups existing links, it never renames
// a route or drops a page, so nothing that already worked can break.
// ─────────────────────────────────────────────────────────────────────────

// Shared nav items present for every industry
function sharedItems(isAdmin: boolean): NavItem[] {
  return [
    { type: 'link', name: 'Dashboard', href: '/dashboard', icon: Home },
  ]
}

// "Grow & Promote" — every tool whose job is bringing in or retaining
// customers (offers, loyalty, UGC, Google, Boost ads). Each of these used to
// be its own multi-tab group (Loyalty: 2 rows, UGC: 3, Google: 2, Boost: 3)
// — now a single row per tool, and the "tabs" live inside that tool's own
// page (see src/pages/hubs/*) instead of the sidebar.
function growPromoteGroup(): NavItem {
  return {
    type: 'group',
    id: 'grow-promote',
    name: 'Grow & Promote',
    description: 'Offers, loyalty, ads & marketing',
    icon: Megaphone,
    children: [
      { name: 'Offers & Coupons', href: '/coupons', icon: Tag, feature: 'coupons' },
      { name: 'Hot Drops', href: '/hot-drops', icon: Flame, feature: 'coupons' },
      // No activeMatch here — Loyalty's two pages (/loyalty-settings,
      // /loyalty-analytics) are hyphen-joined, not slash-nested under a
      // shared parent, so there's no boundary-safe prefix to match both
      // without risking false-positive matches on unrelated future routes.
      // Minor cosmetic gap: this row won't show "active" while on the
      // Analytics tab — harmless, unlike a boundary-unsafe prefix check.
      { name: 'Loyalty', href: '/loyalty-settings', icon: Settings, feature: 'loyalty' },
      { name: 'UGC Cashback', href: '/ugc-cashback/config', activeMatch: '/ugc-cashback', icon: Megaphone },
      { name: 'Google Growth', href: '/google-growth', icon: Sparkles, feature: 'google_growth', beta: true },
      { name: 'Boost', href: '/boost', icon: Zap, beta: true },
    ],
  }
}

// "Marketing Management" — admin-only, its own top-level destination next to
// Merchant/Event/Customer Management. Was a 5-tab group; those 5 tabs now
// live inside the MarketingHub page itself (see src/pages/hubs/MarketingHub).
function marketingManagementGroup(): NavItem {
  return {
    type: 'link',
    name: 'Marketing Management',
    href: '/marketing',
    activeMatch: '/marketing',
    icon: Megaphone,
    feature: 'marketing_studio',
    adminOnly: true,
  }
}

// "Content Studio" — everything a merchant posts or generates: Club Talks,
// Chills, AI creative tools. Club Talks and Chills were each their own
// 3-tab group before — now one row each, tabs live in the hub page.
function contentStudioGroup(outletType: string): NavItem {
  // AI Enhancements / AI Gallery hidden for now (not ready to offer yet) —
  // routes redirect to /dashboard too, see App.tsx, so a stale link/bookmark
  // doesn't land on a half-dead page. Nothing deleted, easy to bring back.
  const aiChildren: Omit<NavLink, 'type'>[] = []
  if (outletType === 'dining' || outletType === 'cafe') {
    aiChildren.push({ name: 'AI Menu Background', href: '/ai-menu-theme-background', icon: Sparkles })
  }
  return {
    type: 'group',
    id: 'content-studio',
    name: 'Content Studio',
    description: 'Posts, reels & AI creative tools',
    icon: Film,
    children: [
      { name: 'Club Talks', href: '/club-talks/posts', activeMatch: '/club-talks', icon: Megaphone },
      { name: 'Chills', href: '/chills/videos', activeMatch: '/chills', icon: Play },
      ...aiChildren,
    ],
  }
}

function sharedBottomItems(outletType: string, isAdmin: boolean): NavItem[] {
  return [
    { type: 'link', name: 'Customers', href: '/customers', icon: Users, feature: 'customer' },
    growPromoteGroup(),
    contentStudioGroup(outletType),
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
    {
      type: 'group',
      id: 'customer-payments',
      name: 'Customer Payments',
      icon: CreditCard,
      children: [
        { name: 'Customer pay & Usage', href: '/billing', icon: CreditCard, feature: 'customer_pay_and_usage' },
        { name: 'Direct Bank Payouts', href: '/route-kyc', icon: Landmark },
      ],
    },
    { type: 'link', name: 'Merchant Management', href: '/admin/merchants', icon: Shield, adminOnly: true },
    { type: 'link', name: 'Event Management', href: '/admin/events', icon: PartyPopper, adminOnly: true },
    { type: 'link', name: 'Customer Management', href: '/admin/customers', icon: Users, adminOnly: true },
    marketingManagementGroup(),
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
      ]
    }
    case 'sports_court':
      return [
        { type: 'link', name: 'Court Bookings', href: '/courts', icon: Trophy, feature: 'tableBooking' },
      ]
    case 'sports_venue':
      return [
        { type: 'link', name: 'Slot Bookings', href: '/appointments', icon: Calendar, feature: 'tableBooking' },
      ]
    case 'fashion':
      return [
      ]
    default:
      return [
        { type: 'link', name: 'Table Bookings', href: '/bookings', icon: Calendar, feature: 'tableBooking' },
      ]
  }
}

export function buildNavigation(outletType: string): NavItem[] {
  const type = outletType || 'dining'
  return [
    ...sharedItems(false),
    industryProductGroup(type),
    ...industryBookingsItems(type),
    ...sharedBottomItems(type, false),
  ]
}
