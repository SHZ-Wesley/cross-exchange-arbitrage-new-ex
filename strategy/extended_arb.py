import asyncio
import logging
from decimal import Decimal
import datetime
from exchanges.extended import ExtendedClient
from exchanges.lighter import LighterClient
from strategy.order_book_manager import OrderBookManager
from strategy.websocket_manager import WebSocketManagerWrapper
from strategy.position_tracker import PositionTracker
from strategy.data_logger import DataLogger

class ExtendedArb:
    def __init__(self, 
                 extended_api_key, 
                 extended_stark_private_key, 
                 extended_vault, 
                 lighter_api_key, 
                 lighter_private_key, 
                 lighter_api_key_index,
                 size, 
                 max_position, 
                 long_ex_threshold, 
                 short_ex_threshold, 
                 fill_timeout=60, 
                 ticker="BTC"):
        
        self.logger = logging.getLogger(__name__)
        
        # 强制转换为 Decimal
        self.size = Decimal(str(size))
        self.max_position = Decimal(str(max_position))
        self.long_ex_threshold = Decimal(str(long_ex_threshold))
        self.short_ex_threshold = Decimal(str(short_ex_threshold))
        self.fill_timeout = fill_timeout
        self.ticker = ticker
        
        self.order_book_manager = OrderBookManager(self.logger)
        self.ws_wrapper = WebSocketManagerWrapper(self.order_book_manager, self.logger)
        
        self.extended_client = ExtendedClient({
            'extended_api_key': extended_api_key,
            'extended_stark_key_private': extended_stark_private_key,
            'extended_vault': extended_vault,
            'ticker': ticker
        })
        
        contract_id = 1 
        self.lighter_client = LighterClient(lighter_api_key, lighter_private_key, lighter_api_key_index, self.logger)
        
        self.ws_wrapper.set_extended_config(ticker, extended_vault, extended_api_key)
        self.ws_wrapper.set_lighter_config(self.lighter_client, contract_id, 0)
        
        self.position_tracker = PositionTracker(
            ticker, self.extended_client, contract_id, 
            "https://mainnet.zklighter.elliot.ai", 0, self.logger, maker_exchange='extended'
        )
        self.data_logger = DataLogger('extended', ticker, self.logger)

    async def run(self):
        # 屏蔽无关日志
        logging.getLogger("websockets").setLevel(logging.ERROR)
        logging.getLogger("urllib3").setLevel(logging.ERROR)
        
        self.logger.info(f"🚀 Starting Extended-Lighter Arb for {self.ticker}")
        
        await self.extended_client.connect()
        await self.ws_wrapper.setup_extended_websocket()
        self.ws_wrapper.start_lighter_websocket()
        
        self.logger.info("⏳ Waiting for Order Books...")
        while not self.order_book_manager.extended_order_book_ready:
            await asyncio.sleep(1)
        self.logger.info("✅ Extended Book Ready")

        while not self.order_book_manager.lighter_order_book_ready:
            await asyncio.sleep(1)
        self.logger.info("✅ Lighter Book Ready")
        
        self.logger.info("✅ Trading Loop Started")
        
        while True:
            await asyncio.sleep(1)
            try:
                ex_bid, ex_ask = self.order_book_manager.get_extended_bbo()
                l_bid, l_ask = self.order_book_manager.get_lighter_bbo()
                
                t_now = datetime.datetime.now().strftime('%H:%M:%S')
                
                if ex_bid and l_bid:
                    # 全 Decimal 运算
                    s_long = l_bid - ex_bid
                    s_short = ex_ask - l_ask
                    
                    print(f"[监控] {t_now} | EX: {ex_bid}/{ex_ask} | LI: {l_bid}/{l_ask} | 差价: {s_long:.1f} / {s_short:.1f}")
                    
                    if s_long > self.long_ex_threshold:
                         self.logger.info(f"📈 Long Opportunity! Spread: {s_long} > {self.long_ex_threshold}")
                         # TODO: 添加实际下单调用
                    elif s_short > self.short_ex_threshold:
                         self.logger.info(f"📉 Short Opportunity! Spread: {s_short} > {self.short_ex_threshold}")
                         # TODO: 添加实际下单调用
                else:
                    print(f"[监控] {t_now} | 等待数据... EX: {ex_bid} | LI: {l_bid}")

            except Exception as e:
                self.logger.error(f"Loop Error: {e}")
