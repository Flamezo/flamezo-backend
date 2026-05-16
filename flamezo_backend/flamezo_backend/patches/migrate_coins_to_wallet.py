import frappe

def execute():
    # 1. Update existing descriptions in Coin Transaction
    frappe.db.sql("""
        UPDATE `tabCoin Transaction`
        Set description = REPLACE(description, 'Coins', 'Balance')
        WHERE description LIKE '%Coins%'
    """)

    frappe.db.sql("""
        UPDATE `tabCoin Transaction`
        Set description = REPLACE(description, 'Coin', 'Balance')
        WHERE description LIKE '%Coin%'
    """)

    # 2. Update descriptive transaction types if necessary
    # Note: We already updated the Doctype options, but existing records
    # will still have 'Free Coins' as the value in transaction_type.
    # It might be better to leave them as is or update them to 'Wallet Credit'.
    
    frappe.db.sql("""
        UPDATE `tabCoin Transaction`
        SET transaction_type = 'Wallet Credit'
        WHERE transaction_type = 'Free Coins'
    """)

    # 3. Update Razorpay Notes in manual purchase records (if any)
    # This is harder since it's JSON in description sometimes, but better safe.
    
    frappe.db.commit()
