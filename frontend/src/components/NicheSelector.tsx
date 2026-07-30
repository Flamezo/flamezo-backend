import { useMemo } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { NICHE_TAXONOMY, findNode, getIndustryForNode } from '@/lib/niche-taxonomy'
import type { NicheNode } from '@/lib/niche-taxonomy'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface NicheSelectorProps {
  /** Flat list of selected niche IDs at any depth */
  value: string[]
  onChange: (ids: string[]) => void
  /** Max total selections across all levels */
  maxSelections?: number
  disabled?: boolean
  className?: string
}

// ── Pill ──────────────────────────────────────────────────────────────────────

function Pill({
  label,
  selected,
  onClick,
  disabled,
}: {
  label: string
  selected: boolean
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled && !selected}
      className={cn(
        'inline-flex items-center rounded-full border px-3 py-1 text-sm font-medium transition-all duration-150 select-none whitespace-nowrap',
        selected
          ? 'border-primary bg-primary text-primary-foreground shadow-sm'
          : 'border-border bg-background text-foreground hover:border-primary/50 hover:bg-primary/5',
        disabled && !selected && 'pointer-events-none opacity-40',
      )}
    >
      {label}
    </button>
  )
}

// ── Level row ─────────────────────────────────────────────────────────────────

function LevelRow({
  nodes,
  selected,
  onToggle,
  disabled,
}: {
  nodes: NicheNode[]
  selected: string[]
  onToggle: (id: string) => void
  disabled?: boolean
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {nodes.map((n) => (
        <Pill
          key={n.id}
          label={n.label}
          selected={selected.includes(n.id)}
          onClick={() => onToggle(n.id)}
          disabled={disabled}
        />
      ))}
    </div>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function NicheSelector({
  value,
  onChange,
  maxSelections,
  disabled,
  className,
}: NicheSelectorProps) {
  // ── Derive visible levels from current selection ──────────────────────────

  // Selected industries (level-0 nodes)
  const selectedIndustries = value.filter((id) =>
    NICHE_TAXONOMY.some((n) => n.id === id),
  )

  // For each selected industry, collect which of its children are selected
  // and whether to show the next level
  const levels = useMemo(() => {
    const result: { parent: NicheNode; selectedChildren: string[] }[] = []

    // Level 1: sub-categories of every selected industry
    const industriesWithChildren = NICHE_TAXONOMY.filter(
      (n) => selectedIndustries.includes(n.id) && (n.children?.length ?? 0) > 0,
    )
    for (const industry of industriesWithChildren) {
      const children = industry.children!
      const selectedChildren = value.filter((id) => children.some((c) => c.id === id))
      result.push({ parent: industry, selectedChildren })

      // Level 2: sub-sub-categories of every selected child
      const childrenWithChildren = children.filter(
        (c) => selectedChildren.includes(c.id) && (c.children?.length ?? 0) > 0,
      )
      for (const child of childrenWithChildren) {
        const grandchildren = child.children!
        const selectedGrandchildren = value.filter((id) =>
          grandchildren.some((g) => g.id === id),
        )
        result.push({ parent: child, selectedChildren: selectedGrandchildren })
      }
    }

    return result
  }, [value, selectedIndustries])

  // ── Handlers ─────────────────────────────────────────────────────────────

  const atMax = maxSelections !== undefined && value.length >= maxSelections

  function toggleIndustry(id: string) {
    const industry = NICHE_TAXONOMY.find((n) => n.id === id)!
    if (value.includes(id)) {
      // Deselect industry + all its descendants
      const toRemove = new Set<string>()
      toRemove.add(id)
      collectDescendants(industry, toRemove)
      onChange(value.filter((v) => !toRemove.has(v)))
    } else {
      if (atMax) return
      onChange([...value, id])
    }
  }

  function toggleChild(parentId: string, childId: string) {
    const parentNode = findNode(parentId)
    if (!parentNode) return

    if (value.includes(childId)) {
      // Deselect child + all its descendants
      const toRemove = new Set<string>()
      toRemove.add(childId)
      const childNode = findNode(childId)
      if (childNode) collectDescendants(childNode, toRemove)
      onChange(value.filter((v) => !toRemove.has(v)))
    } else {
      if (atMax) return
      onChange([...value, childId])
    }
  }

  // ── Chip display (compact selected tags) ─────────────────────────────────

  const chips = useMemo(
    () =>
      value.map((id) => ({
        id,
        label: findNode(id)?.label ?? id,
        industry: getIndustryForNode(id),
      })),
    [value],
  )

  function removeChip(id: string) {
    const node = findNode(id)
    const toRemove = new Set<string>([id])
    if (node) collectDescendants(node, toRemove)
    onChange(value.filter((v) => !toRemove.has(v)))
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className={cn('space-y-4', className)}>
      {/* Selected chips summary */}
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chips.map((chip) => (
            <span
              key={chip.id}
              className="inline-flex items-center gap-1 rounded-full bg-primary/10 border border-primary/20 px-2.5 py-0.5 text-xs font-medium text-primary"
            >
              {chip.label}
              {!disabled && (
                <button
                  type="button"
                  onClick={() => removeChip(chip.id)}
                  className="ml-0.5 rounded-full hover:bg-primary/20 p-0.5 transition-colors"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              )}
            </span>
          ))}
          {!disabled && chips.length > 0 && (
            <button
              type="button"
              onClick={() => onChange([])}
              className="text-xs text-muted-foreground hover:text-destructive transition-colors px-1"
            >
              Clear all
            </button>
          )}
        </div>
      )}

      {/* Level 0: industries */}
      <div className="space-y-1.5">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
          Industry
        </p>
        <LevelRow
          nodes={NICHE_TAXONOMY}
          selected={value}
          onToggle={toggleIndustry}
          disabled={atMax}
        />
      </div>

      {/* Cascading levels */}
      {levels.map(({ parent, selectedChildren }) => {
        const isTopLevel = NICHE_TAXONOMY.some((n) => n.id === parent.id)
        return (
          <div key={parent.id} className="space-y-1.5 animate-in fade-in slide-in-from-top-1 duration-200">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
              {isTopLevel ? parent.label : `${parent.label} · Specialisation`}
            </p>
            <LevelRow
              nodes={parent.children!}
              selected={value}
              onToggle={(childId) => toggleChild(parent.id, childId)}
              disabled={atMax}
            />
          </div>
        )
      })}

      {maxSelections && (
        <p className="text-[11px] text-muted-foreground">
          {value.length}/{maxSelections} tags selected
        </p>
      )}
    </div>
  )
}

// ── Utils ─────────────────────────────────────────────────────────────────────

function collectDescendants(node: NicheNode, acc: Set<string>) {
  for (const child of node.children ?? []) {
    acc.add(child.id)
    collectDescendants(child, acc)
  }
}
