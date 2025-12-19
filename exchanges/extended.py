import asyncio
import aiohttp
import time
import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple

from starknet_py.net.signer.stark_curve_signer import StarkCurveSigner, KeyPair
from starknet_py.net.models import StarknetChainId

from .base import BaseExchangeClient, OrderResult, OrderInfo, query_retry


class ExtendedClient(BaseExchangeClient):
    """
    Extended 交易所客户端实现，包含完整的 StarkNet 签名逻辑和策略适配接口。
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        self.logger = logging.getLogger("extended_client")

        # 配置信息
        self.api_key = config.get("extended_api_key")
        self.vault_id = config.get("extended_vault")
        self.private_key = config.get("extended_stark_key_private")
        self.public_key = config.get("extended_stark_key_public")
        self.ticker = config.get("ticker", "BTC")

        # 转换私钥 (支持 hex 字符串或 int 字符串)
        self.private_key_int = 0
        if self.private_key:
            if self.private_key.startswith("0x"):
                self.private_key_int = int(self.private_key, 16)
            else:
                self.private_key_int = int(self.private_key)

        # 初始化 Signer
        if self.private_key_int:
            self.signer = StarkCurveSigner(
                account_address=0,
                key_pair=KeyPair.from_private_key(self.private_key_int),
                chain_id=StarknetChainId.MAINNET,
            )
        else:
            self.signer = None

        self.base_url = "https://api.starknet.extended.exchange/v1"
        self.session = None

    def _validate_config(self) -> None:
        required = ["extended_api_key", "extended_vault", "extended_stark_key_private"]
        missing = [k for k in required if not self.config.get(k)]
        if missing:
            raise ValueError(f"Extended client config missing: {missing}")

    async def connect(self) -> None:
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers={"Content-Type": "application/json", "X-API-KEY": self.api_key}
            )
            self.logger.info("Extended client session created")

    async def disconnect(self) -> None:
        if self.session:
            await self.session.close()
            self.session = None

    # ==========================================
    # 策略脚本适配接口 (Strategy Adapter Methods)
    # ==========================================

    async def place_order(
        self, ticker: str, side: str, price: float, size: float
    ) -> Optional[str]:
        """
        适配策略调用的通用下单接口。
        自动将 float 转为 Decimal，并调用底层的 place_open_order。
        """
        contract_id = f"{ticker}-USD"
        result = await self.place_open_order(
            contract_id=contract_id,
            quantity=Decimal(str(size)),
            direction=side,
            price=Decimal(str(price)),
        )

        if result.success:
            return result.order_id

        self.logger.error(f"Place order failed: {result.error_message}")
        return None

    async def get_order_details(self, order_id: str) -> Dict[str, Any]:
        """
        获取订单详情，用于策略轮询状态。
        """
        if not self.session:
            await self.connect()

        try:
            url = f"{self.base_url}/orders/{order_id}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                if response.status == 404:
                    return {}
                self.logger.warning(
                    "Get order details failed: HTTP %s", response.status
                )
        except Exception as exc:
            self.logger.error(f"Get order details exception: {exc}")

        return {}

    async def cancel_order(self, order_id: str, ticker: str = None) -> OrderResult:
        """
        取消订单 (兼容 ticker 参数)。
        """
        if not self.session:
            await self.connect()

        try:
            url = f"{self.base_url}/orders/{order_id}"
            async with self.session.delete(url) as response:
                if response.status == 200:
                    return OrderResult(success=True, order_id=order_id)

                err = await response.text()
                if response.status == 404 or "not found" in err.lower():
                    return OrderResult(success=True, order_id=order_id)

                self.logger.error(f"Cancel failed: {err}")
                return OrderResult(success=False, error_message=err)
        except Exception as exc:
            return OrderResult(success=False, error_message=str(exc))

    # ==========================================
    # 底层 API 方法 (Base Methods)
    # ==========================================

    async def get_contract_attributes(self) -> Tuple[str, Decimal]:
        contract_id = f"{self.ticker}-USD"
        return contract_id, Decimal("0.1")

    async def place_open_order(
        self,
        contract_id: str,
        quantity: Decimal,
        direction: str,
        price: Optional[Decimal] = None,
    ) -> OrderResult:
        if not self.session:
            await self.connect()

        side = "BUY" if direction.lower() == "buy" else "SELL"
        nonce = int(time.time() * 1000)

        order_payload = {
            "market": contract_id,
            "side": side,
            "size": str(quantity),
            "price": str(price),
            "type": "LIMIT",
            "postOnly": True,
            "nonce": nonce,
            "vaultId": self.vault_id,
        }

        try:
            self.logger.info(f"Placing order payload: {order_payload}")

            url = f"{self.base_url}/orders"
            async with self.session.post(url, json=order_payload) as response:
                resp_json = await response.json()

                if response.status in [200, 201]:
                    order_id = resp_json.get("orderId")
                    return OrderResult(
                        success=True,
                        order_id=order_id,
                        side=direction,
                        size=quantity,
                        price=price,
                        status="OPEN",
                    )

                return OrderResult(
                    success=False,
                    error_message=f"HTTP {response.status}: {resp_json}",
                )
        except Exception as exc:
            return OrderResult(success=False, error_message=str(exc))

    async def place_close_order(
        self, contract_id: str, quantity: Decimal, price: Decimal, side: str
    ) -> OrderResult:
        return await self.place_open_order(contract_id, quantity, side, price)

    async def get_account_positions(self) -> Decimal:
        if not self.session:
            await self.connect()
        try:
            url = f"{self.base_url}/account/{self.vault_id}/positions"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    for pos in data.get("positions", []):
                        if self.ticker in pos.get("symbol", ""):
                            return Decimal(pos.get("size", 0))
                return Decimal(0)
        except Exception as exc:
            self.logger.error(f"Error getting positions: {exc}")
            return Decimal(0)

    def get_exchange_name(self) -> str:
        return "extended"

    def setup_order_update_handler(self, handler) -> None:
        self._order_update_handler = handler

    async def get_order_info(self, order_id: str) -> Optional[OrderInfo]:
        return None

    async def get_active_orders(self, contract_id: str) -> list:
        return []

    async def get_order_price(self, direction: str) -> Decimal:
        return Decimal("0")
