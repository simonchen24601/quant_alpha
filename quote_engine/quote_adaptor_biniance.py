import asyncio
import json
from unittest import mock
import websockets
from urllib.parse import quote_plus
from typing import Any

from .quote_base import Order, OrderBook, QuoteEngineCallback, Transaction

PROD_STREAM_BASE = "wss://fstream.binance.com/stream"
TESTNET_STREAM_BASE = "wss://stream.binancefuture.com/stream"


class BinanceQuoteEngine:
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
    ):
        self.sandbox = sandbox
        self.timeout_ms = timeout_ms
        self.set_callback(callback)
        self.assets = assets
        self.depth_levels = depth_levels
        self.update_interval_ms = update_interval_ms
        self.include_transactions = include_transactions
        self.ws_url: str | None = None
        self._running = False

    def set_callback(self, callback: QuoteEngineCallback | None) -> None:
        if callback is None:
            self._callback = mock.AsyncMock(spec=QuoteEngineCallback)
        else:
            self._callback = callback

    def _build_streams(self) -> list[str]:
        def _normalize_symbol(self, asset: str) -> str:
            key = asset.strip().upper()
            if key.endswith("USDT"):
                return key
            return self.SYMBOL_ALIASES.get(key, f"{key}USDT")

        streams: list[str] = []
        for asset in self.assets:
            symbol = self._normalize_symbol(asset).lower()
            streams.append(f"{symbol}@depth{self.depth_levels}@{self.update_interval_ms}ms")
            if self.include_transactions:
                streams.append(f"{symbol}@aggTrade")
        return streams

    def connect(self):
        stream_base = self.TESTNET_STREAM_BASE if self.sandbox else self.PROD_STREAM_BASE
        streams = "/".join(self._build_streams())
        self.ws_url = f"{stream_base}?streams={quote_plus(streams, safe='/@')}"
        return self.ws_url

    def _to_order_book(self, payload: dict[str, Any], stream_name: str = "") -> OrderBook:
        # Partial depth payloads sometimes omit the symbol "s", so we extract it from the stream name
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

    async def run(self) -> None:
        ws_url = self.ws_url or self.connect()
        self._running = True

        async with websockets.connect(
            ws_url,
            open_timeout=self.timeout_ms / 1000,
            ping_interval=120,
            ping_timeout=600,
            close_timeout=10,
            max_queue=1024,  # Note: max_queue may trigger a warning in websockets >= 14.0
        ) as websocket:
            while self._running:
                raw_message = await websocket.recv()
                message = json.loads(raw_message)

                # Unwrap the combined stream payload
                stream_name = message.get("stream", "")
                payload = message.get("data", message)
                event_type = payload.get("e")

                # Check stream_name because partial depth streams lack an "e" field
                if "@depth" in stream_name or event_type == "depthUpdate":
                    order_book = self._to_order_book(payload, stream_name)
                    await self._callback.on_order_book(order_book)
                elif "@aggTrade" in stream_name or event_type in ("aggTrade", "trade"):
                    transaction = self._to_transaction(payload)
                    await self._callback.on_transaction(transaction)

    def close(self) -> None:
        self._running = False

    def run_forever(self) -> None:
        asyncio.run(self.run())
