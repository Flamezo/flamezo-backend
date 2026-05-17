# Next.js — Razorpay per-restaurant integration (sample)

This document shows a minimal, secure pattern to integrate Razorpay Checkout from a Next.js frontend while using per-restaurant merchant keys stored on the ERPNext backend.

Overview
- Admin stores merchant keys on the `Restaurant` doc (via admin UI or API `set_restaurant_razorpay_keys`).
- Next.js frontend calls backend endpoint to create a Razorpay order for a specific restaurant. Backend uses the restaurant merchant keys when available and returns `key_id` + `razorpay_order_id`.
- Frontend opens Razorpay Checkout with the returned `key_id` and `order_id`. Verification is done server-side or via webhooks.

1) Backend API (already implemented)
- `flamezo_backend.flamezo.api.payments.create_payment_order(restaurant_id, order_items, total_amount, customer_name, customer_email, ...)`
  - Uses `get_razorpay_client(restaurant_id)` — will use merchant keys if configured for the restaurant.
  - Returns: `{ success: true, data: { key_id, razorpay_order_id, amount, currency, order_id } }`

2) Next.js server-side API route (example)
Create `pages/api/create-order.js`:

```js
import fetch from 'node-fetch'

export default async function handler(req, res) {
  const { restaurantId, items, total, customerName, customerEmail } = req.body
  // Call ERPNext backend (use your server-to-server auth/session)
  const resp = await fetch(process.env.FRAPPE_BACKEND_URL + '/api/method/flamezo_backend.flamezo.api.payments.create_payment_order', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ restaurant_id: restaurantId, order_items: JSON.stringify(items), total_amount: total, customer_name: customerName, customer_email: customerEmail })
  })
  const data = await resp.json()
  if (!data?.message?.success && !data?.success) {
    return res.status(500).json({ error: data?.message?.error || data?.error || 'failed' })
  }
  const body = data.message ?? data
  res.status(200).json(body.data)
}
```

3) Client-side Next.js Checkout (example)
```jsx
// pages/checkout.js
import { useState } from 'react'

export default function Checkout({ restaurantId }) {
  const [loading, setLoading] = useState(false)
  async function startCheckout() {
    setLoading(true)
    const resp = await fetch('/api/create-order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        restaurantId,
        items: [{ product_id: 'iced-americano', quantity: 1, rate: 100, amount: 100 }],
        total: 1,
        customerName: 'Guest',
        customerEmail: 'guest@example.com'
      })
    })
    const data = await resp.json()
    setLoading(false)
    if (!data) return alert('Failed to create order')
    // Load Razorpay script if needed
    if (!window.Razorpay) {
      await new Promise((resolve) => {
        const s = document.createElement('script')
        s.src = 'https://checkout.razorpay.com/v1/checkout.js'
        s.onload = () => resolve(true)
        document.body.appendChild(s)
      })
    }
    const options = {
      key: data.key_id,
      order_id: data.razorpay_order_id,
      name: 'Merchant',
      description: 'Order',
      handler: (response) => {
        // Optionally call backend verify endpoint or rely on webhook
        console.log('Payment response', response)
      }
    }
    const rzp = new window.Razorpay(options)
    rzp.open()
  }

  return <button onClick={startCheckout} disabled={loading}>{loading ? 'Loading...' : 'Pay'}</button>
}
```

4) Testing & E2E
- Admin: Set merchant keys in ERPNext (Administration page or call API `set_restaurant_razorpay_keys`).
- Start local backend and Next.js app.
- Expose backend to the web for webhooks (ngrok):
  - `ngrok http 8000` (or your frappe site port)
  - Add webhook in Razorpay dashboard (Test mode) pointing to: `https://<ngrok-id>.ngrok.io/api/method/flamezo_backend.flamezo.api.webhooks.razorpay_webhook`
- Create an order from the Next.js frontend, open Checkout and complete payment in Razorpay test mode.
- Verify:
  - Razorpay shows order created under merchant account (Orders dashboard).
  - Webhook arrives at backend (check `Razorpay Webhook Log`).
  - Backend maps webhook to Order or TokenizationAttempt and updates Order status / Restaurant tokens.

5) Notes & Security
- Merchant key secret is stored encrypted (Frappe Password field). Only admins may set keys.
- Do NOT store merchant secrets in the Next.js frontend or client-side code.
- Use server-to-server calls (Next.js server API -> ERPNext backend) for sensitive operations.

