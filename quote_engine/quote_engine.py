from __future__ import annotations
from typing import Any

import argparse
import json
import sys


def run() -> None:
	parser = argparse.ArgumentParser(description="Fetch a market quote from Binance with CCXT.")
	parser.add_argument("symbol", nargs="?", default="BTC/USDT", help="Market symbol, for example BTC/USDT")
	parser.add_argument("--sandbox", action="store_true", help="Use Binance sandbox endpoints")
	parser.add_argument("--timeout-ms", type=int, default=10000, help="HTTP timeout in milliseconds")
	parser.add_argument("--order-book-limit", type=int, default=5, help="Number of bid and ask levels to fetch")
	parser.add_argument("--trade-limit", type=int, default=1, help="Number of recent trades to fetch")
	args = parser.parse_args()

	engine = BinanceQuoteEngine(
		sandbox=args.sandbox,
		timeout_ms=args.timeout_ms,
		callback=PrintQuoteCallback(),
	)
	try:
		engine.connect()
		engine.process_quote(
			args.symbol,
			order_book_limit=args.order_book_limit,
			trade_limit=args.trade_limit,
		)
	finally:
		engine.close()


if __name__ == "__main__":
	run()
