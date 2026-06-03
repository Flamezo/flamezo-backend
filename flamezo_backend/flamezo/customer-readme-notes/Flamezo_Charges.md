# Flamezo: Unified Fee Structure & Marketing Audit (2026)

> **Last Updated:** 2026-05-23 — Reflects the current Flamezo platform model post-Razorpay Route migration (May 2026).

This document provides a definitive audit of the Flamezo platform's economics. It has been validated from a marketing perspective to ensure professional clarity and value-driven positioning for restaurant partners.

---

## 1. Platform Access (Onboarding)

Flamezo is **free to onboard**. There is no upfront fee, no prepayment, and no trial timer — every restaurant gets the full feature suite from day 1.

| Item | Amount |
| :--- | :--- |
| **Onboarding Fee** | **₹0** |
| **Prepayment** | **₹0** |
| **Feature Access** | **Full suite from day 1** — ordering, loyalty, marketing, POS, AI, analytics |

> The old **SILVER / GOLD** tier-unlock model has been retired for new restaurants. Tier names may still appear in internal code (`plan_type`) and in legacy/grandfathered restaurant accounts, but they no longer gate any features for new signups.

### 💎 The Success Share Model (Growth Success Partner)
Flamezo only earns when you earn. We deduct a small **Success Share** on the orders that flow through the platform — no fixed monthly subscription beyond a small backstop.

- **3% Success Share** on GMV for **new restaurants** (effective May 2026).
- **1.5% Success Share** grandfathered for **legacy restaurants** onboarded before the new model.
- **18% GST** is applied on the Success Share.
- **₹199 Monthly Floor**: a backstop that guarantees a minimum platform contribution if your Success Share for the month falls below ₹199.
- **The Floor Check**: At the end of your billing month, we check your total Success Share collected.
    - If your Success Share exceeds ₹199, you pay **₹0 extra**.
    - If it's below ₹199, we deduct only the **shortfall**.

> **Example A: Active Month (new restaurant @ 3%)**
> - Monthly Revenue: ₹50,000
> - 3% Success Share: ₹1,500
> - **End-of-Month Floor Charge: ₹0** (You crossed the ₹199 floor)
>
> **Example B: Slow Month (new restaurant @ 3%)**
> - Monthly Revenue: ₹5,000
> - 3% Success Share: ₹150
> - **End-of-Month Floor Charge: ₹49** (To meet the ₹199 minimum)
> - **Total Flamezo Cost: ₹199**

---

## 2. Feature Access

All restaurants on the current model get the complete Flamezo suite immediately on signup. There is no SILVER/GOLD paywall for new signups.

| Feature | Included |
| :--- | :---: |
| Digital QR Menu | ✅ |
| In-Store Table Ordering | ✅ |
| WhatsApp Shadow Ordering | ✅ |
| Lead Unlock (>24h) | **₹1 / Lead** |
| Advanced Marketing Studio | ✅ |
| AI Media Suite | Paid (Per Use) |

> Legacy restaurants on the older SILVER tier may still see a reduced feature set until they're migrated. For all new restaurants, every row above is fully unlocked from day 1.

---

## 3. Marketing Studio & Channel Costs
Communication costs are charged directly from your Unified Wallet per message sent.

| Channel | Unit Cost to Restaurant | Recommended Use |
| :--- | :--- | :--- |
| **SMS** | **₹0.25** | Urgent alerts & OTPs. |
| **WhatsApp** | **₹1.20** | High-engagement marketing & campaigns. |
| **Email** | **₹0.05** | Weekly newsletters & updates. |

---

## 4. Logistics & Order Fulfillment
Transparency in delivery operations ensures a smooth experience for both you and your customers.

- **Self-Managed Delivery**: Restaurants manage delivery fulfillment using their own riders.
- **Default Delivery Fee**: Fully configurable by the restaurant (e.g. base fee plus rate per km).
- **Packaging & Operational Fee**: (Labeled as "Packaging Fee + Operation Overhead").
    - **Marketing Audit**: Recommend renaming to **"Eco-Packaging & Premium Handling"** for better customer reception.

---

## 5. AI Creative Suite (Design Automation)
Leverage state-of-the-art AI to handle your photography and design needs instantly.

| Service | Cost | Use Case |
| :--- | :--- | :--- |
| **AI Dish Generation** | **₹10** | Create menu images without a photoshoot. |
| **AI Image Enhancement** | **₹5** | Professional retouching for existing photos. |
| **Premium Theme (Branding)** | **FREE** | High-impact branding and custom themes. |

---

## 6. Wallet & Loyalty Incentives
The Unified Wallet (1 Coin = ₹1) simplifies payment for all additive services.

### 💰 Recharge Bonus Structure
We reward committed partners with significant recharge bonuses:
- **₹999**: Entry-level top-up (+₹1 Bonus).
- **₹2,999+**: **10% Bonus** (Get ₹3,300 for ₹3,000).
- **₹4,999+**: **20% Bonus** (Get ₹6,000 for ₹5,000).

### 🤝 Referral Program
- **Welcome Gift**: **₹500 for both parties.**
- **Requirement**: Referee must complete an initial recharge of ₹1,000 or more.

---

## 7. Payment Architecture (Razorpay Route)

Online orders flow through **Razorpay Route**, which auto-splits the customer payment in real time:

- **97% → directly to your Linked Account** (lands in your bank in T+2 business days)
- **3% Success Share → Flamezo** (1.5% for legacy/grandfathered restaurants)

For **cash orders**, the Success Share accrues in a commission ledger and is recovered via a 4-tier waterfall:
1. **Wallet** — deducted from your Flamezo wallet first
2. **Online net-off** — netted off against the next online order's split
3. **Autopay sweep** — debited via your UPI/card mandate
4. **Throttle** — if all the above fail, certain growth features are temporarily paused until cleared

---

## 8. Marketing Optimizations (Implementation Checklist)

> [!IMPORTANT]
> **Wallet Transparency**: Invoices and top-up summaries should explicitly state **"18% GST Applied Upfront"** to ensure zero confusion between payment and wallet balance.

1. **Success Share Positioning**: Position the 3% Success Share not as a "fee," but as a **"Growth Success Partner"** model — Flamezo only earns when the restaurant earns.
2. **Safety Buffer**: The **-₹100 Wallet Grace Period** should be marketed as "Uninterrupted Service Protection," ensuring your menu never goes offline during peak hours.
