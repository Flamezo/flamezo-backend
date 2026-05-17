from abc import ABC, abstractmethod

class FlamezoOrderStatus:
    """
    Unified Status Engine: Maps all fragmented POS codes to a single language.
    Values MUST match the Order doctype 'status' field options exactly.
    """
    PLACED = "pending_verification"
    ACCEPTED = "Accepted"
    PREPARING = "preparing"
    READY = "ready"
    DISPATCHED = "Dispatched"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class POSProvider(ABC):
    def __init__(self, restaurant_doc):
        self.restaurant = restaurant_doc
        self.settings = {
            "app_key": restaurant_doc.pos_app_key,
            "app_secret": restaurant_doc.get_password("pos_app_secret"),
            "access_token": restaurant_doc.get_password("pos_access_token") if hasattr(restaurant_doc, 'pos_access_token') else None,
            "merchant_id": restaurant_doc.pos_merchant_id
        }

    @abstractmethod
    def sync_menu(self):
        """Fetch and sync menu from POS to Flamezo (Push strategy)"""
        pass

    @abstractmethod
    def pull_menu(self):
        """Fetch and sync menu from POS to Flamezo (Pull strategy)"""
        pass

    @abstractmethod
    def push_order(self, order_doc):
        """Push a confirmed order to POS"""
        pass

    @abstractmethod
    def handle_callback(self, data):
        """Handle status update callbacks from POS"""
        pass

    def map_status(self, raw_status):
        """
        Translate POS-specific status to Flamezo standard status.
        Default implementation returns the raw status.
        """
        return raw_status

def get_pos_provider(restaurant_doc):
    if not restaurant_doc.pos_enabled or not restaurant_doc.pos_provider:
        return None
    
    if restaurant_doc.pos_provider == "Petpooja":
        from flamezo_backend.flamezo.pos.petpooja import PetpoojaProvider
        return PetpoojaProvider(restaurant_doc)
    
    if restaurant_doc.pos_provider == "UrbanPiper":
        from flamezo_backend.flamezo.pos.urbanpiper import UrbanPiperProvider
        return UrbanPiperProvider(restaurant_doc)
    
    if restaurant_doc.pos_provider == "Restroworks":
        from flamezo_backend.flamezo.pos.restroworks import RestroworksProvider
        return RestroworksProvider(restaurant_doc)
    
    return None
