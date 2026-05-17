# Flamezo — Business Model Migration & Backend Gap Analysis
> Last Updated: May 2026 | Status: Planning Phase

---

## TABLE OF CONTENTS
1. [Old Business Model](#1-old-business-model)
2. [New Business Model](#2-new-business-model)
3. [Model Comparison](#3-model-comparison)
4. [Financial Projections](#4-financial-projections)
5. [Backend — What's Already Built](#5-backend--whats-already-built)
6. [Backend — Gaps & Required Changes](#6-backend--gaps--required-changes)
7. [Build Priority Order](#7-build-priority-order)
8. [Open Questions](#8-open-questions)

---

## 1. OLD BUSINESS MODEL

### Overview
Flamezo operated as a **B2B SaaS platform** — sell software subscriptions to restaurants, charge commission on orders, charge for feature usage.

### Tier Structure

| Tier | Cost | Features |
|---|---|---|
| **SILVER** | ₹0/month | QR menu only. No online payments. No dine-in ordering. |
| **GOLD** | ₹1,299 one-time unlock + ₹399/month floor + 1.5% commission | Full suite: ordering, loyalty, marketing, POS, AI, analytics |

### Gold Floor Model
- 1.5% commission deducted from every order
- ₹399/month minimum guaranteed
- At month end: if commissions > ₹399 → no extra charge. If commissions < ₹399 → only shortfall deducted.
- Example (Active month ₹50k GMV): ₹750 commission, ₹0 floor top-up
- Example (Slow month ₹10k GMV): ₹150 commission + ₹249 top-up = ₹399 total

### Revenue Streams (Old)
| Stream | Rate | Notes |
|---|---|---|
| Gold unlock fee | ₹1,299 one-time | Entry barrier to full features |
| Commission | 1.5% of GMV | Monthly billing via Razorpay mandate |
| Monthly floor | ₹399/month min | Shortfall recovery if commissions low |
| Lead unlock | ₹1/lead (>24h) | Gold only |
| WhatsApp messages | ₹1.20/msg | Margin: ₹0.43/msg over Meta cost |
| SMS | ₹0.25/msg | Margin: ₹0.07/msg |
| Email | ₹0.05/msg | High margin |
| Delivery handling | ₹5/order | Via Borzo/Flash logistics |
| AI dish generation | ₹10/image | Per-use |
| AI image enhancement | ₹5/image | Per-use |
| Wallet recharge bonuses | 10% at ₹2,999+ / 20% at ₹4,999+ | Drives pre-paid float |
| Referral | ₹500 both parties (on ₹1,000 recharge) | Acquisition |

### Payment Flow (Old)
- Restaurant sets up their own Razorpay merchant keys
- Customers pay directly to restaurant (no Flamezo in the middle)
- Flamezo bills commission monthly via mandate on restaurant wallet
- Wallet auto-recharges when balance drops below threshold
- Grace period: -₹100 (suspension below that)

### Acquisition Model (Old)
- Meta Ads (India + Surat campaigns) → leads → demo call → conversion
- ₹55 avg CPL (top 1% for B2B SaaS India, industry avg ₹300–800)
- Demo show rate: 16% (critical problem — industry standard 40–60%)
- 6 customers converted over 158 days of ads (CAC ₹2,161)
- Growth was gated behind paid subscription — high friction for restaurants

### Problems With Old Model
1. **₹1,299 unlock barrier** — restaurants churned at this step without seeing value first
2. **No consumer play** — purely B2B, no reason for customers to use Flamezo over Zomato
3. **No network effect** — 100 restaurants doesn't make it easier to get restaurant #101
4. **Demo show rate 16%** — funnel was leaking badly in the middle
5. **Revenue ceiling** — SaaS multiples are 5–8x; platform multiples are 20–50x
6. **Single acquisition channel** — 100% dependent on Meta Ads

---

## 2. NEW BUSINESS MODEL

### Overview
Flamezo pivots from **B2B SaaS** to a **two-sided restaurant platform**. The new model:
- Onboards restaurants for FREE with full Gold features immediately
- Promises to bring restaurants new customers (via FLAMEZO consumer app)
- Sits in the payment flow — collects 1.5% per transaction
- Passes 2% gateway fee (Razorpay/Cashfree) to consumer or restaurant — Flamezo bears ₹0
- Builds consumer loyalty across the entire restaurant network

### Core Principle
> "We grow when restaurants grow. We earn when they earn."

---

### New Tier Structure

| Tier | Cost | Features |
|---|---|---|
| **FREE ONBOARDING** | ₹0 forever (first 90 days no floor) | FULL Gold features immediately on signup |
| **POST-TRIAL** | ₹199/month floor + 1.5% commission | Same full features, floor kicks in after day 90 |

**No ₹1,299 unlock barrier. No Silver limitations. Every restaurant gets everything on day 1.**

---

### Revenue Streams (New)

#### Primary Revenue
| Stream | Rate | Notes |
|---|---|---|
| **Payment commission** | **1.5% of every order GMV** | Deducted from payment flow, tracked real-time, settled monthly |
| **Monthly floor** | **₹199/month after 90-day trial** | Protects against low-volume restaurants post-trial |

#### Secondary Revenue (Usage-Based)
| Stream | Rate | Notes |
|---|---|---|
| WhatsApp messages | ₹1.20/msg | Margin ₹0.43/msg |
| SMS | ₹0.25/msg | Margin ₹0.07/msg |
| Email | ₹0.05/msg | High margin |
| Delivery handling | ₹5/order | Via Borzo/Flash |
| AI dish generation | ₹10/image | Per-use |
| AI image enhancement | ₹5/image | Per-use |
| Lead unlock | ₹1/lead (>24h) | Customer data access |

#### Future Revenue (Phase 2 — Design Now, Build Later)
| Stream | Rate | Notes |
|---|---|---|
| FLAMEZO Pass (consumer subscription) | ₹99/month | 2x coins + free delivery on first weekly order |
| Featured restaurant placement | ₹500–2,000/month | Top of discovery screen in city |
| Peak-hour convenience fee | ₹10–15 flat | Consumer pays, Flamezo keeps |
| Event/ticket commission | 8–10% | Restaurants list events, consumers buy tickets |
| Table reservation fee | ₹20–30/booking | Consumer pays, split with restaurant |

---

### Payment Flow (New)

```
Consumer places order
       ↓
Flamezo payment gateway (Razorpay/Cashfree)
       ↓
Total collected = Order Amount + 2% Gateway Fee (paid by consumer/restaurant)
       ↓
Flamezo deducts 1.5% commission (tracked in Monthly Billing Ledger)
       ↓
98.5% released to restaurant bank account
       ↓
Gateway 2% goes to Razorpay/Cashfree — Flamezo bears ₹0
```

**Note:** True real-time split requires either:
- **Option A**: Razorpay Route (sub-merchant model) — complex, requires compliance
- **Option B**: Monthly settlement with real-time tracking in dashboard — already built, recommended for Phase 1

---

### Consumer Value Proposition (New)
- Download FLAMEZO app → discover restaurants near you
- Earn FLAMEZO Points (loyalty coins) at every Flamezo restaurant
- Points work across ALL restaurants in the network (earn at A, redeem at B)
- Referral: ₹30 coins for you + friend (on first order)
- Birthday bonus: ₹100 coins
- Welcome reward: ₹50 coins on signup

### Restaurant Value Proposition (New)
- Completely free onboarding — no subscription, no unlock fee
- QR codes, digital menu, ordering, loyalty, marketing — all live on day 1
- Flamezo actively brings new customers via FLAMEZO app
- Dashboard shows: "Flamezo sent you X new customers this month"
- Only pay 1.5% when you actually earn — zero cost in zero-revenue months during trial

---

### Go-to-Market Strategy (New)
- **Surat First** — achieve 200+ restaurant density before city #2
- Two active Meta campaigns: India (national) + Surat (local)
- Ground team: 2–3 field sales people in Surat, 10–15 onboardings/day/person
- Restaurant association partnerships (Hotel & Restaurant Association of South Gujarat)
- Target: Zomato/Swiggy refugees (paying 25–30% commission)
- Consumer acquisition: QR cashback (₹50 first order), influencers, food festivals
- FLAMEZO app on Playstore — launch before restaurant #50 in Surat

---

### Key Metrics to Watch
| Metric | Target | Action if missed |
|---|---|---|
| Restaurants onboarded/month | 100–200 (Surat) | Hire more field sales |
| Active restaurants (payment flowing) | >60% of enrolled | Fix consumer app adoption |
| Avg GMV/active restaurant/month | ₹1.5L | Improve ordering UX |
| Consumer DAU/MAU (Surat) | >30% | Fix retention before expanding city |
| GMV/restaurant at M4–M6 | >₹40,000 | Consumer adoption problem if below |
| Demo show rate (B2B funnel) | >50% | Add reminder sequences |

---

## 3. MODEL COMPARISON

| Dimension | Old Model | New Model |
|---|---|---|
| Entry cost for restaurant | ₹1,299 unlock + ₹399/mo | ₹0 (90-day free, then ₹199 floor) |
| Revenue trigger | Commission + floor from day 1 | Only when payment flows through |
| Who pays gateway fee | Flamezo absorbed (problem) | Consumer/restaurant — Flamezo ₹0 |
| Consumer play | None | FLAMEZO app — cross-restaurant loyalty |
| Network effect | None | Yes — more restaurants → more consumers → more GMV |
| Acquisition model | Ads → demo → close (slow) | Free onboarding + field sales (fast) |
| Revenue floor protection | ₹399/mo from day 1 | ₹199/mo after 90-day trial |
| Comparable business | Petpooja (SaaS) | Razorpay + Zomato hybrid (platform) |
| Valuation model | 5–8x ARR | 20–50x ARR |
| Break-even | Month 7–8 | Month 8–9 |
| Cash needed before profit | ₹7–8L | ₹16–18L |
| MRR at Month 36 | ₹19.2L | ₹1.41Cr |
| Cumulative profit by Year 3 | ₹1.17Cr | ₹14.4Cr |
| Estimated valuation at Year 3 | ₹12Cr | ₹85Cr |

**Verdict:** New model is 12x more profitable by Year 3 but needs ₹16L upfront runway and consumer app adoption to work.

---

## 4. FINANCIAL PROJECTIONS

### Monthly P&L — New Model

| Month | Restaurants | Active | GMV/mo | Revenue (1.5%) | Expenses | **Net Profit** | **Cumulative** |
|---|---|---|---|---|---|---|---|
| M1 | 40 | 12 | ₹7.2L | ₹10,800 | ₹2,80,000 | **-₹2,69,200** | -₹2.7L |
| M3 | 160 | 52 | ₹36.4L | ₹54,600 | ₹3,70,000 | **-₹3,15,400** | -₹8.5L |
| M6 | 470 | 200 | ₹2Cr | ₹3,00,000 | ₹4,80,000 | **-₹1,80,000** | -₹15.3L |
| M9 | 870 | 460 | ₹5.52Cr | ₹8,28,000 | ₹5,80,000 | **+₹2,48,000** | -₹14L |
| M12 | 1,200 | 760 | ₹9.12Cr | ₹13,68,000 | ₹6,70,000 | **+₹6,98,000** | +₹2.5L |
| M18 | 2,200 | 1,400 | ₹22.4Cr | ₹33,60,000 | ₹9,20,000 | **+₹24,40,000** | +₹68L |
| M24 | 3,500 | 2,200 | ₹38.5Cr | ₹57,75,000 | ₹11,70,000 | **+₹46,05,000** | +₹2.1Cr |
| M36 | 7,500 | 5,000 | ₹100Cr | ₹1,50,00,000 | ₹19,50,000 | **+₹1,30,50,000** | +₹14.4Cr |

**Break-even: Month 8–9 | Total runway needed: ₹16–18L**

### Monthly Expense Breakdown (New Model)
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

---

## 5. BACKEND — WHAT'S ALREADY BUILT

The following systems are **complete and do not need changes** for the new model:

| System | File | Status | Notes |
|---|---|---|---|
| Razorpay payment integration | `api/payments.py` | ✅ Complete | 1,148 lines — mandate, webhooks, RBI compliance, signature verification |
| Cross-restaurant loyalty | `utils/loyalty.py` | ✅ Complete | Earn at A, redeem at B — already works perfectly for new model |
| Wallet/coin system | `api/coin_billing.py` | ✅ Complete | Auto-recharge, grace period (-₹100), GST, bonus tiers |
| Monthly floor billing | `tasks/subscription_tasks.py` | ✅ Complete | Needs trial window addition only |
| OTP authentication | `api/otp.py` | ✅ Complete | Works for both restaurant and consumer auth |
| WhatsApp ordering | `api/whatsapp_ordering.py` | ✅ Complete | |
| Marketing automation | `api/marketing.py` + tasks | ✅ Complete | Campaigns, triggers, segments |
| Push notifications | `api/push_notifications.py` | ✅ Complete | Firebase FCM |
| Real-time order updates | `api/realtime.py` | ✅ Complete | Socket.io |
| Coupon/offers engine | `api/coupons.py`, `api/offers.py` | ✅ Complete | Full discount engine |
| Analytics | `api/analytics.py` | ✅ Complete | Needs `acquisition_source` metric added |
| FLAMEZO discovery API | `api/flamezo.py` | ✅ Built | geo-sorting, cross-restaurant offers, member profile, points ledger |
| Haversine geo-distance | `api/flamezo.py::_haversine_km()` | ✅ Built | Already computes distance per restaurant |
| Restaurant lat/lng fields | `Restaurant` doctype | ✅ Present | `latitude`, `longitude` fields exist |
| Cross-restaurant member profile | `api/flamezo.get_flamezo_member()` | ✅ Built | Tier, balance, lifetime stats, expiring coins |
| Cross-restaurant offers feed | `api/flamezo.get_cross_restaurant_offers()` | ✅ Built | All active coupons across network |
| Platform config constants | `utils/platform_config.py` | ✅ Complete | Loyalty rates, tier thresholds, expiry |
| Permission system | `utils/permission_helpers.py` | ✅ Complete | Restaurant-scoped row-level security |
| Feature gate | `utils/feature_gate.py` | ✅ Complete | `@require_plan()` decorator |
| Scheduled jobs | `hooks.py` scheduler_events | ✅ Complete | 23:59 floor, 00:01 plan switch, 15min campaigns, etc. |
| AI services | `services/ai/` | ✅ Complete | Blog, menu extraction, recommendations, coupon generator |

---

## 6. BACKEND — GAPS & REQUIRED CHANGES

---

### GAP 1 — ₹1,299 Gold Unlock Barrier Must Be Removed
**Priority: P0 — Do First**

**Current behavior:**
- `feature_gate.py` checks `plan_type == "GOLD"` for all premium features
- Restaurants must pay ₹1,299 to upgrade from Silver to Gold
- `subscription.py` has upgrade endpoint that charges the unlock fee
- SILVER restaurants cannot access ordering, CRM, marketing, POS

**New behavior:**
- Every new restaurant onboards directly as GOLD — no unlock fee, no Silver state
- Free trial: 90 days, no floor charged
- All GOLD features open immediately on day 1

**Changes required:**

| File | Change |
|---|---|
| `utils/feature_gate.py` | Remove ₹1,299 unlock check. New restaurants default to GOLD plan on creation. |
| `api/subscription.py` | Remove or disable the `upgrade_plan()` endpoint / upgrade barrier logic |
| `api/onboarding.py` | Set `plan_type = "GOLD"` and `plan_activated_on = today` on restaurant creation |
| `doctype/restaurant/restaurant.json` | Add `trial_end_date` field (Date). Set to `plan_activated_on + 90 days` on creation |
| `tasks/subscription_tasks.py` | Add trial check in `process_daily_subscription_floors()` — skip floor if `today < trial_end_date` |

---

### GAP 2 — Silver Plan Blocks Online Payments
**Priority: P0 — Do First**

**Current behavior in `api/payments.py`:**
```python
if restaurant.plan_type == "SILVER":
    frappe.throw("Online payments not available on Silver plan")
```

**New behavior:**
- All restaurants are GOLD — this block becomes irrelevant
- But also: during trial, restaurants should still be able to process payments (that's how Flamezo earns commission)
- The block must be removed or changed to check `is_active` instead of plan

**Changes required:**

| File | Change |
|---|---|
| `api/payments.py` → `create_payment_order()` | Remove Silver payment block. Gate on `restaurant.is_active` instead. |

---

### GAP 3 — Gateway 2% Not Passed to Consumer/Restaurant
**Priority: P0 — Do First**

**Current behavior:**
- `create_payment_order()` calculates `platform_fee_paise = 1.5% of order total`
- Razorpay's 2% fee is NOT explicitly added to the consumer-facing amount
- This means Flamezo is silently absorbing the gateway fee — wrong in new model

**New behavior:**
- Gateway fee (2%) added on top of order total before creating Razorpay order
- Flamezo commission (1.5%) tracked separately in order notes
- Consumer sees: Order Total + Gateway Fee = Total Payable

**Decision needed (see Open Questions #1):** Show as line item or bake into total?

**Changes required:**

| File | Change |
|---|---|
| `api/payments.py` → `create_payment_order()` | Add `gateway_fee_paise = ceil(order_total_paise * 0.02)`. Add to Razorpay order amount. Track separately in order notes. |
| `api/orders.py` → `create_order()` | Add `gateway_fee_amount` field to Order. Include in order total calculation. |
| `doctype/order/order.json` | Add `gateway_fee_amount` (Currency field) |
| `api/bootstrap.py` | Expose `gateway_fee_percent` in restaurant config response so Ono Menu can show it at checkout |

---

### GAP 4 — Floor Changed to ₹199 After 90-Day Trial
**Priority: P0 — Do First**

**Current behavior:**
- `process_daily_subscription_floors()` charges ₹399/month floor from day 1
- No trial period exists
- `flamezo_backend_settings` has GOLD Monthly Floor hardcoded at ₹399

**New behavior:**
- 90-day free trial — zero floor charged
- After day 90 → ₹199/month floor (reduced from ₹399)
- `trial_end_date` field on Restaurant doctype drives this logic

**Changes required:**

| File | Change |
|---|---|
| `tasks/subscription_tasks.py` → `process_daily_subscription_floors()` | Add: `if restaurant.trial_end_date and today() < restaurant.trial_end_date: continue` |
| `doctype/flamezo_backend_settings/flamezo_backend_settings.json` | Change GOLD Monthly Floor default from `399` → `199` |
| `doctype/restaurant/restaurant.json` | Add `trial_end_date` (Date) field |
| `api/onboarding.py` | Set `trial_end_date = add_days(today(), 90)` on restaurant creation |

---

### GAP 5 — Commission Settlement Timing (Critical Architecture Decision)
**Priority: P1**

**Current behavior:**
- Commission collected **monthly** via `schedule_monthly_billing()` and Razorpay mandate
- Restaurant pays directly via their own Razorpay keys
- Flamezo bills separately at month end

**New model says:** 1.5% deducted per transaction — 98.5% to restaurant

**Two implementation options:**

#### Option A — Real-Time Split (Razorpay Route / Sub-Merchant)
- Flamezo collects full payment → immediately splits: 98.5% restaurant, 1.5% Flamezo
- Requires: Razorpay Route activation + restaurants registered as sub-merchants
- **Pros:** True real-time split, restaurant sees instant net settlement
- **Cons:** RBI Payment Aggregator compliance, complex onboarding, was previously tried and removed
- **Estimated effort:** 4–6 weeks + compliance overhead

#### Option B — Monthly Settlement with Real-Time Dashboard (Recommended Phase 1)
- Keep existing monthly billing flow exactly as is
- Add real-time commission tracking per order in dashboard
- Restaurant sees: "This month: ₹2.3L processed, ₹3,450 (1.5%) platform fee, ₹2.27L net release"
- Same money, better communication
- **Pros:** Already built, no compliance changes, launches fast
- **Cons:** Restaurant doesn't see instant net settlement (only monthly)
- **Estimated effort:** 2 days (dashboard widget only)

**Recommendation: Start with Option B. Migrate to Option A when you have 500+ restaurants and investor capital.**

**Changes required (Option B):**

| File | Change |
|---|---|
| `api/analytics.py` | Add `get_commission_summary(restaurant_id, month)` — returns GMV, commission, net |
| `api/orders.py` | Store `commission_amount` on each Order doc (1.5% of total) |
| `doctype/order/order.json` | Add `commission_amount` (Currency field) |
| Merchant dashboard (React) | Add "Flamezo Commission This Month" widget with GMV / commission / net breakdown |

---

### GAP 6 — No `acquisition_source` Tracking on Orders
**Priority: P1**

**Current behavior:**
- Orders have no field to indicate how the customer arrived
- No way to know if a customer came from FLAMEZO discovery vs direct QR scan vs Zomato

**New behavior:**
- Every order tagged with `acquisition_source`: `flamezo_discovery` | `qr_direct` | `whatsapp` | `pos`
- Restaurant dashboard shows: "47 customers this month came from FLAMEZO network"
- This is the #1 retention argument — restaurants see Flamezo working

**Changes required:**

| File | Change |
|---|---|
| `doctype/order/order.json` | Add `acquisition_source` (Select field: qr_direct, flamezo_discovery, whatsapp, pos) |
| `api/orders.py` → `create_order()` | Accept `acquisition_source` param, default `qr_direct` |
| `api/flamezo.py` | Pass `acquisition_source=flamezo_discovery` when order initiated from FLAMEZO discovery |
| `api/analytics.py` | Add `get_flamezo_acquisition_stats(restaurant_id, month)` — count of FLAMEZO-sourced customers |
| Merchant dashboard (React) | Add "New customers from FLAMEZO this month: X" card |

---

### GAP 7 — Cross-Restaurant Offers Feed Filters Only GOLD Restaurants
**Priority: P1**

**Current behavior in `api/flamezo.get_cross_restaurant_offers()`:**
```python
restaurant_filters: dict = {"is_active": 1, "plan_type": "GOLD"}
```

**New behavior:**
- All restaurants are GOLD — this filter still works but semantically outdated
- More importantly: offers should be available from ALL active restaurants (no plan filter needed)
- Update filter to just `is_active = 1`

**Changes required:**

| File | Change |
|---|---|
| `api/flamezo.py` → `get_cross_restaurant_offers()` | Remove `"plan_type": "GOLD"` filter. Use `{"is_active": 1}` only. |

---

### GAP 8 — Platform-Level Consumer Session (For FLAMEZO App)
**Priority: P1**

**Current behavior:**
- Customer sessions are restaurant-scoped: `dm:session:{restaurantId}:tableNumber`
- A consumer logged into Restaurant A is not recognized at Restaurant B
- FLAMEZO app needs one login that works across all restaurants

**New behavior:**
- Platform-level session: `flamezo:session:{phone}` — works at all restaurants
- Existing restaurant-scoped sessions still work for Ono Menu per-restaurant app
- FLAMEZO member token = separate token that authenticates against any restaurant

**Current state of `api/flamezo.py`:**
- `get_flamezo_member()` and `get_points_ledger()` already use `customer_session:{session_token}` pattern ✅
- `register_flamezo_member()` already creates cross-restaurant customer record ✅
- **Session validation uses same `validate_customer_session()` helper** — already unified ✅

**What's missing:**
- A `flamezo_login` / `flamezo_verify_otp` endpoint that issues a platform-scoped token (not restaurant-scoped)
- Currently `api/otp.py` issues restaurant-scoped sessions

**Changes required:**

| File | Change |
|---|---|
| `api/otp.py` | Add `send_flamezo_otp(phone)` and `verify_flamezo_otp(phone, otp)` — issues platform session token stored as `flamezo:session:{token}` |
| `api/flamezo.py` | Update auth in `get_flamezo_member()` and `get_points_ledger()` to check `flamezo:session:{token}` first, then fall back to restaurant session |
| `utils/customer_helpers.py` | Add `validate_flamezo_session(phone, token)` helper |

---

### GAP 9 — Onboarding Flow Must Default to GOLD + Set Trial
**Priority: P1**

**Current behavior in `api/onboarding.py`:**
- Restaurant created with `plan_type = "SILVER"` by default
- Upgrade to GOLD requires separate step + ₹1,299 payment

**New behavior:**
- `plan_type = "GOLD"` set on restaurant creation
- `plan_activated_on = today()`
- `trial_end_date = add_days(today(), 90)`
- No payment required at onboarding

**Changes required:**

| File | Change |
|---|---|
| `api/onboarding.py` → restaurant creation | Set `plan_type = "GOLD"`, `plan_activated_on = today()`, `trial_end_date = add_days(today(), 90)` |
| `tasks/subscription_tasks.py` → `apply_deferred_plan_changes()` | Ensure no deferred downgrade to SILVER is triggered for trial restaurants |

---

### GAP 10 — FLAMEZO App Not on Playstore
**Priority: P1 (Deployment, Not Backend)**

**This is not a backend change** — but backend must be ready before launch:

**Backend readiness checklist:**
- [x] `get_all_restaurants()` — geo-sorted discovery ✅ (`api/flamezo.py`)
- [x] `get_cross_restaurant_offers()` — network-wide offers ✅ (`api/flamezo.py`)
- [x] `get_flamezo_member()` — unified member profile ✅ (`api/flamezo.py`)
- [x] `get_points_ledger()` — cross-restaurant transaction history ✅ (`api/flamezo.py`)
- [x] `register_flamezo_member()` — consumer registration ✅ (`api/flamezo.py`)
- [ ] `send_flamezo_otp()` + `verify_flamezo_otp()` — platform login ❌ (GAP 8)
- [ ] `acquisition_source` on orders — track FLAMEZO-sourced customers ❌ (GAP 6)
- [ ] `get_flamezo_acquisition_stats()` — "X customers sent by FLAMEZO" ❌ (GAP 6)

---

### PHASE 2 GAPS (Design Schema Now, Build Later)

These are not blocking the launch but need doctype planning now to avoid painful schema migrations later.

#### GAP 11 — FLAMEZO Pass (Consumer Subscription)
| Item | Detail |
|---|---|
| What | ₹99/month consumer subscription — 2x loyalty coins + free weekly delivery |
| New Doctype needed | `FLAMEZO Pass Subscription` (customer, start_date, end_date, status, razorpay_subscription_id) |
| Logic | On order: check if customer has active Pass → apply 2x coin multiplier |
| Revenue | 5,000 subscribers × ₹99 = ₹4.95L/month pure margin |

#### GAP 12 — Featured Restaurant Placement
| Item | Detail |
|---|---|
| What | Restaurants pay ₹500–2,000/month to appear at top of discovery in their city |
| New Doctype needed | `FLAMEZO Featured Slot` (restaurant, city, amount, valid_from, valid_until, is_active) |
| Logic | `get_all_restaurants()` → sort featured restaurants first, then by distance |
| Revenue | 50 restaurants × ₹1,000/month = ₹50,000/month |

#### GAP 13 — Peak-Hour Convenience Fee
| Item | Detail |
|---|---|
| What | ₹10–15 flat fee on orders placed Fri/Sat 7–10 PM |
| Logic | In `create_payment_order()` — check day + time → add convenience_fee |
| New field | `convenience_fee` on Order doctype |
| Revenue | 500 orders/day × ₹10 × 8 peak hours/week = ₹40,000/month |

---

## 7. BUILD PRIORITY ORDER

### P0 — Launch Blockers (Do Before Any Restaurant Onboarding)

| # | Task | Files | Effort |
|---|---|---|---|
| 1 | Remove ₹1,299 Gold unlock barrier | `feature_gate.py`, `subscription.py`, `onboarding.py` | 1 day |
| 2 | Set new restaurant default = GOLD with 90-day trial | `onboarding.py`, Restaurant doctype | 0.5 day |
| 3 | Add `trial_end_date` field to Restaurant doctype | `restaurant.json` | 0.5 day |
| 4 | Skip floor for trial restaurants | `subscription_tasks.py` | 0.5 day |
| 5 | Change floor default ₹399 → ₹199 in settings | `flamezo_backend_settings.json` | 0.25 day |
| 6 | Remove Silver payment block | `payments.py` | 0.25 day |
| 7 | Add gateway 2% to consumer checkout | `payments.py`, `orders.py`, Order doctype | 1 day |

**Total P0 effort: ~4 days**

---

### P1 — Required Before FLAMEZO App Playstore Launch

| # | Task | Files | Effort |
|---|---|---|---|
| 8 | Platform-level FLAMEZO OTP login | `api/otp.py`, `api/flamezo.py`, `utils/customer_helpers.py` | 2 days |
| 9 | `acquisition_source` field on Order | `orders.py`, Order doctype, `flamezo.py` | 1 day |
| 10 | Commission tracking per order | `orders.py`, Order doctype | 0.5 day |
| 11 | "FLAMEZO sent you X customers" analytics | `analytics.py`, merchant dashboard | 1.5 days |
| 12 | Commission dashboard widget (GMV / fee / net) | `analytics.py`, merchant dashboard React | 1.5 days |
| 13 | Fix cross-restaurant offers GOLD filter | `flamezo.py` | 0.25 day |

**Total P1 effort: ~7 days**

---

### P2 — Quality & Retention (First 30 Days After Launch)

| # | Task | Files | Effort |
|---|---|---|---|
| 14 | Demo show rate fix (B2B): email + WhatsApp reminders | Marketing automation | 1 day |
| 15 | Consumer ₹50 first-order cashback automation | `loyalty.py`, `api/flamezo.py` | 1 day |
| 16 | Coin expiry WhatsApp re-engagement | `tasks/loyalty_tasks.py` (already exists — verify) | 0.5 day |
| 17 | Social sharing post-order (earn 20 coins) | `api/orders.py`, Ono Menu UI | 1.5 days |
| 18 | Group ordering / bill split link | New feature in `api/cart.py` | 3 days |

---

### P3 — Phase 2 Revenue Streams (Month 3–6)

| # | Task | Files | Effort |
|---|---|---|---|
| 19 | FLAMEZO Pass subscription doctype + logic | New doctype + `payments.py` + `loyalty.py` | 4 days |
| 20 | Featured restaurant placement | New doctype + `flamezo.py` | 2 days |
| 21 | Peak-hour convenience fee | `payments.py`, Order doctype | 1 day |
| 22 | Razorpay Route sub-merchant (Option A commission) | `payments.py` complete rewrite | 6 weeks |

---

## 8. OPEN QUESTIONS

These need answers before starting backend changes:

**Q1 — Gateway fee display**
Should the 2% Razorpay/Cashfree gateway fee show as a separate line item on checkout ("Processing fee: ₹12") or be silently baked into the order total?
> *Answer needed from: Product/Founder*

**Q2 — Commission settlement timing**
Option A (real-time Razorpay Route split — complex) or Option B (monthly settlement, real-time dashboard tracking — already built)?
> *Recommendation: Option B for Phase 1. Answer needed from: Founder*

**Q3 — Trial duration**
90 days confirmed? Or different? Does the 90-day trial apply to existing Gold restaurants or only new signups from now?
> *Answer needed from: Founder*

**Q4 — Existing restaurant migration**
Current Gold restaurants paying ₹399/month floor — do they get migrated to new ₹199 floor? Or stay on old terms until they manually switch?
> *Answer needed from: Founder*

**Q5 — Gateway provider**
Razorpay or Cashfree for the new payment flow? Currently Razorpay is deeply integrated. Switching to Cashfree would require significant rewrite of `payments.py`.
> *Recommendation: Stay on Razorpay. Answer needed from: Founder*

**Q6 — Field sales team**
Who is hiring the 2–3 Surat ground team? What's the budget and timeline? This is the #1 dependency for restaurant supply acquisition.
> *Answer needed from: Founder*

**Q7 — FLAMEZO Playstore app**
Is the Ono Menu codebase being rebranded/extended as FLAMEZO, or is FLAMEZO a new separate app? This affects whether the existing Ono Menu Next.js app needs restructuring.
> *Answer needed from: Founder*

---

## APPENDIX — Key File Locations

| Area | File Path |
|---|---|
| Feature gating | `flamezo_backend/utils/feature_gate.py` |
| Payment processing | `flamezo_backend/api/payments.py` |
| Order creation | `flamezo_backend/api/orders.py` |
| FLAMEZO consumer APIs | `flamezo_backend/api/flamezo.py` |
| Subscription billing | `flamezo_backend/tasks/subscription_tasks.py` |
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

*This document is the single source of truth for the Flamezo model migration. Update this file as decisions are made and gaps are closed.*
