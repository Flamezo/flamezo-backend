import { useRestaurant } from '@/contexts/RestaurantContext'
import { useFrappePostCall } from '@/lib/frappe'
import { useState, useEffect } from 'react'
import { Star, Sparkles, Send, ChevronRight, Crown } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { toast } from 'sonner'
import { Link } from 'react-router-dom'

export default function GoogleGrowthReviews() {
  const { selectedRestaurant, isGold } = useRestaurant()
  const [reviews, setReviews] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [generatingFor, setGeneratingFor] = useState<string | null>(null)
  const [replies, setReplies] = useState<Record<string, string>>({})

  const { call: fetchReviews } = useFrappePostCall('flamezo_backend.flamezo.api.google_business.get_google_reviews')
  const { call: generateReply } = useFrappePostCall('flamezo_backend.flamezo.api.google_business.generate_review_reply')
  const { call: postReply } = useFrappePostCall('flamezo_backend.flamezo.api.google_business.post_review_reply')

  useEffect(() => {
    if (selectedRestaurant) {
      setLoading(true)
      fetchReviews({ restaurant_id: selectedRestaurant })
        .then((res: any) => setReviews(res.message || []))
        .finally(() => setLoading(false))
    }
  }, [selectedRestaurant, fetchReviews])

  const handleGenerateReply = async (review: any) => {
    if (!isGold) {
      toast.error("AI Review Assistant requires a Gold plan.")
      return
    }

    setGeneratingFor(review.reviewId)
    try {
      const res = await generateReply({ 
        review_text: review.comment, 
        rating: review.rating,
        restaurant_id: selectedRestaurant
      })
      if (res.message?.success) {
        setReplies(prev => ({ ...prev, [review.reviewId]: res.message.reply }))
        toast.success("AI Reply Generated!")
      } else {
        toast.error(res.message?.message || "Generation failed")
      }
    } catch (err) {
      toast.error("Failed to generate AI reply")
    } finally {
      setGeneratingFor(null)
    }
  }

  const handlePostReply = async (review: any) => {
    const replyText = replies[review.reviewId]
    if (!replyText) return

    try {
      const res = await postReply({
        restaurant_id: selectedRestaurant,
        review_name: review.name, // This is the full Google resource name
        reply_text: replyText
      })
      
      if (res.message?.success) {
        toast.success("Reply posted to Google Business Profile!")
        // Mark as replied in UI
        setReviews(prev => prev.map(r => 
          r.reviewId === review.reviewId ? { ...r, reviewReply: { comment: replyText } } : r
        ))
        setReplies(prev => {
          const n = { ...prev }; delete n[review.reviewId]; return n;
        })
      } else {
        toast.error(res.message?.message || "Failed to post reply")
      }
    } catch (err) {
      toast.error("An error occurred while posting the reply")
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1.5 text-[11px] font-bold tracking-widest uppercase text-muted-foreground/60 mb-2">
        <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
        <ChevronRight className="h-3 w-3" />
        <Link to="/google-growth" className="hover:text-foreground transition-colors">Google Growth</Link>
        <ChevronRight className="h-3 w-3" />
        <span className="text-foreground font-bold">Reviews & AI Reply</span>
      </nav>

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2 tracking-tight">
            <Star className="h-6 w-6 text-amber-500 fill-amber-500" /> Reviews & AI Assistant
          </h1>
          <p className="text-sm text-muted-foreground">Automate your reputation management with AI-powered replies.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
         <div className="lg:col-span-1 space-y-6">
            <Card className="border-none shadow-lg bg-card overflow-hidden">
                <div className="h-2 bg-gradient-to-r from-amber-400 to-orange-500" />
                <CardHeader>
                    <CardTitle className="text-sm font-bold uppercase tracking-widest text-muted-foreground">GMB Reputation</CardTitle>
                </CardHeader>
                <CardContent className="text-center pb-8">
                    <div className="text-5xl font-black mb-2 tracking-tight">4.2</div>
                    <div className="flex items-center justify-center gap-1 mb-4">
                        {[1,2,3,4].map(i => <Star key={i} className="h-4 w-4 fill-amber-500 text-amber-500" />)}
                        <Star className="h-4 w-4 text-amber-500 opacity-30" />
                    </div>
                    <p className="text-xs text-muted-foreground font-medium">Based on 142 total reviews</p>
                </CardContent>
            </Card>

            <Card className="border-none shadow-lg bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-100 dark:border-indigo-800/20">
               <CardHeader className="pb-2">
                   <CardTitle className="text-sm flex items-center gap-2 text-indigo-700 dark:text-indigo-400">
                    <Sparkles className="h-4 w-4" /> AI Efficiency
                   </CardTitle>
               </CardHeader>
               <CardContent className="space-y-4">
                   <div className="text-3xl font-bold text-indigo-900 dark:text-indigo-100">84%</div>
                   <p className="text-xs text-indigo-700/70 dark:text-indigo-300/60 font-medium">Your AI response rate. Keeping it above 80% boosts local search ranking by 1.4x.</p>
               </CardContent>
            </Card>
         </div>

         <div className="lg:col-span-3 space-y-4">
            <h2 className="text-lg font-bold flex items-center gap-2 mb-2">
                Recent Google Reviews <Badge variant="secondary" className="font-mono">{reviews.length}</Badge>
            </h2>

            {loading ? (
                [1,2,3].map(i => <Skeleton key={i} className="h-48 w-full rounded-xl" />)
            ) : reviews.map(review => (
                <Card key={review.reviewId} className="border-none shadow-md hover:shadow-lg transition-shadow bg-card overflow-hidden">
                    <CardContent className="p-6">
                        <div className="flex flex-col md:flex-row gap-6">
                            <div className="flex-1 space-y-4">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <div className="h-10 w-10 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-500 font-bold uppercase">
                                            {review.name.charAt(0)}
                                        </div>
                                        <div>
                                            <div className="font-bold flex items-center gap-2">
                                                {review.name}
                                                <Badge className="bg-blue-50 text-blue-600 border-blue-200 text-[9px] h-4 py-0 font-bold px-1.5">
                                                    Verified Buyer
                                                </Badge>
                                            </div>
                                            <div className="text-xs text-muted-foreground">{new Date(review.createTime).toLocaleDateString()} · via Google Maps</div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-0.5">
                                        {[...Array(5)].map((_, i) => (
                                            <Star key={i} className={`h-3.5 w-3.5 ${i < review.rating ? 'fill-amber-500 text-amber-500' : 'text-slate-200 dark:text-slate-700'}`} />
                                        ))}
                                    </div>
                                </div>

                                <div className="text-sm leading-relaxed text-foreground italic">
                                    "{review.comment}"
                                </div>

                                {review.reviewReply ? (
                                    <div className="pt-2 p-3 bg-slate-50 dark:bg-slate-900/50 rounded-lg border border-slate-100 dark:border-slate-800">
                                        <div className="flex items-center gap-2 text-[10px] font-black uppercase text-emerald-500 mb-1.5">
                                            <Send className="h-3 w-3" /> Your Reply
                                        </div>
                                        <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap">
                                            {review.reviewReply.comment}
                                        </p>
                                    </div>
                                ) : !replies[review.reviewId] ? (
                                    <Button 
                                        variant="outline" 
                                        size="sm" 
                                        className={`gap-2 text-xs font-bold tracking-tight ${!isGold ? 'opacity-70 grayscale' : 'border-blue-200 dark:border-blue-800 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20'}`}
                                        onClick={() => handleGenerateReply(review)}
                                        disabled={generatingFor === review.reviewId}
                                    >
                                        <Sparkles className={`h-3.5 w-3.5 ${generatingFor === review.reviewId ? 'animate-pulse' : ''}`} />
                                        {generatingFor === review.reviewId ? 'AI thinking...' : 'Generate Smart Reply'}
                                        {!isGold && <Crown className="h-3 w-3 ml-1 fill-amber-500 text-amber-500" />}
                                    </Button>
                                ) : (
                                    <div className="pt-2 animate-in fade-in slide-in-from-top-2 duration-300">
                                        <div className="flex items-center gap-2 text-[10px] font-black uppercase text-indigo-500 mb-2">
                                            <Sparkles className="h-3 w-3" /> AI Suggested Reply
                                        </div>
                                        <Textarea 
                                            value={replies[review.reviewId]} 
                                            onChange={(e) => setReplies(prev => ({ ...prev, [review.reviewId]: e.target.value }))}
                                            className="text-xs min-h-[80px] bg-slate-50 dark:bg-slate-900/20 border-indigo-100 dark:border-indigo-900/30 focus-visible:ring-indigo-500"
                                        />
                                        <div className="flex justify-end mt-3 gap-2">
                                            <Button variant="ghost" size="sm" className="text-xs" onClick={() => setReplies(prev => {
                                                const n = { ...prev }; delete n[review.reviewId]; return n;
                                            })}>Clear</Button>
                                            <Button 
                                                size="sm" 
                                                className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2 text-xs font-bold"
                                                onClick={() => handlePostReply(review)}
                                            >
                                                <Send className="h-3.5 w-3.5" /> Post Reply to Google
                                            </Button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </CardContent>
                </Card>
            ))}
         </div>
      </div>
    </div>
  )
}
