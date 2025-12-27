"""Server module for Stock Sentinel."""

from stock_sentinel.server.webhook import app, run_server

__all__ = ["app", "run_server"]
