// Permission utilities for flamezo_backend UI
import { useFrappeGetCall } from '@/lib/frappe'

export interface Permissions {
  read: boolean
  write: boolean
  create: boolean
  delete: boolean
  submit: boolean
  cancel: boolean
}

export function usePermissions(doctype: string) {
  const { data, error, isLoading } = useFrappeGetCall<{ message: Permissions }>(
    'flamezo_backend.flamezo.api.ui.get_user_permissions',
    { doctype },
    doctype ? `permissions-${doctype}` : null
  )

  return {
    permissions: data?.message || {
      read: false,
      write: false,
      create: false,
      delete: false,
      submit: false,
      cancel: false,
    },
    isLoading,
    error,
  }
}

