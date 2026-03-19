from .quote_base import Order, Transaction, OrderBook


class LogQuoteSink:
    """
    TODO: log to a file for debugging
    """
    def __init__(self, log_file: str):
        pass

    def on_order_book(self, order_book: OrderBook):
        pass

    def on_order(self, order: Order):
        pass

    def on_transaction(self, transaction: Transaction):
        pass


class PostgresQuoteSink:
    """
    TODO: write to Postgres 
    """
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        pass

    def on_order_book(self, order_book: OrderBook):
        pass

    def on_order(self, order: Order):
        pass

    def on_transaction(self, transaction: Transaction):
        pass


class ClickhouseQuoteSink:
    """
    TODO: A quote sink that writes to ClickHouse
    """
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        pass

    def on_order_book(self, order_book: OrderBook):
        pass

    def on_order(self, order: Order):
        pass

    def on_transaction(self, transaction: Transaction):
        pass


class RedisQuoteSink:
    """
    TODO: A quote sink that writes to Redis.
    """
    def __init__(self, host: str, port: int, password: str, database: int):
        pass

    def on_order_book(self, order_book: OrderBook):
        pass

    def on_order(self, order: Order):
        pass

    def on_transaction(self, transaction: Transaction):
        pass


class ProtobufZmqQuoteSink:
    """
    TODO: A quote sink that serializes data using Protobuf and sends it over ZeroMQ.
    """
    def __init__(self, zmq_endpoint: str):
        pass

    def on_order_book(self, order_book: OrderBook):
        pass

    def on_order(self, order: Order):
        pass

    def on_transaction(self, transaction: Transaction):
        pass
