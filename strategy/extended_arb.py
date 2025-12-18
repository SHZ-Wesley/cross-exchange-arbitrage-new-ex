import asyncio
import signal
import logging
import os
import sys
import time
import traceback
from decimal import Decimal

# Correct imports
from exchanges.extended import ExtendedClient
from lighter.signer_client import SignerClient

from .data_logger import DataLogger
from .order_book_manager import OrderBookManager
from .websocket_manager import WebSocketManagerWrapper
from .order_manager import OrderManager
from .position_tracker import PositionTracker

class ExtendedArb:
    """Arbitrage trading bot: Maker on Extended, Taker on Lighter."""

    def __init__(self, ticker: str, order_quantity: Decimal,
                 fill_timeout: int = 5, max_position: Decimal = Decimal('0'),
                 long_ex_threshold: Decimal = Decimal('10'),
                 short_ex_threshold: Decimal = Decimal('10')):
        
        self.ticker = ticker
        self.order_quantity = order_quantity
        self.fill_timeout = fill_timeout
        self.max_position = max_position
        self.long_ex_threshold = long_ex_threshold
        self.short_ex_threshold = short_ex_threshold
        
        self.stop_flag = False
        self._setup_logger()

        # Init Managers
        self.order_book_manager = OrderBookManager(self.logger)
        self.ws_manager = WebSocketManagerWrapper(self.order_book_manager, self.logger)
        self.order_manager = OrderManager(self.order_book_manager, self.logger)
        
        # Env Vars
        self.extended_vault = os.getenv('EXTENDED_VAULT')
        self.extended_stark_key_private = os.getenv('EXTENDED_STARK_KEY_PRIVATE')
        self.extended_stark_key_public = os.getenv('EXTENDED_STARK_KEY_PUBLIC')
        self.extended_api_key = os.getenv('EXTENDED_API_KEY')
        
        self.lighter_base_url = "https://mainnet.zklighter.elliot.ai"
        self.account_index = int(os.getenv('LIGHTER_ACCOUNT_INDEX', 0))
        self.api_key_index = int(os.getenv('LIGHTER_API_KEY_INDEX', 0))

    def _setup_logger(self):
        self.logger = logging.getLogger(f"extended_arb_{self.ticker}")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(handler)

    def initialize_clients(self):
        # 1. Extended Client
        config_dict = {
            'ticker': self.ticker,
            'extended_vault': self.extended_vault,
            'extended_stark_key_private': self.extended_stark_key_private,
            'extended_stark_key_public': self.extended_stark_key_public,
            'extended_api_key': self.extended_api_key,
            'quantity': self.order_quantity
        }
        self.extended_client = ExtendedClient(config_dict)
        
        # 2. Lighter Client
        api_key_private = os.getenv('API_KEY_PRIVATE_KEY')
        if not api_key_private:
            self.logger.error("Missing API_KEY_PRIVATE_KEY for Lighter")
            sys.exit(1)
        
        self.lighter_client = SignerClient(
            url=self.lighter_base_url,
            private_key=api_key_private,
            account_index=self.account_index,
            api_key_index=self.api_key_index
        )
        # Ensure Lighter client check passes
        if err := self.lighter_client.check_client():
            self.logger.error(f"Lighter Client Error: {err}")

    async def run(self):
        self.logger.info(f"🚀 Starting Extended-Lighter Arb for {self.ticker}")
        self.initialize_clients()
        
        await self.extended_client.connect()

        try:
            # 1. Get Contract Info
            ext_contract_id, ext_tick_size = await self.extended_client.get_contract_attributes()
            
            # Assume Lighter config fetch (simplified)
            # In a real scenario, use Lighter API to get market ID
            lighter_mkt_id = 1 
            lighter_base_mult = 10000 
            lighter_price_mult = 100 
            lighter_tick_size = Decimal("0.01")
            
            # 2. Setup Managers
            self.order_manager.set_extended_config(self.extended_client, ext_contract_id, ext_tick_size)
            self.order_manager.set_lighter_config(self.lighter_client, lighter_mkt_id, lighter_base_mult, lighter_price_mult, lighter_tick_size)
            
            # Hook up WebSocket Callbacks
            self.ws_manager.set_callbacks(
                on_extended_order_update=self.order_manager.handle_extended_order_update,
                on_lighter_order_filled=self._handle_lighter_fill
            )
            
            # 3. Setup WS
            self.ws_manager.set_extended_config(self.ticker, self.extended_vault)
            self.ws_manager.set_lighter_config(self.lighter_client, lighter_mkt_id, self.account_index)
            
            await self.ws_manager.setup_extended_websocket()
            self.ws_manager.start_lighter_websocket() 
            
            # 4. Wait for Book
            self.logger.info("⏳ Waiting for Order Books...")
            while not self.order_book_manager.extended_order_book_ready:
                if self.stop_flag: break
                await asyncio.sleep(1)

            # 5. Trading Loop
            self.logger.info("✅ Trading Loop Started")
            while not self.stop_flag:
                try:
                    ex_bid, ex_ask = self.order_book_manager.get_extended_bbo()
                    l_bid, l_ask = self.order_book_manager.get_lighter_bbo()
                    
                    if not all([ex_bid, ex_ask, l_bid, l_ask]):
                        await asyncio.sleep(0.1)
                        continue

                    # Spread Calculation
                    long_opp = (l_bid - ex_bid) > self.long_ex_threshold
                    short_opp = (ex_ask - l_ask) > self.short_ex_threshold
                    
                    if long_opp:
                        self.logger.info(f"💎 Long Opportunity: Buy Ext {ex_bid} / Sell Lighter {l_bid}")
                        # This call waits for fill event inside order_manager
                        await self.order_manager.place_extended_post_only_order('buy', self.order_quantity, self.stop_flag)

                    elif short_opp:
                        self.logger.info(f"💎 Short Opportunity: Sell Ext {ex_ask} / Buy Lighter {l_ask}")
                        await self.order_manager.place_extended_post_only_order('sell', self.order_quantity, self.stop_flag)
                    
                    # Hedging Logic (Executed if Extended order filled)
                    if self.order_manager.waiting_for_lighter_fill:
                        await self.order_manager.place_lighter_market_order(
                            self.order_manager.current_lighter_side,
                            self.order_manager.current_lighter_quantity,
                            self.order_manager.current_lighter_price,
                            self.stop_flag
                        )
                        self.order_manager.waiting_for_lighter_fill = False

                    await asyncio.sleep(0.01)

                except Exception as e:
                    self.logger.error(f"Loop Error: {e}")
                    traceback.print_exc()
                    await asyncio.sleep(1)
        finally:
            await self.extended_client.disconnect()
            self.ws_manager.shutdown()

    def _handle_lighter_fill(self, order):
        self.logger.info(f"Lighter Fill Confirmed: {order}")

    def stop(self):
        self.stop_flag = True
