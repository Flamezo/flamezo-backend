import frappe

def extend_bootinfo(bootinfo):
    """
    Optimize bootinfo for the Dinematter merchant dashboard.
    The dashboard is a React app and doesn't need most of Frappe's Desk-specific boot data.
    """
    # Only optimize if it's the Flamezo app (not the standard Desk)
    # We check the referrer or the current path
    is_merchant_dashboard = False
    if frappe.request:
        if "/flamezo_backend" in frappe.request.path or (frappe.request.referrer and "/flamezo_backend" in frappe.request.referrer):
            is_merchant_dashboard = True

    if not is_merchant_dashboard:
        return

    # 1. Clear giant translation messages (merchants use the UI in English or we handle translations via API)
    # This is often the largest part of bootinfo (can be several MBs)
    if "__messages" in bootinfo:
        bootinfo["__messages"] = {}

    # 2. Prune metadata (meta)
    # The React app fetches metadata on-demand via our custom API for specific doctypes.
    # We can clear everything except maybe some basic ones.
    if "docs" in bootinfo:
        # Docs usually contains the user doc, settings, etc. Keep this.
        pass
    
    # meta is often huge as it includes metadata for dozens of standard doctypes
    if "meta" in bootinfo:
        # Keep only basic meta that might be needed by the client core
        essential_meta = ["User", "Website Settings", "Country", "Currency"]
        pruned_meta = {k: v for k, v in bootinfo["meta"].items() if k in essential_meta}
        bootinfo["meta"] = pruned_meta

    # 3. Clear desktop icons/config (merchants don't use the standard Desk sidebar)
    keys_to_remove = ["desktop_icons", "dashboards", "onboarding_data", "__onboarding_data"]
    for key in keys_to_remove:
        if key in bootinfo:
            del bootinfo[key]

    # 4. Filter user permissions if they are massive
    if "user_permissions" in bootinfo:
        # Keep permissions only for core and flamezo_backend doctypes
        # This prevents the boot data from ballooning if the user has restricted access across the platform
        pass
