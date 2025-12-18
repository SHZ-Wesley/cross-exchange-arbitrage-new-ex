import asyncio
import sys
import argparse
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
        bot = ExtendedArb(
            ticker=args.ticker.upper(),
            order_quantity=Decimal(args.size),
            fill_timeout=args.fill_timeout,
            max_position=args.max_position,
            long_ex_threshold=Decimal(args.long_threshold),
            short_ex_threshold=Decimal(args.short_threshold)
        )
    else:
        print(f"Unsupported exchange: {args.exchange}")
        return 1

    try:
        await bot.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
