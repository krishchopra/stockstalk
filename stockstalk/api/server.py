"""Flask API server for receiving SMS commands and sending updates."""

import logging
from typing import Any

from flask import Flask, jsonify, request

from stockstalk.models import WatchlistItem
from stockstalk.services.analyzer import StockAnalyzer
from stockstalk.services.data_fetcher import StockDataFetcher
from stockstalk.services.notifier import NotificationService
from stockstalk.utils.config import ConfigManager

logger = logging.getLogger(__name__)

app = Flask(__name__)


# Global variables to be initialized
config_manager: ConfigManager | None = None
stock_analyzer: StockAnalyzer | None = None


def init_app(config_mgr: ConfigManager, analyzer: StockAnalyzer) -> None:
    """
    Initialize the Flask app with dependencies.

    Args:
        config_mgr: Configuration manager
        analyzer: Stock analyzer
    """
    global config_manager, stock_analyzer
    config_manager = config_mgr
    stock_analyzer = analyzer


@app.route("/health", methods=["GET"])
def health() -> tuple[dict[str, str], int]:
    """Health check endpoint."""
    return jsonify({"status": "healthy"}), 200


@app.route("/api/stock/<symbol>", methods=["GET"])
def get_stock_info(symbol: str) -> tuple[dict[str, Any], int]:
    """
    Get current stock information and analysis.

    Args:
        symbol: Stock ticker symbol

    Returns:
        JSON response with stock data and analysis
    """
    if not stock_analyzer or not config_manager:
        return jsonify({"error": "Service not initialized"}), 500

    try:
        # Create a temporary watchlist item with all indicators
        from stockstalk.services.analyzer import IndicatorRegistry

        watchlist_item = WatchlistItem(
            symbol=symbol.upper(),
            enabled_indicators=IndicatorRegistry.list_indicators(),
        )

        # Analyze the stock
        results = stock_analyzer.analyze_stock(watchlist_item)

        # Format results
        response = {
            "symbol": symbol.upper(),
            "results": [
                {
                    "indicator": r.indicator_name,
                    "triggered": r.is_triggered,
                    "priority": r.priority.value,
                    "signal_strength": r.signal_strength,
                    "message": r.message,
                    "metadata": r.metadata,
                }
                for r in results
            ],
        }

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error analyzing stock {symbol}: {e}")
        return jsonify({"error": str(e)}), 400


@app.route("/api/watchlist", methods=["GET"])
def get_watchlist() -> tuple[dict[str, Any], int]:
    """
    Get current watchlist.

    Returns:
        JSON response with watchlist
    """
    if not config_manager:
        return jsonify({"error": "Service not initialized"}), 500

    try:
        config = config_manager.load_config()
        watchlist = [
            {
                "symbol": item.symbol,
                "indicators": item.enabled_indicators,
                "custom_params": item.custom_params,
            }
            for item in config.watchlist
        ]

        return jsonify({"watchlist": watchlist}), 200

    except Exception as e:
        logger.error(f"Error getting watchlist: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/sms", methods=["POST"])
def handle_sms() -> tuple[dict[str, str] | str, int]:
    """
    Handle incoming SMS messages (webhook from Twilio).

    Expects:
        - From: Phone number of sender
        - Body: Message text

    Returns:
        TwiML response
    """
    try:
        from_number = request.form.get("From", "")
        message_body = request.form.get("Body", "").strip().upper()

        logger.info(f"Received SMS from {from_number}: {message_body}")

        # Parse command
        parts = message_body.split()
        if not parts:
            return _create_twiml_response("Send 'HELP' for available commands.")

        command = parts[0]

        if command == "HELP":
            help_text = (
                "Commands:\n"
                "QUOTE <SYMBOL> - Get stock quote\n"
                "WATCHLIST - View watchlist\n"
                "ANALYZE <SYMBOL> - Full analysis"
            )
            return _create_twiml_response(help_text)

        elif command == "QUOTE" and len(parts) > 1:
            symbol = parts[1]
            try:
                data_fetcher = StockDataFetcher()
                stock_data = data_fetcher.get_current_data(symbol)
                response_text = (
                    f"{symbol}: ${stock_data.current_price:.2f} "
                    f"({((stock_data.current_price - stock_data.previous_close) / stock_data.previous_close * 100):+.2f}%)"
                )
                return _create_twiml_response(response_text)
            except Exception as e:
                return _create_twiml_response(f"Error fetching {symbol}: {str(e)}")

        elif command == "WATCHLIST":
            if config_manager:
                config = config_manager.load_config()
                symbols = [item.symbol for item in config.watchlist]
                response_text = f"Watching: {', '.join(symbols)}"
                return _create_twiml_response(response_text)
            else:
                return _create_twiml_response("Service not available")

        elif command == "ANALYZE" and len(parts) > 1:
            symbol = parts[1]
            # This would trigger a full analysis and send results
            return _create_twiml_response(
                f"Analyzing {symbol}... Results will be sent shortly."
            )

        else:
            return _create_twiml_response(
                f"Unknown command: {command}. Send 'HELP' for available commands."
            )

    except Exception as e:
        logger.error(f"Error handling SMS: {e}")
        return _create_twiml_response("Error processing request")


def _create_twiml_response(message: str) -> tuple[str, int]:
    """
    Create TwiML response for SMS.

    Args:
        message: Message to send

    Returns:
        TwiML XML response
    """
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{message}</Message>
</Response>"""
    return twiml, 200, {"Content-Type": "text/xml"}


def run_server(host: str = "0.0.0.0", port: int = 5000, debug: bool = False) -> None:
    """
    Run the Flask server.

    Args:
        host: Host to bind to
        port: Port to bind to
        debug: Enable debug mode
    """
    app.run(host=host, port=port, debug=debug)
