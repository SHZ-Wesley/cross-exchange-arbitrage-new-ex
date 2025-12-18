import asyncio
import aiohttp
import time
import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple

from .base import BaseExchangeClient, OrderResult, OrderInfo, query_retry

# 尝试从 perp_dex_tools 导入签名工具 (假设环境中有这个库)
try:
    from perp_dex_tools.utils.starknet import sign_order_msg, get_auth_headers
    HAS_SIGNER_TOOLS = True
except ImportError:
    HAS_SIGNER_TOOLS = False

class ExtendedClient(BaseExchangeClient):
    """
    Extended 交易所客户端实现
    """
    def __init__(self, config: Dict[str, Any]):
        # 初始化父类，确保存储 config
        super().__init__(config)
        
        self.logger = logging.getLogger("extended_client")
        
        # 从 config 中提取必要的认证信息
        self.api_key = config.get('extended_api_key')
        self.vault_id = config.get('extended_vault')
        self.private_key = config.get('extended_stark_key_private')
        self.public_key = config.get('extended_stark_key_public')
        self.ticker = config.get('ticker', 'BTC')
        
        # API URL
        self.base_url = "https://api.starknet.extended.exchange/v1"
        self.session = None

    def _validate_config(self) -> None:
        """验证配置完整性"""
        required = ['extended_api_key', 'extended_vault', 'extended_stark_key_private']
        missing = [k for k in required if not self.config.get(k)]
        if missing:
            raise ValueError(f"Extended client config missing: {missing}")

    async def connect(self) -> None:
        """建立 HTTP 会话"""
        if not self.session:
            self.session = aiohttp.ClientSession(headers={
                "Content-Type": "application/json",
                "X-API-KEY": self.api_key
            })
            self.logger.info("Extended client session created")

    async def disconnect(self) -> None:
        """关闭 HTTP 会话"""
        if self.session:
            await self.session.close()
            self.session = None

    async def get_contract_attributes(self) -> Tuple[str, Decimal]:
        """获取合约ID和Tick Size"""
        # 简单实现，通常需要调用 metadata 接口
        # contract_id = f"{self.ticker}-USD"
        # 假设从 API 获取:
        # async with self.session.get(f"{self.base_url}/public/markets") as resp: ...
        
        # 这里为了演示直接返回常见默认值
        return f"{self.ticker}-USD", Decimal("0.1")

    async def place_open_order(self, contract_id: str, quantity: Decimal, direction: str) -> OrderResult:
        """
        下单接口 (实现 HTTP POST 和 签名占位符)
        """
        if not self.session:
            await self.connect()

        # 1. 准备订单参数
        side = "BUY" if direction.lower() == "buy" else "SELL"
        price = await self.get_order_price(direction) # 获取 Maker 价格
        
        # 2. 构造 Payload
        order_payload = {
            "market": contract_id,
            "side": side,
            "size": str(quantity),
            "price": str(price),
            "type": "LIMIT",
            "postOnly": True,
            "nonce": int(time.time() * 1000)
        }

        # 3. 签名逻辑 (TODO)
        if HAS_SIGNER_TOOLS:
            # 假设 perp-dex-tools 提供了签名功能
            signature = sign_order_msg(self.private_key, order_payload)
            order_payload['signature'] = signature
        else:
            self.logger.warning("STARK 签名工具缺失。无法对订单进行签名。")
            # TODO: 在此实现 Pedersen Hash 签名逻辑
            # order_payload['signature'] = {r: "...", s: "..."}

        # 4. 发送请求
        try:
            url = f"{self.base_url}/orders"
            async with self.session.post(url, json=order_payload) as response:
                resp_json = await response.json()
                
                if response.status in [200, 201]:
                    order_id = resp_json.get('orderId')
                    return OrderResult(
                        success=True,
                        order_id=order_id,
                        side=direction,
                        size=quantity,
                        price=price,
                        status="OPEN"
                    )
                else:
                    return OrderResult(
                        success=False,
                        error_message=f"HTTP {response.status}: {resp_json}"
                    )
        except Exception as e:
            return OrderResult(success=False, error_message=str(e))

    async def place_close_order(self, contract_id: str, quantity: Decimal, price: Decimal, side: str) -> OrderResult:
        """平仓单 (为了接口兼容性)"""
        # 对于套利策略，平仓逻辑通常和开仓类似，只是方向相反
        return await self.place_open_order(contract_id, quantity, side)

    async def cancel_order(self, order_id: str) -> OrderResult:
        """撤单接口"""
        if not self.session:
            await self.connect()

        try:
            # 需要签名撤单请求
            payload = {"orderId": order_id}
            
            if HAS_SIGNER_TOOLS:
                # payload['signature'] = ...
                pass

            url = f"{self.base_url}/orders/{order_id}"
            async with self.session.delete(url) as response:
                if response.status == 200:
                    return OrderResult(success=True, order_id=order_id)
                else:
                    err = await response.text()
                    return OrderResult(success=False, error_message=err)
        except Exception as e:
            return OrderResult(success=False, error_message=str(e))

    async def get_account_positions(self) -> Decimal:
        """获取持仓"""
        if not self.session:
            await self.connect()

        try:
            url = f"{self.base_url}/account/{self.vault_id}/positions"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    # 解析逻辑: 找到当前 ticker 的持仓
                    # 假设返回格式: {'positions': [{'symbol': 'BTC-USD', 'size': '1.5'}]}
                    for pos in data.get('positions', []):
                        if self.ticker in pos.get('symbol', ''):
                            return Decimal(pos.get('size', 0))
                return Decimal(0)
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return Decimal(0)

    # 接口必需的抽象方法实现
    def get_exchange_name(self) -> str:
        return "extended"

    def setup_order_update_handler(self, handler) -> None:
        self._order_update_handler = handler

    async def get_order_info(self, order_id: str) -> Optional[OrderInfo]:
        return None

    async def get_active_orders(self, contract_id: str) -> list:
        return []
        
    async def get_order_price(self, direction: str) -> Decimal:
        """辅助方法：获取 BBO 价格用于挂单"""
        # 在实际逻辑中，这应该从 OrderBookManager 获取，
        # 但作为 Client 内部方法，这里可以做简单的降级处理或留空
        return Decimal("0")
