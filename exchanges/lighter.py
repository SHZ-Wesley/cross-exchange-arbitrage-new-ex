import time
import logging
from decimal import Decimal
from lighter.lighter_client import Client
from lighter.constants import ORDER_TYPE_LIMIT, ORDER_SIDE_BUY, ORDER_SIDE_SELL

class LighterClient:
    def __init__(self, api_key, private_key, api_key_index, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        
        # 初始化 Lighter SDK Client
        self.client = Client(
            api_key=api_key,
            private_key=private_key,
            api_key_index=int(api_key_index)
        )
        self.logger.info("Lighter client initialized")

    async def get_order_book(self, market_id):
        pass

    async def place_order(self, market_id, side, size, price, order_type='limit'):
        try:
            l_side = ORDER_SIDE_BUY if side.lower() == 'buy' else ORDER_SIDE_SELL
            
            # Lighter SDK 为同步调用
            order = self.client.create_order(
                market_id=market_id,
                order_type=ORDER_TYPE_LIMIT,
                side=l_side,
                amount=float(size),
                price=float(price)
            )
            self.logger.info(f"Lighter Order Placed: {order}")
            return order
        except Exception as e:
            self.logger.error(f"Lighter Place Order Error: {e}")
            return None

    async def cancel_order(self, order_id):
        try:
            res = self.client.cancel_order(int(order_id))
            self.logger.info(f"Lighter Order Cancelled: {res}")
            return res
        except Exception as e:
            self.logger.error(f"Lighter Cancel Error: {e}")
            return None
