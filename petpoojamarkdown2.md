## API Guide for Placing Orders on Petpooja.

##### This guide will help you integrate and send orders to Petpooja in a simple, easy-to-follow

##### manner.

# 1 ⃣ Authentication & Setup

##### 👉 Think of this as your login key. Every request must include the following credentials:

##### 👉 You will receive this details from the sandbox account “Configuration” section.

```
Field Description Example Required?
```
```
app_key Unique restaurant
identifier
```
```
d89a6f5b4c12345c78a90d12abcd5678 ✅ Yes
```
```
app_secret Secure key for safe
communication
```
```
a1b2c3d4e5f67890g1h2i3j4k5l6m7n8o9p0 ✅ Yes
```
```
access_token Temporary pass to send
orders
```
```
abcd1234efgh5678ijkl9012mnop3456qrst7890 ✅ Yes
```

# 2 ⃣ Restaurant Information

##### 👉 Restaurant’s basic details.

##### 👉 You are required to provide the Menu sharing code received from the menu payload as a

##### “restID”, or alternatively, you may use the alphanumeric code provided by Petpooja.

```
Field Description Example Required?
```
```
res_name Name of the
restaurant
```
```
XYZ Diner ❌ No
```
```
address Restaurant location 123, Main Street, Mumbai ❌ No
```
```
contact_information Phone number +91-9876543210 ❌ No
```
```
restID Unique Petpooja ID PP12345XYZ ✅ Yes
```
# 3 ⃣ Customer Information

##### 👉 Details about the customer placing the order.

```
Field Description Example Required?
```
```
name Name of the person ordering John Doe ✅ Yes
```
```
phone Contact number (10-digit) 9876543210 ❌ No
```
```
email Customer email john@example.com ❌ No
```
```
address Delivery location 456, Apartment, Delhi ✅ Yes
```
```
latitude GPS coordinates 28.7041 ❌ No
```
```
longitude GPS coordinates 77.1025 ❌ No
```

# 4 ⃣ Order Details

##### 👉 What’s being ordered?

```
Field Description Example Required?
```
```
orderID Unique order reference ORD9876543210 ✅ Yes
```
```
preorder_date Order date (YYYY-MM-DD) 2025-02-15 ✅ Yes
```
```
preorder_time Order time (HH:MM:SS) 14:30:00 ✅ Yes
```
```
advanced_order Placed order is advanced or not. “Y” or “”N” ✅ Yes
```
```
order_type Type of order: H = Home Delivery, P = Parcel,
D = Dine-in
```
```
H ✅ Yes
```
```
total Total price including GST if GST liability is of
the Restaurant. Total = Item Final Price [-
Order level Discount If Any] + GST [if liable
by restaurant] + Packing Charges.]
The "Total" should only include the amount
due to the restaurant.
```
```
500.00 ✅ Yes
```
```
discount_total Discount applied to order. 10% [P] , 100 [F] ❌ No
```
```
discount_type Discount type either Percentage or Fixed “F” or “P” ❌ No
```
```
tax_total Total tax on order. 50.00 ✅ Yes
```
```
description Special instructions Extra spicy, no onion ❌ No
```
```
created_on
```
```
Order creation date/time.
(yyyy-mm-dd H:i:s) 2025-02-15^ 14:30:^
```
```
✅ Yes
```

```
dc_tax_percenta
ge
```
```
Tax percentage applied on the delivery
charges. 5
```
```
✅ Yes
```
```
pc_tax_percenta
ge
```
```
Tax percentage applied on the packing
charge 5
```
```
✅ Yes
```
# 5 ⃣ Payment & Delivery Details

##### 👉 How will the payment and delivery happen?

```
Field Description Example Required?
```
```
payment_type COD = Cash, CARD = Card, ONLINE = Online COD ✅ Yes
```
```
delivery_charges Charges for delivery. 50.00 ❌ No
```
```
urgent_order Is this an urgent order? (true / false) true ❌ No
```
```
urgent_time[Urgent
Order Time]
```
```
If urgent, specify prep time in minutes 30 ❌ No
```
```
enable_delivery 0 = Third-party Rider, 1 = Restaurant Rider 1 ✅ Yes
```

# 6 ⃣ Special Instructions & Callbacks

##### 👉 Additional info for smooth operation.

```
Field Description Example Required?
```
```
callback_url URL to receive order
updates
```
```
https://yourdomain.com/order-status ✅ Yes
```
```
packing_charges Charges for packaging 20.00 ❌ No
```
```
service_charge Service fee applied to
order
```
```
30.00 ❌ No
```
```
OTP for Pickup Verification code for
order pickup
```
```
1234 ❌ No
```
# 7 ⃣ Order Items (Menu Details)

##### 👉 What items are included in the order?

### 📌 Order Items Example: [Refer the “OrderItem” Object from Save Order API.]

"order_items": [
{

"id": "101",
"name": "Margherita Pizza",

"tax_inclusive": true,
"item_discount": "",

"price": "250.00",
"final_price": "250",

"quantity": "2",
"gst_liability": "restaurant",
"item_tax": [
{
"id": "11213", "name": "CGST",
"tax_percentage": "2.5",


```
"amount": "3.15"
},
{
"id": "20375", "name":
"SGST", "tax_percentage": "2.5",
"amount": "3.15"
}
]
```
"variation_name": "",
"variation_id": "",

"addon_items": [
{

"id": "201",
"name": "Extra Cheese",

"price": "50.00",
"quantity": "1"
}

]
}

]

```
Field Description Example Required?
```
```
Item ID : “ID” Unique ID for item received from
Menu Push Payload.
```
```
101 ✅ Yes
```
```
name Name of the dish Margherita Pizza ✅ Yes
```
```
price Price of one unit. [Price = Item unit
price + Add Ons Price if any.]
```
```
250.00 ✅ Yes
```
```
final_price Item Price - Item level discount if any. 250.00 ✅ Yes
```
```
quantity How many units? 2 ✅ Yes
```
```
gst_liability Who pays tax? (vendor / restaurant) restaurant ✅ Yes
```
```
AddonItem Any extra add-ons? Extra Cheese ❌ No
```
```
variation_id Unique ID for variant received from
Menu Push Payload.
```
```
110 ❌ No
```

```
variation_name Half Dish or Full Dish. Half Dish ❌ No
```
```
item_tax Tax bifurcation at item level : CGST &
SGST.
```
###### CGST : 12.

###### SGST : 12.

```
✅ Yes
```
```
tax_inclusive true/false. This is required in case the
item amount is inclusive of tax.
```
```
True/false ✅ Yes
```
```
tax_percentage Percentage tax applied on the item. 2.5 ✅ Yes
```
# 8 ⃣ Tax & Discounts

👉 **Breakdown of all applied taxes and discounts.**

👉 **For discounts you have to avoid “discount” object from the order payload. Please use two keys:
discount type and discount total from the “Order” object.**

#### 📌 Example Tax Structure

"tax_details": [

{
"id": "301",

"title": "CGST",
"type": "P",
"price": "9%",

"tax": "45.00"
"restaurant_liable_amt": "0.00"

},
{

"id": "302",
"title": "SGST",

"type": "P",
"price": "9%",


"tax": "45.00"

"restaurant_liable_amt": "0.00"
}
]

```
Field Description Example Required?
```
```
Tax ID : “id” Unique tax identifier 301 ✅ Yes
```
```
Tax Title : “title” Type of tax (CGST, SGST) CGST ✅ Yes
```
```
Type : “type” Percentage (P) or Fixed (F) P ✅ Yes
```
```
Price Tax percentage 9% or 2.5% ✅ Yes
```
```
Tax Amount : “tax” Tax amount applied 45.00 ✅ Yes
```
```
Restaurant_liable_amt GST amount which is liable
to the restaurant.
```
```
45.00 ✅ Yes
```
## 💡 How to Use This API?

##### 🔹 Step 1: Gather restaurant, customer, and order details.

##### 🔹 Step 2: Format data using the save order API schema.

##### 🔹 Step 3: Send a POST request to

##### https://qle1yy2ydc.execute-api.ap-southeast-1.amazonaws.com/V1/save_order

##### 🔹 Step 4: Receive confirmation & track via Callback URL.


## 🚀 Need Help?

##### If you face any issues, feel free to contact malvi.vaghela@petpooja.com ,

### rohan.sakhrani@petpooja.com or refer to our API reference documentation.


