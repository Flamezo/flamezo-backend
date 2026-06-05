-- Migration: Remove legacy plan_type column and set default platform fee
-- Run this script after updating the DocType schema.

-- Ensure any existing rows have platform_fee_percent set to 3 if not already set
UPDATE `tabRestaurant`
SET `platform_fee_percent` = 3
WHERE (`platform_fee_percent` IS NULL OR `platform_fee_percent` = 0);

-- Drop the legacy plan_type column
ALTER TABLE `tabRestaurant`
DROP COLUMN `plan_type`;
