import { useNavigate } from 'react-router-dom'
import { LifeBuoy } from 'lucide-react'
import { Button } from '@/components/ui/button'

/**
 * "Get help" entry point for pages where merchants actually get stuck —
 * payouts, KYC, menu. Opens Help & Support with the topic and the page it came
 * from already filled in, so the first message can be about the problem
 * instead of explaining where it is.
 *
 * `category` must be one of the merchant categories in pages/HelpSupport.tsx;
 * an unknown one falls back to "Something else" there rather than failing.
 */
export function GetHelpButton({
  category,
  area,
  ctxDoctype,
  ctxName,
  label = 'Get help',
}: {
  category: string
  area: string
  ctxDoctype?: string
  ctxName?: string
  label?: string
}) {
  const navigate = useNavigate()
  const open = () => {
    const q = new URLSearchParams({ category, area })
    if (ctxDoctype) q.set('ctx_doctype', ctxDoctype)
    if (ctxName) q.set('ctx_name', ctxName)
    navigate(`/help-support?${q.toString()}`)
  }
  return (
    <Button type="button" variant="outline" size="sm" onClick={open}>
      <LifeBuoy className="h-4 w-4 mr-1.5" />
      {label}
    </Button>
  )
}

export default GetHelpButton
