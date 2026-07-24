import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardContent, CardHeader } from '@/components/ui/card'

// ─── Shared primitives ────────────────────────────────────────────────────────

function StatCardSkeleton() {
  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-8 w-8 rounded-full" />
      </div>
      <Skeleton className="h-8 w-20" />
      <Skeleton className="h-3 w-32" />
    </Card>
  )
}

function TableRowSkeleton({ cols = 5 }: { cols?: number }) {
  return (
    <div className="flex items-center gap-4 px-4 py-3 border-b border-border/50">
      {Array.from({ length: cols }).map((_, i) => (
        <Skeleton key={i} className="h-4 flex-1" style={{ maxWidth: i === 0 ? 140 : undefined }} />
      ))}
    </div>
  )
}

function FormFieldSkeleton() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-3 w-20" />
      <Skeleton className="h-10 w-full rounded-lg" />
    </div>
  )
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

export function DashboardSkeleton() {
  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Skeleton className="h-7 w-40" />
          <Skeleton className="h-4 w-56" />
        </div>
        <Skeleton className="h-9 w-28 rounded-lg" />
      </div>

      {/* Stat cards row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => <StatCardSkeleton key={i} />)}
      </div>

      {/* Chart + product split */}
      <div className="grid grid-cols-1 lg:grid-cols-7 gap-4">
        <Card className="lg:col-span-4 p-4 space-y-4">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-48 w-full rounded-lg" />
          <div className="grid grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="space-y-1">
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-5 w-16" />
              </div>
            ))}
          </div>
        </Card>
        <Card className="lg:col-span-3 p-4 space-y-3">
          <Skeleton className="h-5 w-28" />
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3">
              <Skeleton className="h-8 w-8 rounded-md flex-shrink-0" />
              <div className="flex-1 space-y-1">
                <Skeleton className="h-3 w-3/4" />
                <Skeleton className="h-2 w-full rounded-full" />
              </div>
              <Skeleton className="h-4 w-10 flex-shrink-0" />
            </div>
          ))}
        </Card>
      </div>

      {/* Bottom split */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-4 space-y-3">
          <Skeleton className="h-5 w-32" />
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 py-2 border-b border-border/30">
              <Skeleton className="h-8 w-8 rounded-full flex-shrink-0" />
              <div className="flex-1 space-y-1">
                <Skeleton className="h-3 w-2/3" />
                <Skeleton className="h-3 w-1/3" />
              </div>
              <Skeleton className="h-5 w-16 rounded-full" />
            </div>
          ))}
        </Card>
        <div className="space-y-4">
          <Card className="p-4 space-y-3">
            <Skeleton className="h-5 w-40" />
            <div className="grid grid-cols-2 gap-3">
              {Array.from({ length: 2 }).map((_, i) => (
                <div key={i} className="rounded-xl border border-border p-3 space-y-2">
                  <Skeleton className="h-8 w-8 rounded-lg" />
                  <Skeleton className="h-3 w-20" />
                  <Skeleton className="h-3 w-14" />
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}

// ─── UGC Cashback Config ──────────────────────────────────────────────────────

export function UGCConfigSkeleton() {
  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Skeleton className="h-10 w-10 rounded-xl" />
          <div className="space-y-2">
            <Skeleton className="h-7 w-44" />
            <Skeleton className="h-4 w-72" />
          </div>
        </div>
        <Skeleton className="h-9 w-32 rounded-lg" />
      </div>

      {/* 4-tile stat row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="p-4 space-y-2">
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-3 w-24" />
          </Card>
        ))}
      </div>

      {/* Template upload + preview */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="p-4 space-y-4">
          <Skeleton className="h-5 w-36" />
          <Skeleton className="h-4 w-56" />
          <Skeleton className="h-48 w-full rounded-xl" />
          <Skeleton className="h-9 w-full rounded-lg" />
        </Card>
        <Card className="p-4 space-y-4">
          <Skeleton className="h-5 w-28" />
          <div className="flex justify-center">
            <Skeleton className="h-72 w-40 rounded-2xl" />
          </div>
          <div className="flex gap-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-8 flex-1 rounded-lg" />
            ))}
          </div>
        </Card>
      </div>

      {/* Viewer coupon form */}
      <Card className="p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <Skeleton className="h-5 w-36" />
            {Array.from({ length: 4 }).map((_, i) => <FormFieldSkeleton key={i} />)}
            <Skeleton className="h-10 w-28 rounded-lg" />
          </div>
          <div className="rounded-xl border border-border p-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-3 w-full" />
            ))}
          </div>
        </div>
      </Card>
    </div>
  )
}

// ─── Coupons ──────────────────────────────────────────────────────────────────

export function CouponsSkeleton() {
  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="space-y-2">
          <Skeleton className="h-7 w-48" />
          <Skeleton className="h-4 w-64" />
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-9 w-24 rounded-lg" />
          <Skeleton className="h-9 w-32 rounded-lg" />
        </div>
      </div>

      {/* Search + filter bar */}
      <Card className="p-4">
        <div className="flex items-center gap-3">
          <Skeleton className="h-9 flex-1 rounded-lg" />
          <Skeleton className="h-9 w-32 rounded-lg" />
          <Skeleton className="h-9 w-32 rounded-lg" />
        </div>
      </Card>

      {/* Coupon card grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <Card key={i} className="overflow-hidden">
            <Skeleton className="h-1 w-full rounded-none" />
            <div className="p-4 space-y-3">
              <div className="flex items-center justify-between">
                <Skeleton className="h-5 w-24 rounded-full" />
                <Skeleton className="h-5 w-10 rounded-full" />
              </div>
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-10 w-32" />
              <div className="grid grid-cols-2 gap-2">
                {Array.from({ length: 4 }).map((_, j) => (
                  <div key={j} className="space-y-1">
                    <Skeleton className="h-2 w-12" />
                    <Skeleton className="h-3 w-16" />
                  </div>
                ))}
              </div>
              <div className="flex gap-2 pt-2 border-t border-border/50">
                <Skeleton className="h-8 flex-1 rounded-lg" />
                <Skeleton className="h-8 w-8 rounded-lg" />
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}

// ─── Loyalty Settings ─────────────────────────────────────────────────────────

export function LoyaltySettingsSkeleton() {
  return (
    <div className="space-y-6 p-6">
      {/* Header + toggle */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Skeleton className="h-10 w-10 rounded-xl" />
          <div className="space-y-2">
            <Skeleton className="h-7 w-40" />
            <Skeleton className="h-4 w-24 rounded-full" />
          </div>
        </div>
        <Card className="p-4 flex items-center gap-4">
          <div className="space-y-1">
            <Skeleton className="h-4 w-36" />
            <Skeleton className="h-3 w-48" />
          </div>
          <Skeleton className="h-6 w-11 rounded-full flex-shrink-0" />
        </Card>
      </div>

      {/* Status banner */}
      <Skeleton className="h-14 w-full rounded-xl" />

      {/* How it works — 3-col */}
      <Card className="p-6 space-y-4">
        <Skeleton className="h-5 w-40" />
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-border p-4 space-y-2">
              <Skeleton className="h-8 w-8 rounded-lg" />
              <Skeleton className="h-6 w-16" />
              <Skeleton className="h-3 w-full" />
            </div>
          ))}
        </div>
      </Card>

      {/* 2-col rules grids */}
      {Array.from({ length: 2 }).map((_, row) => (
        <div key={row} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 2 }).map((_, col) => (
            <Card key={col} className="p-4 space-y-3">
              <Skeleton className="h-5 w-32" />
              {Array.from({ length: 4 }).map((_, j) => (
                <div key={j} className="flex items-center justify-between py-1 border-b border-border/30">
                  <Skeleton className="h-3 w-28" />
                  <Skeleton className="h-4 w-16" />
                </div>
              ))}
            </Card>
          ))}
        </div>
      ))}
    </div>
  )
}

// ─── Bookings ─────────────────────────────────────────────────────────────────

export function BookingsSkeleton() {
  return (
    <div className="space-y-4 p-6">
      {/* Date navigation bar */}
      <div className="flex items-center justify-between">
        <Skeleton className="h-9 w-9 rounded-lg" />
        <div className="flex items-center gap-3">
          <Skeleton className="h-6 w-6 rounded" />
          <Skeleton className="h-6 w-40" />
        </div>
        <Skeleton className="h-9 w-9 rounded-lg" />
      </div>

      {/* Stat chips */}
      <div className="flex gap-2 flex-wrap">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-24 rounded-full" />
        ))}
      </div>

      {/* Filter + search bar */}
      <div className="flex gap-3">
        <Skeleton className="h-9 flex-1 rounded-lg" />
        <Skeleton className="h-9 w-32 rounded-lg" />
      </div>

      {/* Booking list rows */}
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Card key={i} className="p-4">
            <div className="flex items-center gap-4">
              <Skeleton className="h-6 w-20 rounded-full flex-shrink-0" />
              <Skeleton className="h-4 w-24 flex-shrink-0" />
              <Skeleton className="h-4 w-16 flex-shrink-0" />
              <div className="flex-1 space-y-1">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-24" />
              </div>
              <div className="flex gap-2">
                <Skeleton className="h-8 w-20 rounded-lg" />
                <Skeleton className="h-8 w-20 rounded-lg" />
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}

// ─── Customers ────────────────────────────────────────────────────────────────

export function CustomersSkeleton() {
  return (
    <div className="space-y-4 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Skeleton className="h-7 w-36" />
          <Skeleton className="h-4 w-52" />
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-9 w-28 rounded-lg" />
          <Skeleton className="h-9 w-9 rounded-lg" />
        </div>
      </div>

      {/* Search */}
      <Skeleton className="h-10 w-full rounded-lg" />

      {/* Table */}
      <Card>
        {/* Table header */}
        <div className="flex items-center gap-4 px-4 py-3 border-b border-border bg-muted/30">
          {[140, 100, 100, 80, 60].map((w, i) => (
            <Skeleton key={i} className="h-3" style={{ width: w, flexShrink: 0 }} />
          ))}
        </div>
        {/* Table rows */}
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-4 py-3 border-b border-border/50">
            <div className="flex items-center gap-2" style={{ width: 140, flexShrink: 0 }}>
              <Skeleton className="h-8 w-8 rounded-full" />
              <Skeleton className="h-4 w-24" />
            </div>
            <Skeleton className="h-4 w-24 flex-shrink-0" />
            <Skeleton className="h-4 w-24 flex-shrink-0" />
            <Skeleton className="h-5 w-20 rounded-full flex-shrink-0" />
            <Skeleton className="h-7 w-7 rounded ml-auto" />
          </div>
        ))}
      </Card>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-32" />
        <div className="flex gap-1">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-8 rounded" />
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Addon Groups ─────────────────────────────────────────────────────────────

export function AddonGroupsSkeleton() {
  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Skeleton className="h-7 w-40" />
          <Skeleton className="h-4 w-56" />
        </div>
        <Skeleton className="h-9 w-36 rounded-lg" />
      </div>

      {/* Template tiles */}
      <div className="flex gap-3 overflow-x-auto pb-1">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex-shrink-0 rounded-xl border border-border p-3 space-y-2" style={{ width: 120 }}>
            <Skeleton className="h-8 w-8 rounded-lg" />
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-3 w-12" />
          </div>
        ))}
      </div>

      {/* Group cards */}
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i} className="p-4 space-y-4">
            {/* Group header */}
            <div className="flex items-center gap-3">
              <Skeleton className="h-6 w-6 rounded flex-shrink-0" />
              <Skeleton className="h-5 flex-1 max-w-48" />
              <Skeleton className="h-6 w-20 rounded-full" />
              <Skeleton className="h-6 w-16 rounded-full" />
              <div className="ml-auto flex gap-2">
                <Skeleton className="h-8 w-8 rounded" />
                <Skeleton className="h-8 w-8 rounded" />
              </div>
            </div>

            {/* Items list */}
            <div className="space-y-2 pl-9">
              {Array.from({ length: 3 }).map((_, j) => (
                <div key={j} className="flex items-center gap-3 py-1">
                  <Skeleton className="h-4 flex-1" />
                  <Skeleton className="h-4 w-16" />
                  <Skeleton className="h-5 w-8 rounded" />
                  <Skeleton className="h-5 w-8 rounded" />
                  <Skeleton className="h-5 w-8 rounded" />
                  <Skeleton className="h-6 w-6 rounded" />
                </div>
              ))}
              <Skeleton className="h-8 w-full rounded-lg mt-1" />
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}

// ─── Catalogue / Menu Management ─────────────────────────────────────────────

export function CatalogueSkeleton() {
  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <div className="w-64 flex-shrink-0 border-r border-border p-4 space-y-3">
        <Skeleton className="h-9 w-full rounded-lg" />
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 py-2">
            <Skeleton className="h-4 w-4 rounded flex-shrink-0" />
            <Skeleton className="h-4 flex-1" />
            <Skeleton className="h-4 w-8" />
          </div>
        ))}
        <Skeleton className="h-9 w-full rounded-lg mt-4" />
      </div>

      {/* Content area */}
      <div className="flex-1 p-4 space-y-4">
        {/* Toolbar */}
        <div className="flex items-center gap-3">
          <Skeleton className="h-9 flex-1 max-w-64 rounded-lg" />
          <Skeleton className="h-9 w-28 rounded-lg" />
          <Skeleton className="h-9 w-28 rounded-lg" />
          <div className="ml-auto flex gap-2">
            <Skeleton className="h-9 w-32 rounded-lg" />
            <Skeleton className="h-9 w-24 rounded-lg" />
          </div>
        </div>

        {/* Item cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Card key={i} className="overflow-hidden">
              <Skeleton className="h-32 w-full rounded-none" />
              <div className="p-3 space-y-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-full" />
                <div className="flex items-center justify-between pt-1">
                  <Skeleton className="h-5 w-16" />
                  <Skeleton className="h-5 w-10 rounded-full" />
                </div>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Generic fallback (keeps existing PageSkeleton shape) ─────────────────────

export function GenericPageSkeleton() {
  return (
    <div className="space-y-6 p-6">
      <div className="space-y-2">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-4 w-64" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => <StatCardSkeleton key={i} />)}
      </div>
      <Card className="p-4 space-y-3">
        {Array.from({ length: 6 }).map((_, i) => <TableRowSkeleton key={i} />)}
      </Card>
    </div>
  )
}
