import json
import logging
import asyncio
import websockets

class LighterCustomWebSocketManager:
    def __init__(self, config, on_order_update=None, order_book_manager=None):
        self.config = config
        self.on_order_update = on_order_update
        self.order_book_manager = order_book_manager
        self.logger = logging.getLogger(__name__)
        self.ws = None
        self.stop_flag = False
        # 从配置获取 market_id，默认为 1 (BTC-USD)
        self.market_index = getattr(config, 'contract_id', 1) 

    def set_logger(self, logger):
        self.logger = logger
        
    def set_order_book_manager(self, manager):
        self.order_book_manager = manager

    async def connect(self):
        # 备选地址列表，解决 DNS 解析问题
        urls = [
            "wss://mainnet.zklighter.elliot.ai/stream",
            "wss://api.lighter.xyz/v1/stream"
        ]
        
        for url in urls:
            if self.stop_flag: break
            try:
                self.logger.info(f"Connecting to Lighter: {url}")
                async with websockets.connect(url, open_timeout=5) as ws:
                    self.ws = ws
                    self.logger.info(f"✅ Connected to Lighter Stream")
                    
                    sub_msg = {"type": "subscribe", "channel": "order_book/1"}
                    await ws.send(json.dumps(sub_msg))
                    
                    async for message in ws:
                        if self.stop_flag: break
                        try:
                            self._parse_message(message)
                        except Exception:
                            pass
                return 
            except Exception as e:
                self.logger.error(f"Lighter WS Error: {e}")
                await asyncio.sleep(1)

    def _parse_message(self, message):
        try:
            data = json.loads(message)
            # 兼容多种数据结构
            payload = {}
            if "order_book" in data:
                payload = data["order_book"]
            elif "bids" in data:
                payload = data
            elif "data" in data:
                payload = data["data"]

            bids = payload.get('bids', [])
            asks = payload.get('asks', [])

            if self.order_book_manager and (bids or asks):
                # 提取最优价格
                bb = self._extract_price(bids[0]) if bids else None
                ba = self._extract_price(asks[0]) if asks else None
                
                if bb and ba:
                    self.order_book_manager.update_lighter_bbo(bb, ba)
        except:
            pass

    def _extract_price(self, item):
        # 兼容字典 {'price': '100', ...} 或 列表 ['100', '1']
        if isinstance(item, dict):
            return item.get('price') or item.get('p')
        if isinstance(item, (list, tuple)):
            return item[0]
        return item

    def disconnect(self):
        self.stop_flag = True
