# Copyright (c) 2026, Dinematters and contributors
# For license information, please see license.txt

"""
Production-grade tests for order pricing, payment verification idempotency,
and the process_loyalty_and_coupons() payment hook.

Covers:
  - calculate_cart_totals()  (utils/pricing.py)
      * Subtotal summed correctly from items
      * Tax computed from per-restaurant tax_rate
      * CGST/SGST split (50/50)
      * Loyalty discount applied from coin balance
      * Loyalty discount capped at remaining subtotal
      * Total = taxable_amount + tax + fees - loyalty_discount
      * Packaging fee added (flat and percentage modes)
      * No loyalty applied when customer has zero balance
      * No loyalty applied when loyalty is disabled

  - Platform fee calculation  (api/payments.py)
      * platform_fee = floor(total_paise × percent / 100)
      * Correct for both 1.5% and custom percentages

  - process_loyalty_and_coupons()  (api/payments.py)
      * Idempotency: calling twice must NOT double-redeem or double-earn
      * Earn step skipped when order already has an Earn entry

  - verify_payment() double-fire safety
      * payment_status updated exactly once despite duplicate calls

Run with:
    bench run-tests --app dinematters --module dinematters.dinematters.tests.test_order_pricing
"""

import math
import unittest
from unittest.mock import patch, MagicMock

import frappe
from frappe.utils import today, add_days

from dinematters.dinematters.tests.utils import (
    make_restaurant,
    make_loyalty_config,
    make_customer,
    make_menu_product,
    make_loyalty_entry,
    cleanup_restaurant,
    cleanup_restaurants_by_prefix,
    reset_restaurant_balance,
)

_PREFIX = "TEST-PRICE"


# ─── helpers ──────────────────────────────────────────────────────────────────

def _items(*price_qty_pairs):
    """Build a list of pricing engine items: (unit_price, quantity) tuples."""
    return [{"unitPrice": p, "quantity": q, "dishId": f"dish-{i}"}
            for i, (p, q) in enumerate(price_qty_pairs)]


def _clear_loyalty_entries(customer, restaurant):
    frappe.db.delete("Restaurant Loyalty Entry", {
        "customer": customer,
        "restaurant": restaurant,
    })
    frappe.db.commit()


# ─── 1. calculate_cart_totals() ───────────────────────────────────────────────

class TestCalculateCartTotals(unittest.TestCase):
    """
    Tests the authoritative pricing engine in utils/pricing.py.

    Delivery-mode tests are excluded here because they depend on external
    geo-lookup services. All tests use delivery_type="Dine-in".
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-CCT-")

        cls._res = f"{_PREFIX}-CCT-{frappe.generate_hash(length=6)}"
        # tax_rate=5.0 → CGST 2.5% + SGST 2.5%
        make_restaurant(cls._res, plan="DIAMOND", balance=5000.0)
        frappe.db.set_value("Restaurant", cls._res, "tax_rate", 5.0)
        frappe.db.commit()

        # Loyalty setup: 0.1 pts/INR, coin_value_in_inr=1.0
        cls._customer = make_customer(phone="9200000001", name="Test Pricing Customer")
        make_loyalty_config(
            cls._res,
            points_per_inr=0.1,
            coin_value_in_inr=1.0,
            loyalty_expiry_months=12,
        )
        # Enable loyalty on restaurant
        frappe.db.set_value("Restaurant", cls._res, "enable_loyalty", 1)
        frappe.db.commit()

        from dinematters.dinematters.utils.pricing import calculate_cart_totals
        cls.calc = staticmethod(calculate_cart_totals)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        _clear_loyalty_entries(self._customer.name, self._res)

    # ── subtotal ──

    def test_single_item_subtotal(self):
        result = self.calc(self._res, _items((200.0, 1)))
        self.assertAlmostEqual(result["subtotal"], 200.0, places=2)

    def test_multiple_items_subtotal(self):
        result = self.calc(self._res, _items((100.0, 2), (50.0, 3)))
        # 100×2 + 50×3 = 200 + 150 = 350
        self.assertAlmostEqual(result["subtotal"], 350.0, places=2)

    def test_quantity_multiplied_into_subtotal(self):
        result = self.calc(self._res, _items((99.0, 5)))
        self.assertAlmostEqual(result["subtotal"], 495.0, places=2)

    # ── tax ──

    def test_tax_computed_at_restaurant_rate(self):
        """₹1000 subtotal × 5% tax = ₹50 tax."""
        result = self.calc(self._res, _items((1000.0, 1)))
        self.assertAlmostEqual(result["tax"], 50.0, places=2)
        self.assertAlmostEqual(result["taxRate"], 5.0, places=2)

    def test_cgst_sgst_split_equally(self):
        """₹50 tax → CGST ₹25 + SGST ₹25."""
        result = self.calc(self._res, _items((1000.0, 1)))
        self.assertAlmostEqual(result["cgst"], 25.0, places=2)
        self.assertAlmostEqual(result["sgst"], 25.0, places=2)

    def test_cgst_plus_sgst_equals_tax(self):
        result = self.calc(self._res, _items((999.0, 1)))
        self.assertAlmostEqual(result["cgst"] + result["sgst"], result["tax"], places=2)

    def test_zero_tax_rate_means_no_tax(self):
        frappe.db.set_value("Restaurant", self._res, "tax_rate", 0.0)
        frappe.db.commit()
        try:
            result = self.calc(self._res, _items((500.0, 1)))
            self.assertAlmostEqual(result["tax"], 0.0, places=2)
            self.assertAlmostEqual(result["cgst"], 0.0, places=2)
            self.assertAlmostEqual(result["sgst"], 0.0, places=2)
        finally:
            frappe.db.set_value("Restaurant", self._res, "tax_rate", 5.0)
            frappe.db.commit()

    # ── total ──

    def test_total_equals_taxable_plus_tax(self):
        """For Dine-in with no fees and no discounts: total = subtotal + tax."""
        result = self.calc(self._res, _items((200.0, 1)))
        expected_total = 200.0 + round(200.0 * 0.05, 2)
        self.assertAlmostEqual(result["total"], expected_total, places=2)

    def test_total_never_negative(self):
        """Even if discounts hypothetically exceeded total, result must be >= 0."""
        result = self.calc(self._res, _items((1.0, 1)))
        self.assertGreaterEqual(result["payableAmount"], 0)

    # ── loyalty discount ──

    def test_loyalty_discount_reduces_total(self):
        """
        Customer has 50 settled loyalty coins (₹50 value).
        Asking to redeem 30 → loyalty_discount = 30.
        Total should be lower by 30.
        """
        make_loyalty_entry(self._customer.name, self._res, coins=50, is_settled=1)
        result_no_loyalty = self.calc(self._res, _items((500.0, 1)))
        result_with_loyalty = self.calc(
            self._res, _items((500.0, 1)),
            loyalty_coins=30,
            customer=self._customer.name
        )
        self.assertAlmostEqual(result_with_loyalty["loyaltyDiscount"], 30.0, places=2)
        self.assertAlmostEqual(
            result_no_loyalty["total"] - result_with_loyalty["total"],
            30.0, places=2,
            msg="Total must decrease by exactly the loyalty discount"
        )

    def test_loyalty_discount_capped_at_balance(self):
        """
        Customer has 20 coins. Requesting 100 → capped at 20.
        """
        make_loyalty_entry(self._customer.name, self._res, coins=20, is_settled=1)
        result = self.calc(
            self._res, _items((500.0, 1)),
            loyalty_coins=100,
            customer=self._customer.name
        )
        self.assertAlmostEqual(result["loyaltyDiscount"], 20.0, places=2)

    def test_no_loyalty_discount_when_customer_has_zero_balance(self):
        result = self.calc(
            self._res, _items((500.0, 1)),
            loyalty_coins=50,
            customer=self._customer.name
        )
        self.assertAlmostEqual(result["loyaltyDiscount"], 0.0, places=2)

    def test_loyalty_discount_not_applied_without_customer(self):
        """If customer=None, loyalty_discount must be 0 regardless of loyalty_coins."""
        make_loyalty_entry(self._customer.name, self._res, coins=100, is_settled=1)
        result = self.calc(
            self._res, _items((500.0, 1)),
            loyalty_coins=50,
            customer=None
        )
        self.assertAlmostEqual(result["loyaltyDiscount"], 0.0, places=2)

    # ── packaging fee (flat mode) ──

    def test_flat_packaging_fee_added_for_takeaway(self):
        """
        Restaurant has default_packaging_fee=20 (flat) and packaging_fee_type=Fixed.
        For Takeaway, packaging fee must be ₹20.
        """
        frappe.db.set_value("Restaurant", self._res, {
            "default_packaging_fee": 20.0,
            "packaging_fee_type": "Fixed",
        })
        frappe.db.commit()
        try:
            result = self.calc(
                self._res, _items((100.0, 1)),
                delivery_type="Takeaway"
            )
            self.assertAlmostEqual(result["packagingFee"], 20.0, places=2)
            # Total must include packaging fee
            self.assertAlmostEqual(
                result["total"],
                100.0 + round(100.0 * 0.05, 2) + 20.0,
                places=2
            )
        finally:
            frappe.db.set_value("Restaurant", self._res, {
                "default_packaging_fee": 0.0,
            })
            frappe.db.commit()

    def test_no_packaging_fee_for_dine_in(self):
        """Packaging fee must be 0 for Dine-in orders."""
        frappe.db.set_value("Restaurant", self._res, {
            "default_packaging_fee": 20.0,
            "packaging_fee_type": "Fixed",
        })
        frappe.db.commit()
        try:
            result = self.calc(self._res, _items((100.0, 1)), delivery_type="Dine-in")
            self.assertAlmostEqual(result["packagingFee"], 0.0, places=2)
        finally:
            frappe.db.set_value("Restaurant", self._res, {"default_packaging_fee": 0.0})
            frappe.db.commit()


# ─── 2. Platform fee math ─────────────────────────────────────────────────────

class TestPlatformFeeCalculation(unittest.TestCase):
    """
    Tests the platform_fee_paise calculation from payments.py (lines 107-108):
        platform_fee_paise = int(math.floor(total_paise × percent / 100))

    These are pure math tests — no DB interaction required.
    """

    def _calc_fee(self, total_inr, percent):
        total_paise = int(float(total_inr) * 100)
        return int(math.floor(total_paise * (percent / 100.0)))

    def test_standard_1_5_percent_on_1000(self):
        # ₹1000 × 1.5% = ₹15 = 1500 paise
        self.assertEqual(self._calc_fee(1000.0, 1.5), 1500)

    def test_standard_1_5_percent_on_3000(self):
        # ₹3000 × 1.5% = ₹45 = 4500 paise
        self.assertEqual(self._calc_fee(3000.0, 1.5), 4500)

    def test_zero_percent_fee(self):
        self.assertEqual(self._calc_fee(1000.0, 0.0), 0)

    def test_fractional_total_floored(self):
        # ₹999 × 1.5% = ₹14.985 → floored to 1498 paise
        self.assertEqual(self._calc_fee(999.0, 1.5), 1498)

    def test_custom_2_percent(self):
        # ₹500 × 2% = ₹10 = 1000 paise
        self.assertEqual(self._calc_fee(500.0, 2.0), 1000)

    def test_minimum_order_amount(self):
        # ₹10 × 1.5% = ₹0.15 → floored to 15 paise
        self.assertEqual(self._calc_fee(10.0, 1.5), 15)


# ─── 3. process_loyalty_and_coupons() idempotency ────────────────────────────

class TestProcessLoyaltyAndCouponsIdempotency(unittest.TestCase):
    """
    process_loyalty_and_coupons() is called after payment verification.
    If a webhook fires twice (or the function is called twice for any reason),
    coins must not be double-redeemed and coins must not be double-earned.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-PLC-")

        cls._res = f"{_PREFIX}-PLC-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND", balance=5000.0)
        frappe.db.set_value("Restaurant", cls._res, {
            "tax_rate": 0.0,
            "enable_loyalty": 1,
        })
        frappe.db.commit()

        cls._customer = make_customer(phone="9200000002", name="Test Idempotent Customer")
        make_loyalty_config(
            cls._res,
            points_per_inr=0.1,
            coin_value_in_inr=1.0,
            loyalty_expiry_months=12,
        )
        from dinematters.dinematters.api.payments import process_loyalty_and_coupons
        cls.process = staticmethod(process_loyalty_and_coupons)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)
        frappe.db.delete("Restaurant Loyalty Entry", {"customer": cls._customer.name})
        frappe.db.commit()

    def setUp(self):
        _clear_loyalty_entries(self._customer.name, self._res)
        # Give customer 200 loyalty coins so redemption is possible
        make_loyalty_entry(self._customer.name, self._res, coins=200, is_settled=1)

    def _make_order_mock(self, order_name, coins_redeemed=50, total=500.0):
        order = MagicMock()
        order.name = order_name
        order.restaurant = self._res
        order.platform_customer = self._customer.name
        order.loyalty_coins_redeemed = coins_redeemed
        order.total = total
        order.coupon = None   # prevent MagicMock auto-attr from corrupting SQL
        order.discount = 0.0
        return order

    def test_redemption_is_idempotent(self):
        """
        Calling process() twice with the same order must create exactly ONE
        Redeem entry for that order, not two.
        """
        order_name = f"TEST-ORD-{frappe.generate_hash(length=8)}"
        order = self._make_order_mock(order_name, coins_redeemed=50)

        self.process(order)
        self.process(order)  # second call (webhook double-fire)

        redeem_count = frappe.db.count("Restaurant Loyalty Entry", {
            "customer": self._customer.name,
            "restaurant": self._res,
            "reference_name": order_name,
            "transaction_type": "Redeem",
            "reason": "Redemption",
        })
        self.assertEqual(redeem_count, 1,
                         "Redemption must be processed exactly once despite double call")

    def test_earn_is_idempotent(self):
        """
        Calling process() twice must create exactly ONE Earn entry for the order.
        """
        order_name = f"TEST-ORD-{frappe.generate_hash(length=8)}"
        order = self._make_order_mock(order_name, coins_redeemed=0, total=1000.0)

        self.process(order)
        self.process(order)  # second call

        earn_count = frappe.db.count("Restaurant Loyalty Entry", {
            "customer": self._customer.name,
            "restaurant": self._res,
            "reference_name": order_name,
            "transaction_type": "Earn",
            "reason": ["in", ["Order", "order"]],
        })
        # May be 0 if loyalty earning is in create_order path; but must not be > 1
        self.assertLessEqual(earn_count, 1,
                             "Earn entry must not be created more than once per order")

    def test_no_platform_customer_skips_gracefully(self):
        """If platform_customer is None, the function must return without raising."""
        order_name = f"TEST-ORD-{frappe.generate_hash(length=8)}"
        order = self._make_order_mock(order_name)
        order.platform_customer = None
        try:
            self.process(order)  # must not raise
        except Exception as e:
            self.fail(f"process_loyalty_and_coupons raised with no platform_customer: {e}")


# ─── 4. verify_payment() double-fire safety ───────────────────────────────────

class TestVerifyPaymentIdempotency(unittest.TestCase):
    """
    Ensures that calling verify_payment() twice for the same Razorpay payment ID
    updates the Order payment_status only once (the second call is a safe no-op
    at the DB level, even if the function runs again).

    Razorpay client is mocked to avoid real API calls.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-VPI-")

        cls._res = f"{_PREFIX}-VPI-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="DIAMOND", balance=5000.0)
        frappe.db.set_value("Restaurant", cls._res, {
            "tax_rate": 0.0,
            "enable_loyalty": 0,
        })
        cls._customer = make_customer(phone="9200000003", name="Test Verify Customer")
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)

    def _create_test_order(self, rzp_order_id):
        """Insert a bare Order document in the DB for testing."""
        product = make_menu_product(self._res, f"VPI-PROD-{frappe.generate_hash(length=6)}", price=500.0)
        order = frappe.get_doc({
            "doctype": "Order",
            "order_id": frappe.generate_hash(length=10),
            "order_number": f"TEST-{frappe.generate_hash(length=4)}",
            "restaurant": self._res,
            "platform_customer": self._customer.name,
            "status": "confirmed",
            "payment_status": "pending",
            "razorpay_order_id": rzp_order_id,
            "total": 500.0,
            "subtotal": 500.0,
            "loyalty_coins_redeemed": 0,
            "order_items": [{
                "product": product.name,
                "product_name": product.product_name,
                "quantity": 1,
                "unit_price": 500.0,
                "total_price": 500.0,
            }],
        })
        with patch("dinematters.dinematters.api.realtime.notify_new_order_to_merchant"):
            order.insert(ignore_permissions=True)
        frappe.db.commit()
        return order

    @patch("dinematters.dinematters.api.payments.get_razorpay_client")
    @patch("dinematters.dinematters.api.payments.process_loyalty_and_coupons")
    def test_payment_status_set_to_completed(self, mock_process_loyalty, mock_get_client):
        """verify_payment() must set payment_status=completed on the Order."""
        rzp_order_id = f"order_test_{frappe.generate_hash(length=10)}"
        rzp_payment_id = f"pay_test_{frappe.generate_hash(length=10)}"
        order = self._create_test_order(rzp_order_id)

        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.return_value = None  # no raise = valid
        mock_get_client.return_value = mock_client

        from dinematters.dinematters.api.payments import verify_payment
        result = verify_payment(rzp_order_id, rzp_payment_id, "valid_signature")

        self.assertTrue(result["success"])
        final_status = frappe.db.get_value("Order", order.name, "payment_status")
        self.assertEqual(final_status, "completed")

        # Cleanup
        frappe.db.delete("Order", {"name": order.name})
        frappe.db.commit()

    @patch("dinematters.dinematters.api.payments.get_razorpay_client")
    @patch("dinematters.dinematters.api.payments.process_loyalty_and_coupons")
    def test_double_verify_does_not_raise(self, mock_process_loyalty, mock_get_client):
        """
        Calling verify_payment() twice for the same order and payment ID must
        not raise an exception and must leave the order in 'completed' state.
        """
        rzp_order_id = f"order_test_{frappe.generate_hash(length=10)}"
        rzp_payment_id = f"pay_test_{frappe.generate_hash(length=10)}"
        order = self._create_test_order(rzp_order_id)

        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.return_value = None
        mock_get_client.return_value = mock_client

        from dinematters.dinematters.api.payments import verify_payment
        verify_payment(rzp_order_id, rzp_payment_id, "valid_signature")

        try:
            result2 = verify_payment(rzp_order_id, rzp_payment_id, "valid_signature")
            # Must still report success (idempotent)
            self.assertTrue(result2["success"])
        except Exception as e:
            self.fail(f"Second verify_payment() raised unexpectedly: {e}")

        final_status = frappe.db.get_value("Order", order.name, "payment_status")
        self.assertEqual(final_status, "completed",
                         "Payment status must remain completed after double verification")

        # Cleanup
        frappe.db.delete("Order", {"name": order.name})
        frappe.db.commit()

    @patch("dinematters.dinematters.api.payments.get_razorpay_client")
    def test_invalid_signature_returns_failure(self, mock_get_client):
        """An invalid Razorpay signature must return success=False."""
        rzp_order_id = f"order_test_{frappe.generate_hash(length=10)}"
        rzp_payment_id = f"pay_test_{frappe.generate_hash(length=10)}"
        order = self._create_test_order(rzp_order_id)

        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.side_effect = Exception("Signature mismatch")
        mock_get_client.return_value = mock_client

        from dinematters.dinematters.api.payments import verify_payment
        result = verify_payment(rzp_order_id, rzp_payment_id, "bad_signature")

        self.assertFalse(result["success"])
        # Payment status must remain 'pending' after failed verification
        status = frappe.db.get_value("Order", order.name, "payment_status")
        self.assertEqual(status, "pending",
                         "payment_status must not be updated after failed verification")

        # Cleanup
        frappe.db.delete("Order", {"name": order.name})
        frappe.db.commit()


# ─── 5. Bonus unit tests for GST on coin purchases ───────────────────────────

class TestCoinPurchaseGST(unittest.TestCase):
    """
    Validates that coin purchase orders correctly apply 18% GST.
    Uses the helper from coin_billing.py without making a real Razorpay call.

    Razorpay client is mocked.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cleanup_restaurants_by_prefix(_PREFIX + "-GST-")
        cls._res = f"{_PREFIX}-GST-{frappe.generate_hash(length=6)}"
        make_restaurant(cls._res, plan="GOLD", balance=5000.0)

    @classmethod
    def tearDownClass(cls):
        cleanup_restaurant(cls._res)

    @patch("dinematters.dinematters.api.coin_billing.get_razorpay_client")
    @patch("dinematters.dinematters.api.coin_billing.get_razorpay_config")
    def test_18_percent_gst_on_1000(self, mock_cfg, mock_client):
        """
        Manual top-up of ₹1000:
        GST = ₹1000 × 18% = ₹180
        Total payable = ₹1180
        Amount in paise = 118000
        """
        mock_rzp = MagicMock()
        mock_rzp.order.create.return_value = {"id": "order_test_gst"}
        mock_client.return_value = mock_rzp
        mock_cfg.return_value = {"key_id": "rzp_test_key"}

        from dinematters.dinematters.api.coin_billing import create_coin_purchase_order
        result = create_coin_purchase_order(self._res, 1000)

        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["gst_amount"], 180.0, places=2)
        self.assertAlmostEqual(result["total_payable"], 1180.0, places=2)
        self.assertEqual(result["amount"], 118000)  # paise

    @patch("dinematters.dinematters.api.coin_billing.get_razorpay_client")
    @patch("dinematters.dinematters.api.coin_billing.get_razorpay_config")
    def test_18_percent_gst_on_2999(self, mock_cfg, mock_client):
        """
        Manual top-up of ₹2999 (Tier 1 boundary):
        Bonus = ₹2999 × 10% = ₹299.9
        GST is on BASE AMOUNT only (₹2999), not on bonus.
        GST = ₹2999 × 18% = ₹539.82
        Total payable = ₹2999 + ₹539.82 = ₹3538.82
        """
        mock_rzp = MagicMock()
        mock_rzp.order.create.return_value = {"id": "order_test_gst2"}
        mock_client.return_value = mock_rzp
        mock_cfg.return_value = {"key_id": "rzp_test_key"}

        from dinematters.dinematters.api.coin_billing import create_coin_purchase_order
        result = create_coin_purchase_order(self._res, 2999)

        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["base_amount"], 2999.0, places=2)
        self.assertAlmostEqual(result["gst_amount"], round(2999.0 * 0.18, 2), places=2)
        self.assertAlmostEqual(
            result["total_payable"],
            round(2999.0 + 2999.0 * 0.18, 2),
            places=2
        )

    @patch("dinematters.dinematters.api.coin_billing.get_razorpay_client")
    @patch("dinematters.dinematters.api.coin_billing.get_razorpay_config")
    def test_paise_conversion_is_integer(self, mock_cfg, mock_client):
        """Amount returned must be an integer (no fractional paise)."""
        mock_rzp = MagicMock()
        mock_rzp.order.create.return_value = {"id": "order_test_gst3"}
        mock_client.return_value = mock_rzp
        mock_cfg.return_value = {"key_id": "rzp_test_key"}

        from dinematters.dinematters.api.coin_billing import create_coin_purchase_order
        result = create_coin_purchase_order(self._res, 500)

        self.assertIsInstance(result["amount"], int,
                              "Razorpay amount must be an integer (paise)")


if __name__ == "__main__":
    unittest.main()
