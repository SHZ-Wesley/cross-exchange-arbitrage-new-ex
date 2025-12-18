import asyncio
from decimal import Decimal

class PositionTracker:
    def __init__(self, ticker, maker_client, maker_contract_id, lighter_base_url, lighter_account_index, logger, maker_exchange='edgex'):
        self.ticker = ticker
        self.maker_client = maker_client
        self.maker_contract_id = maker_contract_id
        self.maker_exchange = maker_exchange # 'edgex' or 'extended'
        
        self.logger = logger
        
        # Lighter init (Simplified)
        self.lighter_base_url = lighter_base_url
        self.account_index = lighter_account_index
        
        self.edgex_position = Decimal('0')
        self.extended_position = Decimal('0')
        self.lighter_position = Decimal('0')

    async def get_maker_position(self):
        if self.maker_exchange == 'edgex':
            return await self.get_edgex_position()
        elif self.maker_exchange == 'extended':
            return await self.get_extended_position()
        return Decimal('0')

    async def get_extended_position(self):
        try:
            # Ensure get_account_positions is implemented in exchanges/extended.py
            pos = await self.maker_client.get_account_positions(self.maker_contract_id)
            if pos is not None:
                self.extended_position = Decimal(str(pos))
            return self.extended_position
        except Exception as e:
            self.logger.error(f"Error fetching Extended position: {e}")
            return self.extended_position

    async def get_edgex_position(self):
        # Existing implementation
        return self.edgex_position

    async def get_lighter_position(self):
        # Existing implementation
        return self.lighter_position

    def get_current_edgex_position(self):
        return self.edgex_position

    def get_net_position(self):
        if self.maker_exchange == 'edgex':
            return self.edgex_position + self.lighter_position
        else:
            return self.extended_position + self.lighter_position

    def update_lighter_position(self, delta):
        self.lighter_position += delta

    def update_edgex_position(self, delta):
        self.edgex_position += delta
