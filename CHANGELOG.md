# Changelog

## Unreleased

### Changed
- Refactored `BinanceQuoteEngine` in `quote_engine/quote_adaptor_biniance.py` to use a supervised websocket worker with automatic reconnect and exponential backoff.
- Decoupled websocket reads from downstream callbacks with a bounded `asyncio.Queue` to reduce the impact of slow consumers.
- Added graceful shutdown support by actively closing the websocket and providing `aclose()` for async callers.
- Isolated callback failures so malformed messages or downstream exceptions no longer terminate the main receive loop.
- Replaced the default `None` callback with a no-op callback implementation intended for runtime use.
