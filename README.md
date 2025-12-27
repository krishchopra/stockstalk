# 📈 Stock Sentinel

[![CI](https://github.com/yourusername/stock-sentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/yourusername/stock-sentinel/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A highly extensible stock monitoring system with real-time technical indicators and SMS notifications via Beeper. Get alerted when stocks show signs of being a hot buy!

## 🚀 Features

- **Real-time Stock Monitoring**: Continuously monitors your watchlist using Yahoo Finance data
- **6 Built-in Technical Indicators**:
  - **RSI (Relative Strength Index)**: Identifies oversold/overbought conditions
  - **MACD**: Detects trend changes and momentum shifts
  - **Volume Spike**: Catches unusual trading activity
  - **Golden Cross/Death Cross**: Moving average crossover signals
  - **Bollinger Bands**: Price volatility and breakout detection
  - **Price Change**: Significant price movement alerts
- **SMS Notifications**: Get instant alerts via Beeper API
- **Text Message Commands**: Control and query the system by texting it
- **Plugin Architecture**: Easily add custom indicators
- **Terminal CLI**: Configure watchlist and phone numbers
- **REST API**: Full API for integration with other systems
- **Docker Ready**: Deploy easily on any server

## 📊 Indicators Explained

### RSI (Relative Strength Index)
Measures the speed and magnitude of price changes. Generates alerts when:
- **RSI < 30**: Oversold - potential buying opportunity 📈
- **RSI < 25**: Extremely oversold - strong buy signal 🚀
- **RSI > 70**: Overbought - consider taking profits 📉
- **RSI > 80**: Extremely overbought - strong sell signal 🔻

### MACD (Moving Average Convergence Divergence)
Tracks the relationship between two EMAs. Alerts on:
- **Bullish Crossover**: MACD crosses above signal line
- **Bearish Crossover**: MACD crosses below signal line
- **Strong Momentum**: Histogram shows accelerating trend

### Volume Spike
Detects unusual trading activity that often precedes big moves:
- **High volume + price up** = Bullish accumulation
- **High volume + price down** = Distribution/selling pressure
- **Extreme volume (3x+)** = Major institutional activity

### Golden Cross / Death Cross
Classic moving average crossover signals:
- **Golden Cross**: Short-term MA crosses above long-term MA (bullish)
- **Death Cross**: Short-term MA crosses below long-term MA (bearish)

### Bollinger Bands
Measures price volatility and identifies extremes:
- **Price below lower band**: Oversold, potential bounce
- **Price above upper band**: Overbought, potential pullback
- **Band squeeze**: Volatility contraction, big move coming

### Price Change
Monitors significant price movements:
- **+5% or more**: Significant gain, momentum building
- **+10% or more**: Extreme gain, major catalyst
- **52-week high/low**: Key psychological levels

## 🛠 Installation

### Prerequisites
- Python 3.11 or higher
- [UV](https://github.com/astral-sh/uv) package manager

### Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/stock-sentinel.git
cd stock-sentinel

# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings
```

### Docker Deployment

```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f stock-sentinel

# Stop
docker-compose down
```

## ⚙️ Configuration

All configuration is done through environment variables. Copy `.env.example` to `.env` and customize:

```bash
# Core Settings
STOCK_SENTINEL_CHECK_INTERVAL_MINUTES=15
STOCK_SENTINEL_MARKET_HOURS_ONLY=true

# Beeper API (for SMS)
STOCK_SENTINEL_BEEPER_API_KEY=your_api_key
STOCK_SENTINEL_BEEPER_SENDER_ID=+1234567890

# Alert Settings
STOCK_SENTINEL_COOLDOWN_MINUTES=60
STOCK_SENTINEL_MAX_ALERTS_PER_HOUR=10

# Indicator Thresholds
STOCK_SENTINEL_RSI_OVERSOLD=30.0
STOCK_SENTINEL_RSI_OVERBOUGHT=70.0
STOCK_SENTINEL_VOLUME_SPIKE_MULTIPLIER=2.0
STOCK_SENTINEL_PRICE_CHANGE_THRESHOLD=5.0
```

## 📱 Usage

### Terminal CLI

```bash
# Start the monitoring scheduler
stock-sentinel start

# Run a one-time check on specific stocks
stock-sentinel check AAPL GOOGL TSLA

# Get a quick quote
stock-sentinel quote NVDA

# Manage your watchlist
stock-sentinel watchlist

# Manage notification phone numbers
stock-sentinel phones

# View available indicators
stock-sentinel indicators

# Show current configuration
stock-sentinel config
```

### Text Message Commands

Text these commands to your Stock Sentinel number:

| Command | Description |
|---------|-------------|
| `HELP` | Show all commands |
| `QUOTE AAPL` | Get current quote for AAPL |
| `CHECK TSLA` | Run all indicators on TSLA |
| `WATCH NVDA` | Add NVDA to watchlist |
| `UNWATCH MSFT` | Remove MSFT from watchlist |
| `LIST` | Show current watchlist |
| `STATUS` | System status |
| `AAPL` | Quick quote (just send symbol) |

### REST API

The webhook server provides a full REST API:

```bash
# Health check
curl http://localhost:8080/health

# Check a stock
curl -X POST http://localhost:8080/api/check \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'

# Get watchlist
curl http://localhost:8080/api/watchlist

# Add to watchlist
curl -X POST http://localhost:8080/api/watchlist/NVDA

# List indicators
curl http://localhost:8080/api/indicators
```

## 🔌 Creating Custom Indicators

Stock Sentinel uses a plugin architecture. Create your own indicator in 3 steps:

### 1. Create Your Indicator Class

```python
# src/stock_sentinel/indicators/my_indicator.py

from stock_sentinel.indicators.base import Indicator, IndicatorResult, SignalType
from stock_sentinel.indicators.registry import indicator_registry
from stock_sentinel.data.models import StockData


@indicator_registry.register
class MyCustomIndicator(Indicator):
    """My custom trading indicator."""

    @property
    def name(self) -> str:
        return "my_indicator"

    @property
    def description(self) -> str:
        return "My custom indicator - does amazing things"

    @property
    def required_history_days(self) -> int:
        return 20  # Minimum days of history needed

    async def analyze(self, stock_data: StockData) -> IndicatorResult | None:
        # Your analysis logic here
        closes = stock_data.closes

        if len(closes) < self.required_history_days:
            return None

        # Calculate your signal
        my_value = sum(closes[-10:]) / 10  # Example: 10-day SMA

        # Determine signal
        if my_value > stock_data.quote.price * 1.05:
            signal = SignalType.BUY
            message = "Price below 10-day SMA - potential buy"
            should_alert = True
        else:
            signal = SignalType.NEUTRAL
            message = "No signal"
            should_alert = False

        return self._create_result(
            symbol=stock_data.symbol,
            signal=signal,
            value=my_value,
            message=message,
            should_alert=should_alert,
            # Add any custom metadata
            sma_10=my_value,
        )
```

### 2. Import in `__init__.py`

```python
# src/stock_sentinel/indicators/__init__.py

from stock_sentinel.indicators import my_indicator  # Add this line
```

### 3. That's It!

Your indicator will automatically:
- Be registered with the system
- Run during each check cycle
- Generate alerts when conditions are met
- Be available via CLI and API

## 🧪 Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/stock_sentinel --cov-report=html

# Run specific test file
pytest tests/test_indicators/test_rsi.py -v

# Run tests matching a pattern
pytest -k "rsi" -v
```

## 📁 Project Structure

```
stock-sentinel/
├── src/stock_sentinel/
│   ├── __init__.py
│   ├── main.py                 # Main entry point
│   ├── config/
│   │   └── settings.py         # Pydantic settings
│   ├── data/
│   │   ├── models.py           # Data models (OHLCV, StockData)
│   │   └── providers/
│   │       ├── base.py         # Abstract provider
│   │       └── yahoo.py        # Yahoo Finance implementation
│   ├── indicators/
│   │   ├── base.py             # Indicator base class
│   │   ├── registry.py         # Plugin registry
│   │   ├── rsi.py              # RSI indicator
│   │   ├── macd.py             # MACD indicator
│   │   ├── volume_spike.py     # Volume spike indicator
│   │   ├── golden_cross.py     # MA crossover indicator
│   │   ├── bollinger_bands.py  # Bollinger Bands
│   │   └── price_change.py     # Price change indicator
│   ├── notifications/
│   │   ├── base.py             # Notification base class
│   │   └── beeper.py           # Beeper SMS implementation
│   ├── server/
│   │   └── webhook.py          # FastAPI webhook server
│   ├── scheduler/
│   │   └── jobs.py             # APScheduler jobs
│   ├── storage/
│   │   └── database.py         # SQLAlchemy database
│   └── cli/
│       └── terminal.py         # Typer CLI
├── tests/                      # Test suite
├── .github/workflows/          # GitHub Actions
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## 🐳 DigitalOcean Deployment

### 1. Create a Droplet

```bash
# SSH into your droplet
ssh root@your-droplet-ip

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install docker-compose-plugin
```

### 2. Deploy

```bash
# Clone repository
git clone https://github.com/yourusername/stock-sentinel.git
cd stock-sentinel

# Create .env file
cp .env.example .env
nano .env  # Edit with your settings

# Start services
docker compose up -d

# View logs
docker compose logs -f
```

### 3. Set Up Webhook (Optional)

To receive text messages, configure Beeper to send webhooks to:
```
http://your-droplet-ip:8080/webhook/incoming
```

## 🔒 Security Notes

- Never commit your `.env` file
- Use strong API keys
- Run the container as non-root (already configured)
- Consider using a reverse proxy (nginx) with HTTPS for the webhook

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Write tests for your changes
4. Run `black` and `ruff` for formatting
5. Submit a pull request

## 📧 Support

- Open an issue for bugs or feature requests
- Check existing issues before creating new ones

---

**Disclaimer**: This software is for educational and informational purposes only. It is not financial advice. Always do your own research and consult with a qualified financial advisor before making investment decisions.
