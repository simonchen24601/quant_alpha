import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

import websockets

from .quote_base import Order, OrderBook, QuoteEngineCallback, L2_Snapshot, Transaction

logger = logging.getLogger(__name__)


class _NullQuoteCallback(QuoteEngineCallback):
    async def on_snapshot(self, snapshot: L2_Snapshot) -> None:
        return None

    async def on_transaction(self, transaction: Transaction | None) -> None:
        return None

    async def on_order(self, order: Order | None) -> None:
        return None

    async def on_order_book(self, order_book: OrderBook) -> None:
        return None


@dataclass(slots=True)
class _QueueEvent:
    event_type: str
    payload: OrderBook | Transaction


class BinanceQuoteEngine:
    PROD_STREAM_BASE = "wss://fstream.binance.com/stream"
    TESTNET_STREAM_BASE = "wss://stream.binancefuture.com/stream"
    SYMBOL_ALIASES = {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
    }

    def __init__(
        self,
        sandbox: bool = False,
        timeout_ms: int = 10000,
        callback: QuoteEngineCallback | None = None,
        assets: tuple[str, ...] = ("BTC", "ETH"),
        depth_levels: int = 20,
        update_interval_ms: int = 100,
        include_transactions: bool = True,
        queue_maxsize: int = 10000,
        reconnect_initial_delay: float = 1.0,
        reconnect_max_delay: float = 30.0,
    ):
        self.sandbox = sandbox
        self.timeout_ms = timeout_ms
        self.set_callback(callback)
        self.assets = assets
        self.depth_levels = depth_levels
        self.update_interval_ms = update_interval_ms
        self.include_transactions = include_transactions
        self.queue_maxsize = queue_maxsize
        self.reconnect_initial_delay = reconnect_initial_delay
        self.reconnect_max_delay = reconnect_max_delay
        self.ws_url: str | None = None
        self._running = False
        self._queue: asyncio.Queue[_QueueEvent | None] | None = None
        self._consumer_task: asyncio.Task[None] | None = None
        self._websocket: Any = None
        self._dropped_events = 0

    def set_callback(self, callback: QuoteEngineCallback | None) -> None:
        self._callback = callback if callback is not None else _NullQuoteCallback()

    def _build_streams(self) -> list[str]:
        def _normalize_symbol(asset: str) -> str:
            key = asset.strip().upper()
            if key.endswith("USDT"):
                return key
            return self.SYMBOL_ALIASES.get(key, f"{key}USDT")

        streams: list[str] = []
        for asset in self.assets:
            symbol = _normalize_symbol(asset).lower()
            streams.append(f"{symbol}@depth{self.depth_levels}@{self.update_interval_ms}ms")
            if self.include_transactions:
                streams.append(f"{symbol}@aggTrade")
        return streams

    def connect(self) -> str:
        stream_base = self.TESTNET_STREAM_BASE if self.sandbox else self.PROD_STREAM_BASE
        streams = "/".join(self._build_streams())
        self.ws_url = f"{stream_base}?streams={quote_plus(streams, safe='/@')}"
        return self.ws_url

    def _to_order_book(self, payload: dict[str, Any], stream_name: str = "") -> OrderBook:
        symbol = payload.get("s")
        if not symbol and stream_name:
            symbol = stream_name.split("@")[0].upper()

        bids = [Order(side="bid", price=float(price), amount=float(size)) for price, size in payload.get("b", [])]
        asks = [Order(side="ask", price=float(price), amount=float(size)) for price, size in payload.get("a", [])]

        return OrderBook(
            symbol=symbol or "",
            timestamp=payload.get("E") or payload.get("T"),
            datetime=None,
            nonce=payload.get("u") or payload.get("lastUpdateId"),
            bids=bids,
            asks=asks,
        )

    def _to_transaction(self, payload: dict[str, Any]) -> Transaction:
        return Transaction(
            trade_id=str(payload.get("a") or payload.get("t") or payload.get("f") or ""),
            order_id=None,
            side="sell" if payload.get("m") else "buy",
            price=float(payload["p"]) if payload.get("p") is not None else None,
            amount=float(payload["q"]) if payload.get("q") is not None else None,
            cost=(
                float(payload["p"]) * float(payload["q"])
                if payload.get("p") is not None and payload.get("q") is not None
                else None
            ),
            timestamp=payload.get("E") or payload.get("T"),
            datetime=None,
            fee=None,
            raw=payload,
        )

    def _enqueue_event(self, event: _QueueEvent) -> None:
        if self._queue is None:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._dropped_events += 1
            logger.warning(
                "Event queue full; dropping %s event (dropped=%s, maxsize=%s)",
                event.event_type,
                self._dropped_events,
                self.queue_maxsize,
            )

    async def _dispatch_event(self, event: _QueueEvent) -> None:
        try:
            if event.event_type == "order_book":
                await self._callback.on_order_book(event.payload)  # type: ignore[arg-type]
            elif event.event_type == "transaction":
                await self._callback.on_transaction(event.payload)  # type: ignore[arg-type]
        except Exception:
            logger.exception("Callback failed for %s event", event.event_type)

    async def _consume_events(self) -> None:
        assert self._queue is not None
        while True:
            event = await self._queue.get()
            try:
                if event is None:
                    return
                await self._dispatch_event(event)
            finally:
                self._queue.task_done()

    async def _recv_loop(self) -> None:
        assert self._websocket is not None
        while self._running:
            try:
                raw_message = await self._websocket.recv()
            except asyncio.CancelledError:
                raise
            except websockets.ConnectionClosed as exc:
                logger.warning("WebSocket connection closed: code=%s reason=%s", exc.code, exc.reason)
                raise

            try:
                message: dict[str, Any] = json.loads(raw_message)
            except json.JSONDecodeError:
                logger.exception("Failed to decode websocket message")
                continue

            stream_name = message.get("stream", "")
            payload = message.get("data", message)
            event_type = payload.get("e")

            if "@depth" in stream_name or event_type == "depthUpdate":
                self._enqueue_event(_QueueEvent("order_book", self._to_order_book(payload, stream_name)))
            elif "@aggTrade" in stream_name or event_type in ("aggTrade", "trade"):
                self._enqueue_event(_QueueEvent("transaction", self._to_transaction(payload)))
            else:
                logger.debug("Ignoring unsupported event type from stream=%s event=%s", stream_name, event_type)

    async def _close_websocket(self) -> None:
        if self._websocket is None:
            return
        websocket = self._websocket
        self._websocket = None
        try:
            await websocket.close()
        except Exception:
            logger.exception("Failed to close websocket cleanly")

    async def run(self) -> None:
        ws_url = self.ws_url or self.connect()
        self._running = True
        self._queue = asyncio.Queue(maxsize=self.queue_maxsize)
        self._consumer_task = asyncio.create_task(self._consume_events())
        reconnect_delay = self.reconnect_initial_delay

        try:
            while self._running:
                try:
                    async with websockets.connect(
                        ws_url,
                        open_timeout=self.timeout_ms / 1000,
                        ping_interval=120,
                        ping_timeout=600,
                        close_timeout=10,
                        max_queue=1024,
                    ) as websocket:
                        self._websocket = websocket
                        reconnect_delay = self.reconnect_initial_delay
                        logger.info("Connected to Binance stream: %s", ws_url)
                        await self._recv_loop()
                except asyncio.CancelledError:
                    raise
                except (OSError, TimeoutError, websockets.WebSocketException):
                    if not self._running:
                        break
                    logger.exception("Binance websocket loop failed; reconnecting in %.1fs", reconnect_delay)
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, self.reconnect_max_delay)
                finally:
                    await self._close_websocket()
        finally:
            self._running = False
            if self._queue is not None:
                await self._queue.put(None)
            if self._consumer_task is not None:
                await self._consumer_task
                self._consumer_task = None
            self._queue = None

    def close(self) -> None:
        self._running = False
        if self._websocket is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._close_websocket())

    async def aclose(self) -> None:
        self.close()
        while self._websocket is not None:
            await asyncio.sleep(0)

    def run_forever(self) -> None:
        asyncio.run(self.run())
