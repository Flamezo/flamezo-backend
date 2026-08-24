import type { LucideIcon } from 'lucide-react'
import { Card } from '@/components/ui/card'

export interface StatTile {
  label: string
  value: string
  icon: LucideIcon
}

/**
 * The summary stat row used at the top of the Chills videos and Club Talks
 * posts pages (Total Views / Likes / …). One reusable component so both pages
 * stay identical — 2 columns on mobile, then 3 or 4 depending on tile count.
 */
export default function StatTiles({ stats }: { stats: StatTile[] }) {
  const cols = stats.length >= 4 ? 'sm:grid-cols-4' : 'sm:grid-cols-3'
  return (
    <div className={`grid grid-cols-2 ${cols} gap-4`}>
      {stats.map(({ label, value, icon: Icon }) => (
        <Card key={label} className="p-4">
          <div className="flex items-center gap-2 text-muted-foreground mb-1">
            <Icon className="h-4 w-4" />
            <span className="text-xs">{label}</span>
          </div>
          <p className="text-2xl font-semibold tabular-nums">{value}</p>
        </Card>
      ))}
    </div>
  )
}
