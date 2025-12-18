import asyncio
import json
import logging
import websockets
from decimal import Decimal

class WebSocketManagerWrapper:
    """
    Wrapper to manage WebSockets for Lighter, EdgeX, and Extended.
    """
    def __init__(self, order_book_manager, logger):
        self.order_book_manager = order_book_manager
        self.logger = logger
        
        # EdgeX state
        self.edgex_ws_manager = None
        self.edgex_contract_id = None
        
        # Lighter state
        self.lighter_client = None
        self.lighter_market_index = None
        self.lighter_account_index = None
        self.lighter_ws_task = None

        # Extended state
        self.extended_ticker = None
        self.extended_ws_task = None
        self.extended_account_ws_task = None
        self.extended_vault_id = None
        
        self.stop_flag = False

        self.on_lighter_order_filled = None
        self.on_edgex_order_update = None
        self.on_extended_order_update = None 

    def set_callbacks(self, on_lighter_order_filled=None, on_edgex_order_update=None, on_extended_order_update=None):
        self.on_lighter_order_filled = on_lighter_order_filled
        self.on_edgex_order_update = on_edgex_order_update
        self.on_extended_order_update = on_extended_order_update

    def set_edgex_ws_manager(self, ws_manager, contract_id):
        self.edgex_ws_manager = ws_manager
        self.edgex_contract_id = contract_id

    def set_lighter_config(self, client, market_index, account_index):
        self.lighter_client = client
        self.lighter_market_index = market_index
        self.lighter_account_index = account_index

    def set_extended_config(self, ticker, vault_id=None):
        self.extended_ticker = ticker
        self.extended_vault_id = vault_id

    # --- EdgeX Logic ---
    async def setup_edgex_websocket(self):
        if self.edgex_ws_manager:
            await self.edgex_ws_manager.connect()

    # --- Lighter Logic ---
    def start_lighter_websocket(self):
        from exchanges.lighter_custom_websocket import LighterCustomWebSocketManager
        
        # 构造一个 Config 对象传给 WebSocketManager
        class Config:
            contract_id = self.lighter_market_index
            account_index = self.lighter_account_index
            lighter_client = self.lighter_client
            
        config = Config()
        
        async def run_lighter_ws():
            ws = LighterCustomWebSocketManager(config, self._handle_lighter_order_update)
            ws.set_logger(self.logger)
            await ws.connect()

        self.lighter_ws_task = asyncio.create_task(run_lighter_ws())

    def _handle_lighter_order_update(self, orders):
        for order in orders:
            # 简单的判断：如果 status 是 FILLED，触发回调
            if order.get('status') == 'FILLED' and self.on_lighter_order_filled:
                self.on_lighter_order_filled(order)

    # --- Extended Logic ---
    async def setup_extended_websocket(self):
        """Setup Extended WebSocket for Orderbook and User Data."""
        if not self.extended_ticker:
            self.logger.error("Extended ticker not set")
            return

        market_name = f"{self.extended_ticker}-USD"
        
        # 1. 公共行情流 (Orderbook)
        url_public = f"wss://api.starknet.extended.exchange/v1/stream/market/{market_name}"

        async def run_public_ws():
            self.logger.info(f"Connecting to Extended Public WS: {url_public}")
            while not self.stop_flag:
                try:
                    async with websockets.connect(url_public) as ws:
                        self.logger.info("✅ Connected to Extended Public Stream")
                        
                        # 订阅
                        sub_msg = {"type": "subscribe", "channel": "orderbook", "market": market_name}
                        await ws.send(json.dumps(sub_msg))

                        async for message in ws:
                            if self.stop_flag: break
                            try:
                                data = json.loads(message)
                                if "bids" in data or "asks" in data:
                                    self._handle_extended_book_update(data)
                            except Exception as e:
                                self.logger.error(f"Extended Public WS Parse Error: {e}")
                except Exception as e:
                    self.logger.error(f"Extended Public WS Connection Error: {e}")
                    await asyncio.sleep(5)

        self.extended_ws_task = asyncio.create_task(run_public_ws())

        # 2. 私有订单流 (Order Updates)
        if self.extended_vault_id:
            # 注意：Extended 的私有 WS 可能需要鉴权，这里假设简单的连接
            # 实际情况可能需要发送 Auth Frame
            url_private = f"wss://api.starknet.extended.exchange/v1/stream/account/{self.extended_vault_id}"
            
            async def run_private_ws():
                self.logger.info(f"Connecting to Extended Private WS: {url_private}")
                while not self.stop_flag:
                    try:
                        async with websockets.connect(url_private) as ws:
                            self.logger.info("✅ Connected to Extended Private Stream")
                            async for message in ws:
                                if self.stop_flag: break
                                try:
                                    data = json.loads(message)
                                    if data.get('type') == 'ORDER_UPDATE':
                                        self._handle_extended_order_update(data)
                                except Exception as e:
                                    pass
                    except Exception as e:
                        self.logger.error(f"Extended Private WS Error: {e}")
                        await asyncio.sleep(5)

            self.extended_account_ws_task = asyncio.create_task(run_private_ws())

    def _handle_extended_book_update(self, data):
        """Parse Extended WS message."""
        bids = data.get('bids', [])
        asks = data.get('asks', [])

        best_bid = None
        best_ask = None

        if bids:
            # 假设数据格式为 [[price, size], ...]
            best_bid = Decimal(str(bids[0][0]))
        
        if asks:
            best_ask = Decimal(str(asks[0][0]))

        if best_bid is not None and best_ask is not None:
             self.order_book_manager.update_extended_bbo(best_bid, best_ask)

    def _handle_extended_order_update(self, data):
        """Handle execution report"""
        if self.on_extended_order_update:
            # 转换格式适配 OrderManager
            update = {
                'order_id': data.get('orderId'),
                'status': data.get('status'), # FILLED, OPEN, CANCELED
                'side': data.get('side'),
                'filled_size': data.get('filledSize', 0)
            }
            self.on_extended_order_update(update)

    def shutdown(self):
        self.stop_flag = True
        if self.extended_ws_task: self.extended_ws_task.cancel()
        if self.extended_account_ws_task: self.extended_account_ws_task.cancel()
        if self.lighter_ws_task: self.lighter_ws_task.cancel()
        if self.edgex_ws_manager: self.edgex_ws_manager.disconnect_all()
