import asyncio
import json
import logging
import websockets
from decimal import Decimal

class WebSocketManagerWrapper:
    def __init__(self, order_book_manager, logger):
        self.order_book_manager = order_book_manager
        self.logger = logger
        self.stop_flag = False
        
        self.on_lighter_order_filled = None
        self.on_extended_order_update = None 

        self.extended_ticker = None
        self.extended_vault_id = None
        self.extended_api_key = None
        
        self.edgex_ws_manager = None
        self.lighter_client = None
        self.lighter_market_index = None
        self.lighter_account_index = None
        self.lighter_ws_task = None
        self.extended_ws_task = None

    def set_callbacks(self, on_lighter_order_filled=None, on_edgex_order_update=None, on_extended_order_update=None):
        self.on_lighter_order_filled = on_lighter_order_filled
        self.on_edgex_order_update = on_edgex_order_update
        self.on_extended_order_update = on_extended_order_update

    def set_extended_config(self, ticker, vault_id=None, api_key=None):
        self.extended_ticker = ticker
        self.extended_vault_id = vault_id
        self.extended_api_key = api_key

    def set_lighter_config(self, client, market_index, account_index):
        self.lighter_client = client
        self.lighter_market_index = market_index
        self.lighter_account_index = account_index

    # --- Extended Logic ---
    async def setup_extended_websocket(self):
        if not self.extended_ticker:
            return

        base_host = "wss://api.starknet.extended.exchange"
        prefix = "/stream.extended.exchange/v1"
        
        public_url = f"{base_host}{prefix}/orderbooks/{self.extended_ticker}-USD?depth=1"
        private_url = f"{base_host}{prefix}/account"
        
        headers = {
            "User-Agent": "Extended-Python-Client/1.0",
            "X-Api-Key": self.extended_api_key or ""
        }

        async def run_ws():
            asyncio.create_task(self._run_single_extended_stream(
                public_url, headers, "Public Orderbook"
            ))
            if self.extended_vault_id and self.extended_api_key:
                await self._run_single_extended_stream(
                    private_url, headers, "Private Account"
                )
            else:
                while not self.stop_flag:
                    await asyncio.sleep(1)

        self.extended_ws_task = asyncio.create_task(run_ws())

    async def _run_single_extended_stream(self, url, headers, stream_name):
        self.logger.info(f"Connecting to Extended {stream_name}: {url}")
        while not self.stop_flag:
            try:
                async with websockets.connect(url, additional_headers=headers) as ws:
                    self.logger.info(f"✅ Connected to Extended {stream_name}")
                    
                    async for message in ws:
                        if self.stop_flag: break
                        try:
                            data = json.loads(message)
                            msg_type = data.get("type")
                            payload = data.get("data", {})

                            if msg_type in ["SNAPSHOT", "L2_UPDATE"] or "b" in payload:
                                self._handle_extended_book(payload)
                            elif msg_type == "ORDER":
                                self._handle_extended_orders(payload)
                        except Exception:
                            pass
            except Exception as e:
                self.logger.error(f"Extended {stream_name} Error: {e}")
                await asyncio.sleep(5)

    def _handle_extended_book(self, data):
        bids = data.get('b', [])
        asks = data.get('a', [])
        if bids and asks:
            try:
                # 适配 {"p": "...", "q": "..."} 格式
                best_bid = Decimal(str(bids[0]['p']))
                best_ask = Decimal(str(asks[0]['p']))
                self.order_book_manager.update_extended_bbo(best_bid, best_ask)
            except: pass

    def _handle_extended_orders(self, data):
        orders = data.get("orders", [])
        if self.on_extended_order_update:
            for o in orders:
                self.on_extended_order_update({
                    'order_id': str(o.get('id')),
                    'status': o.get('status'),
                    'filled_size': Decimal(str(o.get('filledQty', 0)))
                })

    # --- Lighter Logic ---
    def start_lighter_websocket(self):
        from exchanges.lighter_custom_websocket import LighterCustomWebSocketManager
        class Config:
            contract_id = self.lighter_market_index
            account_index = self.lighter_account_index
            lighter_client = self.lighter_client   
        config = Config()
        
        async def run_lighter_ws():
            ws = LighterCustomWebSocketManager(config, self._handle_lighter_order_update)
            ws.set_logger(self.logger)
            # 关键：注入 order_book_manager
            ws.set_order_book_manager(self.order_book_manager)
            await ws.connect()
            
        self.lighter_ws_task = asyncio.create_task(run_lighter_ws())

    def _handle_lighter_order_update(self, orders):
        for order in orders:
            if order.get('status') == 'FILLED' and self.on_lighter_order_filled:
                self.on_lighter_order_filled(order)

    def shutdown(self):
        self.stop_flag = True
        if self.extended_ws_task: self.extended_ws_task.cancel()
        if self.lighter_ws_task: self.lighter_ws_task.cancel()
        if self.edgex_ws_manager: self.edgex_ws_manager.disconnect_all()
