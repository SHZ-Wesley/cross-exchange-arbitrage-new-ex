import asyncio
import sys
import argparse
import os
from decimal import Decimal
import dotenv

from strategy.edgex_arb import EdgexArb
from strategy.extended_arb import ExtendedArb

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Cross-Exchange Arbitrage Bot Entry Point',
        formatter_class=argparse.RawDescriptionHelpFormatter
        )

    parser.add_argument('--exchange', type=str, default='edgex',
                        help='Exchange to use (edgex or extended)')
    parser.add_argument('--ticker', type=str, default='BTC',
                        help='Ticker symbol (default: BTC)')
    parser.add_argument('--size', type=str, required=True,
                        help='Number of tokens to buy/sell per order')
    parser.add_argument('--fill-timeout', type=int, default=5,
                        help='Timeout in seconds for maker order fills (default: 5)')
    parser.add_argument('--max-position', type=Decimal, default=Decimal('0'),
                        help='Maximum position to hold (default: 0)')
    parser.add_argument('--long-threshold', type=Decimal, default=Decimal('10'),
                        help='Long threshold (default: 10)')
    parser.add_argument('--short-threshold', type=Decimal, default=Decimal('10'),
                        help='Short threshold (default: 10)')
    return parser.parse_args()

async def main():
    args = parse_arguments()
    dotenv.load_dotenv()

    # Dispatch strategy
    if args.exchange.lower() == 'edgex':
        bot = EdgexArb(
            ticker=args.ticker.upper(),
            order_quantity=Decimal(args.size),
            fill_timeout=args.fill_timeout,
            max_position=args.max_position,
            long_ex_threshold=Decimal(args.long_threshold),
            short_ex_threshold=Decimal(args.short_threshold)
        )
    elif args.exchange.lower() == 'extended':
        extended_api_key = os.getenv("EXTENDED_API_KEY")
        extended_private_key = os.getenv("EXTENDED_PRIVATE_KEY")
        extended_vault = os.getenv("EXTENDED_VAULT")

        lighter_private_key = os.getenv("API_KEY_PRIVATE_KEY")
        lighter_api_key_index = int(os.getenv("LIGHTER_API_KEY_INDEX", 0))
        lighter_api_key = os.getenv("LIGHTER_API_KEY", "")

        if not all([extended_api_key, extended_private_key, extended_vault, lighter_private_key]):
            print("错误: 缺少 Extended 或 Lighter 交易所的环境变量配置。请检查 .env 文件。")
            return 1

        bot = ExtendedArb(
            extended_api_key=extended_api_key,
            extended_stark_private_key=extended_private_key,
            extended_vault=extended_vault,
            lighter_api_key=lighter_api_key,
            lighter_private_key=lighter_private_key,
            lighter_api_key_index=lighter_api_key_index,
            ticker=args.ticker.upper(),
            size=args.size,
            fill_timeout=args.fill_timeout,
            max_position=args.max_position,
            long_ex_threshold=args.long_threshold,
            short_ex_threshold=args.short_threshold
        )
    else:
        print(f"不支持的交易所: {args.exchange}")
        return 1

    try:
        await bot.run()
    except KeyboardInterrupt:
        print("\n用户中断程序")
    except Exception as e:
        print(f"发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
