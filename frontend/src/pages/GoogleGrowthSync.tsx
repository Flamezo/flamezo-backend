import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappeGetDocList, useFrappePostCall } from '@/lib/frappe'
import { useState } from 'react'
import { Package, RefreshCw, CheckCircle2, Search, Globe, ChevronRight } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from 'sonner'
import { Link } from 'react-router-dom'

export default function GoogleGrowthSync() {
  const { selectedRestaurant, isGold } = useRestaurant()
  const [syncing, setSyncing] = useState(false)
  const [search, setSearch] = useState('')

  const { data: products, isLoading, mutate: refreshProducts } = useFrappeGetDocList('Menu Product', {
    fields: ['name', 'product_name', 'category_name', 'price', 'is_active', 'google_item_id', 'google_product_id', 'seo_slug'],
    filters: [['restaurant', '=', selectedRestaurant || '']],
    limit: 1000
  }, selectedRestaurant || '')

  const { call: syncMenu } = useFrappePostCall('flamezo_backend.flamezo.api.google_business.sync_menu_to_google')

  const handleSync = async () => {
    if (!isGold) {
      toast.error("Automated Google Sync requires a Gold plan.")
      return
    }
    
    setSyncing(true)
    try {
      const res = await syncMenu({ restaurant_id: selectedRestaurant })
      if (res.message?.success) {
        toast.success(res.message.message)
        refreshProducts()
      } else {
        toast.error(res.message?.message || "Sync failed")
      }
    } catch (err) {
      toast.error("Failed to trigger sync")
    } finally {
      setSyncing(false)
    }
  }

  const filteredProducts = products?.filter(p => 
    p.product_name.toLowerCase().includes(search.toLowerCase()) || 
    p.category_name?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1.5 text-[11px] font-bold tracking-widest uppercase text-muted-foreground/60 mb-2">
        <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
        <ChevronRight className="h-3 w-3" />
        <Link to="/google-growth" className="hover:text-foreground transition-colors">Google Growth</Link>
        <ChevronRight className="h-3 w-3" />
        <span className="text-foreground font-bold">Menu Sync</span>
      </nav>

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2 tracking-tight">
            <Package className="h-6 w-6 text-blue-500" /> Menu & Product Sync
          </h1>
          <p className="text-sm text-muted-foreground">Keep your Google Maps dishes and prices up to date.</p>
        </div>
        
        <Button 
          className="bg-blue-600 hover:bg-blue-700 text-white gap-2 h-11 px-6 shadow-lg shadow-blue-500/20" 
          onClick={handleSync}
          disabled={syncing}
        >
          <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
          {syncing ? 'Syncing...' : 'Sync Now to Google'}
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="md:col-span-1 bg-slate-50 dark:bg-slate-900/50 border-none shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">Sync Status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Total Active Products</span>
              <span className="font-bold">{products?.filter(p => p.is_active).length || 0}</span>
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Synced to Menu</span>
              <span className="font-bold text-emerald-600">{products?.filter(p => p.google_item_id).length || 0}</span>
            </div>
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Synced to Products</span>
              <span className="font-bold text-blue-600">{products?.filter(p => p.google_product_id).length || 0}</span>
            </div>
            
            <div className="pt-4 border-t border-slate-200 dark:border-slate-800">
               {!isGold && (
                 <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-100 dark:border-amber-800/50">
                    <p className="text-xs text-amber-800 dark:text-amber-200 leading-relaxed font-medium">
                      <RefreshCw className="h-3 w-3 inline mr-1" /> Automated real-time sync is a <strong>Gold</strong> feature. Upgrade to enable auto-sync on every update.
                    </p>
                 </div>
               )}
            </div>
          </CardContent>
        </Card>

        <Card className="md:col-span-2 border-none shadow-xl bg-card">
          <CardHeader className="pb-3 border-b border-muted/30">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Product Index</CardTitle>
              <div className="relative w-64">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input 
                  placeholder="Search products..." 
                  className="pl-9 h-9 text-sm"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-muted/30 text-left text-muted-foreground border-b border-muted/30 uppercase text-[10px] font-bold tracking-widest">
                    <th className="px-6 py-4">Product</th>
                    <th className="px-6 py-4">Category</th>
                    <th className="px-6 py-4">Status</th>
                    <th className="px-6 py-4">SEO Slug</th>
                    <th className="px-6 py-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-muted/30">
                  {isLoading ? (
                    [1,2,3].map(i => (
                      <tr key={i}><td colSpan={5} className="px-6 py-4"><Skeleton className="h-8 w-full" /></td></tr>
                    ))
                  ) : filteredProducts?.map(p => (
                    <tr key={p.name} className="hover:bg-muted/30 transition-colors">
                      <td className="px-6 py-4">
                        <div className="font-semibold text-foreground">{p.product_name}</div>
                        <div className="text-[10px] text-muted-foreground uppercase">Price: ₹{p.price}</div>
                      </td>
                      <td className="px-6 py-4 text-muted-foreground">{p.category_name}</td>
                      <td className="px-6 py-4">
                        <div className="flex flex-wrap gap-1.5">
                          {p.google_item_id ? (
                            <Badge variant="outline" className="bg-emerald-50 text-emerald-600 border-emerald-200 text-[10px] uppercase font-bold py-0 h-5">
                              <CheckCircle2 className="h-2.5 w-2.5 mr-1" /> Menu
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="bg-slate-100 text-slate-500 border-slate-200 text-[10px] uppercase font-bold py-0 h-5">
                              Pending
                            </Badge>
                          )}
                          {p.google_product_id && (
                             <Badge variant="outline" className="bg-blue-50 text-blue-600 border-blue-200 text-[10px] uppercase font-bold py-0 h-5">
                             <Globe className="h-2.5 w-2.5 mr-1" /> Product
                           </Badge>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4 font-mono text-[11px] text-muted-foreground max-w-[150px] truncate">
                        {p.seo_slug || '—'}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <Button variant="ghost" size="sm" asChild>
                           <Link to={`/products/${p.name}/edit`}>Edit</Link>
                        </Button>
                      </td>
                    </tr>
                  ))}
                  {filteredProducts?.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-6 py-12 text-center text-muted-foreground italic">
                         No products found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
