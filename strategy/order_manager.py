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
        
        # Extended config
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
        
        # Hedging State
        self.current_lighter_side = None
        self.current_lighter_quantity = None
        self.current_lighter_price = None
        
        # Callbacks
        self.on_order_filled = None
        
        # Events
        self.extended_fill_event = asyncio.Event()

    def set_callbacks(self, on_order_filled):
        self.on_order_filled = on_order_filled

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

        best_bid, best_ask = self.order_book_manager.get_extended_bbo()
        if best_bid is None or best_ask is None:
            self.logger.warning("Extended BBO not ready")
            return False

        # Maker Price Logic
        price = best_bid if side == 'buy' else best_ask
        
        self.logger.info(f"Creating Extended {side} order: {quantity} @ {price}")
        
        try:
            result = await self.extended_client.place_open_order(
                contract_id=self.extended_contract_id,
                quantity=quantity,
                direction=side.lower(),
                price=price
            )
            
            if not result.success:
                self.logger.error(f"Extended order failed: {result.error_message}")
                return False
            
            self.current_maker_order_id = result.order_id
            self.logger.info(f"Extended Order Placed ID: {self.current_maker_order_id}")
            
            # Reset event
            self.extended_fill_event.clear()
            
            # Wait for fill event or timeout
            try:
                await asyncio.wait_for(self.extended_fill_event.wait(), timeout=10)
                self.logger.info("Extended Order Fill Detected via Event!")
                return True
            except asyncio.TimeoutError:
                self.logger.info(f"Extended order timeout, cancelling: {self.current_maker_order_id}")
                await self.extended_client.cancel_order(self.current_maker_order_id)
                return False

        except Exception as e:
            self.logger.error(f"Error placing Extended order: {e}")
            traceback.print_exc()
            return False

    def handle_extended_order_update(self, order_data):
        """Handle order update from Extended WebSocket."""
        oid = order_data.get('order_id')
        status = order_data.get('status')
        
        if oid == self.current_maker_order_id and status == 'FILLED':
            self.logger.info(f"Extended Order {oid} FILLED")
            side = order_data.get('side')
            qty = Decimal(str(order_data.get('filled_size', 0)))
            
            # Setup Lighter Hedge Params
            self.current_lighter_side = 'sell' if side.upper() == 'BUY' else 'buy'
            self.current_lighter_quantity = qty
            
            # Calculate aggressive taker price
            l_bid, l_ask = self.order_book_manager.get_lighter_bbo()
            
            if self.current_lighter_side == 'buy':
                # Buying on Lighter (Short on Maker) -> Pay Ask
                self.current_lighter_price = l_ask * Decimal('1.05') if l_ask else None
            else:
                # Selling on Lighter (Long on Maker) -> Sell into Bid
                self.current_lighter_price = l_bid * Decimal('0.95') if l_bid else None

            self.waiting_for_lighter_fill = True
            self.order_execution_complete = False
            
            # Signal the main loop to proceed
            self.extended_fill_event.set()

    # --- Lighter Logic ---
    async def place_lighter_market_order(self, side, quantity, price, stop_flag):
        """Execute Lighter Hedge"""
        self.logger.info(f"Placing Lighter Hedge: {side} {quantity} @ {price}")
        if not self.lighter_client:
            return

        try:
            # Call Lighter Place Order (implementation depends on LighterClient in exchanges/lighter.py)
            # Assuming it supports place_limit_order or place_market_order
            # Here we use limit order with aggressive price as market order
            res = await self.lighter_client.place_limit_order(
                contract_id=self.lighter_market_index,
                quantity=quantity,
                price=price,
                side=side
            )
            
            if res.success:
                 self.logger.info(f"Lighter Hedge Placed: {res.order_id}")
            else:
                 self.logger.error(f"Lighter Hedge Failed: {res.error_message}")

        except Exception as e:
            self.logger.error(f"Lighter Hedge Exception: {e}")
