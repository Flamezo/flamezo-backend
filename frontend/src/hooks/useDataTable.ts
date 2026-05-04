import { useState, useMemo, useEffect } from 'react'
import { useFrappeGetDocList, useFrappeGetCall } from '@/lib/frappe'
import { FilterCondition } from '@/components/ListFilters'

interface UseDataTableOptions {
  doctype?: string
  initialFilters?: FilterCondition[]
  initialPageSize?: number
  paramNames?: {
    page?: string
    pageSize?: string
    search?: string
    filters?: string
  }
  orderBy?: { field: string; order: 'asc' | 'desc' }
  fields?: string[]
  searchFields?: string[]
  customEndpoint?: string
  customParams?: Record<string, any>
  debugId?: string
}

export function useDataTable(options: UseDataTableOptions) {
  const {
    doctype,
    initialFilters = [],
    initialPageSize = 20,
    paramNames = {
      page: 'page',
      pageSize: 'page_size',
      search: 'search',
      filters: 'filters'
    },
    orderBy = { field: 'modified', order: 'desc' },
    fields = ['name'],
    searchFields = ['name'],
    customEndpoint,
    customParams = {},
    debugId
  } = options

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(initialPageSize)
  const [searchQuery, setSearchQuery] = useState('')
  const [filters, setFilters] = useState<FilterCondition[]>(initialFilters)

  // Reset page when search or filters change
  useEffect(() => {
    setPage(1)
  }, [searchQuery, filters, pageSize])

  // Prepare filters for Frappe
  const frappeFilters = useMemo(() => {
    // Transform from [{fieldname, operator, value}] to [['fieldname', 'operator', 'value']]
    return filters.map(f => [f.fieldname, f.operator, f.value])
  }, [filters])

  // Data fetching
  let data: any[] = []
  let isLoading = false
  let mutate: () => void = () => {}
  let totalCount = 0

  if (customEndpoint) {
    // Construct params for custom endpoint
    const customEndpointParams: Record<string, any> = {
      ...customParams,
      [paramNames.page || 'page']: page,
      [paramNames.pageSize || 'page_size']: pageSize,
    }

    if (searchQuery && paramNames.search) {
      customEndpointParams[paramNames.search] = searchQuery
    }

    if (frappeFilters.length > 0 && paramNames.filters) {
      customEndpointParams[paramNames.filters] = JSON.stringify(frappeFilters)
    }

    const { data: response, isLoading: loading, mutate: refresh } = useFrappeGetCall(
      customEndpoint,
      customEndpointParams,
      debugId ? `${debugId}-${page}-${pageSize}-${searchQuery}-${JSON.stringify(filters)}` : null
    )

    // Handle standard production-grade API response structure
    const result = (response as any)?.message || response
    
    // Robust data extraction
    if (Array.isArray(result?.data)) {
      data = result.data
    } else if (result?.data?.items && Array.isArray(result.data.items)) {
      data = result.data.items
    } else {
      // Fallback: find first array property in data
      const firstArrayKey = Object.keys(result?.data || {}).find(k => Array.isArray(result?.data?.[k]))
      data = firstArrayKey ? result?.data?.[firstArrayKey] : []
    }

    // Robust total count extraction
    totalCount = result?.total_count || 
                 result?.total || 
                 result?.data?.total || 
                 result?.data?.totalCount || 
                 result?.data?.pagination?.total || 
                 data.length

    isLoading = loading
    mutate = refresh
  } else if (doctype) {
    // Standard DocList call
    const listFilters = [...frappeFilters]
    let orFilters: any[] = []

    if (searchQuery) {
      // If we have single search field, just add to filters
      if (searchFields.length === 1) {
        listFilters.push([searchFields[0], 'like', `%${searchQuery}%`])
      } else {
        // Construct or_filters for multiple fields
        orFilters = searchFields.map(f => [f, 'like', `%${searchQuery}%`])
      }
    }

    const { data: listData, isLoading: loading, mutate: refresh } = useFrappeGetDocList(doctype, {
      fields,
      filters: listFilters as any,
      orFilters: orFilters.length > 0 ? orFilters : undefined,
      orderBy: orderBy as any,
      limit_start: (page - 1) * pageSize,
      limit: pageSize,
    }, debugId ? `${debugId}-${page}-${pageSize}-${JSON.stringify(listFilters)}-${JSON.stringify(orFilters)}` : null)

    // Fetch count separately
    const { data: countData, mutate: refreshCount } = useFrappeGetCall('frappe.client.get_count', {
      doctype,
      filters: JSON.stringify(listFilters),
      or_filters: orFilters.length > 0 ? JSON.stringify(orFilters) : undefined
    }, doctype ? `count-${doctype}-${JSON.stringify(listFilters)}-${JSON.stringify(orFilters)}` : null)

    data = listData || []
    totalCount = (countData as any)?.message || 0
    isLoading = loading
    mutate = () => { refresh(); refreshCount() }
  }

  // Sync internal filters with initialFilters when they change (e.g. restaurant switch)
  useEffect(() => {
    setFilters(initialFilters)
  }, [JSON.stringify(initialFilters)])

  return {
    data,
    isLoading,
    mutate,
    page,
    setPage,
    pageSize,
    setPageSize,
    totalCount,
    searchQuery,
    setSearchQuery,
    filters,
    setFilters
  }
}
