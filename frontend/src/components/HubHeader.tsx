import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

export interface HubTab {
  value: string
  label: string
}

interface HubHeaderProps {
  title: string
  subtitle: string
  tabs: HubTab[]
  activeTab: string
  onTabChange: (value: string) => void
}

/**
 * Shared header for the Content Studio / feature hubs (Chills, Club Talks, UGC,
 * Boost, Loyalty, Marketing, Google Growth).
 *
 * The title sits on the LEFT and the tab switcher on the SAME line, centered in
 * the row (a balancing spacer on the right keeps it truly centered). Stacks on
 * small screens. Tabs are large & bold and animate smoothly when switched.
 */
export default function HubHeader({ title, subtitle, tabs, activeTab, onTabChange }: HubHeaderProps) {
  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
      <div className="lg:flex-1 lg:min-w-0">
        <h1 className="text-2xl font-bold">{title}</h1>
        <p className="text-sm text-muted-foreground">{subtitle}</p>
      </div>
      <div className="flex justify-center lg:flex-1">
        <Tabs value={activeTab} onValueChange={onTabChange}>
          <TabsList className="h-auto max-w-full gap-1 overflow-x-auto p-1.5">
            {tabs.map((t) => (
              <TabsTrigger
                key={t.value}
                value={t.value}
                className="px-4 py-2 text-base font-semibold transition-all duration-300 ease-out sm:px-5 sm:text-lg"
              >
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      {/* balancing spacer keeps the tab bar centered against the title */}
      <div className="hidden lg:block lg:flex-1" />
    </div>
  )
}
