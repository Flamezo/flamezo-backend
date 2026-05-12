/**
 * SETUP WIZARD FIELD GATE — Single source of truth.
 *
 * Rules:
 *  1. EVERY field on a wizard step doctype must appear in exactly one of:
 *     - alwaysHidden   → never shown to any plan
 *     - silverOnly     → shown to Silver, hidden from Gold  (rare)
 *     - goldOnly       → shown to Gold, hidden from Silver
 *     - shown          → shown to ALL plans
 *
 *  2. When a new field is added to Restaurant or Restaurant Config,
 *     add it here explicitly before it appears in the wizard.
 *     Nothing flows through automatically.
 *
 *  3. "shown" is the source of truth for what we WANT users to fill in.
 *     The DynamicForm will hide everything in alwaysHidden + plan-filtered lists.
 *
 * To add a new field:
 *   a) Decide which step it belongs to ('restaurant' | 'config')
 *   b) Decide the plan visibility (alwaysHidden / goldOnly / silverOnly / shown)
 *   c) Add it to that list below — DO NOT leave it unlisted.
 */

export type WizardStepId = 'restaurant' | 'config'

interface StepFieldGate {
  /** Fields to hide for ALL plans — system/billing/internal fields */
  alwaysHidden: string[]
  /** Fields shown to Silver only (hidden from Gold) */
  silverOnly: string[]
  /** Fields shown to Gold only (hidden from Silver) */
  goldOnly: string[]
  /** Fields shown to all plans */
  shown: string[]
}

export const WIZARD_FIELD_GATE: Record<WizardStepId, StepFieldGate> = {

  // ─────────────────────────────────────────────────────────────
  // STEP: restaurant  (doctype: Restaurant)
  // ─────────────────────────────────────────────────────────────
  restaurant: {

    shown: [
      // Identity
      'restaurant_name',
      'owner_name',
      'owner_email',
      'owner_phone',
      // Location
      'address',
      'city',
      'state',
      'zip_code',
      'country',
      'latitude',
      'longitude',
      'timezone',
      'google_map_url',
      // Operations
      'tables',
      'enable_dine_in',
    ],

    silverOnly: [],

    goldOnly: [],

    alwaysHidden: [
      // System / internal IDs
      'restaurant_id',
      'company',
      'subdomain',
      'slug',
      'restaurant_config',
      'qr_codes_pdf_url',
      'referral_code',
      'referred_by_restaurant',

      // Plan & billing
      'plan_type',
      'plan_activated_on',
      'plan_changed_by',
      'plan_change_reason',
      'platform_fee_percent',
      'monthly_minimum',
      'billing_status',
      'mandate_status',
      'onboarding_date',
      'is_active',
      'deferred_plan_type',
      'plan_change_date',
      'plan_change_history',
      'max_images_silver',
      'max_images_lite',

      // Revenue / stats
      'total_orders',
      'total_revenue',
      'commission_earned',
      'current_image_count',

      // Wallet / auto-recharge
      'coins_balance',
      'auto_recharge_enabled',
      'auto_recharge_threshold',
      'auto_recharge_amount',
      'daily_auto_recharge_limit',
      'daily_auto_recharge_count',
      'last_auto_recharge_date',
      'enable_floor_recovery',
      'floor_recovery_activated_on',
      'last_floor_recovery_date',

      // AI
      'total_ai_generations',
      'total_ai_cost',
      'recommendation_run',
      'recommendation_run_count',

      // Razorpay
      'razorpay_account_id',
      'razorpay_kyc_status',
      'razorpay_customer_id',
      'razorpay_token_id',
      'razorpay_merchant_key_id',
      'razorpay_merchant_key_secret',
      'razorpay_keys_updated_at',
      'razorpay_keys_updated_by',
      'razorpay_webhook_secret',

      // POS
      'pos_provider',
      'pos_enabled',
      'pos_app_key',
      'pos_app_secret',
      'pos_access_token',
      'pos_merchant_id',
      'pos_last_sync_at',
      'pos_sync_status',

      // Loyalty (managed via Restaurant Config)
      'enable_loyalty',

      // Ordering / delivery (managed via dedicated settings page, not wizard)
      'enable_takeaway',
      'enable_delivery',
      'no_ordering',
      'default_delivery_fee',
      'default_packaging_fee',
      'packaging_fee_type',
      'minimum_order_value',
      'estimated_prep_time',
      'preferred_logistics_provider',
      'flash_store_id',
      'delivery_markup_type',
      'delivery_markup_value',
      'max_delivery_distance',
      'currency',

      // Tax
      'tax_rate',
      'gst_number',

      // Branding assets (managed via Config step)
      'logo',
      'hero_video',
      'description',

      // Google Business
      'google_business_account_id',
      'google_business_location_id',
      'enable_google_sync',
      'google_review_url',
      'google_insights_data',
      'google_refresh_token',

      // Geo (internal)
      'city_latitude',
      'city_longitude',
    ],
  },

  // ─────────────────────────────────────────────────────────────
  // STEP: config  (doctype: Restaurant Config)
  // ─────────────────────────────────────────────────────────────
  config: {

    shown: [
      // Branding
      'tagline',
      'subtitle',
      'description',
      'default_theme',
      'logo',
      'logo_size',
      'hero_video',

      // Color palette
      'color_palette_violet',
      'color_palette_indigo',
      'color_palette_blue',
      'color_palette_green',
      'color_palette_yellow',
      'color_palette_orange',
      'color_palette_red',

      // Layout
      'menu_layout',

      // Feature toggles — BOTH plans
      // Source of truth: feature_gate.py FEATURE_PLAN_MAP + config.py features response
      'enable_loyalty',         // loyalty: ['SILVER', 'GOLD']

      // Social / contact — both plans
      'google_review_link',
      'instagram_profile_link',
      'facebook_profile_link',
      'whatsapp_phone_number',
      'swiggy_link',
      'zomato_link',
    ],

    silverOnly: [],

    goldOnly: [
      // All transactional feature toggles are GOLD-only.
      // Backend proof:
      //   • feature_gate.py: table_booking → ['GOLD'], events/offers/experience_lounge not
      //     in FEATURE_PLAN_MAP but config.py explicitly gates them as plan_type == "GOLD"
      //   • restaurant.py on_submit: sets all these to 0 for SILVER, 1 for GOLD
      'enable_table_booking',       // tableBooking: plan_type == 'GOLD'
      'enable_banquet_booking',     // no API flag but defaults 0 for SILVER
      'enable_events',              // events: plan_type == 'GOLD'
      'enable_offers',              // offers: plan_type == 'GOLD'
      'enable_coupons',             // coupons: ['GOLD'] in FEATURE_PLAN_MAP
      'enable_experience_lounge',   // experience_lounge: plan_type == 'GOLD'
      'enable_cart_milestones',     // enableCartMilestones: plan_type == 'GOLD' (tied to coupons)
      'cart_milestones',            // same — cart milestone data is GOLD-only
    ],

    alwaysHidden: [
      // Internal / system
      'restaurant',
      'restaurant_name',
      'currency',
      'primary_color',
      'apple_touch_icon',
      'verify_my_user',

      // AI Theme Background section — managed via dedicated page
      'section_break_ai_theme_background',
      'column_break_ai_theme_background',
      'menu_theme_background_enabled',
      'menu_theme_paid_until',
      'menu_theme_generation_status',
      'menu_theme_background_active',
      'menu_theme_wallpapers',
      'menu_theme_main_index',
      'menu_theme_selected_items',
      'menu_theme_color_theme',
      'menu_theme_background_preview',
      'menu_theme_background_sources',
      'menu_theme_background_history',
      'menu_theme_last_error',

      // Advanced branding (managed via dedicated page)
      'qr_code',
      'brand_logo',
      'hero_image',
      'menu_theme',
      'custom_css',

      // Internal push tokens
      'merchant_push_tokens',
    ],
  },
}

/**
 * Returns the list of fields to pass to DynamicForm's hideFields prop.
 * Combines alwaysHidden + plan-filtered goldOnly/silverOnly fields.
 */
export function getHiddenFields(stepId: WizardStepId, planType: 'SILVER' | 'GOLD'): string[] {
  const gate = WIZARD_FIELD_GATE[stepId]
  const hidden = [...gate.alwaysHidden]

  if (planType === 'SILVER') {
    hidden.push(...gate.goldOnly)
  }
  if (planType === 'GOLD') {
    hidden.push(...gate.silverOnly)
  }

  return hidden
}
