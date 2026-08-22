# Copyright (c) 2026, Flamezo and contributors
# For license information, please see license.txt

"""
Unified geo engine — single source of truth for distance math and
location-based ranking across Discovery, Chills, Crowd and Clubs.

Everything on the app is "nearest wins": a location match beats a
preference match, with a hard cutoff past MAX_RADIUS_KM. Every feed
should import from here instead of hand-rolling haversine again.
"""

import math

# Anything farther than this never outranks a nearer, weaker match —
# distance is a hard cutoff before it's a weighted score.
MAX_RADIUS_KM = 25.0

# Weights for the shared ranking formula. Location dominates; preference
# and engagement only break ties within "near enough".
WEIGHT_LOCATION = 0.55
WEIGHT_PREFERENCE = 0.30
WEIGHT_ENGAGEMENT = 0.15

# Score assigned when either side has no coordinates at all — neutral,
# neither boosted nor buried, matches the existing Chills convention.
NO_GPS_SCORE = 0.5


def haversine_km(lat1, lon1, lat2, lon2):
	"""Great-circle distance in km between two lat/lon points."""
	R = 6371.0
	d_lat = math.radians(lat2 - lat1)
	d_lon = math.radians(lon2 - lon1)
	a = (
		math.sin(d_lat / 2) ** 2
		+ math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
	)
	return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def location_score(distance_km, max_km=MAX_RADIUS_KM):
	"""Linear decay 1.0 (right here) -> 0.0 (at max_km or beyond).

	None distance (no GPS on either side) returns NO_GPS_SCORE so
	un-located content isn't buried, just deprioritized vs a real match.
	"""
	if distance_km is None:
		return NO_GPS_SCORE
	if distance_km <= 0:
		return 1.0
	if distance_km >= max_km:
		return 0.0
	return 1.0 - (distance_km / max_km)


def bbox_deltas(lat, radius_km):
	"""lat/lon deltas for a cheap SQL BETWEEN pre-filter before haversine sort."""
	lat_delta = radius_km / 111.0
	lon_delta = radius_km / (111.0 * math.cos(math.radians(lat))) if lat else lat_delta
	return lat_delta, lon_delta


def blended_score(
	distance_km,
	preference_score=None,
	engagement_score=None,
	max_km=MAX_RADIUS_KM,
	w_location=WEIGHT_LOCATION,
	w_preference=WEIGHT_PREFERENCE,
	w_engagement=WEIGHT_ENGAGEMENT,
):
	"""Shared ranking formula for every location-aware feed.

	distance_km beyond max_km is a hard cutoff — caller should exclude it
	before calling this (this function still scores it 0 either way).
	preference_score / engagement_score default to a neutral 0.5 when a
	feed doesn't track them yet, so location still carries the ranking.
	"""
	loc = location_score(distance_km, max_km)
	pref = 0.5 if preference_score is None else preference_score
	eng = 0.5 if engagement_score is None else engagement_score
	return (w_location * loc) + (w_preference * pref) + (w_engagement * eng)


def within_radius(distance_km, radius_km):
	"""True if distance_km is known and within radius_km. None distance passes
	(un-located content isn't hard-excluded, only deprioritized by score)."""
	if distance_km is None:
		return True
	return distance_km <= radius_km
