import frappe


def setup_hostinger_email():
    """
    Sync Hostinger SMTP credentials from Flamezo Settings → Frappe Email Account.
    Only called when hostinger_email or hostinger_password actually changes.
    """
    email_account_name = "Contact Flamezo"
    settings = frappe.get_single("Flamezo Settings")

    email = settings.hostinger_email
    if not email:
        frappe.log_error("Hostinger email not configured in Flamezo Settings", "Email Setup")
        return

    # Read the password stored in Frappe's encrypted __Auth table
    password = settings.get_password("hostinger_password", raise_exception=False)
    if not password:
        frappe.log_error("Hostinger password not set in Flamezo Settings", "Email Setup")
        return

    # Update Email Domain via DB to avoid triggering SMTP validation on every save
    if frappe.db.exists("Email Domain", "flamezo_backend.com"):
        frappe.db.set_value("Email Domain", "flamezo_backend.com", {
            "smtp_server": "smtp.hostinger.com",
            "use_tls": 1,
            "use_ssl_for_outgoing": 0,
            "smtp_port": 587,
        })

    # Create or update the Email Account
    if not frappe.db.exists("Email Account", email_account_name):
        doc = frappe.new_doc("Email Account")
        doc.email_account_name = email_account_name
    else:
        doc = frappe.get_doc("Email Account", email_account_name)

    doc.email_id = email
    doc.smtp_server = "smtp.hostinger.com"
    doc.use_tls = 1
    doc.use_ssl_for_outgoing = 0
    doc.smtp_port = 587
    doc.enable_outgoing = 1
    doc.default_outgoing = 1
    doc.password = password  # Frappe's _save_passwords() will encrypt this on save

    doc.save(ignore_permissions=True)
    frappe.db.commit()


@frappe.whitelist()
def test_email_delivery(recipient="dhyeymdeveloper@gmail.com"):
    """Send a test email and flush the queue immediately."""
    frappe.sendmail(
        recipients=[recipient],
        sender="contact@flamezo_backend.com",
        subject="Flamezo Outbound Test (Final Sync)",
        message="This email confirms complete SMTP transport parity across infrastructure.",
        now=True
    )
    print(f"Successfully attempted outbound test to {recipient}")

