import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

function initApp() {
  const win = window as any;
  // Ensure frappe object exists
  if (!win.frappe) {
    win.frappe = {} as any;
  }

  // Only sync if frappe.model exists (frappe-react-sdk handles model syncing)
  if (win.frappe.boot && win.frappe.boot.docs && win.frappe.model && typeof win.frappe.model.sync === 'function') {
    try {
      win.frappe.model.sync(win.frappe.boot.docs);
    } catch (e) {
      // Silently fail - frappe-react-sdk will handle model syncing
      console.debug('frappe.model.sync not available, using frappe-react-sdk');
    }
  }

  createRoot(document.getElementById('root') as HTMLElement).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

if (import.meta.env.DEV) {
  fetch('/api/method/flamezo_backend.www.flamezo_backend.get_context_for_dev', {
    method: 'POST',
  })
    .then(response => response.json())
    .then((values) => {
      const v = JSON.parse(values.message)
      const win = window as any;
      if (!win.frappe) win.frappe = {} as any;
      win.frappe.boot = v;
      win.frappe._messages = v["__messages"] || {};
      initApp();
    })
    .catch((error) => {
      console.error('Failed to load boot data:', error);
      initApp();
    })
} else {
  // Production trace
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      initApp();
    });
  } else {
    initApp();
  }
}

// Global start marker

