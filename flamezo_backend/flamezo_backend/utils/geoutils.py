import math
import requests
import frappe

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the straight-line distance between two points on Earth using the Haversine formula.
    Returns distance in kilometers.
    """
    if None in [lat1, lon1, lat2, lon2]:
        return 0
    
    try:
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
    except ValueError:
        return 0

    R = 6371.0  # Earth radius in KM

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2)**2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c

def get_osrm_road_distance(lat1, lon1, lat2, lon2):
    """
    Get real road distance using Open Source Routing Machine (OSRM) public API.
    Returns distance in KM or None if fails.
    """
    try:
        # Note: OSRM uses {longitude},{latitude} format
        url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if data.get("code") == "Ok":
            # distance is in meters
            return round(data["routes"][0]["distance"] / 1000.0, 2)
    except Exception as e:
        frappe.log_error(f"OSRM Error: {str(e)}", "GeoUtils OSRM")
    
    return None

def estimate_road_distance(straight_distance, multiplier=1.3):
    """
    Fallback: Apply a circuity factor to estimate actual road distance.
    """
    return straight_distance * multiplier
