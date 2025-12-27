# StockStalk 📈

A powerful, extensible stock monitoring application that watches stocks and sends real-time notifications via Beeper when indicators signal potential buy opportunities.

## Features

- **Multiple Technical Indicators**: RSI, MACD, Moving Average Crossover, Volume Spike Detection, and Price Change alerts
- **Extensible Architecture**: Easily add custom indicators
- **Real-time Notifications**: Beeper webhook integration for instant alerts
- **SMS Support**: Text-based interface for receiving stock updates on the go
- **Terminal Configuration UI**: Easy setup and management of watchlists
- **REST API**: Query stock analysis via HTTP endpoints
- **Strongly Typed**: Built with Pydantic for robust data validation
- **Docker Ready**: Simple deployment with Docker and Docker Compose
- **Scheduled Monitoring**: Automated checks at configurable intervals

## Tech Stack

- **Python 3.11+**: Modern Python with type hints
- **Pydantic**: Data validation and settings management
- **yfinance**: Real-time stock data from Yahoo Finance
- **Flask**: REST API server
- **NumPy & Pandas**: Numerical analysis
- **UV**: Fast Python package manager
- **Docker**: Containerized deployment

## Installation

### Using UV (Recommended)

```bash
# Install UV
pip install uv

# Clone the repository
git clone https://github.com/krishchopra/stockstalk.git
cd stockstalk

# Install dependencies
uv pip install -e .

# For development (includes pytest, black, mypy)
uv pip install -e ".[dev]"
```

### Using Docker

```bash
# Build the image
docker build -t stockstalk .

# Run with docker-compose
docker-compose up -d
```

## Quick Start

### 1. Configure the Application

Run the interactive configuration UI:

```bash
python -m stockstalk --configure
```

This will guide you through:
- Adding stocks to your watchlist
- Selecting indicators for each stock
- Setting up notification preferences
- Configuring check intervals

### 2. Set Environment Variables

Create a `.env` file (see `.env.example`):

```bash
BEEPER_WEBHOOK_URL=https://your-beeper-webhook-url
PHONE_NUMBERS=+1234567890,+0987654321
```

### 3. Run the Monitoring Service

```bash
# Run continuous monitoring (default)
python -m stockstalk

# Run analysis once and exit
python -m stockstalk --once

# Run the API server
python -m stockstalk --server --port 5000
```

## Available Indicators

### 1. **RSI (Relative Strength Index)**
- Identifies overbought (>70) and oversold (<30) conditions
- **Buy Signal**: RSI < 30 (oversold)
- **Parameters**: `period` (default: 14), `oversold_threshold` (default: 30)

### 2. **Moving Average Crossover**
- Detects golden cross (bullish) and death cross (bearish)
- **Buy Signal**: Short-term MA crosses above long-term MA
- **Parameters**: `short_period` (default: 10), `long_period` (default: 50)

### 3. **MACD (Moving Average Convergence Divergence)**
- Shows momentum and trend direction
- **Buy Signal**: MACD crosses above signal line
- **Parameters**: `fast_period` (default: 12), `slow_period` (default: 26), `signal_period` (default: 9)

### 4. **Volume Spike Detection**
- Identifies unusual trading volume
- **Buy Signal**: Volume >2x average with price increase
- **Parameters**: `lookback_period` (default: 20), `spike_threshold` (default: 2.0)

### 5. **Price Change Percentage**
- Detects significant price movements
- **Buy Signal**: Price drops ≥5% (potential dip buy)
- **Parameters**: `significant_drop_pct` (default: -5.0), `significant_gain_pct` (default: 5.0)

## Usage Examples

### Python API

```python
from stockstalk.services import StockDataFetcher, StockAnalyzer, NotificationService
from stockstalk.models import WatchlistItem, NotificationConfig
from stockstalk.utils import ConfigManager

# Load configuration
config_manager = ConfigManager()
config = config_manager.load_config()

# Initialize services
data_fetcher = StockDataFetcher()
notifier = NotificationService(config.notification_config)
analyzer = StockAnalyzer(data_fetcher, notifier, lookback_days=30)

# Analyze a stock
watchlist_item = WatchlistItem(
    symbol="AAPL",
    enabled_indicators=["RSI", "MACD", "Volume_Spike"]
)
results = analyzer.analyze_stock(watchlist_item)

for result in results:
    if result.is_triggered:
        print(f"{result.message}")
```

### REST API Endpoints

```bash
# Health check
curl http://localhost:5000/health

# Get stock analysis
curl http://localhost:5000/api/stock/AAPL

# View watchlist
curl http://localhost:5000/api/watchlist
```

### SMS Commands

Text these commands to your configured Twilio number:

- `HELP` - Show available commands
- `QUOTE AAPL` - Get current price for AAPL
- `WATCHLIST` - View your watchlist
- `ANALYZE AAPL` - Run full analysis on AAPL

## Configuration

### Config File Structure (`config.json`)

```json
{
  "watchlist": [
    {
      "symbol": "AAPL",
      "enabled_indicators": ["RSI", "MACD", "Volume_Spike"],
      "custom_params": {
        "RSI": {"period": 14, "oversold_threshold": 30}
      }
    }
  ],
  "notification_config": {
    "beeper_webhook_url": "https://...",
    "phone_numbers": ["+1234567890"],
    "min_priority": "medium"
  },
  "check_interval_minutes": 15,
  "data_lookback_days": 30
}
```

## Adding Custom Indicators

Create a new indicator by extending `BaseIndicator`:

```python
from stockstalk.indicators.base import BaseIndicator
from stockstalk.models import IndicatorResult, StockData, HistoricalData, AlertPriority

class MyCustomIndicator(BaseIndicator):
    @property
    def name(self) -> str:
        return "My_Custom_Indicator"
    
    def analyze(self, current_data: StockData, historical_data: HistoricalData) -> IndicatorResult:
        # Your analysis logic here
        is_triggered = False  # Your condition
        
        return IndicatorResult(
            indicator_name=self.name,
            symbol=current_data.symbol,
            is_triggered=is_triggered,
            priority=AlertPriority.MEDIUM,
            signal_strength=0.5,
            message="Your message here",
            metadata={"custom_data": "value"}
        )

# Register the indicator
from stockstalk.services.analyzer import IndicatorRegistry
IndicatorRegistry.register_indicator("My_Custom_Indicator", MyCustomIndicator)
```

## Docker Deployment

### Build and Run

```bash
# Build
docker build -t stockstalk .

# Run monitoring service
docker run -d \
  -v $(pwd)/config.json:/app/config.json \
  -e BEEPER_WEBHOOK_URL="https://..." \
  stockstalk

# Run API server
docker run -d \
  -p 5000:5000 \
  -v $(pwd)/config.json:/app/config.json \
  stockstalk python -m stockstalk --server
```

### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Development

### Running Tests

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=stockstalk --cov-report=html

# Run specific test file
pytest tests/test_indicators.py
```

### Code Formatting

```bash
# Format code with Black
black stockstalk/ tests/

# Check formatting
black --check stockstalk/ tests/

# Type checking with mypy
mypy stockstalk/
```

### Project Structure

```
stockstalk/
├── stockstalk/
│   ├── __init__.py
│   ├── __main__.py          # Entry point
│   ├── models/              # Pydantic models
│   ├── indicators/          # Technical indicators
│   │   ├── base.py
│   │   ├── rsi.py
│   │   ├── macd.py
│   │   ├── moving_average.py
│   │   ├── volume_spike.py
│   │   └── price_change.py
│   ├── services/            # Business logic
│   │   ├── data_fetcher.py
│   │   ├── analyzer.py
│   │   └── notifier.py
│   ├── api/                 # REST API
│   │   └── server.py
│   └── utils/               # Utilities
│       ├── config.py
│       └── terminal_ui.py
├── tests/                   # Test suite
├── .github/workflows/       # CI/CD
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## Deployment on DigitalOcean

1. **Create a Droplet** with Ubuntu 22.04

2. **Install Docker**:
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sh get-docker.sh
   ```

3. **Clone and Deploy**:
   ```bash
   git clone https://github.com/krishchopra/stockstalk.git
   cd stockstalk
   
   # Set environment variables
   cp .env.example .env
   nano .env  # Edit with your values
   
   # Deploy with docker-compose
   docker-compose up -d
   ```

4. **Set up as a systemd service** (optional):
   ```bash
   sudo systemctl enable docker
   docker-compose up -d
   ```

## Scheduled Monitoring with Cron

If not using Docker, set up a cron job:

```bash
# Edit crontab
crontab -e

# Run every 15 minutes
*/15 * * * * cd /path/to/stockstalk && python -m stockstalk --once >> /var/log/stockstalk.log 2>&1
```

## Troubleshooting

### Common Issues

1. **"No module named 'stockstalk'"**
   - Ensure you've installed the package: `uv pip install -e .`

2. **Yahoo Finance API errors**
   - Yahoo Finance may rate-limit requests
   - Try increasing `check_interval_minutes`

3. **Notification not sending**
   - Verify `BEEPER_WEBHOOK_URL` is correct
   - Check logs for API errors

4. **Docker container exits immediately**
   - Check logs: `docker logs stockstalk`
   - Ensure config.json exists

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

MIT License - See LICENSE file for details

## Disclaimer

This software is for educational purposes only. Stock trading involves risk. Always do your own research and consult with financial advisors before making investment decisions.

## Support

For issues, questions, or feature requests, please open an issue on GitHub.