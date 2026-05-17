import frappe
from flamezo_backend.flamezo.api.legacy import generate_legacy_content

def run_test():
    try:
        frappe.set_user("Administrator")

        res = frappe.get_all("Restaurant", filters={"restaurant_name": ["like", "%unvind%"]}, fields=["name", "restaurant_name"])
        if not res:
            print("Restaurant 'unvind' not found.")
            all_res = frappe.get_all("Restaurant", fields=["name", "restaurant_name"], limit=10)
            print("Available restaurants:")
            for r in all_res:
                print(f"  - {r.restaurant_name} ({r.name})")
            return

        restaurant_id = res[0].name
        restaurant_name = res[0].restaurant_name
        print(f"\nGenerating legacy for: {restaurant_name} ({restaurant_id})\n")

        result = generate_legacy_content(restaurant_id=restaurant_id)

        if result.get("success"):
            data = result.get("data", {})
            print("══════════════════════════════════════════")
            print("             GENERATED OUTPUT")
            print("══════════════════════════════════════════")

            print("\n[ HERO ]")
            print(f"  Title: {data.get('hero', {}).get('title')}")

            print("\n[ CONTENT ]")
            content = data.get("content", {})
            print(f"  Opening : {content.get('openingText')}")
            print(f"  Para 1  : {content.get('paragraph1')}")
            print(f"  Para 2  : {content.get('paragraph2')}")

            print("\n[ TESTIMONIALS ]")
            for i, t in enumerate(data.get("testimonials", []), 1):
                print(f"  {i}. {t['name']} ({t['location']}) ★{t['rating']}")
                print(f"     \"{t['text']}\"")

            print("\n[ MEMBERS ]")
            for m in data.get("members", []):
                print(f"  • {m['name']} — {m['role']}")

            print("\n[ SIGNATURE DISHES ]")
            for d in data.get("signature_dish_names", []):
                print(f"  • {d}")

            print("\n[ FOOTER ]")
            footer = data.get("footer", {})
            print(f"  Title : {footer.get('title')}")
            print(f"  Desc  : {footer.get('description')}")
            cta = footer.get("ctaButton", {})
            print(f"  CTA   : [{cta.get('text')}] → {cta.get('route')}")

            print("\n══════════════════════════════════════════")
            print("         CHARACTER COUNT AUDIT")
            print("══════════════════════════════════════════")
            checks = [
                ("Hero title",       data.get("hero", {}).get("title", ""),          90),
                ("Opening text",     content.get("openingText", ""),                120),
                ("Paragraph 1",      content.get("paragraph1", ""),                 700),
                ("Paragraph 2",      content.get("paragraph2", ""),                 700),
                ("Footer title",     footer.get("title", ""),                        80),
                ("Footer desc",      footer.get("description", ""),                 400),
            ]
            all_pass = True
            for label, text, limit in checks:
                length = len(text)
                status = "✓" if length <= limit else "✗ OVER LIMIT"
                if length > limit:
                    all_pass = False
                print(f"  {status}  {label}: {length}/{limit} chars")

            for i, t in enumerate(data.get("testimonials", []), 1):
                length = len(t.get("text", ""))
                status = "✓" if length <= 280 else "✗ OVER LIMIT"
                if length > 280:
                    all_pass = False
                print(f"  {status}  Testimonial {i}: {length}/280 chars")

            print(f"\n  {'ALL LIMITS PASSED ✓' if all_pass else 'SOME LIMITS EXCEEDED ✗'}")
            print("══════════════════════════════════════════\n")
        else:
            print(f"Generation failed: {result.get('error')}")

    except Exception as e:
        import traceback
        print(f"Error: {str(e)}")
        traceback.print_exc()
