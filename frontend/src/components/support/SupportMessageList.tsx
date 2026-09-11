import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'

export type SupportMessage = {
  id: string
  sender_type: string
  sender_name: string
  sender_user?: string
  message: string
  is_system: boolean
  is_automated?: boolean
  created_at: string
}

// Frappe datetimes look like "2026-09-10 13:44:55.372902"; six fractional
// digits don't parse reliably in every engine, so trim to seconds first.
export const parseDate = (s: string) => (s ? new Date(s.slice(0, 19).replace(' ', 'T')) : null)

export const fmtTime = (s: string) => {
  const d = parseDate(s)
  if (!d || Number.isNaN(d.getTime())) return ''
  const sameDay = d.toDateString() === new Date().toDateString()
  return sameDay
    ? d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    : d.toLocaleDateString([], { day: 'numeric', month: 'short' })
}

type Props = {
  messages: SupportMessage[]
  loading: boolean
  /**
   * Whose side the page is on. "requester" = the merchant's Help & Support
   * (their own messages on the right, automated lines as team bubbles).
   * "team" = the admin Support Requests page (team replies on the right, the
   * agent's real name shown, automated lines as small centred notes).
   */
  perspective: 'requester' | 'team'
}

/** One support conversation — shared by the merchant and admin pages. */
export function SupportMessageList({ messages, loading, perspective }: Props) {
  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-10 w-1/2 ml-auto" />
        <Skeleton className="h-10 w-3/5" />
      </div>
    )
  }
  return (
    <>
      {messages.map((m) => {
        if (m.is_system || (perspective === 'team' && m.is_automated)) {
          return (
            <div key={m.id} className="text-center text-xs text-muted-foreground py-1 px-6">
              {m.message}
            </div>
          )
        }
        const mine = perspective === 'team' ? m.sender_type === 'agent' : m.sender_type === 'customer'
        const name = perspective === 'team' && m.sender_type === 'agent' ? m.sender_user || m.sender_name : m.sender_name
        return (
          <div key={m.id} className={cn('flex', mine ? 'justify-end' : 'justify-start')}>
            <div
              className={cn(
                'max-w-[78%] rounded-2xl px-3.5 py-2 text-sm',
                mine ? 'bg-primary text-primary-foreground rounded-br-md' : 'bg-muted rounded-bl-md',
              )}
            >
              {(!mine || perspective === 'team') && (
                <div className="text-[11px] font-semibold opacity-75 mb-0.5">{name}</div>
              )}
              <div className="whitespace-pre-wrap break-words">{m.message}</div>
              <div className="text-[10px] opacity-60 mt-1 text-right tabular-nums">{fmtTime(m.created_at)}</div>
            </div>
          </div>
        )
      })}
    </>
  )
}
