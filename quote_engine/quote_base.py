from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class L1_Tick:
    symbol: str  # Trading pair, for example "BTCUSDT"
    exchange_time: int  # Timestamp when the exchange generated this event, in milliseconds
    local_time: int  # Timestamp when this event was received locally, used to monitor network latency
    bid_price: float  # Best bid price
    bid_size: float  # Order size resting at the best bid
    ask_price: float  # Best ask price
    ask_size: float  # Order size resting at the best ask

    @property
    def spread(self) -> float:
        """Derived metric: bid-ask spread."""
        return self.ask_price - self.bid_price

    @property
    def mid_price(self) -> float:
        """Derived metric: mid price, commonly used in microstructure modeling."""
        return (self.ask_price + self.bid_price) / 2.0
    
    @property
    def micro_price(self) -> float:
        """
        Derived metric: Stoikov's Micro-price.
        A cross-volume-weighted price that anticipates short-term directional breaks.
        """
        total_size = self.bid_size + self.ask_size
        
        # Edge case handling: If the order book entirely empties on one side 
        # (circuit breaker or extreme illiquidity), fallback to the mid-price.
        if total_size == 0.0:
            return self.mid_price
            
        return (self.ask_price * self.bid_size + self.bid_price * self.ask_size) / total_size

    @property
    def order_book_imbalance(self) -> float:
        """
        Derived metric: Order Book Imbalance (OBI).
        Ranges from -1.0 (pure selling pressure) to 1.0 (pure buying pressure).
        """
        total_size = self.bid_size + self.ask_size
        if total_size == 0.0:
            return 0.0
            
        return (self.bid_size - self.ask_size) / total_size

@dataclass
class L2_Snapshot:
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
class L2_OrderBook:
    symbol: str
    timestamp: int | None
    nonce: int | None
    bids_px: list
    bids_qty: list
    asks_px: list
    asks_qty: list

    def deep_micro_price(self, depth: int = 10) -> float:
        # Corrected to use bids_px, asks_px, etc.
        actual_depth = min(depth, len(self.bids_px), len(self.asks_px))
        
        if actual_depth == 0:
            return 0.0

        numerator = 0.0
        total_volume = 0.0

        for i in range(actual_depth):
            bid_price, bid_size = self.bids_px[i], self.bids_qty[i]
            ask_price, ask_size = self.asks_px[i], self.asks_qty[i]

            numerator += (ask_price * bid_size) + (bid_price * ask_size)
            total_volume += (bid_size + ask_size)

        if total_volume == 0.0:
            return (self.bids_px[0] + self.asks_px[0]) / 2.0

        return numerator / total_volume

    def deep_imbalance(self, depth: int = 10) -> float:
        actual_depth = min(depth, len(self.bids_qty), len(self.asks_qty))
        
        if actual_depth == 0:
            return 0.0
            
        bid_vol = sum(self.bids_qty[:actual_depth])
        ask_vol = sum(self.asks_qty[:actual_depth])
        
        total_vol = bid_vol + ask_vol
        if total_vol == 0.0:
            return 0.0
            
        return (bid_vol - ask_vol) / total_vol

@dataclass
class L2_Transaction:
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
class L3_Order:
    side: str
    price: float
    amount: float


@dataclass(slots=True)
class PerpetualMetrics:
    """
    Tracks the systemic leverage and sentiment of the derivative market.
    Can be used for funding rate arbitrage and predicting liquidations.
    """
    symbol: str
    timestamp: int
    mark_price: float           # The price used for liquidation calculations
    index_price: float          # The underlying spot index price
    funding_rate: float         # Current funding rate (e.g., 0.0001 = 0.01%)
    predicted_funding_rate: float | None # Estimated next funding rate
    open_interest: float | None # Total outstanding contracts. Spikes indicate high leverage.


@dataclass(slots=True)
class LiquidationEvent:
    """
    A forced market execution by the exchange's risk engine.
    When a cascade of these occurs, your model should step in to provide liquidity at a premium.
    """
    symbol: str
    side: str           # "buy" (a short got liquidated) or "sell" (a long got liquidated)
    price: float        # The bankruptcy/execution price
    quantity: float     # Size of the liquidated position
    timestamp: int


@dataclass
class MarketQuote:
    market_type: str # "spot" or "futures"
    snapshot: L2_Snapshot | None
    transaction: L2_Transaction | None
    order: L3_Order | None
    order_book: L2_OrderBook | None
    perpetual_metrics: PerpetualMetrics | None
    liquidation: LiquidationEvent | None


class QuoteEngineCallback(ABC):
    @abstractmethod
    async def on_snapshot(self, snapshot: L2_Snapshot) -> None:
        pass

    @abstractmethod
    async def on_transaction(self, transaction: L2_Transaction | None) -> None:
        pass

    @abstractmethod
    async def on_order(self, order: L3_Order | None) -> None:
        pass

    @abstractmethod
    async def on_order_book(self, order_book: L2_OrderBook) -> None:
        pass

    @abstractmethod
    async def on_perpetual_metrics(self, metrics: PerpetualMetrics) -> None:
        """
        Triggered when Funding Rate, Mark Price, or Open Interest updates.
        Critical for recalculating your carry costs.
        """
        pass

    @abstractmethod
    async def on_liquidation(self, liquidation: LiquidationEvent) -> None:
        """
        Triggered when the exchange force-liquidates a trader.
        Use this to feed momentum exhaustion factors into LightGBM.
        """
        pass
