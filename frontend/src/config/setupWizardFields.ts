/**
 * SETUP WIZARD FIELD GATE — Single source of truth.
 *
 * Rules:
 *  1. Every field on a wizard step doctype must appear in exactly one of:
 *     - alwaysHidden — never shown
 *     - shown        — surfaced to the merchant
 *  2. When a new field is added to Restaurant or Restaurant Config,
 *     add it here explicitly before it appears in the wizard.
 */

export type WizardStepId = 'restaurant' | 'config'

interface StepFieldGate {
  alwaysHidden: string[]
  shown: string[]
}

export const WIZARD_FIELD_GATE: Record<WizardStepId, StepFieldGate> = {
  restaurant: {
    shown: [
      'restaurant_name',
      'owner_name',
      'owner_email',
      'owner_phone',
      'address',
      'city',
      'state',
      'zip_code',
      'country',
      'latitude',
      'longitude',
      'timezone',
      'google_map_url',
      'tables',
      'enable_dine_in',
    ],

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

      // POS
      'pos_provider',
      'pos_enabled',
      'pos_app_key',
      'pos_app_secret',
      'pos_access_token',
      'pos_merchant_id',
      'pos_last_sync_at',
      'pos_sync_status',

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
      'max_delivery_distance',
      'delivery_charge_per_km',
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

      // Feature toggles
      'enable_loyalty',
      'enable_table_booking',
      'enable_banquet_booking',
      'enable_events',
      'enable_offers',
      'enable_coupons',
      'enable_experience_lounge',
      'enable_cart_milestones',
      'cart_milestones',

      // Social / contact
      'google_review_link',
      'instagram_profile_link',
      'facebook_profile_link',
      'whatsapp_phone_number',
      'swiggy_link',
      'zomato_link',
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

export function getHiddenFields(stepId: WizardStepId): string[] {
  return WIZARD_FIELD_GATE[stepId].alwaysHidden
}

export function getShownFields(stepId: WizardStepId): string[] {
  return WIZARD_FIELD_GATE[stepId].shown
}
