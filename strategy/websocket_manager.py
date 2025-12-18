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
        
        # Existing managers
        self.edgex_ws_manager = None
        self.edgex_contract_id = None
        
        self.lighter_client = None
        self.lighter_market_index = None
        self.lighter_account_index = None
        self.lighter_ws_task = None

        # Extended (New)
        self.extended_ticker = None
        self.extended_ws_task = None
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

    def set_extended_config(self, ticker):
        self.extended_ticker = ticker

    # --- EdgeX Logic (Simplified for brevity, keep original logic) ---
    async def setup_edgex_websocket(self):
        if not self.edgex_ws_manager: return
        # ... (Keep original logic calling connect and subscribe) ...
        await self.edgex_ws_manager.connect()

    # --- Lighter Logic (Keep original logic) ---
    def start_lighter_websocket(self):
        # ... (Keep original logic starting LighterCustomWebSocketManager) ...
        pass

    # --- Extended Logic (New) ---
    async def setup_extended_websocket(self):
        """Setup Extended WebSocket for Orderbook Depth."""
        if not self.extended_ticker:
            self.logger.error("Extended ticker not set")
            return

        market_name = f"{self.extended_ticker}-USD"
        url = f"wss://api.starknet.extended.exchange/stream.extended.exchange/v1/orderbooks/{market_name}?depth=1"

        async def run_ws():
            self.logger.info(f"Connecting to Extended WS: {url}")
            while not self.stop_flag:
                try:
                    async with websockets.connect(url) as ws:
                        self.logger.info("✅ Connected to Extended Orderbook Stream")
                        async for message in ws:
                            if self.stop_flag: break
                            try:
                                data = json.loads(message)
                                if data.get("type") in ["SNAPSHOT", "DELTA"]:
                                    self._handle_extended_book_update(data)
                            except Exception as e:
                                self.logger.error(f"Extended WS Parse Error: {e}")
                except Exception as e:
                    self.logger.error(f"Extended WS Connection Error: {e}")
                    await asyncio.sleep(2)

        self.extended_ws_task = asyncio.create_task(run_ws())

    def _handle_extended_book_update(self, data):
        """Parse Extended WS message."""
        book_data = data.get("data", {})
        if not book_data: return

        bids = book_data.get('b', [])
        asks = book_data.get('a', [])

        best_bid = None
        best_ask = None

        if bids:
            bid = bids[0]
            val = bid.get('p') if isinstance(bid, dict) else bid[0]
            best_bid = Decimal(str(val))
        
        if asks:
            ask = asks[0]
            val = ask.get('p') if isinstance(ask, dict) else ask[0]
            best_ask = Decimal(str(val))

        if best_bid is not None and best_ask is not None:
             self.order_book_manager.update_extended_bbo(best_bid, best_ask)

    def shutdown(self):
        self.stop_flag = True
        if self.extended_ws_task:
            self.extended_ws_task.cancel()
        if self.lighter_ws_task:
            self.lighter_ws_task.cancel()
        if self.edgex_ws_manager:
            self.edgex_ws_manager.disconnect_all()
