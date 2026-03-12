from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Order:
    order_id: str
    symbol: str
    qty: float
    price: float


@dataclass
class OrderStatus:
    order_id: str       # origin order id
    exch_order_id: str  # exchange order id
    status: str         # e.g. NEW, PARTIALLY_FILLED, FILLED, CANCELLED 
    filled_qty: float   # total filled quantity
    cancelled_qty: float    # total cancelled quantity
    total_qty: float    # total quantity
    match_price: float   # match price, price of the latest fill
    match_qty: float     # match quantity, quantity of the latest fill


@dataclass
class Position:
    symbol: str         # symbol of the position
    qty: float          # total quantity of the position
    avg_price: float    # average price of the position
    market_value: float # market value of the position
    unrealized_pnl: float   #   unrealized profit and loss of the position
    realized_pnl: float # realized profit and loss of the position


@dataclass
class Account:
    account_id: str
    balance: float
    available_funds: float
    equity: float
    margin: float
    unrealized_pnl: float
    realized_pnl: float


class TradeBase(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def send_order(self, order: Order):
        pass

    @abstractmethod
    def cancel_order(self, origin_order_id):
        pass

    @abstractmethod
    def qry_account(self):
        pass

    @abstractmethod
    def qry_order_status(self, order_id):
        pass

    @abstractmethod
    def qry_position(self, symbol):
        pass

    # callbacks

    def on_login(self):
        pass

    def on_logout(self):
        pass

    def on_order_ack(self, order: Order):
        pass

    def on_order_reject(self, order: Order, reason: str):
        pass

    def on_order_status(self, order_status: OrderStatus):
        pass

