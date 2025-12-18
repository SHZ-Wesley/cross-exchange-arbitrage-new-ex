import time
import asyncio
import traceback
from decimal import Decimal
import logging

class OrderManager:
    """
    Manages order placement and lifecycle for EdgeX, Extended, and Lighter.
    """
    def __init__(self, order_book_manager, logger):
        self.order_book_manager = order_book_manager
        self.logger = logger
        
        # EdgeX config
        self.edgex_client = None
        self.edgex_contract_id = None
        self.edgex_tick_size = None
        
        # Extended config (New)
        self.extended_client = None
        self.extended_contract_id = None
        self.extended_tick_size = None

        # Lighter config
        self.lighter_client = None
        self.lighter_market_index = None
        self.base_amount_multiplier = None
        self.price_multiplier = None
        self.lighter_tick_size = None

        # State
        self.current_maker_order_id = None
        self.waiting_for_lighter_fill = False
        self.order_execution_complete = False
        self.current_lighter_side = None
        self.current_lighter_quantity = None
        self.current_lighter_price = None
        
        # Callbacks
        self.on_order_filled = None

    def set_callbacks(self, on_order_filled):
        self.on_order_filled = on_order_filled

    def set_edgex_config(self, client, contract_id, tick_size):
        self.edgex_client = client
        self.edgex_contract_id = contract_id
        self.edgex_tick_size = tick_size

    def set_extended_config(self, client, contract_id, tick_size):
        self.extended_client = client
        self.extended_contract_id = contract_id
        self.extended_tick_size = tick_size

    def set_lighter_config(self, client, market_index, base_mult, price_mult, tick_size):
        self.lighter_client = client
        self.lighter_market_index = market_index
        self.base_amount_multiplier = base_mult
        self.price_multiplier = price_mult
        self.lighter_tick_size = tick_size

    # --- Extended Order Logic ---

    async def place_extended_post_only_order(self, side: str, quantity: Decimal, stop_flag: bool):
        """Place Post-Only Order on Extended."""
        if not self.extended_client:
            raise ValueError("Extended client not configured")

        # Get BBO
        best_bid, best_ask = self.order_book_manager.get_extended_bbo()
        if best_bid is None or best_ask is None:
            self.logger.warning("Extended BBO not ready")
            return False

        # Determine Price (Maker)
        price = best_bid if side == 'buy' else best_ask
        
        self.logger.info(f"Creating Extended {side} order: {quantity} @ {price}")
        
        try:
            # Note: This calls the place_open_order method in exchanges/extended.py
            result = await self.extended_client.place_open_order(
                contract_id=self.extended_contract_id,
                quantity=quantity,
                direction=side.lower(),
                price=price
            )
            
            # Simple simulation of result handling, assuming result object has .success and .order_id
            if hasattr(result, 'success') and not result.success:
                self.logger.error(f"Extended order failed: {getattr(result, 'error_message', 'Unknown error')}")
                return False
            
            self.current_maker_order_id = getattr(result, 'order_id', 'unknown')
            self.logger.info(f"Extended Order Placed ID: {self.current_maker_order_id}")
            
            # Monitor for fill (Simplified polling for demo)
            return await self._monitor_extended_order_fill(self.current_maker_order_id, side, quantity, stop_flag)

        except Exception as e:
            self.logger.error(f"Error placing Extended order: {e}")
            traceback.print_exc()
            return False

    async def _monitor_extended_order_fill(self, order_id, side, quantity, stop_flag):
        """
        Monitor Extended order status.
        Strategy: Wait for fill -> Trigger Lighter Hedge.
        """
        start_time = time.time()
        while not stop_flag:
            if time.time() - start_time > 5: # 5s Timeout
                self.logger.info(f"Extended order timeout, cancelling: {order_id}")
                await self.extended_client.cancel_order(order_id)
                return False

            # NOTE: In a real system, we'd check `self.current_maker_status` updated by WS.
            # Here we assume a fill happens if we are integrating with the real system.
            # For now, return False unless WS logic is fully hooked up.
            await asyncio.sleep(0.1)
            
        return False

    def handle_extended_order_update(self, order_data):
        """Handle order update from Extended WebSocket."""
        oid = order_data.get('order_id')
        status = order_data.get('status')
        
        if oid == self.current_maker_order_id and status == 'FILLED':
            self.logger.info("Extended Order FILLED")
            side = order_data.get('side')
            qty = Decimal(str(order_data.get('filled_size', 0)))
            
            # Setup Lighter Hedge
            self.current_lighter_side = 'sell' if side == 'buy' else 'buy'
            self.current_lighter_quantity = qty
            
            # Calculate aggressive taker price
            l_bid, l_ask = self.order_book_manager.get_lighter_bbo()
            if self.current_lighter_side == 'buy':
                self.current_lighter_price = l_ask * Decimal('1.05') if l_ask else None
            else:
                self.current_lighter_price = l_bid * Decimal('0.95') if l_bid else None

            self.waiting_for_lighter_fill = True
            self.order_execution_complete = False

    # --- Lighter Logic (Keep existing methods) ---
    async def place_lighter_market_order(self, side, quantity, price, stop_flag):
        # Implementation from original file...
        pass
    
    # --- EdgeX Logic (Keep existing methods) ---
    def get_edgex_client_order_id(self):
        # Implementation...
        pass
        
    def update_edgex_order_status(self, status):
        # Implementation...
        pass
        
    async def fetch_edgex_bbo_prices(self):
        # Implementation...
        pass
        
    async def place_edgex_post_only_order(self, side, quantity, stop_flag):
        # Implementation...
        pass
        
    def handle_edgex_order_update(self, order_data):
        # Implementation...
        pass
