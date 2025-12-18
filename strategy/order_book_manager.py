from decimal import Decimal
import logging

class OrderBookManager:
    """
    Manages order book data for Lighter, EdgeX, and Extended.
    """
    def __init__(self, logger):
        self.logger = logger
        
        # Lighter state
        self.lighter_best_bid = None
        self.lighter_best_ask = None
        self.lighter_order_book_ready = False
        
        # EdgeX state
        self.edgex_best_bid = None
        self.edgex_best_ask = None
        self.edgex_order_book_ready = False

        # Extended state (New)
        self.extended_best_bid = None
        self.extended_best_ask = None
        self.extended_order_book_ready = False

    def update_lighter_bbo(self, best_bid: Decimal, best_ask: Decimal):
        self.lighter_best_bid = best_bid
        self.lighter_best_ask = best_ask
        self.lighter_order_book_ready = True

    def update_edgex_bbo(self, best_bid: Decimal, best_ask: Decimal):
        self.edgex_best_bid = best_bid
        self.edgex_best_ask = best_ask
        self.edgex_order_book_ready = True

    def update_extended_bbo(self, best_bid: Decimal, best_ask: Decimal):
        """Update Extended BBO data."""
        self.extended_best_bid = best_bid
        self.extended_best_ask = best_ask
        self.extended_order_book_ready = True

    def get_lighter_bbo(self):
        return self.lighter_best_bid, self.lighter_best_ask

    def get_edgex_bbo(self):
        return self.edgex_best_bid, self.edgex_best_ask

    def get_extended_bbo(self):
        """Get Extended Best Bid and Ask."""
        return self.extended_best_bid, self.extended_best_ask
