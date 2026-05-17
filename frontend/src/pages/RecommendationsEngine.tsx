import { useEffect, useMemo, useState } from 'react'
import { useFrappeGetCall, useFrappePostCall, useFrappeGetDocList } from '@/lib/frappe'
import { useRestaurant } from '../contexts/RestaurantContext'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Badge } from '../components/ui/badge'
import { Loader2, RefreshCw, ChevronRight, Utensils } from 'lucide-react'
import { toast } from 'sonner'
import { getFrappeError } from '@/lib/utils'
import { Input } from '../components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { useConfirm } from '@/hooks/useConfirm'

interface Recommendation {
  id: string
  name: string
  category?: string
  mainCategory?: string
  isVegetarian?: boolean
  price?: number
  reason?: string
  score?: number
  image?: string
  clicks?: number
  add_to_cart?: number
  co_order_freq?: number
}

interface ProductWithRecommendations {
  id: string
  name: string
  category?: string
  mainCategory?: string
  image?: string
  recommendations: Recommendation[]
  total_rec_clicks?: number
  total_rec_add_to_cart?: number
}

interface RecommendationsResponse {
  message: {
    success: boolean
    data: {
      recommendation_run: number
      recommendation_last_run: string | null
      products: ProductWithRecommendations[]
    }
  }
}

export default function RecommendationsEngine() {
  const { selectedRestaurant } = useRestaurant()
  const { confirm, ConfirmDialogComponent } = useConfirm()

  // Track which products are expanded; default is all collapsed
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedNewRec, setSelectedNewRec] = useState<Record<string, string>>({})

  const {
    data,
    isLoading,
    mutate
  } = useFrappeGetCall<RecommendationsResponse>(
    'flamezo_backend.flamezo.api.recommendations.get_recommendations_tree',
    selectedRestaurant ? { restaurant_id: selectedRestaurant } : undefined,
    selectedRestaurant ? `recommendations-tree-${selectedRestaurant}` : null
  )

  const { call: runEngine, loading: running } = useFrappePostCall(
    'flamezo_backend.flamezo.api.recommendations.run_recommendation_engine'
  )

  const { call: updateRecs, loading: updating } = useFrappePostCall(
    'flamezo_backend.flamezo.api.recommendations.update_product_recommendations'
  )

  const { data: allProductsData } = useFrappeGetDocList(
    'Menu Product',
    {
      fields: ['product_id', 'product_name', 'category_name', 'main_category'],
      filters: selectedRestaurant ? ({ restaurant: selectedRestaurant, is_active: 1 } as any) : undefined,
      limit: 500,
      orderBy: { field: 'product_name', order: 'asc' } as any
    },
    selectedRestaurant ? `recommendation-products-${selectedRestaurant}` : null
  )

  const allProducts: { product_id: string; product_name: string; category_name?: string; main_category?: string }[] =
    (allProductsData as any) || []

  const recommendationRun = data?.message?.data?.recommendation_run ?? 0
  const recommendationLastRun = data?.message?.data?.recommendation_last_run ?? null
  const products = data?.message?.data?.products ?? []

  const filteredProducts = useMemo(() => {
    if (!searchTerm.trim()) return products
    const term = searchTerm.toLowerCase()
    return products.filter(product => {
      const inRoot =
        product.name.toLowerCase().includes(term) ||
        product.id.toLowerCase().includes(term) ||
        (product.category || '').toLowerCase().includes(term) ||
        (product.mainCategory || '').toLowerCase().includes(term)

      const inChildren =
        product.recommendations?.some(rec => {
          return (
            (rec.name || '').toLowerCase().includes(term) ||
            (rec.id || '').toLowerCase().includes(term) ||
            (rec.category || '').toLowerCase().includes(term) ||
            (rec.mainCategory || '').toLowerCase().includes(term)
          )
        }) || false

      return inRoot || inChildren
    })
  }, [products, searchTerm])

  const handleSaveRecommendations = async (product: ProductWithRecommendations, newIds: string[]) => {
    if (!selectedRestaurant) return
    try {
      await updateRecs({
        restaurant_id: selectedRestaurant,
        source_product_id: product.id,
        recommendation_ids: newIds,
      } as any)
      toast.success('Recommendations updated.')
      await mutate()
    } catch (error: any) {
      toast.error('Could not update recommendations', { description: getFrappeError(error) })
    }
  }

  const handleRemoveRecommendation = (product: ProductWithRecommendations, recId: string) => {
    const remaining = product.recommendations.filter(r => r.id !== recId).map(r => r.id)
    void handleSaveRecommendations(product, remaining)
  }

  const handleAddRecommendation = (product: ProductWithRecommendations) => {
    const selectedId = selectedNewRec[product.id]
    if (!selectedId) return

    const currentIds = product.recommendations.map(r => r.id)
    if (currentIds.includes(selectedId)) {
      toast.info('This product is already in the recommendations list.')
      return
    }

    if (currentIds.length >= 8) {
      toast.error('You can only keep up to 8 recommendations.')
      return
    }

    const updatedIds = [...currentIds, selectedId]
    void handleSaveRecommendations(product, updatedIds)
  }

  useEffect(() => {
    if (!selectedRestaurant) {
      toast.info('Please select a restaurant to manage recommendations.')
    }
  }, [selectedRestaurant])

  const handleRunEngine = async () => {
    if (!selectedRestaurant) return

    const hasExisting = recommendationRun >= 1
    if (hasExisting) {
      const confirmed = await confirm({
        title: 'Re-run Recommendation Engine',
        description: 'This will re-run the AI engine and overwrite all existing recommendations with fresh scores. Co-order signals from real orders will be used. Continue?',
        variant: 'warning',
        confirmText: 'Re-run Engine',
        cancelText: 'Cancel',
      })
      if (!confirmed) return
    }

    try {
      const resp = await runEngine({ restaurant_id: selectedRestaurant })
      if ((resp as any)?.message?.success) {
        toast.success('Recommendations generated successfully for this restaurant.')
      } else {
        toast.success('Recommendations generated.')
      }
      await mutate()
    } catch (error: any) {
      toast.error('Could not run recommendation engine', { description: getFrappeError(error) })
    }
  }

  const toggleProduct = (productId: string) => {
    setExpanded(prev => ({
      ...prev,
      [productId]: !prev[productId],
    }))
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2 flex-1">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Recommendations Engine</h1>
            <p className="text-muted-foreground mt-1 text-sm sm:text-base">
              Run the AI engine once to generate optimized recommendations across the entire menu,
              then explore product-wise suggestion trees.
            </p>
          </div>
          <div className="max-w-md">
            <Input
              placeholder="Search products or recommendations..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
            />
            {products.length > 0 && (
              <p className="mt-1 text-[11px] text-muted-foreground">
                Showing {filteredProducts.length} of {products.length} products
              </p>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-2">
            <Badge variant={recommendationRun >= 1 ? 'outline' : 'default'}>
              {recommendationRun >= 1 ? 'Run' : 'Not Run Yet'}
            </Badge>
            {recommendationLastRun && (
              <span className="text-xs text-muted-foreground">
                Last run: {new Date(recommendationLastRun).toLocaleString()}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              onClick={handleRunEngine}
              disabled={!selectedRestaurant || running}
            >
              {running && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {recommendationRun >= 1 ? 'Re-run Engine' : 'Run Recommendation Engine'}
            </Button>
            <Button
              size="icon"
              variant="ghost"
              onClick={() => mutate()}
              disabled={isLoading}
              title="Refresh recommendations view"
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : !products.length ? (
        <Card>
          <CardContent className="py-10 flex flex-col items-center justify-center text-center space-y-3">
            <p className="text-base font-medium">
              {recommendationRun >= 1
                ? 'No recommendations available for this restaurant.'
                : 'No recommendations yet. Run the engine once to generate them.'}
            </p>
            <p className="text-sm text-muted-foreground max-w-md">
              Ensure your restaurant has active products and categories configured before running the
              engine. This process uses the full menu snapshot to compute suggestions.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {filteredProducts.map(product => (
            <Card key={product.id}>
              <CardHeader
                className="cursor-pointer"
                onClick={() => toggleProduct(product.id)}
              >
                <CardTitle className="flex items-center justify-between gap-2">
                  <div className="flex items-start gap-3 flex-1">
                    <ChevronRight
                      className={
                        'mt-1 h-4 w-4 text-muted-foreground transition-transform ' +
                        (expanded[product.id] ? 'rotate-90' : '')
                      }
                    />
                    <div className="flex items-center gap-3 flex-1">
                      <div className="h-10 w-10 rounded-md border border-border bg-muted/40 flex items-center justify-center overflow-hidden flex-shrink-0">
                        {product.image ? (
                          <img
                            src={product.image}
                            alt={product.name}
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <Utensils className="h-5 w-5 text-muted-foreground" />
                        )}
                      </div>
                      <div className="flex flex-col gap-1 flex-1 min-w-0">
                        <span className="truncate">{product.name}</span>
                        <span className="text-xs text-muted-foreground truncate">
                          {product.category || 'Uncategorised'} ·{' '}
                          {product.mainCategory ? product.mainCategory : 'menu item'}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {((product.total_rec_clicks ?? 0) > 0 || (product.total_rec_add_to_cart ?? 0) > 0) && (
                      <span className="text-xs text-emerald-600 dark:text-emerald-400">
                        {(product.total_rec_clicks ?? 0) > 0 && `${product.total_rec_clicks} clicks`}
                        {(product.total_rec_clicks ?? 0) > 0 && (product.total_rec_add_to_cart ?? 0) > 0 && ' · '}
                        {(product.total_rec_add_to_cart ?? 0) > 0 && `${product.total_rec_add_to_cart} added`}
                      </span>
                    )}
                    <Badge variant="secondary">
                      {product.id}
                    </Badge>
                  </div>
                </CardTitle>
              </CardHeader>
              {expanded[product.id] && (
                <CardContent>
                  {product.recommendations && product.recommendations.length > 0 ? (
                    <div className="border-l border-border pl-4 space-y-2">
                      {product.recommendations.map((rec, index) => (
                        <div
                          key={`${product.id}-${rec.id}-${index}`}
                          className="relative pl-4 py-2 rounded-md hover:bg-muted/60 transition-colors"
                        >
                          <div className="absolute left-0 top-3 w-3 h-px bg-border" />
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-3 flex-1 min-w-0">
                              <div className="h-9 w-9 rounded-md border border-border bg-muted/40 flex items-center justify-center overflow-hidden flex-shrink-0">
                                {rec.image ? (
                                  <img
                                    src={rec.image}
                                    alt={rec.name}
                                    className="h-full w-full object-cover"
                                  />
                                ) : (
                                  <Utensils className="h-4 w-4 text-muted-foreground" />
                                )}
                              </div>
                              <div className="flex flex-col gap-0.5 min-w-0">
                                <div className="flex items-center gap-2">
                                <span className="text-sm font-semibold">
                                  {index + 1}. {rec.name}
                                </span>
                                {rec.isVegetarian && (
                                  <Badge variant="outline" className="text-xs">
                                    Veg
                                  </Badge>
                                )}
                                </div>
                                <div className="text-xs text-muted-foreground">
                                  {(rec.category || '').trim() || 'Category not set'} ·{' '}
                                  {(rec.mainCategory || '').trim() || 'Type not set'}
                                </div>
                                {rec.reason && (
                                  <div className="text-xs text-muted-foreground mt-1">
                                    {rec.reason}
                                  </div>
                                )}
                                {((rec.clicks ?? 0) > 0 || (rec.add_to_cart ?? 0) > 0) && (
                                  <div className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-2">
                                    {(rec.clicks ?? 0) > 0 && (
                                      <span>{rec.clicks} click{rec.clicks !== 1 ? 's' : ''}</span>
                                    )}
                                    {(rec.add_to_cart ?? 0) > 0 && (
                                      <span>{rec.add_to_cart} added to cart</span>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>
                            <div className="flex flex-col items-end gap-1">
                              {typeof rec.price === 'number' && rec.price > 0 && (
                                <span className="text-xs font-medium">₹{rec.price}</span>
                              )}
                              {/* Score intentionally hidden in UI */}
                              <button
                                type="button"
                                className="text-[11px] text-destructive hover:underline mt-1"
                                disabled={updating}
                                onClick={e => {
                                  e.stopPropagation()
                                  handleRemoveRecommendation(product, rec.id)
                                }}
                              >
                                Remove
                              </button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      No recommendations stored for this product.
                    </p>
                  )}

                  <div className="mt-4 flex flex-col sm:flex-row sm:items-center gap-2">
                    <div className="flex-1 min-w-0">
                      {(() => {
                        const existingIds = new Set<string>([
                          product.id,
                          ...product.recommendations.map(r => r.id),
                        ])
                        const availableOptions = allProducts.filter(
                          p => !existingIds.has(p.product_id)
                        )

                        return (
                          <Select
                            value={selectedNewRec[product.id] || ''}
                            onValueChange={value =>
                              setSelectedNewRec(prev => ({
                                ...prev,
                                [product.id]: value,
                              }))
                            }
                          >
                            <SelectTrigger
                              disabled={updating || availableOptions.length === 0}
                            >
                              <SelectValue placeholder="Add another product as recommendation" />
                            </SelectTrigger>
                            <SelectContent>
                              {availableOptions.map(p => (
                                <SelectItem key={p.product_id} value={p.product_id}>
                                  <div className="flex flex-col gap-0.5">
                                    <span className="text-sm">{p.product_name}</span>
                                    <span className="text-[11px] text-muted-foreground">
                                      {p.category_name || 'Uncategorised'} ·{' '}
                                      {p.main_category || 'menu item'}
                                    </span>
                                  </div>
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        )
                      })()}
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={updating || !selectedNewRec[product.id]}
                      onClick={e => {
                        e.stopPropagation()
                        handleAddRecommendation(product)
                      }}
                    >
                      Add
                    </Button>
                  </div>
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      )}
      {ConfirmDialogComponent}
    </div>
  )
}

