import frappe
from abc import ABC, abstractmethod

class LogisticsProvider(ABC):
    """
    Abstract base class for all logistics providers.
    All methods should be implemented by concrete providers (Borzo, Flash).
    """
    
    @abstractmethod
    def calculate_quote(self, restaurant, order_details):
        """
        Calculates delivery cost and ETA.
        Args:
            restaurant: Restaurant document
            order_details: dict with {address, latitude, longitude, items, total}
        Returns:
            dict: {success: bool, delivery_fee: float, eta_mins: int, error: str}
        """
        pass

    @abstractmethod
    def create_order(self, restaurant, order):
        """
        Places a real delivery order with the provider.
        Args:
            restaurant: Restaurant document
            order: Order document
        Returns:
            dict: {success: bool, delivery_id: str, status: str, tracking_url: str, delivery_fee: float}
        """
        pass

    @abstractmethod
    def cancel_order(self, delivery_id):
        """
        Cancels an existing delivery.
        """
        pass

    @abstractmethod
    def track_order(self, delivery_id):
        """
        Polls the provider for the current status and rider details of a delivery.
        Args:
            delivery_id: The provider's unique task/order ID.
        Returns:
            dict: {success: bool, status: str, rider_name: str, rider_phone: str, tracking_url: str, lat: float, lng: float}
        """
        pass

    @abstractmethod
    def verify_webhook(self, data, signature):
        """
        Verifies the authenticity of a webhook request.
        """
        pass
