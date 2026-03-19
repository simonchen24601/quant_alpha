"""
Kraken Pro quote adaptor implementation
    reference: https://docs.kraken.com/api/
"""
import asyncio
import json
import logging
from typing import Any
import websockets

from .quote_base import L3_Order, L2_OrderBook, Transaction, QuoteEngineCallback, L2_Snapshot
# Assuming _QueueEvent and _NullQuoteCallback are imported or defined in the same file

logger = logging.getLogger(__name__)

class KrakenQuoteEngine:
    PROD_STREAM_BASE = "wss://ws.kraken.com/v2"
    
    # Kraken uses standard fiat tickers. Crucial for your Tripartite setup.
    SYMBOL_ALIASES = {
        "BTC_CAD": "BTC/CAD",
        "ETH_CAD": "ETH/CAD",
        "USDC_CAD": "USDC/CAD",
    }

    def __init__(
        self,
        timeout_ms: int = 10000,
        callback: QuoteEngineCallback | None = None,
        assets: tuple[str, ...] = ("BTC_CAD", "USDC_CAD"),
        depth_levels: int = 10,
        include_transactions: bool = True,
        queue_maxsize: int = 10000,
        reconnect_initial_delay: float = 1.0,
        reconnect_max_delay: float = 30.0,
    ):
        self.timeout_ms = timeout_ms
        self._callback = callback if callback is not None else _NullQuoteCallback()
        self.assets = assets
        self.depth_levels = depth_levels
        self.include_transactions = include_transactions
        self.queue_maxsize = queue_maxsize
        self.reconnect_initial_delay = reconnect_initial_delay
        self.reconnect_max_delay = reconnect_max_delay
        
        self.ws_url = self.PROD_STREAM_BASE
        self._running = False
        self._queue: asyncio.Queue[_QueueEvent | None] | None = None
        self._consumer_task: asyncio.Task[None] | None = None
        self._websocket: Any = None
        self._dropped_events = 0

    def _normalize_symbols(self) -> list[str]:
        return [self.SYMBOL_ALIASES.get(a.strip().upper(), a) for a in self.assets]

    async def _subscribe(self) -> None:
        """Kraken V2 requires explicit JSON subscription payloads after connection."""
        symbols = self._normalize_symbols()
        
        # Subscribe to L2 Orderbook
        book_sub = {
            "method": "subscribe",
            "params": {
                "channel": "book",
                "symbol": symbols,
                "depth": self.depth_levels
            }
        }
        await self._websocket.send(json.dumps(book_sub))

        # Subscribe to Public Trades
        if self.include_transactions:
            trade_sub = {
                "method": "subscribe",
                "params": {
                    "channel": "trade",
                    "symbol": symbols
                }
            }
            await self._websocket.send(json.dumps(trade_sub))

    def _to_order_book(self, payload: dict[str, Any]) -> OrderBook:
        # Kraken V2 payload data is a list
        data = payload.get("data", [{}])[0]
        symbol = data.get("symbol", "")
        
        bids = [Order(side="bid", price=float(item["price"]), amount=float(item["qty"])) for item in data.get("bids", [])]
        asks = [Order(side="ask", price=float(item["price"]), amount=float(item["qty"])) for item in data.get("asks", [])]

        return OrderBook(
            symbol=symbol,
            timestamp=data.get("timestamp"),
            datetime=None,
            nonce=data.get("checksum"),
            bids=bids,
            asks=asks,
        )

    def _to_transaction(self, payload: dict[str, Any]) -> Transaction:
        data = payload.get("data", [{}])[0]
        return Transaction(
            trade_id=str(data.get("trade_id", "")),
            order_id=None,
            side=data.get("side"),
            price=float(data["price"]) if data.get("price") else None,
            amount=float(data["qty"]) if data.get("qty") else None,
            cost=(
                float(data["price"]) * float(data["qty"])
                if data.get("price") and data.get("qty")
                else None
            ),
            timestamp=data.get("timestamp"),
            datetime=None,
            fee=None,
            raw=payload,
        )

    # ... [Include identical _enqueue_event, _dispatch_event, _consume_events, close, aclose as Binance Base] ...

    async def _recv_loop(self) -> None:
        assert self._websocket is not None
        while self._running:
            try:
                raw_message = await self._websocket.recv()
                message: dict[str, Any] = json.loads(raw_message)
                
                channel = message.get("channel", "")
                
                if channel == "book":
                    self._enqueue_event(_QueueEvent("order_book", self._to_order_book(message)))
                elif channel == "trade":
                    self._enqueue_event(_QueueEvent("transaction", self._to_transaction(message)))
                    
            except json.JSONDecodeError:
                continue
            except (asyncio.CancelledError, websockets.ConnectionClosed):
                raise

    async def run(self) -> None:
        self._running = True
        self._queue = asyncio.Queue(maxsize=self.queue_maxsize)
        self._consumer_task = asyncio.create_task(self._consume_events())
        reconnect_delay = self.reconnect_initial_delay

        try:
            while self._running:
                try:
                    async with websockets.connect(self.ws_url, max_size=None) as websocket:
                        self._websocket = websocket
                        reconnect_delay = self.reconnect_initial_delay
                        logger.info("Connected to Kraken stream.")
                        
                        await self._subscribe() # Crucial divergence from Binance
                        await self._recv_loop()
                        
                except (OSError, TimeoutError, websockets.WebSocketException):
                    if not self._running: break
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, self.reconnect_max_delay)
        finally:
            self._running = False
            if self._queue: await self._queue.put(None)
