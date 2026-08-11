import { useState, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from "@/components/ui/input"
import { NumberInput } from "@/components/ui/number-input"
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  Trash2,
  Plus,
  Edit2,
  Check,
  ChevronDown,
  GripVertical,
  Scale,
  Maximize2,
  Utensils,
  Pizza,
  Soup,
  MousePointer2,
  Copy,
  Search,
  Loader2
} from 'lucide-react'

import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { useCurrency } from '@/hooks/useCurrency'
import { useOutlet } from '@/contexts/OutletContext'
import { useFrappeGetCall } from '@/lib/frappe'

interface CustomizationOption {
  name?: string
  option_id?: string
  label?: string
  price?: number
  is_default?: boolean | number
  is_vegetarian?: boolean | number
  isVegetarian?: boolean | number
  display_order?: number

}

interface CustomizationQuestion {
  name?: string
  question_id?: string
  title?: string
  subtitle?: string
  question_type?: 'single' | 'multiple' | 'checkbox'
  is_required?: boolean | number
  display_order?: number
  options?: CustomizationOption[]
}

interface CustomizationQuestionsTableProps {
  value?: CustomizationQuestion[]
  onChange?: (questions: CustomizationQuestion[]) => void
  disabled?: boolean
}

const TEMPLATES = [
  { id: 'quantity', title: 'Quantity', subtitle: 'Quantity variations like - Small, medium, large, etc', icon: Scale },
  { id: 'size', title: 'Size', subtitle: 'Different sizes of an item, eg - bread size, pizza size - 6", 12", etc', icon: Maximize2 },
  { id: 'prep', title: 'Preparation type', subtitle: 'Item preparation style, eg - Halal, non-Halal, etc', icon: Utensils },
  { id: 'base', title: 'Base', subtitle: 'Item Base types, eg - wheat bread, multi-grain bread, etc', icon: Pizza },
  { id: 'rice', title: 'Rice', subtitle: "Choice of item's rice selection.", icon: Soup },
  { id: 'custom', title: 'Make your own', subtitle: "Define your own variation if you can't find a template above.", icon: Plus, highlight: true },
]

export default function CustomizationQuestionsTable({
  value = [],
  onChange,
  disabled
}: CustomizationQuestionsTableProps) {

  const { formatAmountNoDecimals } = useCurrency()
  const { selectedOutlet } = useOutlet()
  const [expandedQuestions, setExpandedQuestions] = useState<Set<number>>(new Set())
  const [editingQuestion, setEditingQuestion] = useState<number | null>(null)
  const [editingOption, setEditingOption] = useState<{ questionIndex: number; optionIndex: number } | null>(null)

  // Copy from item dialog state
  const [isCopyDialogOpen, setIsCopyDialogOpen] = useState(false)
  const [copySearchQuery, setCopySearchQuery] = useState('')

  // Fetch products with customizations for the copy dialog
  const { data: allProductsData, isLoading: productsLoading } = useFrappeGetCall(
    'flamezo_backend.flamezo.api.products.get_products',
    { outlet_id: selectedOutlet, include_inactive: 1, limit: 500 },
    isCopyDialogOpen && selectedOutlet ? `copy-customizations-products-${selectedOutlet}` : null
  )

  // Filter to only products that have customizations
  const productsWithCustomizations = useMemo(() => {
    const products = allProductsData?.message?.data?.products || []
    return products.filter((p: any) =>
      p.customizationQuestions && p.customizationQuestions.length > 0
    )
  }, [allProductsData])

  // Search filter for copy dialog
  const filteredCopyProducts = useMemo(() => {
    if (!copySearchQuery.trim()) return productsWithCustomizations
    const q = copySearchQuery.toLowerCase()
    return productsWithCustomizations.filter((p: any) =>
      (p.name || '').toLowerCase().includes(q) ||
      (p.category || '').toLowerCase().includes(q)
    )
  }, [productsWithCustomizations, copySearchQuery])

  const currentValue = Array.isArray(value) ? value : []

  const generateId = () => {
    return `id_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
  }

  const toggleQuestion = (index: number) => {
    const newExpanded = new Set(expandedQuestions)
    if (newExpanded.has(index)) {
      newExpanded.delete(index)
    } else {
      newExpanded.add(index)
    }
    setExpandedQuestions(newExpanded)
  }

  const handleCopyFromProduct = (product: any) => {
    const sourceQuestions: CustomizationQuestion[] = (product.customizationQuestions || []).map(
      (q: any, qIdx: number) => ({
        question_id: generateId(),
        title: q.title || q.question || '',
        subtitle: q.subtitle || '',
        question_type: q.type || q.question_type || 'multiple',
        is_required: q.required ?? q.is_required ?? false,
        display_order: currentValue.length + qIdx,
        options: (q.options || []).map((opt: any, oIdx: number) => ({
          option_id: generateId(),
          label: opt.label || '',
          price: opt.price || 0,
          is_default: opt.isDefault ?? opt.is_default ?? false,
          is_vegetarian: opt.isVegetarian ?? opt.is_vegetarian ?? false,
          display_order: oIdx,
        })),
      })
    )

    if (sourceQuestions.length === 0) {
      toast.error('No customizations found on this item')
      return
    }

    const updated = [...currentValue, ...sourceQuestions]
    onChange?.(updated)

    // Expand newly added questions
    const newExpanded = new Set(expandedQuestions)
    sourceQuestions.forEach((_, i) => newExpanded.add(currentValue.length + i))
    setExpandedQuestions(newExpanded)

    setIsCopyDialogOpen(false)
    setCopySearchQuery('')
    toast.success(`Copied ${sourceQuestions.length} customization group${sourceQuestions.length > 1 ? 's' : ''} from "${product.name}"`)
  }

  const handleAddQuestion = (templateId?: string) => {
    if (templateId === 'copy') {
      setIsCopyDialogOpen(true)
      return
    }
    const template = TEMPLATES.find(t => t.id === templateId)
    const newQuestion: CustomizationQuestion = {
      question_id: generateId(),
      title: template?.id !== 'custom' ? template?.title || '' : '',
      subtitle: template?.id !== 'custom' ? template?.subtitle || '' : '',
      question_type: 'multiple',
      is_required: false,
      display_order: currentValue.length,
      options: []
    }
    const updated = [...currentValue, newQuestion]
    onChange?.(updated)
    setEditingQuestion(currentValue.length)
    setExpandedQuestions(new Set([...expandedQuestions, currentValue.length]))
  }

  const handleRemoveQuestion = (index: number) => {
    const updated = currentValue.filter((_, i) => i !== index)
    const reordered = updated.map((q, idx) => ({
      ...q,
      display_order: idx
    }))
    onChange?.(reordered)
    const newExpanded = new Set(expandedQuestions)
    newExpanded.delete(index)
    setExpandedQuestions(newExpanded)
  }

  const handleQuestionChange = (index: number, field: keyof CustomizationQuestion, newValue: any) => {
    const updated = [...currentValue]
    updated[index] = {
      ...updated[index],
      [field]: newValue
    }
    onChange?.(updated)
  }

  const handleAddOption = (questionIndex: number) => {
    const question = currentValue[questionIndex]
    const newOption: CustomizationOption = {
      option_id: generateId(),
      label: '',
      price: 0,
      is_default: false,
      is_vegetarian: false,
      display_order: (question.options?.length || 0)
    }
    const updated = [...currentValue]
    updated[questionIndex] = {
      ...question,
      options: [...(question.options || []), newOption]
    }
    onChange?.(updated)
    setEditingOption({ questionIndex, optionIndex: question.options?.length || 0 })
  }

  const handleRemoveOption = (questionIndex: number, optionIndex: number) => {
    const question = currentValue[questionIndex]
    const updatedOptions = (question.options || []).filter((_, i) => i !== optionIndex)
    const reorderedOptions = updatedOptions.map((opt, idx) => ({
      ...opt,
      display_order: idx
    }))



    const updated = [...currentValue]
    updated[questionIndex] = {
      ...question,
      options: reorderedOptions
    }
    onChange?.(updated)
  }

  const handleOptionChange = (
    questionIndex: number, 
    optionIndex: number, 
    field: keyof CustomizationOption, 
    newValue: any
  ) => {
    const question = currentValue[questionIndex]
    const updatedOptions = [...(question.options || [])]
    updatedOptions[optionIndex] = {
      ...updatedOptions[optionIndex],
      [field]: newValue
    }
    const updated = [...currentValue]
    updated[questionIndex] = {
      ...question,
      options: updatedOptions
    }
    onChange?.(updated)
  }

  const handleSaveQuestion = (index: number) => {
    const question = currentValue[index]
    if (!question.title || !question.title.trim()) {
      toast.error('Question title is required')
      return
    }
    setEditingQuestion(null)
    toast.success('Question saved')
  }

  const handleSaveOption = (questionIndex: number, optionIndex: number) => {
    const option = currentValue[questionIndex].options?.[optionIndex]
    if (!option?.label || !option.label.trim()) {
      toast.error('Option label is required')
      return
    }
    setEditingOption(null)
    toast.success('Option saved')
  }

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-foreground/80 uppercase tracking-tight">Variants of this item</h3>
            <p className="text-xs text-muted-foreground mt-1">You can create different variations of this item— like quantity, size, base/crust, etc.</p>
          </div>
          {!disabled && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsCopyDialogOpen(true)}
              className="shrink-0 gap-1.5 border-primary/30 text-primary hover:bg-primary/5 hover:border-primary/50"
            >
              <Copy className="h-3.5 w-3.5" />
              Copy from Item
            </Button>
          )}
        </div>
        
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
          {TEMPLATES.map((template) => (
            <Card 
              key={template.id} 
              className={cn(
                "group transition-all duration-300 border-border/40 bg-card/30",
                !disabled && "cursor-pointer hover:border-primary/50",
                template.highlight && "border-primary/20",
                disabled && "opacity-60 grayscale"
              )}
              onClick={() => !disabled && handleAddQuestion(template.id)}
            >

              <CardContent className="p-4 flex flex-col gap-2">
                <div className="flex items-start justify-between">
                  <div className="p-2 rounded-lg bg-muted text-muted-foreground group-hover:text-primary transition-colors">
                    <template.icon className="h-4 w-4" />
                  </div>
                </div>
                <div>
                  <h4 className="text-xs font-bold text-foreground/90">{template.title}</h4>
                  <p className="text-[10px] text-muted-foreground leading-relaxed mt-1 line-clamp-2">{template.subtitle}</p>
                </div>
                <div className="pt-2">
                  <span className="text-[10px] font-bold text-primary opacity-0 group-hover:opacity-100 transition-opacity uppercase tracking-widest">
                    + Add New
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <div className="space-y-4 pt-4 border-t border-border/40">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-foreground/80 uppercase tracking-tight">Add-on groups for this item</h3>
          <Badge variant="outline" className="text-[10px] h-5 border-border/60 text-muted-foreground">
            {currentValue.length} GROUPS
          </Badge>
        </div>

        {currentValue.length === 0 ? (
          <div className="p-12 border border-dashed rounded-xl bg-muted/10 flex flex-col items-center justify-center text-center gap-3">
             <MousePointer2 className="h-6 w-6 text-muted-foreground/30" />
             <p className="text-xs text-muted-foreground font-medium uppercase tracking-widest">No customization groups yet</p>
          </div>
        ) : (
          <div className="space-y-4">
            {currentValue.map((question, questionIndex) => {
              const isExpanded = expandedQuestions.has(questionIndex)
              const isEditing = editingQuestion === questionIndex
              const questionOptions = question.options || []

              return (
                <Card key={questionIndex} className={cn(
                  "overflow-hidden border-border/40 transition-all duration-300 shadow-none bg-card/20",
                  isExpanded && "border-border shadow-md"
                )}>
                  <CardHeader 
                    className="p-4 cursor-pointer select-none" 
                    onClick={() => !isEditing && toggleQuestion(questionIndex)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        <GripVertical className="h-4 w-4 text-muted-foreground/20 cursor-grab" />
                        <div className="flex-1 min-w-0">
                          {isEditing ? (
                            <div className="flex flex-col gap-2 pr-4">
                               <Input
                                  value={question.title || ''}
                                  onClick={(e) => e.stopPropagation()}
                                  onChange={(e) => handleQuestionChange(questionIndex, 'title', e.target.value)}
                                  placeholder="Group Title (e.g., Choice of Bread)"
                                  className="h-8 text-sm font-bold bg-background/50 border-border/60"
                                  disabled={disabled}
                                  autoFocus
                                />
                                <Input
                                  value={question.subtitle || ''}
                                  onClick={(e) => e.stopPropagation()}
                                  onChange={(e) => handleQuestionChange(questionIndex, 'subtitle', e.target.value)}
                                  placeholder="Subtitle (e.g., Choose any 1)"
                                  className="h-7 text-[10px] bg-background/30 border-border/40"
                                  disabled={disabled}
                                />

                            </div>
                          ) : (
                            <div>
                              <div className="flex items-center gap-2">
                                <h4 className="text-sm font-bold text-foreground/80">
                                  {question.title || `Untitled Group`}
                                </h4>
                                {question.is_required && (
                                  <Badge variant="default" className="text-[8px] h-3.5 bg-orange-500/10 text-orange-500 border-none px-1">REQUIRED</Badge>
                                )}
                              </div>
                              {question.subtitle && (
                                <p className="text-[10px] text-muted-foreground mt-0.5">{question.subtitle}</p>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-2">
                        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                          {isEditing ? (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-green-500 hover:bg-green-500/10"
                              onClick={() => handleSaveQuestion(questionIndex)}
                            >
                              <Check className="h-4 w-4" />
                            </Button>
                          ) : (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-muted-foreground hover:text-foreground hover:bg-muted"
                              onClick={() => {
                                setEditingQuestion(questionIndex)
                                if (!isExpanded) toggleQuestion(questionIndex)
                              }}
                            >
                              <Edit2 className="h-3.5 w-3.5" />
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-destructive/60 hover:text-destructive hover:bg-destructive/10"
                            onClick={() => handleRemoveQuestion(questionIndex)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                        <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", isExpanded && "rotate-180")} />
                      </div>

                    </div>
                  </CardHeader>

                  {isExpanded && (
                    <CardContent className="p-4 pt-0 border-t border-border/40 bg-muted/5">
                       <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-4 mb-4 border-b border-border/40">
                          <div className="space-y-1">
                            <Label className="text-[10px] font-bold text-muted-foreground/80 uppercase">Selection Type</Label>
                            <Select
                              value={question.question_type || 'multiple'}
                              onValueChange={(val: any) => handleQuestionChange(questionIndex, 'question_type', val)}
                              disabled={disabled}
                            >

                              <SelectTrigger className="h-8 text-xs bg-background/50 border-border/60">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="single">Single Choice (Radio)</SelectItem>
                                <SelectItem value="multiple">Multiple Choices (Checkbox)</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="flex items-end pb-1.5">
                            <div className="flex items-center space-x-2">
                              <input
                                type="checkbox"
                                id={`req-${questionIndex}`}
                                checked={!!question.is_required}
                                onChange={(e) => handleQuestionChange(questionIndex, 'is_required', e.target.checked)}
                                className="h-4 w-4 rounded border-border/60 text-primary"
                                disabled={disabled}
                              />

                              <Label htmlFor={`req-${questionIndex}`} className="text-xs font-medium cursor-pointer">Selection Mandatory?</Label>
                            </div>
                          </div>
                       </div>

                       <div className="space-y-4">
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60">Options & Pricing</span>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => !disabled && handleAddOption(questionIndex)}
                              className="h-6 text-[10px] border-primary/20 text-primary hover:bg-primary/5"
                              disabled={disabled}
                            >

                              <Plus className="h-3 w-3 mr-1" />
                              ADD OPTION
                            </Button>
                          </div>

                          <div className="rounded-lg border border-border/40 overflow-hidden bg-background/30">
                            <Table>
                              <TableHeader className="bg-muted/30">
                                <TableRow className="hover:bg-transparent border-none h-8">
                                  <TableHead className="text-[9px] font-bold uppercase h-8">Name</TableHead>
                                  <TableHead className="text-[9px] font-bold uppercase h-8 text-right">Price</TableHead>
                                  <TableHead className="text-[9px] font-bold uppercase h-8 text-center">Veg</TableHead>
                                  <TableHead className="text-[9px] font-bold uppercase h-8 text-right">Action</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {questionOptions.map((option, optionIndex) => {
                                  const isEditingOpt = editingOption?.questionIndex === questionIndex && 
                                                     editingOption?.optionIndex === optionIndex

                                  return (
                                    <TableRow key={optionIndex} className="hover:bg-muted/20 border-border/20 h-10 group/row">
                                      <TableCell className="py-2">
                                        {isEditingOpt ? (
                                          <Input
                                            value={option.label || ''}
                                            onChange={(e) => handleOptionChange(questionIndex, optionIndex, 'label', e.target.value)}
                                            className="h-7 text-xs bg-background"
                                            disabled={disabled}
                                            autoFocus
                                          />

                                        ) : (
                                          <div className="flex items-center gap-2">
                                            {(option.is_vegetarian || option.isVegetarian) && <div className="h-1.5 w-1.5 rounded-full bg-green-500" />}
                                            <span className="text-xs font-medium">{option.label || '-'}</span>
                                          </div>

                                        )}
                                      </TableCell>
                                      <TableCell className="py-2 text-right">
                                        {isEditingOpt ? (
                                          <NumberInput
                                            
                                            value={option.price ?? 0}
                                            onChange={(e) => handleOptionChange(questionIndex, optionIndex, 'price', parseFloat(e.target.value) || 0)}
                                            className="h-7 text-xs text-right w-20 ml-auto bg-background"
                                            disabled={disabled}
                                          />

                                        ) : (
                                          <span className="text-xs font-mono text-muted-foreground">
                                            {option.price ? formatAmountNoDecimals(option.price) : 'FREE'}
                                          </span>
                                        )}

                                      </TableCell>
                                      <TableCell className="py-2 text-center">
                                        <input
                                          type="checkbox"
                                          checked={!!(option.is_vegetarian ?? option.isVegetarian)}
                                          onChange={(e) => handleOptionChange(questionIndex, optionIndex, 'is_vegetarian', e.target.checked)}
                                          className="h-3.5 w-3.5 rounded border-border/40"
                                          disabled={disabled}
                                        />

                                      </TableCell>
                                      <TableCell className="py-2 text-right">
                                        <div className="flex justify-end gap-1">
                                          {isEditingOpt ? (
                                            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => handleSaveOption(questionIndex, optionIndex)}>
                                              <Check className="h-3.5 w-3.5 text-green-500" />
                                            </Button>
                                          ) : (
                                            <Button 
                                              variant="ghost" 
                                              size="icon" 
                                              className="h-6 w-6 opacity-0 group-hover/row:opacity-100"
                                              onClick={() => setEditingOption({ questionIndex, optionIndex })}
                                            >
                                              <Edit2 className="h-3 w-3" />
                                            </Button>
                                          )}
                                          <Button 
                                            variant="ghost" 
                                            size="icon" 
                                            className="h-6 w-6 opacity-0 group-hover/row:opacity-100 text-destructive/60"
                                            onClick={() => handleRemoveOption(questionIndex, optionIndex)}
                                          >
                                            <Trash2 className="h-3 w-3" />
                                          </Button>
                                        </div>
                                      </TableCell>
                                    </TableRow>
                                  )
                                })}
                              </TableBody>
                            </Table>
                          </div>
                       </div>
                    </CardContent>
                  )}
                </Card>
              )
            })}
          </div>
        )}
      </div>

      {/* Copy from Item Dialog */}
      <Dialog open={isCopyDialogOpen} onOpenChange={(open) => { setIsCopyDialogOpen(open); if (!open) setCopySearchQuery('') }}>
        <DialogContent className="sm:max-w-lg max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">Copy Customizations from Item</DialogTitle>
            <p className="text-xs text-muted-foreground">Select an item to copy all its customization groups and options.</p>
          </DialogHeader>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search items..."
              value={copySearchQuery}
              onChange={(e) => setCopySearchQuery(e.target.value)}
              className="pl-9"
              autoFocus
            />
          </div>

          <div className="flex-1 overflow-y-auto min-h-0 -mx-6 px-6">
            {productsLoading ? (
              <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-sm">Loading items...</span>
              </div>
            ) : filteredCopyProducts.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center gap-2">
                <MousePointer2 className="h-6 w-6 text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">
                  {copySearchQuery ? 'No matching items found.' : 'No items with customizations yet.'}
                </p>
              </div>
            ) : (
              <div className="space-y-2 py-2">
                {filteredCopyProducts.map((product: any) => {
                  const questionCount = product.customizationQuestions?.length || 0
                  const totalOptions = (product.customizationQuestions || []).reduce(
                    (sum: number, q: any) => sum + (q.options?.length || 0), 0
                  )
                  return (
                    <button
                      key={product.docname || product.id}
                      className="w-full text-left p-3 rounded-lg border border-border/40 hover:border-primary/50 hover:bg-primary/5 transition-all group"
                      onClick={() => handleCopyFromProduct(product)}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            {product.is_vegetarian ? (
                              <div className="h-2 w-2 rounded-full bg-green-500 shrink-0" />
                            ) : (
                              <div className="h-2 w-2 rounded-full bg-red-500 shrink-0" />
                            )}
                            <h4 className="text-sm font-semibold text-foreground truncate">{product.name}</h4>
                          </div>
                          <p className="text-[10px] text-muted-foreground mt-0.5 ml-4">{product.category}</p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <Badge variant="outline" className="text-[9px] h-5 border-border/60 text-muted-foreground">
                            {questionCount} group{questionCount !== 1 ? 's' : ''} · {totalOptions} option{totalOptions !== 1 ? 's' : ''}
                          </Badge>
                          <Copy className="h-3.5 w-3.5 text-muted-foreground/40 group-hover:text-primary transition-colors" />
                        </div>
                      </div>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
