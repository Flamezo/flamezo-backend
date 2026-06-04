import { useState, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { X, Filter, Plus, Search, Loader2 } from 'lucide-react'
import { useDocTypeMeta } from '@/lib/doctype'
import { useFrappeGetDocList } from '@/lib/frappe'

export interface FilterCondition {
  fieldname: string
  operator: string
  value: any
}

interface ListFiltersProps {
  doctype: string
  filters: FilterCondition[]
  onFiltersChange: (filters: FilterCondition[]) => void
  searchQuery: string
  onSearchChange: (query: string) => void
  searchPlaceholder?: string
}

const OPERATORS = [
  { value: '=', label: 'Equals' },
  { value: '!=', label: 'Not Equals' },
  { value: '>', label: 'Greater Than' },
  { value: '<', label: 'Less Than' },
  { value: '>=', label: 'Greater Than or Equal' },
  { value: '<=', label: 'Less Than or Equal' },
  { value: 'like', label: 'Contains' },
  { value: 'not like', label: 'Does Not Contain' },
  { value: 'in', label: 'In' },
  { value: 'not in', label: 'Not In' },
  { value: 'is', label: 'Is' },
  { value: 'is not', label: 'Is Not' },
]

export function ListFilters({
  doctype,
  filters,
  onFiltersChange,
  searchQuery,
  onSearchChange,
  searchPlaceholder = 'Search...',
}: ListFiltersProps) {
  const [isOpen, setIsOpen] = useState(false)
  const { meta } = useDocTypeMeta(doctype)
  
  // Get filterable fields (exclude hidden, section breaks, column breaks, and restaurant field)
  const filterableFields = useMemo(() => {
    if (!meta?.fields) return []
    return meta.fields.filter(field => 
      !field.hidden && 
      field.fieldtype !== 'Section Break' && 
      field.fieldtype !== 'Column Break' &&
      field.fieldtype !== 'Tab Break' &&
      field.fieldtype !== 'HTML' &&
      field.fieldtype !== 'Button' &&
      field.fieldname !== 'restaurant' // Exclude restaurant field from filters
    )
  }, [meta])

  const addFilter = () => {
    if (filterableFields.length > 0) {
      onFiltersChange([
        ...filters,
        {
          fieldname: filterableFields[0].fieldname,
          operator: '=',
          value: '',
        },
      ])
    }
  }

  const removeFilter = (index: number) => {
    onFiltersChange(filters.filter((_, i) => i !== index))
  }

  const updateFilter = (index: number, updates: Partial<FilterCondition>) => {
    const newFilters = [...filters]
    newFilters[index] = { ...newFilters[index], ...updates }
    onFiltersChange(newFilters)
  }

  const clearAllFilters = () => {
    onFiltersChange([])
  }

  const activeFiltersCount = filters.filter(f => {
    // Count filters with valid values (including false and 0)
    return f.value !== '' && f.value !== null && f.value !== undefined
  }).length

  return (
    <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
      <div className="relative flex-1 w-full sm:max-w-sm">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          type="text"
          placeholder={searchPlaceholder}
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-9 pr-9"
        />
        {searchQuery && (
          <button
            onClick={() => onSearchChange('')}
            className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Filter Button */}
      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogTrigger asChild>
          <Button variant="outline" className="w-full sm:w-auto">
            <Filter className="h-4 w-4 mr-2" />
            Filters
            {activeFiltersCount > 0 && (
              <Badge variant="secondary" className="ml-2">
                {activeFiltersCount}
              </Badge>
            )}
          </Button>
        </DialogTrigger>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Filters</DialogTitle>
            <DialogDescription>
              Add filters to narrow down your results. You can filter by any field.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 mt-4">
            {/* Active Filters */}
            {filters.length > 0 && (
              <div className="space-y-3">
                {filters.map((filter, index) => {
                  const field = filterableFields.find(f => f.fieldname === filter.fieldname)
                  return (
                    <div key={index} className="flex flex-col sm:flex-row gap-2 sm:items-end p-3 border border-border rounded-md bg-muted/50">
                      <div className="flex-1 grid grid-cols-1 sm:grid-cols-3 gap-2">
                        {/* Field Select */}
                        <div>
                          <Label className="text-xs text-muted-foreground mb-1 block">Field</Label>
                          <Select
                            value={filter.fieldname}
                            onValueChange={(value) => updateFilter(index, { fieldname: value, value: '' })}
                          >
                            <SelectTrigger className="h-9">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {filterableFields.map((f) => (
                                <SelectItem key={f.fieldname} value={f.fieldname}>
                                  {f.label || f.fieldname}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>

                        {/* Operator Select */}
                        <div>
                          <Label className="text-xs text-muted-foreground mb-1 block">Operator</Label>
                          <Select
                            value={filter.operator}
                            onValueChange={(value) => updateFilter(index, { operator: value })}
                          >
                            <SelectTrigger className="h-9">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {OPERATORS.map((op) => (
                                <SelectItem key={op.value} value={op.value}>
                                  {op.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>

                        {/* Value Input */}
                        <div>
                          <Label className="text-xs text-muted-foreground mb-1 block">Value</Label>
                          {field?.fieldtype === 'Link' && field.options ? (
                            <LinkFieldSelect
                              doctype={field.options}
                              value={filter.value || ''}
                              onValueChange={(value) => updateFilter(index, { value })}
                            />
                          ) : field?.fieldtype === 'Select' && field.options ? (
                            <Select
                              value={filter.value || ''}
                              onValueChange={(value) => updateFilter(index, { value })}
                            >
                              <SelectTrigger className="h-9">
                                <SelectValue placeholder="Select value" />
                              </SelectTrigger>
                              <SelectContent>
                                {field.options.split('\n')
                                  .filter(option => option.trim() !== '') // Filter out empty strings
                                  .map((option) => (
                                    <SelectItem key={option} value={option.trim()}>
                                      {option.trim()}
                                    </SelectItem>
                                  ))}
                              </SelectContent>
                            </Select>
                          ) : field?.fieldtype === 'Check' ? (
                            <Select
                              value={filter.value === true || filter.value === '1' || filter.value === 1 ? '1' : filter.value === false || filter.value === '0' || filter.value === 0 ? '0' : ''}
                              onValueChange={(value) => updateFilter(index, { value: value === '1' ? true : value === '0' ? false : null })}
                            >
                              <SelectTrigger className="h-9">
                                <SelectValue placeholder="Select value" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="1">Yes</SelectItem>
                                <SelectItem value="0">No</SelectItem>
                              </SelectContent>
                            </Select>
                          ) : (
                            <Input
                              type={field?.fieldtype === 'Int' || field?.fieldtype === 'Float' || field?.fieldtype === 'Currency' ? 'number' : 'text'}
                              value={filter.value || ''}
                              onChange={(e) => updateFilter(index, { value: e.target.value })}
                              placeholder="Enter value"
                              className="h-9"
                            />
                          )}
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeFilter(index)}
                        className="h-9 w-9 p-0"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  )
                })}
              </div>
            )}

            {/* Add Filter Button */}
            <Button
              variant="outline"
              onClick={addFilter}
              className="w-full"
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Filter
            </Button>

            {/* Clear All Button */}
            {filters.length > 0 && (
              <Button
                variant="ghost"
                onClick={clearAllFilters}
                className="w-full"
              >
                Clear All Filters
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// Component for Link field dropdown
function LinkFieldSelect({ 
  doctype, 
  value, 
  onValueChange 
}: { 
  doctype: string
  value: string
  onValueChange: (value: string) => void
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  
  // Fetch linked doctype records with search
  const { data: linkedDocs, isLoading } = useFrappeGetDocList(
    doctype,
    {
      fields: ['name'],
      filters: searchQuery ? [['name', 'like', `%${searchQuery}%`]] : undefined,
      limit: 100,
      orderBy: { field: 'name', order: 'asc' }
    },
    searchQuery ? `link-filter-${doctype}-${searchQuery}` : `link-filter-${doctype}`
  )

  // Get display value
  const displayValue = value || ''

  return (
    <Select 
      value={value || ''} 
      onValueChange={onValueChange}
      open={isOpen}
      onOpenChange={setIsOpen}
    >
      <SelectTrigger className="h-9">
        <SelectValue placeholder={isLoading ? "Loading..." : `Select ${doctype}`}>
          {displayValue || `Select ${doctype}`}
        </SelectValue>
      </SelectTrigger>
      <SelectContent className="max-h-[300px]">
        {/* Search input */}
        <div className="p-2 border-b border-border sticky top-0 bg-background z-10">
          <Input
            type="text"
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
            }}
            className="h-8"
            autoFocus
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              e.stopPropagation()
              if (e.key === 'Escape') {
                setIsOpen(false)
              }
            }}
          />
        </div>
        
        {/* Options list */}
        <div className="max-h-[250px] overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center p-4">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          ) : linkedDocs && linkedDocs.length > 0 ? (
            linkedDocs
              .filter((doc: any) => doc.name && doc.name.trim() !== '') // Filter out empty names
              .map((doc: any) => (
                <SelectItem 
                  key={doc.name} 
                  value={doc.name}
                  onClick={() => {
                    onValueChange(doc.name)
                    setIsOpen(false)
                    setSearchQuery('')
                  }}
                >
                  {doc.name}
                </SelectItem>
              ))
          ) : (
            <div className="p-4 text-sm text-muted-foreground text-center">
              {searchQuery ? 'No results found' : 'No records available'}
            </div>
          )}
        </div>
      </SelectContent>
    </Select>
  )
}

