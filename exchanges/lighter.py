import logging
from lighter.signer_client import SignerClient
from lighter.constants import ORDER_TYPE_LIMIT, ORDER_SIDE_BUY, ORDER_SIDE_SELL

from exchanges.base import OrderResult

class LighterClient:
    def __init__(self, api_key, private_key, api_key_index, logger=None, account_index=0):
        self.logger = logger or logging.getLogger(__name__)
        
        # 初始化 Lighter SDK SignerClient
        self.client = SignerClient(
            url="https://mainnet.zklighter.elliot.ai",
            private_key=private_key,
            account_index=int(account_index),
            api_key_index=int(api_key_index),
        )
        self.logger.info("Lighter client initialized")

    async def get_order_book(self, market_id):
        pass

    async def place_order(self, market_id, side, size, price, order_type='limit'):
        try:
            l_side = ORDER_SIDE_BUY if side.lower() == 'buy' else ORDER_SIDE_SELL
            
            order = await self.client.create_limit_order(
                market_id=int(market_id),
                side=l_side,
                amount=float(size),
                price=float(price),
                order_type=ORDER_TYPE_LIMIT,
            )
            self.logger.info(f"Lighter Order Placed: {order}")

            order_id = order.get('id') if isinstance(order, dict) else str(order)

            return OrderResult(success=True, order_id=order_id)
        except Exception as e:
            self.logger.error(f"Lighter Place Order Error: {e}")
            return OrderResult(success=False, error_message=str(e))

    async def cancel_order(self, order_id):
        try:
            res = await self.client.cancel_order(int(order_id))
            self.logger.info(f"Lighter Order Cancelled: {res}")
            return OrderResult(success=True)
        except Exception as e:
            self.logger.error(f"Lighter Cancel Error: {e}")
            return OrderResult(success=False, error_message=str(e))

    async def place_limit_order(self, contract_id, quantity, price, side):
        return await self.place_order(contract_id, side, quantity, price)
