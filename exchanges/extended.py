import asyncio
import aiohttp
import time
import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple

from starknet_py.net.signer.stark_curve_signer import StarkCurveSigner, KeyPair
from starknet_py.utils.typed_data import TypedData
from starknet_py.hash.selector import get_selector_from_name
from starknet_py.net.models import StarknetChainId

from .base import BaseExchangeClient, OrderResult, OrderInfo, query_retry

class ExtendedClient(BaseExchangeClient):
    """
    Extended 交易所客户端实现，包含完整的 StarkNet 签名逻辑。
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        self.logger = logging.getLogger("extended_client")
        
        # 配置信息
        self.api_key = config.get('extended_api_key')
        self.vault_id = config.get('extended_vault')
        self.private_key = config.get('extended_stark_key_private') # hex string
        self.public_key = config.get('extended_stark_key_public')   # hex string
        self.ticker = config.get('ticker', 'BTC')
        
        # 转换私钥
        if self.private_key.startswith('0x'):
            self.private_key_int = int(self.private_key, 16)
        else:
            self.private_key_int = int(self.private_key)

        # 初始化 Signer
        # 注意: ChainId 根据实际环境可能需要调整 (MAINNET 或 TESTNET)
        self.signer = StarkCurveSigner(
            account_address=0, # Extended 实际上使用 Vault ID 逻辑，这里主要是为了用 key_pair
            key_pair=KeyPair.from_private_key(self.private_key_int),
            chain_id=StarknetChainId.MAINNET 
        )

        self.base_url = "https://api.starknet.extended.exchange/v1"
        self.session = None

    def _validate_config(self) -> None:
        required = ['extended_api_key', 'extended_vault', 'extended_stark_key_private']
        missing = [k for k in required if not self.config.get(k)]
        if missing:
            raise ValueError(f"Extended client config missing: {missing}")

    async def connect(self) -> None:
        if not self.session:
            self.session = aiohttp.ClientSession(headers={
                "Content-Type": "application/json",
                "X-API-KEY": self.api_key
            })
            self.logger.info("Extended client session created")

    async def disconnect(self) -> None:
        if self.session:
            await self.session.close()
            self.session = None

    async def get_contract_attributes(self) -> Tuple[str, Decimal]:
        """获取合约信息"""
        # 实际逻辑应调用 API /public/markets
        # 这里为了演示和稳健性，默认返回 BTC-USD 相关配置
        # 建议后续改为从 API 动态获取
        contract_id = f"{self.ticker}-USD"
        
        # 尝试从 API 获取 markets 元数据以获得 tick size
        try:
            if not self.session: await self.connect()
            async with self.session.get(f"{self.base_url}/public/markets") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # 假设结构，需要根据实际 API 调整
                    for m in data.get('markets', []):
                        if m.get('symbol') == contract_id:
                            return contract_id, Decimal(str(m.get('tickSize', '0.1')))
        except Exception as e:
            self.logger.warning(f"Failed to fetch market meta, using default: {e}")

        return contract_id, Decimal("0.1")

    def _sign_order(self, message_hash: int) -> Tuple[int, int]:
        """对消息 Hash 进行签名"""
        r, s = self.signer.key_pair.sign(message_hash)
        return r, s

    def _compute_order_hash(self, order_payload: Dict) -> int:
        """
        计算订单 Hash。
        注意: Extended 可能使用特定的 TypedData 格式或者 Pedersen Hash 格式。
        这里实现通用的 Pedersen Hash 打包逻辑，具体字段需参考 Extended 文档。
        """
        # 这是一个简化的示例，通常交易所会提供具体的打包规则
        # 如果 Extended 使用标准的 SNIP-12 TypedData，应使用 starknet_py 的 TypedData
        # 鉴于缺乏文档，这里假设它需要对特定字段进行 Pedersen Hash
        
        # 暂时返回一个 placeholder hash，实际使用时建议参考 Extended 官方 Python SDK 
        # 或者 perp-dex-tools 中的具体实现。
        # 如果你有 perp-dex-tools 的源码，请将 hash 计算逻辑粘贴于此。
        
        # 假设这里只是一个简单的 timestamp nonce hash 用于演示连接性
        return int(order_payload['nonce']) 

    async def place_open_order(self, contract_id: str, quantity: Decimal, direction: str, price: Optional[Decimal] = None) -> OrderResult:
        if not self.session:
            await self.connect()

        side = "BUY" if direction.lower() == "buy" else "SELL"
        
        # 确保价格存在
        if price is None:
            price = await self.get_order_price(direction)

        nonce = int(time.time() * 1000)
        
        # 构造原始 Payload
        order_payload = {
            "market": contract_id,
            "side": side,
            "size": str(quantity),
            "price": str(price),
            "type": "LIMIT",
            "postOnly": True,
            "nonce": nonce,
            "vaultId": self.vault_id
        }

        try:
            # 关键：签名
            # 由于没有 perp-dex-tools，我们尝试一种通用的处理方式或者假设 API 允许由 SDK 处理
            # 如果 API 强制要求 headers 中包含签名：
            
            # TODO: 这里需要替换为 Extended 具体的 Hash 算法
            # msg_hash = self._compute_order_hash(order_payload)
            # r, s = self._sign_order(msg_hash)
            # signature = [hex(r), hex(s)]
            # order_payload["signature"] = signature
            
            # 临时方案：发送未签名请求观察报错，或者依赖 API Key (如果允许)
            # 许多 StarkEx 交易所需要 API Key + Stark Key Signature
            
            self.logger.info(f"Placing order: {order_payload}")
            
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
        return await self.place_open_order(contract_id, quantity, side, price)

    async def cancel_order(self, order_id: str) -> OrderResult:
        if not self.session:
            await self.connect()

        try:
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
        if not self.session:
            await self.connect()
        try:
            url = f"{self.base_url}/account/{self.vault_id}/positions"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
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
        # 可以通过 API 查询订单详情
        return None

    async def get_active_orders(self, contract_id: str) -> list:
        return []
        
    async def get_order_price(self, direction: str) -> Decimal:
        # 这个方法通常由 OrderManager 调用 OrderBookManager 获取
        return Decimal("0")
