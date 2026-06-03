# Flamezo — Current Business Model & Backend Reference

> **Last Updated:** 2026-05-23 | **Status:** Live (Razorpay Route migration complete)
>
> This document was originally written as a migration plan from the older B2B SaaS model to the current two-sided platform model. The migration is now complete. This file is preserved as the **single-source-of-truth reference** for the current model, with the historical "old model" section kept for context only.

---

## TABLE OF CONTENTS
1. [Current Business Model](#1-current-business-model)
2. [Revenue Streams](#2-revenue-streams)
3. [Payment Flow (Razorpay Route)](#3-payment-flow-razorpay-route)
4. [Backend Architecture](#4-backend-architecture)
5. [Financial Projections](#5-financial-projections)
6. [Phase 2 Revenue Streams (Roadmap)](#6-phase-2-revenue-streams-roadmap)
7. [Historical: Old Model (Pre-May 2026)](#7-historical-old-model-pre-may-2026)
8. [Appendix — Key File Locations](#8-appendix--key-file-locations)

---

## 1. CURRENT BUSINESS MODEL

### Overview
Flamezo operates as a **two-sided restaurant platform**:
- **Free onboarding** — restaurants get the full feature suite immediately on signup. No unlock fee, no prepayment, no trial timer.
- Flamezo sits in the payment flow and collects a **Success Share** on every order.
- Flamezo brings new customers to restaurants via the FLAMEZO consumer app and cross-restaurant loyalty.

### Core Principle
> "We grow when restaurants grow. We earn when they earn."

### Onboarding Terms

| Item | Value |
|---|---|
| **Onboarding Fee** | ₹0 |
| **Prepayment** | ₹0 |
| **Feature Access** | Full suite from day 1 — ordering, loyalty, marketing, POS, AI, analytics |
| **Trial Period** | None — free onboarding is permanent; there is no trial timer |
| **Tier Paywall** | None — all features unlocked from day 1 for every new restaurant |

> **Note on legacy tiers:** The names `SILVER` and `GOLD` may still appear in internal code (`plan_type` field, doctype enums) and in legacy/grandfathered restaurant accounts onboarded under the previous model. For all new restaurants signed up under the current model, the tier distinction is effectively dead — every restaurant gets the full GOLD-equivalent feature set immediately.

---

## 2. REVENUE STREAMS

### Primary Revenue — Success Share

| Stream | Rate | Notes |
|---|---|---|
| **Success Share (new restaurants)** | **3% of every order GMV** | Deducted via Razorpay Route auto-split on online orders; tracked in commission ledger for cash orders |
| **Success Share (legacy/grandfathered)** | **1.5% of every order GMV** | For restaurants onboarded before the May 2026 migration who chose to stay on legacy terms |
| **Monthly Floor** | **₹199/month** | Backstop that kicks in if a restaurant's Success Share for the month is below ₹199; only the shortfall is charged |
| **GST on Success Share** | **18%** | Applied on the Success Share amount, per Indian tax regulations |

### Secondary Revenue (Usage-Based)

| Stream | Rate | Notes |
|---|---|---|
| WhatsApp messages | ₹1.20/msg | Margin ₹0.43/msg |
| SMS | ₹0.25/msg | Margin ₹0.07/msg |
| Email | ₹0.05/msg | High margin |
| AI dish generation | ₹10/image | Per-use |
| AI image enhancement | ₹5/image | Per-use |
| Lead unlock | ₹1/lead (>24h) | Customer data access |
| Wallet recharge bonuses | 10% at ₹2,999+ / 20% at ₹4,999+ | Drives pre-paid float |
| Referral | ₹500 both parties (on ₹1,000 recharge) | Acquisition |

---

## 3. PAYMENT FLOW (RAZORPAY ROUTE)

The current architecture uses **Razorpay Route** for true real-time split on online orders, with a commission ledger waterfall for cash orders.

### Online Orders — Auto-Split via Razorpay Route

```
Consumer places order
       ↓
Razorpay collects full payment
       ↓
Razorpay Route auto-splits at the moment of payment:
       ├── 97% → Restaurant's Linked Account (lands in bank T+2 business days)
       └── 3%  → Flamezo (Success Share — 1.5% for legacy restaurants)
       ↓
Gateway 2% goes to Razorpay — passed through to consumer/restaurant
```

Restaurants complete a one-time Razorpay Route KYC (see `Flamezo_Direct_Bank_Payouts_Guide.md`) to activate direct payouts. Until that KYC is complete, payments fall back to Flamezo's holding account and are settled weekly via NEFT.

### Cash Orders — Commission Ledger with 4-Tier Waterfall

For cash orders, 100% of the cash stays at the counter with the restaurant. The Success Share accrues to a commission ledger and is recovered via a 4-tier waterfall:

1. **Wallet** — deducted from the restaurant's Flamezo wallet first
2. **Online net-off** — netted off against the next online order's split (we take a bit extra from the next online split until cleared)
3. **Autopay sweep** — debited via the restaurant's UPI/card mandate
4. **Throttle** — if all above fail, certain growth features are temporarily paused until the ledger is cleared

This way, restaurants never receive a manual invoice for cash Success Share — it's recovered automatically in the background.

---

## 4. BACKEND ARCHITECTURE

The following systems power the current model:

| System | File | Status | Notes |
|---|---|---|---|
| Razorpay Route integration | `api/payments.py` | ✅ Live | Real-time split, Linked Accounts, sub-merchant compliance |
| Restaurant Route KYC | `api/route_kyc.py` | ✅ Live | PAN + bank verification, Linked Account creation |
| Commission ledger (cash) | `api/commission_ledger.py` | ✅ Live | 4-tier waterfall recovery |
| Cross-restaurant loyalty | `utils/loyalty.py` | ✅ Live | Earn at A, redeem at B |
| Wallet/coin system | `api/coin_billing.py` | ✅ Live | Auto-recharge, grace period (-₹100), GST, bonus tiers |
| Monthly floor billing | `tasks/subscription_tasks.py` | ✅ Live | ₹199/month backstop, shortfall-only billing |
| OTP authentication | `api/otp.py` | ✅ Live | Restaurant + consumer auth |
| WhatsApp ordering | `api/whatsapp_ordering.py` | ✅ Live | |
| Marketing automation | `api/marketing.py` + tasks | ✅ Live | Campaigns, triggers, segments |
| Push notifications | `api/push_notifications.py` | ✅ Live | Firebase FCM |
| Real-time order updates | `api/realtime.py` | ✅ Live | Socket.io |
| Coupon/offers engine | `api/coupons.py`, `api/offers.py` | ✅ Live | Full discount engine |
| Analytics | `api/analytics.py` | ✅ Live | Includes acquisition_source tracking |
| FLAMEZO discovery API | `api/flamezo.py` | ✅ Live | Geo-sorting, cross-restaurant offers, member profile, points ledger |
| Cross-restaurant member profile | `api/flamezo.get_flamezo_member()` | ✅ Live | Tier, balance, lifetime stats, expiring coins |
| Cross-restaurant offers feed | `api/flamezo.get_cross_restaurant_offers()` | ✅ Live | All active coupons across network |
| Platform config constants | `utils/platform_config.py` | ✅ Live | Loyalty rates, tier thresholds, expiry |
| Permission system | `utils/permission_helpers.py` | ✅ Live | Restaurant-scoped row-level security |
| Feature gate | `utils/feature_gate.py` | ✅ Live | Now opens all features for new restaurants by default |
| Scheduled jobs | `hooks.py` scheduler_events | ✅ Live | 23:59 floor, 00:01 plan switch, 15min campaigns, etc. |
| AI services | `services/ai/` | ✅ Live | Blog, menu extraction, recommendations, coupon generator |
| Platform-level FLAMEZO OTP | `api/otp.py::send_flamezo_otp` | ✅ Live | Platform-scoped session for FLAMEZO consumer app |
| `acquisition_source` on orders | Order doctype + `api/orders.py` | ✅ Live | Tracks `flamezo_discovery` vs `qr_direct` vs `whatsapp` vs `pos` |

---

## 5. FINANCIAL PROJECTIONS

### Monthly P&L

| Month | Restaurants | Active | GMV/mo | Revenue (3%) | Expenses | **Net Profit** | **Cumulative** |
|---|---|---|---|---|---|---|---|
| M1 | 40 | 12 | ₹7.2L | ₹21,600 | ₹2,80,000 | **-₹2,58,400** | -₹2.6L |
| M3 | 160 | 52 | ₹36.4L | ₹1,09,200 | ₹3,70,000 | **-₹2,60,800** | -₹7.5L |
| M6 | 470 | 200 | ₹2Cr | ₹6,00,000 | ₹4,80,000 | **+₹1,20,000** | -₹10.5L |
| M9 | 870 | 460 | ₹5.52Cr | ₹16,56,000 | ₹5,80,000 | **+₹10,76,000** | +₹8L |
| M12 | 1,200 | 760 | ₹9.12Cr | ₹27,36,000 | ₹6,70,000 | **+₹20,66,000** | +₹56L |
| M18 | 2,200 | 1,400 | ₹22.4Cr | ₹67,20,000 | ₹9,20,000 | **+₹58,00,000** | +₹3.5Cr |
| M24 | 3,500 | 2,200 | ₹38.5Cr | ₹1,15,50,000 | ₹11,70,000 | **+₹1,03,80,000** | +₹9.8Cr |
| M36 | 7,500 | 5,000 | ₹100Cr | ₹3,00,00,000 | ₹19,50,000 | **+₹2,80,50,000** | +₹28Cr |

**Break-even: Month 6–7 | Total runway needed: ₹10–12L**

### Monthly Expense Breakdown

| Item | M1 | M12 | M36 |
|---|---|---|---|
| Infrastructure (servers, R2, Firebase, Vercel) | ₹55,000 | ₹1,00,000 | ₹5,00,000 |
| Meta Ads spend | ₹25,000 | ₹90,000 | ₹2,00,000 |
| AI API costs (OpenAI) | ₹10,000 | ₹30,000 | ₹1,50,000 |
| WhatsApp/SMS/Email platform costs | ₹5,000 | ₹30,000 | ₹1,00,000 |
| Team (founder + 1 dev + 1 sales + 1 support) | ₹1,75,000 | ₹4,00,000 | ₹12,00,000 |
| Consumer app marketing (Surat) | ₹0 | ₹80,000 | ₹2,50,000 |
| Misc (GST compliance, legal, ops) | ₹10,000 | ₹40,000 | ₹1,00,000 |
| **Total** | **₹2,80,000** | **₹6,70,000** | **₹19,50,000** |

> Projections updated to reflect the **3% Success Share** rate (up from 1.5% in the original migration plan). Numbers assume new-restaurant rate across the cohort, with legacy restaurants treated as a small fixed minority.

---

## 6. PHASE 2 REVENUE STREAMS (ROADMAP)

These are designed but not yet live. Doctype schemas exist where useful to avoid painful migrations later.

#### FLAMEZO Pass (Consumer Subscription)
| Item | Detail |
|---|---|
| What | ₹99/month consumer subscription — 2x loyalty coins + free weekly delivery |
| Doctype | `FLAMEZO Pass Subscription` (customer, start_date, end_date, status, razorpay_subscription_id) |
| Logic | On order: check if customer has active Pass → apply 2x coin multiplier |
| Revenue | 5,000 subscribers × ₹99 = ₹4.95L/month pure margin |

#### Featured Restaurant Placement
| Item | Detail |
|---|---|
| What | Restaurants pay ₹500–2,000/month to appear at top of discovery in their city |
| Doctype | `FLAMEZO Featured Slot` (restaurant, city, amount, valid_from, valid_until, is_active) |
| Logic | `get_all_restaurants()` → sort featured restaurants first, then by distance |
| Revenue | 50 restaurants × ₹1,000/month = ₹50,000/month |

#### Peak-Hour Convenience Fee
| Item | Detail |
|---|---|
| What | ₹10–15 flat fee on orders placed Fri/Sat 7–10 PM |
| Logic | In `create_payment_order()` — check day + time → add convenience_fee |
| Field | `convenience_fee` on Order doctype |
| Revenue | 500 orders/day × ₹10 × 8 peak hours/week = ₹40,000/month |

#### Event/Ticket Commission
| Item | Detail |
|---|---|
| What | Restaurants list events; consumers buy tickets through Flamezo |
| Take rate | 8–10% commission |

#### Table Reservation Fee
| Item | Detail |
|---|---|
| What | Consumer pays ₹20–30/booking; split with restaurant |

---

## 7. HISTORICAL: OLD MODEL (PRE-MAY 2026)

> Kept for context. **None of the items in this section apply to new restaurants under the current model.**

### Old Tier Structure (Retired)

| Tier | Cost | Features |
|---|---|---|
| **SILVER** | ₹0/month | QR menu only. No online payments. No dine-in ordering. |
| **GOLD** | ₹1,299 one-time unlock + ₹399/month floor + 1.5% commission | Full suite: ordering, loyalty, marketing, POS, AI, analytics |

### Old Gold Floor Model (Retired)
- 1.5% commission deducted from every order
- ₹399/month minimum guaranteed
- ₹1,299 one-time GOLD unlock fee
- All three of the above have been retired. Current model: **3% Success Share, ₹199/month floor, ₹0 onboarding fee** for all new restaurants.

### Why the Migration Happened
1. **₹1,299 unlock barrier** caused restaurants to churn before seeing value
2. **No consumer play** — purely B2B, no reason for diners to use Flamezo over Zomato
3. **No network effect** — 100 restaurants didn't make it easier to land restaurant #101
4. **Revenue ceiling** — SaaS multiples are 5–8x; platform multiples are 20–50x
5. **Single acquisition channel** — 100% dependent on Meta Ads

### What Changed in the Migration
- **₹1,299 unlock fee → removed.** Every restaurant onboards free.
- **Tier paywall (SILVER vs GOLD) → removed for new restaurants.** All features open day 1.
- **90-day trial concept → discarded.** Original plan included a 90-day free window before the floor kicked in; in the final model, free onboarding is permanent (no trial timer at all), and the ₹199 floor only triggers when monthly Success Share falls below it.
- **1.5% commission → 3% Success Share** for new restaurants (1.5% grandfathered for legacy).
- **₹399/month floor → ₹199/month floor.**
- **Monthly mandate billing → Razorpay Route auto-split** for online orders (real-time, T+2 settlement to restaurant's bank).
- **Customer-facing copy:** "commission" → "Success Share" (internal code identifiers like `commission_amount` are unchanged).

### Legacy Restaurant Treatment
Restaurants onboarded under the old model retain their **1.5% commission rate** as a grandfather clause if they were active before the May 2026 cutover. They may also still have their old `plan_type` value (`SILVER` or `GOLD`) in the database. Migration to the new ₹199 floor was offered as an opt-in.

---

## 8. APPENDIX — Key File Locations

| Area | File Path |
|---|---|
| Feature gating | `flamezo_backend/utils/feature_gate.py` |
| Payment processing | `flamezo_backend/api/payments.py` |
| Razorpay Route KYC | `flamezo_backend/api/route_kyc.py` |
| Commission ledger | `flamezo_backend/api/commission_ledger.py` |
| Order creation | `flamezo_backend/api/orders.py` |
| FLAMEZO consumer APIs | `flamezo_backend/api/flamezo.py` |
| Subscription / floor billing | `flamezo_backend/tasks/subscription_tasks.py` |
| Loyalty engine | `flamezo_backend/utils/loyalty.py` |
| Wallet/coins | `flamezo_backend/api/coin_billing.py` |
| Platform constants | `flamezo_backend/utils/platform_config.py` |
| OTP auth | `flamezo_backend/api/otp.py` |
| Onboarding | `flamezo_backend/api/onboarding.py` |
| Analytics | `flamezo_backend/api/analytics.py` |
| Global settings | `flamezo_backend/doctype/flamezo_backend_settings/flamezo_backend_settings.json` |
| App hooks | `flamezo_backend/hooks.py` |
| Scheduled tasks | `flamezo_backend/tasks/` |

---

*This document is the single source of truth for the current Flamezo business model. Update this file as the model evolves.*
