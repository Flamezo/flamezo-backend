import frappe

def test_deletion():
    # Find a test restaurant
    restaurant = frappe.db.get_value("Restaurant", {}, "name")
    if not restaurant:
        print("No restaurant found to test with.")
        return
        
    print(f"Using restaurant: {restaurant}")

    # Create test product with nested child tables
    product = frappe.get_doc({
        "doctype": "Menu Product",
        "restaurant": restaurant,
        "product_name": "Test Product Nested Deletion",
        "price": 100,
        "is_vegetarian": 1,
        "calories": 200,
        "customization_questions": [
            {
                "question_id": "test_q1",
                "title": "Test Question",
                "question_type": "single",
                "options": [
                    {
                        "option_id": "test_o1",
                        "title": "Option 1",
                        "price_adjustment": 10
                    }
                ]
            }
        ]
    })
    
    product.insert(ignore_permissions=True)
    product_name = product.name
    
    # In frappe, when we insert, sometimes nested children are not inserted by default 
    # unless there's custom logic. Let's see if the option was created.
    question_name = product.customization_questions[0].name
    options = frappe.get_all("Customization Option", filters={"parent": question_name})
    
    print(f"Options before delete: {len(options)}")
    
    # Delete product
    frappe.delete_doc("Menu Product", product_name, force=True, ignore_permissions=True)
    
    # Check for orphans
    questions = frappe.get_all("Customization Question", filters={"parent": product_name})
    options_after = frappe.get_all("Customization Option", filters={"parent": question_name})
    
    print(f"Questions after delete: {len(questions)}")
    print(f"Options after delete: {len(options_after)}")

    # Clean up orphans if they exist so we don't pollute the db
    if options_after:
        frappe.db.delete("Customization Option", {"parent": question_name})
        frappe.db.commit()
