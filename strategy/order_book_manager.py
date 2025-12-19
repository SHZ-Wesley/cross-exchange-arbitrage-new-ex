from decimal import Decimal
import logging

class OrderBookManager:
    def __init__(self, logger=None):
        self.extended_bbo = {"bid": None, "ask": None}
        self.lighter_bbo = {"bid": None, "ask": None}
        self.edgex_bbo = {"bid": None, "ask": None}
        self.logger = logger or logging.getLogger(__name__)

    @property
    def extended_order_book_ready(self):
        return self.extended_bbo["bid"] is not None and self.extended_bbo["ask"] is not None

    @property
    def lighter_order_book_ready(self):
        return self.lighter_bbo["bid"] is not None and self.lighter_bbo["ask"] is not None

    @property
    def edgex_order_book_ready(self):
        return self.edgex_bbo["bid"] is not None and self.edgex_bbo["ask"] is not None

    def _to_decimal(self, value):
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except:
            return None

    def update_extended_bbo(self, bid, ask):
        try:
            self.extended_bbo["bid"] = self._to_decimal(bid)
            self.extended_bbo["ask"] = self._to_decimal(ask)
        except Exception:
            pass

    def update_lighter_bbo(self, bid, ask):
        try:
            self.lighter_bbo["bid"] = self._to_decimal(bid)
            self.lighter_bbo["ask"] = self._to_decimal(ask)
        except Exception:
            pass

    def update_edgex_bbo(self, bid, ask):
        try:
            self.edgex_bbo["bid"] = self._to_decimal(bid)
            self.edgex_bbo["ask"] = self._to_decimal(ask)
        except Exception:
            pass

    def get_extended_bbo(self):
        return self.extended_bbo["bid"], self.extended_bbo["ask"]

    def get_lighter_bbo(self):
        return self.lighter_bbo["bid"], self.lighter_bbo["ask"]

    def get_edgex_bbo(self):
        return self.edgex_bbo["bid"], self.edgex_bbo["ask"]
