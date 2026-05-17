# OTP API & Customer UI Integration Guide

**Flamezo** — Phone verification for checkout, table booking, banquet booking, and coupons.

*Version 1.0 | February 2025*

---

## Table of Contents

1. [Overview](#1-overview)
2. [API Reference](#2-api-reference)
3. [Backend Implementation](#3-backend-implementation)
4. [Frontend Integration](#4-frontend-integration)
5. [Integration Checklist](#5-integration-checklist)
6. [Configuration](#6-configuration)
7. [Error Handling](#7-error-handling)
8. [E2E Testing](#8-e2e-testing)

---

## 1. Overview

| Aspect | Detail |
|--------|--------|
| **Feature Toggle** | `verify_my_user` in Restaurant Config |
| **Verification Scope** | **Platform-wide** — once verified, works at all restaurants |
| **Channels** | SMS primary, WhatsApp fallback |
| **Rate Limit** | 3 OTPs per phone per hour, 30s resend cooldown |
| **OTP** | 4 digits, 5-minute expiry |

### When OTP Is Required (verify_my_user = true)

- Order/Checkout
- Table Booking
- Banquet Booking
- Coupon application (during order creation)

### Flow Summary

```
verify_my_user = false  →  Collect name + phone  →  Proceed
verify_my_user = true   →  Collect name + phone  →  Already verified? → Skip OTP
                                        →  Not verified? → Send OTP → Verify → Proceed
```

---

## 2. API Reference

Base URL: `https://<your-site>/api/method/`

All endpoints: `@frappe.whitelist(allow_guest=True)` — no auth required.

---

### 2.1 Send OTP

**Endpoint:** `flamezo_backend.flamezo.api.otp.send_otp`  
**Method:** POST

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `restaurant_id` | string | Yes | Restaurant ID (e.g. `unvind`) |
| `phone` | string | Yes | 10-digit India phone (e.g. `7487871213`) |
| `purpose` | string | No | Default: `verification`. Use `checkout`, `table_booking`, `banquet_booking` for logs |
| `restaurant_name` | string | No | Display name for SMS. **Pass from frontend** for branded message |

#### Success Responses

| Scenario | Response |
|----------|----------|
| Verification not required | `{ "success": true, "skip_verification": true }` |
| Already verified (platform-wide) | `{ "success": true, "already_verified": true }` |
| OTP sent | `{ "success": true, "token": "...", "expires_in": 300, "channel": "sms", "message": "OTP sent successfully" }` |

#### Error Responses

| Error Code | HTTP | Message |
|------------|------|---------|
| `INVALID_PHONE` | 200 | Invalid phone number |
| `RATE_LIMIT_EXCEEDED` | 200 | Max 3 OTPs per hour. Try again later. |
| `COOLDOWN` | 200 | Wait 30 seconds before resending. |
| `OTP_SERVICE_NOT_CONFIGURED` | 200 | OTP service not configured |
| `OTP_SEND_FAILED` | 200 | Failed to send OTP |

#### Example (cURL)

```bash
curl -X POST "https://your-site.com/api/method/flamezo_backend.flamezo.api.otp.send_otp" \
  -H "Content-Type: application/json" \
  -d '{
    "restaurant_id": "unvind",
    "phone": "7487871213",
    "restaurant_name": "Unvind",
    "purpose": "checkout"
  }'
```

#### Example (JavaScript/fetch)

```javascript
const res = await fetch('/api/method/flamezo_backend.flamezo.api.otp.send_otp', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    restaurant_id: restaurantId,
    restaurant_name: restaurantName,  // from Restaurant.restaurant_name
    phone: phone.trim(),
    purpose: 'checkout'
  })
});
const data = await res.json();
```

---

### 2.2 Verify OTP

**Endpoint:** `flamezo_backend.flamezo.api.otp.verify_otp`  
**Method:** POST

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `restaurant_id` | string | Yes | Restaurant ID |
| `phone` | string | Yes | Same phone used in send_otp |
| `otp` | string | Yes | 4-digit OTP received on phone |
| `token` | string | Yes | Token from send_otp response |
| `name` | string | No | Customer name (for Customer record) |
| `email` | string | No | Customer email |

#### Success Response

```json
{
  "success": true,
  "verified": true,
  "customer_id": "CUST-2026-00001"
}
```

#### Error Responses

| Error Code | Description |
|------------|-------------|
| `INVALID_PHONE` | Invalid phone format |
| `OTP_EXPIRED_OR_INVALID` | Token expired or wrong token |
| `INVALID_OTP` | Wrong OTP entered |
| `CUSTOMER_CREATE_FAILED` | Failed to create Customer |

#### Example (JavaScript)

```javascript
const res = await fetch('/api/method/flamezo_backend.flamezo.api.otp.verify_otp', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    restaurant_id: restaurantId,
    phone: phone.trim(),
    otp: otp,
    token: token,
    name: customerName,
    email: customerEmail
  })
});
```

---

### 2.3 Check Verified

**Endpoint:** `flamezo_backend.flamezo.api.otp.check_verified`  
**Method:** POST or GET

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `phone` | string | Yes | 10-digit phone to check |

#### Success Response

```json
{
  "success": true,
  "verified": true
}
```

or

```json
{
  "success": true,
  "verified": false
}
```

#### Example (GET)

```
GET /api/method/flamezo_backend.flamezo.api.otp.check_verified?phone=7487871213
```

#### Example (POST)

```javascript
const res = await fetch('/api/method/flamezo_backend.flamezo.api.otp.check_verified', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ phone: phone })
});
const { verified } = await res.json();
```

---

## 3. Backend Implementation

### File Locations

| File | Purpose |
|------|---------|
| `flamezo_backend/flamezo_backend/api/otp.py` | API: send_otp, verify_otp, check_verified |
| `flamezo_backend/flamezo_backend/utils/otp_service.py` | Fast2SMS: SMS (Quick/DLT) + WhatsApp |
| `flamezo_backend/flamezo_backend/utils/customer_helpers.py` | normalize_phone, get_or_create_customer, is_phone_verified, require_verified_phone |

### Gating Points (Backend)

These APIs check `require_verified_phone()` and return `PHONE_NOT_VERIFIED` if not verified:

| API | File | Line (approx) |
|-----|------|---------------|
| `create_order` | `api/orders.py` | ~44 |
| Razorpay tokenization / capture | `api/payments.py` | ~61 |
| `create_table_booking` | `api/bookings.py` | ~34 |
| `create_banquet_booking` | `api/bookings.py` | ~270 |

### Constants (otp_service.py)

```python
OTP_LENGTH = 4
OTP_EXPIRY_MINUTES = 5
OTP_RESEND_COOLDOWN = 30
OTP_MAX_PER_HOUR = 3
```

### SMS Message Format

**Quick SMS route (testing):**
```
Your {restaurant_name} verification code is: {otp}. Don't share this code with anyone.
```

**Example:** `Your Unvind verification code is: 1234. Don't share this code with anyone.`

- Restaurant name truncated to 25 chars
- Single-line (no newlines) for better delivery
- Fallback label: `Flamezo` if `restaurant_name` not provided

---

## 4. Frontend Integration

### 4.1 OTPVerification Component

**Path:** `frontend/src/components/OTPVerification.tsx`

Reusable component for the OTP flow (Send → Verify).

#### Props

| Prop | Type | Required | Description |
|------|------|----------|-------------|
| `restaurantId` | string | Yes | Restaurant ID |
| `restaurantName` | string | No | **Pass this** for branded SMS (e.g. `restaurant.restaurant_name`) |
| `phone` | string | Yes | Customer phone |
| `name` | string | No | Customer name (passed to verify_otp) |
| `email` | string | No | Customer email |
| `onVerified` | () => void | Yes | Callback when verification succeeds |
| `onSkip` | () => void | No | Optional skip button |

#### Usage Example

```tsx
import { OTPVerification } from '../components/OTPVerification';

<OTPVerification
  restaurantId={restaurantId!}
  restaurantName={restaurant.restaurant_name}  // ← For branded SMS
  phone={customerPhone}
  name={customerName}
  email={customerEmail}
  onVerified={() => {
    setVerifiedPhone(customerPhone);
    setShowOTPStep(false);
    setShowPayment(true);
  }}
/>
```

---

### 4.2 Verified Phone Storage (localStorage)

**Path:** `frontend/src/utils/otpStorage.ts`

| Function | Description |
|----------|-------------|
| `normalizePhone(phone)` | Returns 10-digit India number |
| `getStoredVerifiedPhone()` | Returns stored verified phone or null |
| `setVerifiedPhone(phone)` | Stores verified phone + timestamp |
| `clearVerifiedPhone()` | Clears stored verification |
| `isVerifiedExpired(maxAgeMs?)` | Default 30 days; returns true if expired |

**Keys:** `flamezo_backend_verified_phone`, `flamezo_backend_verified_at`

---

### 4.3 Payment Page Flow (Reference Implementation)

**Path:** `frontend/src/pages/Payment.tsx`

1. **Get config:** `verifyMyUser` from `restaurantConfig.settings`
2. **On customer details submit:**
   - If `!verifyMyUser` → go to payment
   - If `verifyMyUser`:
     - Check `getStoredVerifiedPhone()` === current phone and `!isVerifiedExpired()`
     - If match → call `check_verified` API
     - If API says verified → go to payment
     - Else → show OTP step
3. **OTP step:** Render `<OTPVerification ... />`
4. **On verify:** Call `setVerifiedPhone(customerPhone)`, then go to payment

```tsx
// Pseudo-code from Payment.tsx
if (verifyMyUser) {
  const stored = getStoredVerifiedPhone();
  if (stored === normalized && !isVerifiedExpired()) {
    const res = await checkVerified({ phone: customerPhone });
    if (res?.success && res.verified) {
      setShowPayment(true);
      return;
    }
  }
  setShowOTPStep(true);
} else {
  setShowPayment(true);
}
```

---

### 4.4 Adding OTP to a New Page (e.g. Table Booking)

1. **Get restaurant config** with `verifyMyUser`
2. **After user enters phone (and name):**
   - If `verifyMyUser`:
     - Check `getStoredVerifiedPhone()` === normalized phone, `!isVerifiedExpired()`
     - Call `check_verified`
     - If verified → proceed to submit booking
     - Else → show OTP step
3. **OTP step:**
   ```tsx
   <OTPVerification
     restaurantId={restaurantId}
     restaurantName={restaurant?.restaurant_name}
     phone={phone}
     name={name}
     onVerified={() => {
       setVerifiedPhone(phone);
       setShowOTPStep(false);
       submitBooking();  // or set state to show success
     }}
   />
   ```
4. **On verify success:** `setVerifiedPhone(phone)` so next restaurant visit skips OTP

---

## 5. Integration Checklist

### Backend (Already Done)

- [x] `send_otp`, `verify_otp`, `check_verified` APIs
- [x] `require_verified_phone` gating in orders, payments, bookings
- [x] `get_or_create_customer` with fallback name
- [x] Restaurant Config: `verify_my_user`
- [x] Flamezo Settings: Fast2SMS config
- [x] `verifyMyUser` in `get_restaurant_config`

### Frontend (Payment)

- [x] OTPVerification component
- [x] otpStorage (localStorage)
- [x] Payment page: OTP step, check_verified, restaurantName

### Frontend (To Add)

- [ ] Table Booking page: OTP step when verifyMyUser
- [ ] Banquet Booking page: OTP step when verifyMyUser
- [ ] Coupon UI: Coupon is gated at order creation; ensure Payment OTP runs before coupon step

---

## 6. Configuration

### Flamezo Settings (Desk → Flamezo Settings)

| Field | Required | Description |
|-------|----------|-------------|
| Fast2SMS API Key | Yes | Password field; use `get_password()` in code |
| DLT Sender ID | For production | e.g. DINMAT |
| DLT Template ID | For production | From Fast2SMS DLT Manager |
| WhatsApp Phone Number ID | For fallback | When SMS fails |
| WhatsApp OTP Template Name | For fallback | Meta-approved template |

### Restaurant Config

| Field | Default | Description |
|-------|---------|-------------|
| Verify My User | 0 (unchecked) | Require OTP for protected actions |

### SMS Routes

| Route | When Used | Cost |
|-------|-----------|------|
| `q` (Quick SMS) | No DLT sender/template configured | ~₹5/SMS (testing) |
| `dlt` | DLT sender + template configured | ~₹0.12–0.25/SMS (production) |

---

## 7. Error Handling

### Frontend Error Mapping

| API Error | User Message |
|-----------|--------------|
| `INVALID_PHONE` | Invalid phone number |
| `RATE_LIMIT_EXCEEDED` | Max 3 OTPs per hour. Try again later. |
| `COOLDOWN` | Wait 30 seconds before resending |
| `OTP_SERVICE_NOT_CONFIGURED` | OTP service not available |
| `OTP_SEND_FAILED` | Failed to send OTP. Try again. |
| `OTP_EXPIRED_OR_INVALID` | OTP expired. Request a new one. |
| `INVALID_OTP` | Invalid OTP |
| `PHONE_NOT_VERIFIED` | Please verify your phone with OTP first |

### Backend Error (Orders/Bookings)

When `require_verified_phone` fails:

```json
{
  "success": false,
  "error": {
    "code": "PHONE_NOT_VERIFIED",
    "message": "Please verify your phone with OTP first"
  }
}
```

Frontend should show OTP flow when this is returned.

---

## 8. E2E Testing

### Prerequisites

1. Flamezo Settings: Set Fast2SMS API key
2. Restaurant Config: Enable "Verify My User" for test restaurant
3. Add ₹100+ to Fast2SMS account (for Quick route)

### Manual Flow

1. **Checkout with OTP**
   - Add items → Checkout → Enter name + phone → Proceed
   - OTP step appears → Send OTP → Enter 4-digit code → Verify → Payment

2. **Platform-wide**
   - Verify at Restaurant A → Go to Restaurant B → Same phone → Should skip OTP

3. **Rate limit**
   - Send 4 OTPs within an hour → 4th should return RATE_LIMIT_EXCEEDED

### Backend Test (No SMS Cost for Dry Run)

```bash
# Send OTP (costs ₹5 with Quick route — use sparingly)
bench --site your-site execute "flamezo_backend.flamezo.api.otp.send_otp" \
  --args '["unvind","7487871213"]'

# Verify (use OTP from SMS + token from send response)
bench --site your-site execute "flamezo_backend.flamezo.api.otp.verify_otp" \
  --args '["unvind","7487871213","1234","<TOKEN>","Test User"]'

# Check verified
bench --site your-site execute "flamezo_backend.flamezo.api.otp.check_verified" \
  --args '["7487871213"]'
```

---

## Quick Reference: API Call Order

```
1. GET get_restaurant_config  →  verifyMyUser
2. If verifyMyUser:
   a. getStoredVerifiedPhone() + check_verified  →  if verified, skip OTP
   b. Else: send_otp  →  get token
   c. verify_otp (otp, token, name, email)  →  on success: setVerifiedPhone(), proceed
3. Proceed to order/booking/payment
```
