"""
NDAX quote adaptor implementation
    reference: https://apidoc.ndax.io/
    Candian Domestic Exchange, trades in CAD instead of USD, so symbols are like BTC/CAD instead of BTC/USD
"""
import asyncio
import json
import logging
from typing import Any

import websockets

from .quote_base import Order, OrderBook, Transaction, QuoteEngineCallback, L2_Snapshot
# Assuming _QueueEvent and _NullQuoteCallback are imported

logger = logging.getLogger(__name__)

class NdaxQuoteEngine:
    PROD_STREAM_BASE = "wss://api.ndax.io/WSGateway/"
    
    # NDAX/AlphaPoint Hardcoded Instrument IDs (Mandatory for subscription)
    INSTRUMENT_MAP = {
        "BTC_CAD": 1,
        "ETH_CAD": 2,
        "XRP_CAD": 3,
        "LTC_CAD": 4,
        "USDC_CAD": 24 
    }
    
    # Reverse map for parsing incoming data back to readable strings
    REVERSE_MAP = {v: k for k, v in INSTRUMENT_MAP.items()}

    def __init__(
        self,
        timeout_ms: int = 10000,
        callback: QuoteEngineCallback | None = None,
        assets: tuple[str, ...] = ("BTC_CAD",),
        depth_levels: int = 20,
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
        self._msg_id = 0

    def _get_msg_id(self) -> int:
        self._msg_id += 2
        return self._msg_id

    async def _subscribe(self) -> None:
        """AlphaPoint requires a highly specific frame format."""
        for asset in self.assets:
            instrument_id = self.INSTRUMENT_MAP.get(asset.strip().upper())
            if not instrument_id:
                logger.error(f"Unmapped NDAX asset: {asset}")
                continue

            # Level 2 Subscription Payload
            l2_payload = {
                "OMSId": 1,
                "InstrumentId": instrument_id,
                "Depth": self.depth_levels
            }
            sub_msg = {
                "m": 0, # Message Type 0 = Request
                "i": self._get_msg_id(),
                "n": "SubscribeLevel2",
                "o": json.dumps(l2_payload) # The inner payload MUST be a string
            }
            await self._websocket.send(json.dumps(sub_msg))

            # Public Trades Subscription Payload
            if self.include_transactions:
                trade_payload = {
                    "OMSId": 1,
                    "InstrumentId": instrument_id,
                    "IncludeLastCount": 10
                }
                trade_msg = {
                    "m": 0,
                    "i": self._get_msg_id(),
                    "n": "SubscribeTrades",
                    "o": json.dumps(trade_payload)
                }
                await self._websocket.send(json.dumps(trade_msg))

    def _to_order_book(self, payload: dict[str, Any]) -> OrderBook:
        # AlphaPoint pushes the payload inside the "o" key as a string.
        try:
            data = json.loads(payload.get("o", "{}"))
        except TypeError:
            data = payload.get("o", {})

        # Re-map the ID to a string
        instrument_id = data[0] if isinstance(data, list) and len(data) > 0 else data.get("InstrumentId")
        symbol = self.REVERSE_MAP.get(instrument_id, str(instrument_id))
        
        # NDAX formats books differently depending on if it's a snapshot or update.
        # This parses standard L2 updates.
        bids = [Order(side="bid", price=float(item[0]), amount=float(item[1])) for item in data.get("Bids", [])]
        asks = [Order(side="ask", price=float(item[0]), amount=float(item[1])) for item in data.get("Asks", [])]

        return OrderBook(
            symbol=symbol,
            timestamp=data.get("MDUpdateId"), # AlphaPoint uses sequence IDs
            datetime=None,
            nonce=None,
            bids=bids,
            asks=asks,
        )

    # ... [Include identical _enqueue_event, _dispatch_event, _consume_events, close, aclose as Base] ...

    async def _recv_loop(self) -> None:
        assert self._websocket is not None
        while self._running:
            try:
                raw_message = await self._websocket.recv()
                message: dict[str, Any] = json.loads(raw_message)
                
                # AlphaPoint event messages are type '3'
                if message.get("m") == 3:
                    event_name = message.get("n", "")
                    
                    if event_name == "Level2UpdateEvent":
                        self._enqueue_event(_QueueEvent("order_book", self._to_order_book(message)))
                    elif event_name == "TradeDataUpdateEvent":
                        # NDAX Trade processing logic here (similar JSON string extraction)
                        pass 
                        
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
                        logger.info("Connected to NDAX AlphaPoint stream.")
                        
                        await self._subscribe() 
                        await self._recv_loop()
                        
                except (OSError, TimeoutError, websockets.WebSocketException):
                    if not self._running: break
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, self.reconnect_max_delay)
        finally:
            self._running = False
            if self._queue: await self._queue.put(None)