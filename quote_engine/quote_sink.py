from .quote_base import Order, Transaction, OrderBook


class LogQuoteSink:
    def __init__(self, log_file: str):
        pass

    def on_order_book(self, order_book: OrderBook):
        pass

    def on_order(self, order: Order):
        pass

    def on_transaction(self, transaction: Transaction):
        pass


class PostgresQuoteSink:
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        pass

    def on_order_book(self, order_book: OrderBook):
        pass

    def on_order(self, order: Order):
        pass

    def on_transaction(self, transaction: Transaction):
        pass


class ClickhouseQuoteSink:
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        pass

    def on_order_book(self, order_book: OrderBook):
        pass

    def on_order(self, order: Order):
        pass

    def on_transaction(self, transaction: Transaction):
        pass
