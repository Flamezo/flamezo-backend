import frappe
from pydantic import BaseModel, Field
from typing import List
from .base import get_openai_client, handle_ai_error
import logging
import re

logger = logging.getLogger(__name__)


# ─── Pydantic Schema ──────────────────────────────────────────────────────────

class CtaButton(BaseModel):
    text: str = Field(
        description="Call-to-action button label. Max 40 chars. E.g. 'Explore Our Menu', 'Reserve Your Table'.",
        max_length=40
    )
    route: str = Field(
        description="Frontend route. Always '/main-menu'.",
        max_length=50
    )

class HeroSection(BaseModel):
    title: str = Field(
        description=(
            "Hero headline — the single most evocative sentence about this restaurant. "
            "Should feel like a luxury magazine cover line, not a tagline. Max 90 chars."
        ),
        max_length=90
    )

class ContentSection(BaseModel):
    openingText: str = Field(
        description=(
            "One powerful opening sentence (no more than 120 chars) that captures the soul of "
            "this place. Should make someone lean in and read more."
        ),
        max_length=120
    )
    paragraph1: str = Field(
        description=(
            "Brand story paragraph 1 (max 700 chars). Describe the atmosphere, the philosophy, "
            "the founder's vision. Use sensory language. Name the city, the vibe, the feeling. "
            "Do NOT start with 'Welcome to'. Make it feel written by a journalist, not a marketer."
        ),
        max_length=700
    )
    paragraph2: str = Field(
        description=(
            "Brand story paragraph 2 (max 700 chars). Shift focus to the food & drink craft. "
            "Mention 2-3 specific signature items by name. Close with an emotional hook about "
            "why guests keep coming back."
        ),
        max_length=700
    )

class FooterSection(BaseModel):
    title: str = Field(
        description="Footer headline. An inviting, warm closing line. Max 80 chars.",
        max_length=80
    )
    description: str = Field(
        description=(
            "Footer body text (max 400 chars). One final invitation. Should feel personal and "
            "genuine, not generic. Reference the restaurant name and city."
        ),
        max_length=400
    )
    ctaButton: CtaButton

class Testimonial(BaseModel):
    name: str = Field(
        description="Realistic Indian full name. Max 40 chars. Vary by gender and region.",
        max_length=40
    )
    location: str = Field(
        description="Indian city, e.g. 'Surat, Gujarat' or 'Mumbai, Maharashtra'. Max 40 chars.",
        max_length=40
    )
    rating: int = Field(description="Always 5.", ge=5, le=5)
    text: str = Field(
        description=(
            "Authentic testimonial (max 280 chars). Each testimonial must focus on a DIFFERENT "
            "aspect: one about the atmosphere, one about a specific dish, one about the coffee, "
            "one about working there, one about coming with friends. Never generic. "
            "Mention specific items or moments."
        ),
        max_length=280
    )

class Member(BaseModel):
    name: str = Field(
        description="Person's full name. Max 50 chars.",
        max_length=50
    )
    role: str = Field(
        description="Their role. E.g. 'Founder & Visionary', 'Head Barista', 'Executive Chef'. Max 50 chars.",
        max_length=50
    )

class LegacyGenerationResult(BaseModel):
    hero: HeroSection
    content: ContentSection
    footer: FooterSection
    testimonials: List[Testimonial] = Field(
        description="Exactly 4 testimonials, each covering a distinct visit occasion."
    )
    members: List[Member] = Field(
        description=(
            "Exactly 1 entry for the restaurant owner/founder. "
            "Use the owner name provided in the profile. "
            "Assign a premium role title like 'Founder & Visionary', 'Proprietor', or 'Head Chef & Founder'."
        )
    )
    signature_dish_names: List[str] = Field(
        description=(
            "Exactly 3 dish names chosen from the menu list provided. "
            "Choose the most iconic, photogenic, or brand-defining items. "
            "Return the EXACT product_name string as given in the menu — no paraphrasing."
        )
    )


# ─── Generator ────────────────────────────────────────────────────────────────

class LegacyGenerator:
    """Generates 10/10 Legacy page content for Flamezo restaurants."""

    def __init__(self):
        self.client = get_openai_client()
        self.model = "gpt-4o"

    def generate_legacy_text(self, restaurant_info: dict, dishes: list) -> dict:
        system_prompt = self._get_system_prompt(restaurant_info)
        user_prompt = self._build_user_prompt(restaurant_info, dishes)

        logger.info(f"Generating Legacy content for: {restaurant_info.get('restaurant_name')}")
        logger.debug(f"User prompt:\n{user_prompt}")

        response = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format=LegacyGenerationResult,
            temperature=0.75
        )

        result = response.choices[0].message.parsed
        if not result:
            raise ValueError("OpenAI returned empty or unparseable content.")

        return result.model_dump()

    def _get_system_prompt(self, restaurant_info: dict) -> str:
        cuisine_identity = restaurant_info.get("cuisine_identity", "café")
        city = restaurant_info.get("city", "India")

        return f"""You are a world-class hospitality copywriter and SEO strategist — the kind hired by Soho House, Blue Tokai, and Smoke House Deli to tell their stories and rank on Google.

Your task: write the "Legacy" page content for a {cuisine_identity} in {city}, India.
This content must BOTH rank on Google AND make people want to share it on Instagram and WhatsApp.

VOICE & TONE:
- Premium but warm. Think: luxury lifestyle magazine meets neighbourhood love letter.
- Specific, not generic. Use real dish names. Name the city. Paint a picture.
- Avoid ALL clichés: "culinary journey", "symphony of flavours", "gastronomic experience", "nestled in the heart of", "beacon of".
- Write like a journalist who has actually eaten there, not a marketing bot.
- Every sentence must earn its place.

SEO RULES (apply to ALL text fields):
- Naturally weave in high-intent local search phrases people actually type:
  "best café in {city}", "{city} coffee shop", "cafés in {city} for work", "best places to eat in {city}"
- Use the restaurant name early in hero title and paragraph 1 — Google weights first occurrences.
- Paragraph 2 should include at least 2 specific dish names — long-tail food searches ("best hazelnut frappe {city}") drive real traffic.
- Footer description should include city name + a call-to-action phrase like "visit us in {city}" or "find us in {city}" — these appear in rich snippets.
- Testimonials: location field should always include city + state (e.g. "Surat, Gujarat") — helps local pack signals.
- Keep sentences short and scannable — Google rewards low bounce rate; people skim.

VIRALITY RULES:
- The hero title must be instantly shareable — the kind of line someone screenshots for their story.
- Opening text must create FOMO. Someone reading it on their phone should think "I need to go here."
- Testimonials must feel real enough that the subject could have actually written them — not like AI wrote them.
- Paragraph 2's closing line should be emotionally resonant — the kind of line people quote in a review.

STRUCTURE RULES:
- Hero title: one iconic, shareable line with the restaurant name and city.
- Opening text: first sentence hook. Short. Punchy. Creates desire and FOMO.
- Paragraph 1: The place — atmosphere, founder intent, who it's for. SEO-optimised for local search.
- Paragraph 2: The food & drink — craft, 2-3 specific dishes by name, why people return. SEO-optimised for food search.
- Testimonials: 4 distinct voices, each tied to a different reason to visit.
  Guest 1 → the atmosphere/vibe
  Guest 2 → a specific food item
  Guest 3 → the coffee/beverages
  Guest 4 → work-from-café or regular visit habit
- Footer: A personal, warm closing with city name and restaurant name for local SEO. Not a sales pitch. An invitation.

CONSTRAINTS (HARD LIMITS — NEVER EXCEED):
- Hero title: 90 chars
- Opening text: 120 chars
- Paragraph 1: 700 chars
- Paragraph 2: 700 chars
- Each testimonial: 280 chars
- Footer title: 80 chars
- Footer description: 400 chars

Always return the exact JSON schema structure. No markdown. No extra text."""

    def _build_user_prompt(self, restaurant_info: dict, dishes: list) -> str:
        name = restaurant_info.get("restaurant_name", "")
        owner = restaurant_info.get("owner_name", "")
        city = restaurant_info.get("city", "")
        state = restaurant_info.get("state", "")
        description = restaurant_info.get("description_clean", "")
        cuisine_identity = restaurant_info.get("cuisine_identity", "café")
        categories = restaurant_info.get("categories", [])

        lines = ["═══ RESTAURANT PROFILE ═══"]
        lines.append(f"Name: {name}")
        if owner:
            lines.append(f"Founder/Owner: {owner}")
        if city:
            lines.append(f"Location: {city}{', ' + state if state else ''}, India")
        lines.append(f"Type: {cuisine_identity}")
        if categories:
            lines.append(f"Menu Categories: {', '.join(categories)}")
        if description:
            lines.append(f"\nBrand Story (from owner):\n{description}")

        lines.append("\n═══ MENU HIGHLIGHTS (choose 3 signature dishes from this list) ═══")
        # Group by category for better signal
        by_category: dict = {}
        for dish in dishes:
            cat = dish.get("item_group", "Other")
            by_category.setdefault(cat, []).append(dish)

        for cat, cat_dishes in by_category.items():
            lines.append(f"\n[{cat}]")
            for dish in cat_dishes[:4]:  # max 4 per category
                desc = (dish.get("description") or "").strip()
                desc_part = f" — {desc}" if desc else ""
                lines.append(f"  • {dish.get('item_name')}{desc_part}")

        lines.append(
            f"\n═══ YOUR TASK ═══\n"
            f"Write the full Legacy page for {name}. "
            f"Pick the 3 most iconic dishes from the menu above (use exact product names). "
            f"Create 4 testimonials from distinct guest personas. "
            f"Make it feel like this restaurant truly deserves to be remembered."
        )

        return "\n".join(lines)


# ─── Description Cleaner ──────────────────────────────────────────────────────

def clean_description(raw: str, max_chars: int = 500) -> str:
    """
    Deduplicate and truncate a restaurant description.
    Some descriptions are copy-pasted multiple times in the DB.
    """
    if not raw:
        return ""

    # Split into sentences, deduplicate preserving order
    sentences = re.split(r'(?<=[.!?])\s+', raw.strip())
    seen = set()
    unique = []
    for s in sentences:
        normalized = re.sub(r'\s+', ' ', s).strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(s.strip())

    clean = " ".join(unique)

    # Hard truncate at word boundary
    if len(clean) > max_chars:
        clean = clean[:max_chars].rsplit(' ', 1)[0] + "…"

    return clean


def infer_cuisine_identity(categories: list) -> str:
    """
    Infer a concise restaurant type label from menu category names.
    Used to give GPT strong context about what kind of venue this is.
    """
    cats_lower = " ".join(categories).lower()

    if any(k in cats_lower for k in ["frappe", "cold brew", "espresso", "latte", "matcha", "manual brew"]):
        if any(k in cats_lower for k in ["pizza", "pasta", "sushi", "mains", "small plates"]):
            return "specialty café with an all-day dining menu"
        return "specialty coffee café"
    if any(k in cats_lower for k in ["biryani", "curry", "dal", "roti"]):
        return "Indian restaurant"
    if any(k in cats_lower for k in ["sushi", "ramen", "dimsum"]):
        return "Asian cuisine restaurant"
    if any(k in cats_lower for k in ["steak", "grill", "bbq"]):
        return "grill and steakhouse"
    if any(k in cats_lower for k in ["pizza", "pasta", "risotto"]):
        return "Italian restaurant"
    if any(k in cats_lower for k in ["burger", "fries", "wings"]):
        return "casual dining restaurant"
    return "restaurant"
