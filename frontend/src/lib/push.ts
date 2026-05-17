/**
 * Flamezo Merchant Dashboard — Push Notification Utility (Firebase/FCM)
 * Cost: ZERO — FCM Web Push is free forever.
 *
 * Saves merchant device FCM tokens so the backend can push new order alerts
 * even when the dashboard tab is backgrounded or minimized.
 */

import { initializeApp, getApps, FirebaseApp } from 'firebase/app'
import { getMessaging, getToken, onMessage, Messaging } from 'firebase/messaging'

const FIREBASE_CONFIG = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}
const VAPID_KEY = import.meta.env.VITE_FIREBASE_VAPID_KEY

let app: FirebaseApp | null = null
let messaging: Messaging | null = null

function getFirebaseApp(): FirebaseApp {
  if (!app) {
    app = getApps().length > 0 ? getApps()[0] : initializeApp(FIREBASE_CONFIG)
  }
  return app
}

/**
 * Initializes push notifications for the merchant dashboard.
 * Registers the service worker, gets an FCM token, and saves it to the backend.
 *
 * @param restaurantId  The slug of the restaurant
 * @param frappeBaseUrl Base URL of the Frappe backend (e.g. https://api.flamezo_backend.com)
 * @param onNewOrder    Callback fired when a new-order push arrives while tab is open
 */
export async function initMerchantPush(
  restaurantId: string,
  frappeBaseUrl: string,
  onNewOrder?: (data: Record<string, string>) => void
): Promise<boolean> {
  try {
    if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
      return false
    }

    if (!FIREBASE_CONFIG.apiKey || !FIREBASE_CONFIG.projectId) {
      console.warn('[MerchantPush] Firebase not configured — skipping')
      return false
    }

    // 1. Request permission
    const permission = await Notification.requestPermission()
    if (permission !== 'granted') {
      console.info('[MerchantPush] Permission denied')
      return false
    }

    // 2. Register service worker
    const swReg = await navigator.serviceWorker.register('/firebase-messaging-sw.js')

    if (swReg.active || swReg.waiting || swReg.installing) {
      const sw = swReg.active || swReg.waiting || swReg.installing!
      sw.postMessage({ type: 'FIREBASE_CONFIG', config: FIREBASE_CONFIG })
    }

    // 3. Get FCM token
    const fbApp = getFirebaseApp()
    messaging = getMessaging(fbApp)

    const fcmToken = await getToken(messaging, {
      vapidKey: VAPID_KEY,
      serviceWorkerRegistration: swReg,
    })

    if (!fcmToken) {
      console.warn('[MerchantPush] No FCM token obtained')
      return false
    }

    // 4. Save to backend
    const res = await fetch(
      `${frappeBaseUrl}/api/method/flamezo_backend.flamezo.api.push_notifications.save_merchant_subscription`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Frappe-CSRF-Token': (window as any).csrf_token || '',
        },
        body: JSON.stringify({
          restaurant_id: restaurantId,
          fcm_token: fcmToken,
        }),
        credentials: 'include',
      }
    )

    if (!res.ok) {
      console.warn('[MerchantPush] Backend save failed:', res.status)
    }

    // 5. Handle foreground messages (tab is active — show toast in the UI)
    onMessage(messaging, (payload) => {
      const data = payload.data || {}
      if (data.type === 'new_order' && onNewOrder) {
        onNewOrder(data as Record<string, string>)
      }
    })

    console.info('[MerchantPush] Merchant push initialized')
    return true
  } catch (err) {
    console.error('[MerchantPush] Init failed:', err)
    return false
  }
}
