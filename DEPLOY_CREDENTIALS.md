# Post-Deploy — Credentials the Senior Must Add (Production)

After merging & deploying, the app reads these **secure** values from
`sites/<site>/site_config.json` (server-side, never committed to git).

Set each with:
```bash
bench --site <live-site> set-config <key> "<value>"
```
then `bench restart`. (Secret values are NOT listed here — get the API key from
the Fast2SMS / Meta dashboards.)

---

## 1. SMS OTP — Fast2SMS DLT  (required for "Continue with SMS")

| Config key | Value |
|---|---|
| `fast2sms_api_key` | **<your Fast2SMS API key>** (secret) |
| `fast2sms_sender_id` | `FLAMZO` |
| `fast2sms_dlt_template_id` | `220653` |
| `fast2sms_entity_id` | `1201178342555253864` (optional — record only, not sent) |

Also confirm the DLT template `220653` shows **"Registered with All TSP"** on the
Jio/DLT portal, or the OTP is accepted by Fast2SMS but dropped by the operator.

---

## 2. WhatsApp OTP — Meta Cloud API  (the PRIMARY login channel)

| Config key | Value |
|---|---|
| `whatsapp_phone_number_id` | **<Meta phone number id>** |
| `whatsapp_access_token` | **<Meta permanent access token>** (secret) |
| `whatsapp_otp_template` | **<template name>** (e.g. `otp_verify`) |

Login tries WhatsApp first and falls back to SMS, so both sets should be present.

---

## 3. Verify after setting (live `bench console`)

```python
import frappe
for k in [
    "fast2sms_api_key", "fast2sms_sender_id", "fast2sms_dlt_template_id",
    "whatsapp_phone_number_id", "whatsapp_access_token",
]:
    print(k, "->", "SET" if frappe.conf.get(k) else "MISSING")
```
All should print `SET`.

---

## 4. Razorpay (already on prod — just verify)

- Route uses the existing platform Razorpay keys + `webhook_secret` in
  `site_config.json` — no new values needed.
- **Action:** in the Razorpay dashboard, ensure the webhook is subscribed to
  `account.*` events (account.activated / under_review / needs_clarification /
  suspended / rejected). This is what keeps merchant KYC status in sync.

---

### Notes
- The code reads Fast2SMS config from `site_config.json` first, then falls back
  to **Flamezo Settings** — so either location works, but `site_config.json` is
  the recommended secure place.
- `bench migrate` on deploy auto-runs the Route orphan-reconnect patch and
  registers the hourly KYC reconcile job — no manual bench console needed for
  those.
