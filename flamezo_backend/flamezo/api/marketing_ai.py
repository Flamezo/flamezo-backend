import frappe
from flamezo_backend.flamezo.services.ai.seo_blog import generate_seo_content, VoiceMatcher
from flamezo_backend.flamezo.utils.api_helpers import validate_restaurant_for_api

@frappe.whitelist()
def generate_blog_post(restaurant_id, keyword, title=None, length=1500, style="professional"):
    """
    Generate an SEO-optimized blog post for a restaurant.
    """
    validate_restaurant_for_api(restaurant_id)
    
    # Optional: Fetch restaurant context to provide to AI
    restaurant = frappe.get_doc("Restaurant", restaurant_id)
    context = f"Restaurant Name: {restaurant.restaurant_name}\n"
    if restaurant.description:
        context += f"Description: {restaurant.description}\n"
    
    # You could also fetch recent successful posts to use VoiceMatcher here
    
    return generate_seo_content(
        keyword=keyword,
        title=title,
        length=length,
        style=style,
        context=context
    )

@frappe.whitelist()
def analyze_restaurant_voice(restaurant_id):
    """
    Analyze existing marketing content to create a voice profile.
    """
    validate_restaurant_for_api(restaurant_id)
    
    # Fetch existing content (e.g., from a 'Marketing Content' DocType if it exists)
    # For now, we'll look for any existing blog posts or descriptions
    contents = []
    
    # 1. Get restaurant description
    desc = frappe.db.get_value("Restaurant", restaurant_id, "description")
    if desc: contents.append(desc)
    
    # 2. Get any existing blog posts (assuming a DocType named 'Blog Post' exists)
    # if frappe.db.exists("DocType", "AI Blog Post"):
    #     posts = frappe.get_all("AI Blog Post", filters={"restaurant": restaurant_id}, fields=["content"])
    #     contents.extend([p.content for p in posts if p.content])
    
    matcher = VoiceMatcher()
    profile = matcher.analyze_voice(contents)
    
    return {
        "success": True,
        "profile": profile
    }

@frappe.whitelist(allow_guest=True)
def get_articles(limit=10, offset=0):
    """
    Whitelisted API to fetch published blog posts for the portfolio.
    """
    posts = frappe.get_all("Blog Post", 
        filters={"published": 1},
        fields=["name", "title", "blog_intro", "published_on", "blogger", "blog_category", "meta_description", "meta_title", "route", "_user_tags", "meta_image"],
        limit=limit,
        start=offset,
        order_by="published_on desc"
    )
    # Map _user_tags to tags for frontend consistency (as Array)
    for post in posts:
        raw_tags = post.get("_user_tags", "")
        post["tags"] = [t.strip() for t in raw_tags.split(",")] if raw_tags else []
    return posts

@frappe.whitelist(allow_guest=True)
def get_article_by_slug(slug):
    """
    Whitelisted API to fetch a single blog post by its slug (name).
    """
    if not frappe.db.exists("Blog Post", slug):
        frappe.throw(f"Blog post with slug '{slug}' not found", frappe.DoesNotExistError)
        
    doc = frappe.get_doc("Blog Post", slug)
    if not doc.published:
        frappe.throw("This blog post is not published", frappe.PermissionError)
        
    result = doc.as_dict()
    # ✅ FIX: Map _user_tags to tags as an ARRAY for React compatibility
    raw_tags = doc.get("_user_tags", "")
    result["tags"] = [t.strip() for t in raw_tags.split(",")] if raw_tags else []
    return result
