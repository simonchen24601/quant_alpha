from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class L1Tick:
    symbol: str  # Trading pair, for example "BTCUSDT"
    exchange_time: int  # Timestamp when the exchange generated this event, in milliseconds
    local_time: int  # Timestamp when this event was received locally, used to monitor network latency
    bid_price: float  # Best bid price
    bid_size: float  # Order size resting at the best bid
    ask_price: float  # Best ask price
    ask_size: float  # Order size resting at the best ask

    # @classmethod
    # def from_binance_bookticker(cls, payload: Dict[str, Any], local_ts: int = None) -> "Level1Tick":
    #     """
    #     Parse L1 data from a Binance @bookTicker websocket payload.
    #     Example Binance bookTicker format:
    #     {"u":400900217,"s":"BTCUSDT","b":"60000.00","B":"3.12","a":"60000.01","A":"4.06"}
    #     Note: the bookTicker payload itself does not include timestamp E,
    #     so it usually relies on local time or another layer in the stream.
    #     """
    #     return cls(
    #         symbol=payload["s"],
    #         exchange_time=payload.get("E", 0), # bookTicker may not have E; in combined streams it may exist at the outer layer
    #         local_time=local_ts or int(time.time() * 1000),
    #         bid_price=float(payload["b"]),
    #         bid_size=float(payload["B"]),
    #         ask_price=float(payload["a"]),
    #         ask_size=float(payload["A"])
    #     )

    @property
    def spread(self) -> float:
        """Derived metric: bid-ask spread."""
        return self.ask_price - self.bid_price

    @property
    def mid_price(self) -> float:
        """Derived metric: mid price, commonly used in microstructure modeling."""
        return (self.ask_price + self.bid_price) / 2.0


@dataclass
class Snapshot:
    exchange: str
    symbol: str
    open: float | None
    bid: float | None
    ask: float | None
    last: float | None
    close: float | None
    high: float | None
    low: float | None
    base_volume: float | None
    quote_volume: float | None
    timestamp: int | None
    datetime: str | None


@dataclass
class Transaction:
    trade_id: str | None
    order_id: str | None
    side: str | None
    price: float | None
    amount: float | None
    cost: float | None
    timestamp: int | None
    datetime: str | None
    fee: dict[str, Any] | None
    raw: dict[str, Any]


@dataclass
class Order:
    side: str
    price: float
    amount: float


@dataclass
class OrderBook:
    symbol: str
    timestamp: int | None
    datetime: str | None
    nonce: int | None
    bids: list[Order]
    asks: list[Order]


@dataclass
class MarketQuote:
    snapshot: Snapshot
    transaction: Transaction | None
    order: Order | None
    order_book: OrderBook


class QuoteEngineCallback(ABC):
    @abstractmethod
    async def on_snapshot(self, snapshot: Snapshot) -> None:
        pass

    @abstractmethod
    async def on_transaction(self, transaction: Transaction | None) -> None:
        pass

    @abstractmethod
    async def on_order(self, order: Order | None) -> None:
        pass

    @abstractmethod
    async def on_order_book(self, order_book: OrderBook) -> None:
        pass
