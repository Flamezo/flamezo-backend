# 🎯 Petpooja Sandbox Guide for Integration Testing

## Overview

Petpooja provides a **Sandbox Environment** for testing API calls and webhooks before going
live. You can access the dashboard and test various online order APIs with the Petpooja
platform using this environment.

## 1 ⃣ Accessing the Sandbox

To get started with the Petpooja Sandbox environment, you need to follow these steps:

1. **Obtain your Network IP Address:**
    ○ Visit What is My IP to find your IP address and share it with us to whitelist that IP.
    ○ This IP address will be required to access the dashboard.
2. **Dashboard Login:**
    ○ Use the **ID and Password** sent via email to access the dashboard.
    ○ Dashboard link: Petpooja Developer API

## 2 ⃣ Sandbox Dashboard Components

The dashboard contains the following sections:
● **API Documentation**
● **Configuration**
● **Menu Management**
● **Order Listing**

## 3 ⃣ Configuration Page

Once logged in to the dashboard, the **Configuration** tab allows you to manage authentication
and setup webhook configurations.
**Key Components:**

1. **Authentication Tokens:**
    ○ **App Key** : Used to identify the third-party application.
    ○ **App Secret Key** : Secures communication between the third-party and Petpooja.
    ○ **Access Token** : Temporary credentials for performing API calls.


2. **Note:** These tokens are for **Sandbox** use. For **Production** environments, different
    tokens will be provided.
3. **Webhook Configuration:**
    ○ **Base URL** : The common URL used for all webhooks (e.g.,
       https://developerapi.petpooja.com/).
          ■ Example: Menu Sharing Endpoint will be
             https://developerapi.petpooja.com/pushmenu.
    ○ **Webhook URL for Testing** : The base URL entered here will be used for all
       webhooks.
4. **Optional Client Configuration:**
    ○ **Client Authorization** : (If required by the third party).
    ○ **Headers Configuration** : Some third-party apps may require headers for
       authorization in API requests.
5. **Petpooja API Endpoints for Testing:**
    ○ **Save Order API** : Relays order information to Petpooja.
    ○ **Update Order Status API** : Allows you to cancel orders.
    ○ **Rider Info Webhook** : Sends rider info (if the third-party is managing delivery).


## 4 ⃣ Menu Management Section

This section lets you test and manage the menu items. It contains two main sub-sections:

1. **Menu List:**
    ○ Use this section to trigger the **Push Menu API** by clicking the menu trigger
       button.
    ○ It sends the **catalogue data** to the **Menu Sharing Endpoint**.


2. **Menu Item On/Off:**
    ○ Test the item stock status (in-stock or out-of-stock) using the **Item On/Off**
       **Webhook**.
    ○ You can also test **Store On/Off Webhooks** to manage your store's availability.


### 5 ⃣ Order Listing Section

This section allows you to test order management by viewing relayed orders. You can also
perform the following actions:

1. **Test the Order Relay API** : After sending an order, check if it appears in the **Order**
    **Listing** page.
2. **Test Callback URL** :
    ○ Accept orders, mark food as ready, or reject orders via the callback URL.
3. **Rider Information API** (If you manage deliveries):
    ○ Send rider information to Petpooja for dispatch and delivery calls.
4.

### 6 ⃣ Example Workflow

Here’s a step-by-step guide for testing the integration:

1. **Step 1: Login to the Dashboard**
    ○ Use the credentials provided in the email to log into the sandbox environment.
2. **Step 2: Configure Webhooks**
    ○ Set the **Base URL** for all your webhooks and configure any optional authorization
       or header settings if needed.
3. **Step 3: Test API Calls**
    ○ Use the **API Documentation** to test API calls like **Save Order** , **Update Order**
       **Status** , and **Rider Info Webhook**.
4. **Step 4: Push Menu**
    ○ Use the **Menu Management** section to push your menu to Petpooja’s system.
    ○ Test stock availability with **Item On/Off Webhooks**.
5. **Step 5: Verify Orders**
    ○ Place sample orders and verify if they appear in the **Order Listing** section.
    ○ Test callback actions such as order acceptance and updating order status.


### 7 ⃣ Notes

```
● Sandbox IP Access:
○ The sandbox is restricted to the IP address you provide. Ensure that your IP is
registered to access the dashboard.
● Use Demo Tokens for Testing:
○ The provided App Key, App Secret , and Access Token are only valid for
sandbox use. Separate tokens will be issued for the live environment once
integration is successful.
```
### 8 ⃣ Additional Resources

If you need further assistance or guidance, refer to the following resources:
● **Petpooja API Documentation** : Full API reference for all endpoints.
● **Support** : For troubleshooting and questions, contact support at **malvi@petpooja.com**.
This guide should provide you with everything needed to test and configure Petpooja’s APIs. By
using the sandbox, you can safely test and debug your integration before going live.
Feel free to reach out if you need further clarifications or if you'd like to discuss anything else!


