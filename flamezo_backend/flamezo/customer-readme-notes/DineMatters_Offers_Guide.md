# 🎁 Flamezo Offers & Coupons — Complete Guide

> **Your restaurant's most powerful growth lever.** Offers and coupons drive repeat visits, unlock new customers, and boost average order value — all from one place.

---

## 📖 Table of Contents

1. [Quick Start — Your First Coupon in 60 Seconds](#1-quick-start)
2. [The 4 Offer Types — Which One Should You Use?](#2-offer-types)
3. [Discount Modes — Flat, Percent, Free Delivery](#3-discount-modes)
4. [Validity Controls — Date, Day & Time Restrictions](#4-validity-controls)
5. [Usage Limits — Preventing Abuse](#5-usage-limits)
6. [Combo Offers — Swiggy-Style Bundle Deals](#6-combo-offers)
7. [Auto Offers — Applied Without a Code](#7-auto-offers)
8. [Offer Stacking — Combining Multiple Deals](#8-offer-stacking)
9. [Ready-to-Use Templates](#9-templates)
10. [Discount Calculation — Exactly How the Math Works](#10-math)
11. [Error Codes — What They Mean](#11-errors)
12. [Best Practices & Strategy](#12-strategy)

---

## 1. Quick Start

### Your First Coupon in 60 Seconds

```
Setup & Config → Manage Offer and Coupons → + Create Coupon
```

**Recommended Starter Offer:**

| Field | Value |
|---|---|
| **Code** | `WELCOME50` |
| **Offer Type** | Coupon |
| **Discount** | ₹50 Flat |
| **Minimum Order** | ₹299 |
| **Per-Customer Limit** | 1 |
| **Description** | ₹50 off your first order |

> ✅ This is the single highest-converting coupon type for new restaurants. First-time customers convert at **3× the rate** when they have a welcome discount.

---

## 2. The 4 Offer Types

```
┌─────────────────────────────────────────────────────────────────┐
│                    OFFER TYPE SELECTOR                          │
│                                                                  │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │  COUPON  │   │   AUTO   │   │  COMBO   │   │DELIVERY  │    │
│  │          │   │          │   │          │   │          │    │
│  │  🏷️ Code  │   │ ⚡ Always │   │ 🎁 Bundle │   │ 🚴 Fee   │    │
│  │  Required│   │  Applied │   │  Price   │   │  Waiver  │    │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 🏷️ Coupon
A code the customer types at checkout. Best for:
- Welcome offers (`WELCOME50`)
- Promotional campaigns (`DIWALI30`)
- Loyalty rewards sent via WhatsApp/SMS
- Influencer-specific codes (`ZOMATO20`)

### ⚡ Auto
Applied automatically — no code needed. Customer sees the discount applied in real time. Best for:
- Lunchtime deals (12–3 PM)
- Weekday slow-period offers
- Order-value upsell (e.g. ₹30 off orders above ₹500)
- "Today only" flash sales

### 🎁 Combo
A fixed bundle price for specific dish combinations. Best for:
- Meal deals ("Burger + Fries + Drink = ₹249")
- Family packages
- Upselling sides with mains

### 🚴 Delivery
Applies only to the delivery fee — the cart subtotal is unchanged. Best for:
- "Free delivery on orders above ₹300"
- Competing with Swiggy/Zomato free delivery
- Re-engagement campaigns

---

## 3. Discount Modes

### Flat Discount (`flat`)
A fixed rupee amount is removed from the cart total.

```
Cart Total:  ₹450
Flat Off:   -₹50
            ──────
You Pay:     ₹400
```

**When to use:** When you want predictable, easy-to-communicate savings. "₹50 OFF" is clearer to customers than "15% OFF."

---

### Percentage Discount (`percent`)
A percentage of the cart total. Optional cap prevents over-discounting on large orders.

```
Cart Total:   ₹800
20% Discount: ₹160   ← would be ₹160
Max Cap:       ₹80   ← but capped at ₹80
You Save:      ₹80
You Pay:      ₹720
```

**When to use:** When you want the discount to feel generous on mid-sized orders but protect margins on large ones. Always set a `Max Cap`.

---

### Free Delivery (`delivery`)
Waives the delivery fee entirely. Cart subtotal and taxes are unchanged.

```
Cart Total:     ₹350
Delivery Fee:   ₹60  → ₹0 (waived)
Tax (5%):       ₹18
You Pay:        ₹368  (instead of ₹428)
```

**When to use:** For delivery orders only. This is the #1 incentive that drives delivery conversions.

---

## 4. Validity Controls

Control exactly when your offer is live with three independent gates. **All three must pass** for an offer to apply.

### 📅 Date Window

```
Valid From:  2026-06-01
Valid Until: 2026-06-30
```

The offer activates at midnight on `valid_from` and expires at end-of-day on `valid_until`. Leave both blank for a permanent offer.

---

### 📆 Day of Week

```
┌─────┬─────┬─────┬─────┬─────┬─────┬─────┐
│ Mon │ Tue │ Wed │ Thu │ Fri │ Sat │ Sun │
└──●──┴──●──┴──●──┴──●──┴──●──┴─────┴─────┘
                                 ↑ OFF  ↑ OFF
```

Toggle individual days. Blank = every day.

**Example use cases:**
- Weekend-only deals → Saturday + Sunday
- Weekday lunch offers → Monday–Friday
- "Taco Tuesday" promotions → Tuesday only

---

### ⏰ Time Window

```
Time Start: 12:00   Time End: 15:00
```

Only available within the specified hours. Leave blank for all-day.

**Example use cases:**
- Lunch special (12:00–15:00)
- Breakfast deal (07:00–10:00)
- Late-night offer (22:00–00:00)

> ⚠️ **Important:** Time windows use your restaurant's server time. For "Lunch 12–3 PM," set `12:00:00` to `15:00:00`.

---

## 5. Usage Limits

### Global Limit (`max_uses`)

```
Max Uses: 100
```

The offer disappears once redeemed 100 times total. Set to `0` for unlimited.

**When to use:** Flash sales, limited-stock bundles, budget-capped campaigns.

---

### Per-Customer Limit (`max_uses_per_user`)

```
Per Customer Limit: 1
```

Each customer can only use this offer once. Tracked via their customer account.

**When to use:** Welcome offers, new-user promotions, referral bonuses.

> 💡 **Pro Tip:** Combine `max_uses=500` with `max_uses_per_user=1` for a controlled new-customer campaign. First 500 new customers get ₹50 off, automatically stopping further abuse.

---

## 6. Combo Offers — Bundle Deals

Combo offers let you create deals that appear as **scrollable cards at the top of your menu page** and apply automatically at checkout. Three distinct combo types cover every bundle use-case.

---

### The 3 Combo Types

```
┌──────────────────┬──────────────────┬──────────────────────────┐
│  FIXED BUNDLE    │      BOGO        │    BUILD YOUR OWN        │
│                  │                  │                          │
│  All listed      │  Pick N items    │  Pick N items from a     │
│  items at one    │  from a pool —   │  pool — pay one fixed    │
│  combo price     │  cheapest FREE   │  combo price for them    │
└──────────────────┴──────────────────┴──────────────────────────┘
```

---

### 6a. Fixed Bundle

All specified products must be in the cart. The customer pays the combo price instead of the sum of individual prices.

**How to set up:**
1. Offer Type → **Combo Deal**
2. Combo Type → **Fixed Bundle**
3. Display Name → e.g. `Weekend Bundle`
4. Required Products → select all dishes that must be in cart
5. Combo Price → the fixed price the customer pays
6. Show as combo card on menu → ✅ toggle on

**Example:**
```
Required:      [Classic Burger ₹180, Fries ₹120, Coke ₹80]
Individual:    ₹380
Combo Price:   ₹249
Customer Saves: ₹131

Discount = Cart Total (₹380) − Combo Price (₹249) = ₹131
```

**What the customer sees:**
- A combo card on the menu page with an "Add Combo" button
- Tapping it adds all items to cart in one tap
- Discount applied automatically at checkout

---

### 6b. BOGO — Buy N Get Cheapest Free

Customer picks **N items** from a specified pool. The cheapest of those items is automatically made free.

**How to set up:**
1. Offer Type → **Combo Deal**
2. Combo Type → **BOGO — cheapest item free**
3. Display Name → e.g. `Buy 2 Get 1 Free`
4. Item Pool → all dishes the customer can pick from
5. Items to Buy (N) → how many they must select (e.g. 2)
6. No combo price needed — discount is auto-calculated
7. Show as combo card on menu → ✅

**Example:**
```
Pool:          [Pizza ₹300, Burger ₹200, Wrap ₹150, Salad ₹120]
Items to Buy:  2
Customer picks: Pizza (₹300) + Burger (₹200)
Cheapest free: Burger ₹200 → ₹0

Discount = price of cheapest qualifying item = ₹200
```

**What the customer sees:**
- Combo card with "Pick Items" button
- Tapping opens a bottom-sheet picker showing the pool
- Progress dots show N/needed selected
- Button reads "Add to Cart — Cheapest FREE"

> 💡 BOGO works best with 4–8 items in the pool so customers feel choice, but not overwhelm.

---

### 6c. Build Your Own

Customer picks **N items** from a pool and pays one fixed **combo price** for all of them — regardless of individual prices.

**How to set up:**
1. Offer Type → **Combo Deal**
2. Combo Type → **Build Your Own**
3. Display Name → e.g. `Build Your Meal`
4. Item Pool → all dishes to choose from
5. Items to Select → how many they pick (e.g. 3)
6. Combo Price → what they pay for the N items (e.g. ₹399)
7. Show as combo card on menu → ✅

**Example:**
```
Pool:           [Steak ₹450, Pasta ₹350, Salad ₹180, Soup ₹120]
Items to Select: 2
Combo Price:    ₹399
Customer picks: Steak (₹450) + Pasta (₹350) = ₹800 individual

Discount = Sum of selected (₹800) − Combo Price (₹399) = ₹401 saved
```

**What the customer sees:**
- Card with "Pick Items" button
- Picker shows the pool; they select exactly N
- Button reads "Add Combo · ₹399"

---

### How Combo Cards Appear on the Menu

When **"Show as combo card on menu"** is enabled, the combo appears as a horizontally scrollable card strip at the **top of the menu page**, before any categories — exactly like Swiggy's combo section.

```
┌─────────────────────────────────────────────────────┐
│  🎁 Combo Deals                              [2]    │
│  ┌──────────┐  ┌──────────┐                        │
│  │ [image]  │  │ [image]  │                        │
│  │          │  │          │                        │
│  │ Save ₹131│  │  BOGO    │                        │
│  │ Weekend  │  │Buy 2 Get │                        │
│  │ Bundle   │  │ 1 Free   │                        │
│  │ ₹249  ▶  │  │Pick Items│                        │
│  └──────────┘  └──────────┘                        │
└─────────────────────────────────────────────────────┘
```

Each card shows:
- The first item's image as background
- Orange savings badge (e.g. "Save ₹131") or "BOGO"
- Item thumbnails strip at the bottom
- Combo name + price
- CTA button: "Add Combo" (fixed bundle) or "Pick Items" (bogo/byo)

---

### Cart Nudge — "1 Item Away"

If a customer has some but not all combo items in cart, a nudge banner automatically appears above the offers section in the cart:

```
🎁  Add 1 more item to unlock Weekend Bundle combo!
```

This only shows when the customer is 1–2 items away from qualifying.

---

### Combo + Cart Interaction (Edge Cases)

| Scenario | Behaviour |
|---|---|
| Customer taps "Add Combo" (fixed bundle) | All required items added to cart in one tap |
| Customer already has 1 of 3 items | Combo still applies when all 3 are present |
| Customer removes a required item | Combo discount disappears automatically |
| BOGO: customer has 3 pool items, needed 2 | Cheapest of the 3 is free |
| Combo not on menu (display_on_menu off) | Still applies at checkout when code/auto matches |

---

### Display Name Tips

The **Display Name** is what customers see on the card. Make it punchy:

| Type | Good Names |
|---|---|
| Fixed Bundle | "Weekend Bundle", "Meal for Two", "Office Lunch Deal" |
| BOGO | "Buy 2 Get 1 Free", "1+1 Offer", "Double Up" |
| Build Your Own | "Build Your Meal", "Pick Your Combo", "Create Your Plate" |

> ⚠️ **Validation:** If any product in a required_items or item_pool is deleted from your menu, the combo may stop applying. Always verify combos after menu changes.

---

## 7. Auto Offers

Auto offers have **no coupon code** — they apply instantly when a customer's cart meets the conditions.

### When to Use Auto vs Coupon

| Situation | Use |
|---|---|
| Flash discount visible to everyone | Auto |
| Code shared via WhatsApp campaign | Coupon |
| Loyalty reward for specific users | Coupon |
| Lunch hour automatic discount | Auto |
| "Spend ₹500, save ₹50" passive upsell | Auto |

### Auto Offer Example

```
Offer Type:    Auto
Discount:      ₹30 flat
Min Order:     ₹400
Active Days:   Monday, Tuesday, Wednesday, Thursday
Time:          11:30 – 15:00
Description:   Weekday Lunch Deal — ₹30 off
```

This runs silently every weekday lunch. No marketing needed. Customers see it applied at checkout.

---

## 8. Offer Stacking

### Default Behaviour (Non-Stackable)

When multiple offers are eligible simultaneously, the one with the **highest discount** wins. Others are silently skipped.

```
Offer A: 20% off = ₹80  ← APPLIED (highest)
Offer B: ₹30 off = ₹30  ← skipped
```

### Stackable Offers

Enable **Stackable** on an offer to make it combine with other offers.

```
Offer A: 20% off = ₹80, stackable=NO  → Applied first
Offer B: ₹30 off = ₹30, stackable=YES → Also applied on top
                                         ─────────────
                          Total Saved: ₹110
```

> ⚠️ **Use stacking carefully.** It can lead to unexpected deep discounts. Test with small values first.

### Priority Field

When multiple non-stackable offers exist, `priority` determines which is **evaluated first** (higher wins). Use this to ensure featured offers take precedence in tie situations.

```
Offer A: priority=10, ₹50 discount
Offer B: priority=5,  ₹50 discount
→ Offer A wins (same discount, higher priority)
```

---

## 9. Ready-to-Use Templates

Click **+ Create Coupon** and choose a template to get started instantly.

### 🎉 Welcome Offer
```
Code:        WELCOME20
Type:        Coupon | 20% OFF | Max Cap ₹60
Min Order:   ₹199
Per Customer: 1 use only
Best For:    New customer acquisition
```

### 💰 Flat Deal
```
Code:        SAVE50
Type:        Coupon | ₹50 flat
Min Order:   ₹300
Best For:    Mid-week promotions
```

### 🔥 Flash Percent
```
Code:        FLASH25
Type:        Coupon | 25% OFF | Max Cap ₹80
Min Order:   ₹250
Best For:    Weekend pushes, social campaigns
```

### 🚴 Free Delivery
```
Code:        FREEDEL
Type:        Delivery | Free delivery
Min Order:   ₹299
Best For:    Competing with aggregator apps
```

### 🌞 Lunch Special
```
Code:        LUNCH30
Type:        Auto | ₹30 flat
Min Order:   ₹200
Time:        12:00–15:00
Days:        Mon–Fri
Best For:    Driving weekday lunch traffic
```

### 🎊 Weekend Blast
```
Code:        WEEKEND15
Type:        Auto | 15% OFF | Cap ₹60
Days:        Saturday, Sunday
Best For:    Weekend volume maximisation
```

### 👑 Loyalty Reward
```
Code:        LOYAL10
Type:        Coupon | ₹10 flat
Min Order:   ₹150
Best For:    Send via WhatsApp to repeat customers
```

### 📦 Bulk Order
```
Code:        BULK100
Type:        Coupon | ₹100 flat
Min Order:   ₹800
Best For:    Office catering, group orders
```

### 🍔 Fixed Bundle
```
Type:        Combo → Fixed Bundle
Items:       [Main Dish + Side + Drink]
Combo Price: Set lower than sum of items
Display Name: "Meal Deal"
Show on Menu: Yes
Best For:    Menu upselling, increasing items-per-order
```

### 🔁 BOGO
```
Type:        Combo → BOGO
Pool:        [Any 4–8 mid-range dishes]
Items to Buy: 2
Display Name: "Buy 2 Get 1 Free"
Show on Menu: Yes
Best For:    Moving mid-range items, social sharing
```

### 🏗️ Build Your Own
```
Type:        Combo → Build Your Own
Pool:        [All mains or all sides]
Items to Select: 3
Combo Price: Set 20-30% below sum of 3 typical picks
Display Name: "Build Your Meal"
Show on Menu: Yes
Best For:    Premium AOV, customer engagement
```

### ✏️ Custom / Blank
Start from scratch with full control.

---

## 10. Discount Calculation — The Exact Math

### Standard Orders

```
Step 1: Subtotal = sum of (quantity × unit_price) for all items

Step 2: Eligible offers filtered by:
        active=YES + date ✓ + day ✓ + time ✓ + min_order ✓ + usage_limits ✓

Step 3: Best offer selected (highest discount_amount)

Step 4: Discount applied:
        Flat:              discount = discount_value
        Percent:           discount = subtotal × (discount_value / 100)
                           if discount > max_cap → discount = max_cap
        Combo/Fixed Bundle: discount = cart_total − combo_price  (min 0)
        Combo/BOGO:        discount = price of cheapest qualifying item in cart
        Combo/Build Own:   discount = sum(selected pool items) − combo_price  (min 0)

Step 5: Taxable Amount = subtotal − discount
        Tax = taxable_amount × tax_rate (default 5%)
        CGST = SGST = tax / 2

Step 6: Total = taxable_amount + tax + delivery_fee + packaging_fee − loyalty_discount
```

### Delivery Order (with delivery discount)

```
Delivery Fee:        ₹60
Delivery Discount:   ₹60 (free delivery coupon)
Effective Fee:       ₹0   = max(0, 60 − 60)

Note: Delivery discount is ALWAYS capped to the actual delivery fee.
      A "free delivery" coupon cannot give cash back on the cart.
```

### Percent + Cap Example

```
Cart:         ₹1,200
Coupon:       20% OFF, Max Cap ₹80
Raw Discount: ₹1,200 × 0.20 = ₹240
Capped At:    ₹80
Final:        ₹80 off  →  Pay ₹1,120 + tax
```

---

## 11. Error Codes

When a coupon fails validation, the system returns a specific error code. Here's what each means and how to fix it.

| Error Code | What It Means | How to Fix |
|---|---|---|
| `COUPON_NOT_FOUND` | Code doesn't exist or wrong restaurant | Double-check the code spelling |
| `COUPON_INACTIVE` | Offer is toggled off | Go to Edit → enable the Active toggle |
| `COUPON_EXPIRED` | `valid_until` is in the past | Update the expiry date or create a new coupon |
| `COUPON_NOT_VALID_YET` | `valid_from` is in the future | Correct the start date |
| `MIN_ORDER_NOT_MET` | Cart total below threshold | Customer needs to add more items |
| `COUPON_LIMIT_REACHED` | Global `max_uses` exhausted | Increase the limit or create a new coupon |
| `CUSTOMER_LIMIT_REACHED` | This customer already used it | Per-user limit enforced — expected behaviour |
| `INVALID_DAY` | Not a valid day of week | Check day-of-week settings on the coupon |
| `INVALID_TIME` | Outside the time window | Check time start/end settings |
| `COMBO_ITEMS_MISSING` | Required combo dishes not all in cart (fixed bundle) | Customer must add all required items |
| `COMBO_INCOMPLETE` | Not enough items selected from the pool (bogo/byo) | Customer must add more items from the eligible pool |

---

## 12. Best Practices & Strategy

### 🎯 Acquisition — Getting New Customers

```
WELCOME50  →  ₹50 off first order, min ₹299, 1 use per customer
```
- Promote this code on Instagram bio, Google listing, and at your entrance
- Use a generous flat amount (not %) — it's easier to communicate

### 📈 Upsell — Increase Average Order Value

```
AUTO500  →  ₹50 flat, min order ₹500, Auto type
```
- Customers at ₹420 will actively add ₹80 more to unlock ₹50 off
- This is the most profitable offer type — you earn more per order

### 🔄 Retention — Bring Back Lapsed Customers

```
COMEBACK30  →  ₹30 flat, send via WhatsApp to customers inactive 14+ days
```
- Use Marketing Studio → Customer Insights to identify lapsed customers
- Send personalised WhatsApp message with the code

### 🕐 Slow Period Filler

```
LUNCH (Auto)  →  ₹25 flat, 12:00–15:00, weekdays only
```
- No ongoing management needed — runs automatically
- Track usage_count to measure lunchtime traffic lift

### ⚠️ Common Mistakes to Avoid

| Mistake | Why It's a Problem | Fix |
|---|---|---|
| Percent coupon without a cap | ₹2,000 order gets ₹400 off at 20% | Always set `Max Cap` |
| Welcome offer without per-customer limit | Single customer can reuse it | Set `Per Customer Limit: 1` |
| Combo referencing a deleted dish | Combo silently stops applying | Verify combos after menu changes |
| Multiple auto offers without priority | Unpredictable winner | Set explicit `Priority` values |
| Stackable offers without testing | Can stack into very deep discounts | Test with real cart values first |

---

> 📞 **Need help?** Contact your Flamezo account manager or write to support@flamezo_backend.in
>
> 🏷️ **Offers are restaurant-scoped** — a coupon code created in one outlet does not work at another.

---

*Flamezo Offers & Coupons Guide — Updated May 2026 (v2 — Combo Deals with Fixed Bundle, BOGO, Build Your Own)*
