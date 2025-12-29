# StockStalk

A powerful, extensible stock monitoring application that watches stocks and sends real-time SMS notifications when indicators signal potential opportunities.

## Features

- **Technical Indicators**: RSI, MACD, Moving Average Crossover, Volume Spike Detection, and Price Change alerts
- **Fundamental Indicators**: PEG Ratio, Debt-to-Equity, Operating Margins, ROIC, Free Cash Flow, Revenue Growth, Earnings Growth, and Fundamental Score
- **Extensible Architecture**: Easily add custom indicators
- **SMS Notifications**: AWS SNS integration for instant alerts with rate limiting and cooldowns
- **Terminal Configuration UI**: Easy setup and management of watchlists
- **REST API**: Query stock analysis via HTTP endpoints (FastAPI)
- **Async Architecture**: Built with async/await for efficient concurrent operations
- **Strongly Typed**: Built with Pydantic for robust data validation
- **Docker Ready**: Simple deployment with Docker and Docker Compose
- **Scheduled Monitoring**: Automated checks at configurable intervals

## Tech Stack

- **Python 3.11+**: Modern Python with type hints
- **Pydantic**: Data validation and settings management
- **yfinance**: Real-time stock data from Yahoo Finance
- **FastAPI**: Async REST API server
- **AWS SNS**: SMS notifications via Amazon Simple Notification Service
- **SQLAlchemy + aiosqlite**: Async database for alert tracking
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

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
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

### 1. Set Up AWS Credentials

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` with your AWS credentials:

```bash
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
```

> **Note**: Your AWS account needs SNS permissions to send SMS messages. See [AWS SNS SMS documentation](https://docs.aws.amazon.com/sns/latest/dg/sns-mobile-phone-number-as-subscriber.html).

### 2. Create Your Configuration

Copy the example config and customize your watchlist:

```bash
cp config.example.json config.json
```

Edit `config.json` to add your stocks and phone numbers:

```json
{
  "watchlist": [
    {
      "symbol": "AAPL",
      "enabled_indicators": ["RSI", "MACD", "Fundamental_Score"],
      "custom_params": {
        "RSI": { "period": 14, "oversold_threshold": 30 }
      }
    }
  ],
  "notification_config": {
    "phone_numbers": ["+14155551234"],
    "min_priority": "medium",
    "cooldown_minutes": 60,
    "max_alerts_per_hour": 20
  },
  "check_interval_minutes": 15,
  "data_lookback_days": 30
}
```

### 3. Run the Interactive Configuration (Optional)

Run the interactive configuration UI to set up your watchlist:

```bash
python -m stockstalk --configure
```

### 4. Run the Monitoring Service

```bash
# Run continuous monitoring (default)
python -m stockstalk

# Run analysis once and exit
python -m stockstalk --once

# Run the API server
python -m stockstalk --server --port 8000
```

## Available Indicators

### Technical Indicators

#### 1. **RSI (Relative Strength Index)**

- Identifies overbought (>70) and oversold (<30) conditions
- **Buy Signal**: RSI < 30 (oversold)
- **Parameters**: `period` (default: 14), `oversold_threshold` (default: 30)

#### 2. **Moving Average Crossover**

- Detects golden cross (bullish) and death cross (bearish)
- **Buy Signal**: Short-term MA crosses above long-term MA
- **Parameters**: `short_period` (default: 10), `long_period` (default: 50)

#### 3. **MACD (Moving Average Convergence Divergence)**

- Shows momentum and trend direction
- **Buy Signal**: MACD crosses above signal line
- **Parameters**: `fast_period` (default: 12), `slow_period` (default: 26), `signal_period` (default: 9)

#### 4. **Volume Spike Detection**

- Identifies unusual trading volume
- **Buy Signal**: Volume >2x average with price increase
- **Parameters**: `lookback_period` (default: 20), `spike_threshold` (default: 2.0)

#### 5. **Price Change Percentage**

- Detects significant price movements
- **Buy Signal**: Price drops ≥5% (potential dip buy)
- **Parameters**: `significant_drop_pct` (default: -5.0), `significant_gain_pct` (default: 5.0)

### Fundamental Indicators

#### 6. **PEG Ratio**

- Price/Earnings to Growth ratio
- **Buy Signal**: PEG < 1.5 (undervalued relative to growth)
- **Parameters**: `threshold` (default: 1.5)

#### 7. **Debt-to-Equity Ratio**

- Measures financial leverage
- **Buy Signal**: D/E < 0.5 (low debt, strong balance sheet)
- **Parameters**: `threshold` (default: 0.5)

#### 8. **Operating Margins**

- Measures operational efficiency
- **Buy Signal**: Margins > 15%
- **Parameters**: `min_margin` (default: 0.15)

#### 9. **ROIC (Return on Invested Capital)**

- Measures how well a company uses capital
- **Buy Signal**: ROIC > 15%
- **Parameters**: `threshold` (default: 0.15)

#### 10. **Free Cash Flow**

- Measures cash generation capability
- **Buy Signal**: Positive FCF with good yield
- **Parameters**: `min_fcf_yield` (default: 0.03)

#### 11. **Revenue Growth**

- Year-over-year revenue growth
- **Buy Signal**: Growth > 10%
- **Parameters**: `threshold` (default: 0.10)

#### 12. **Earnings Growth**

- EPS growth rate
- **Buy Signal**: Growth > 10%
- **Parameters**: `threshold` (default: 0.10)

#### 13. **Fundamental Score**

- Composite score from multiple fundamental metrics
- **Buy Signal**: Score ≥ 5 out of 8 checks passing
- **Parameters**: `min_score` (default: 5)

## Usage Examples

### Python API

```python
import asyncio
from stockstalk.services import StockDataFetcher, StockAnalyzer, NotificationService
from stockstalk.models import WatchlistItem, NotificationConfig
from stockstalk.utils import ConfigManager

# Load configuration
config_manager = ConfigManager()
config = config_manager.load_config()

# Initialize services
data_fetcher = StockDataFetcher()
notifier = NotificationService(config.notification_config)
analyzer = StockAnalyzer(
    data_fetcher,
    notifier,
    config.notification_config,
    lookback_days=30
)

# Analyze a stock
async def analyze():
    watchlist_item = WatchlistItem(
        symbol="AAPL",
        enabled_indicators=["RSI", "MACD", "Fundamental_Score"]
    )
    results = await analyzer.analyze_stock(watchlist_item)

    for result in results:
        if result.is_triggered:
            print(f"{result.message}")

asyncio.run(analyze())
```

### REST API Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Get stock analysis
curl http://localhost:8000/api/stock/AAPL

# View watchlist
curl http://localhost:8000/api/watchlist

# List available indicators
curl http://localhost:8000/api/indicators
```

## Configuration

### Config File Structure (`config.json`)

```json
{
  "watchlist": [
    {
      "symbol": "AAPL",
      "enabled_indicators": ["RSI", "MACD", "Fundamental_Score"],
      "custom_params": {
        "RSI": { "period": 14, "oversold_threshold": 30 },
        "Fundamental_Score": { "min_score": 5 }
      }
    }
  ],
  "notification_config": {
    "phone_numbers": ["+14155551234"],
    "min_priority": "medium",
    "cooldown_minutes": 60,
    "max_alerts_per_hour": 20
  },
  "check_interval_minutes": 15,
  "data_lookback_days": 30
}
```

### Notification Configuration

| Field                 | Description                                                  | Default  |
| --------------------- | ------------------------------------------------------------ | -------- |
| `phone_numbers`       | List of E.164 format phone numbers                           | `[]`     |
| `min_priority`        | Minimum alert priority (`low`, `medium`, `high`, `critical`) | `medium` |
| `cooldown_minutes`    | Minutes between alerts for same symbol/indicator             | `60`     |
| `max_alerts_per_hour` | Rate limit for total alerts per hour                         | `20`     |

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
  -e AWS_ACCESS_KEY_ID="your_key" \
  -e AWS_SECRET_ACCESS_KEY="your_secret" \
  -e AWS_REGION="us-east-1" \
  stockstalk

# Run API server
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/config.json:/app/config.json \
  -e AWS_ACCESS_KEY_ID="your_key" \
  -e AWS_SECRET_ACCESS_KEY="your_secret" \
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
│   ├── indicators/          # Stock indicators
│   │   ├── base.py
│   │   ├── rsi.py
│   │   ├── macd.py
│   │   ├── moving_average.py
│   │   ├── volume_spike.py
│   │   ├── price_change.py
│   │   └── fundamentals.py  # All fundamental indicators
│   ├── services/            # Business logic
│   │   ├── data_fetcher.py
│   │   ├── analyzer.py
│   │   └── notifier.py      # AWS SNS integration
│   ├── storage/             # Database layer
│   │   └── database.py      # SQLAlchemy async models
│   ├── api/                 # REST API
│   │   └── server.py        # FastAPI server
│   └── utils/               # Utilities
│       ├── config.py
│       └── terminal_ui.py
├── tests/                   # Test suite
├── .github/workflows/       # CI/CD
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── config.example.json      # Example configuration
├── .env.example             # Example environment variables
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
   nano .env  # Add your AWS credentials

   # Create your config
   cp config.example.json config.json
   nano config.json  # Add your watchlist and phone numbers

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
*/15 * * * * cd /path/to/stockstalk && source .venv/bin/activate && python -m stockstalk --once >> /var/log/stockstalk.log 2>&1
```

## Troubleshooting

### Common Issues

1. **"No module named 'stockstalk'"**

   - Ensure you've installed the package: `uv pip install -e .`

2. **Yahoo Finance API errors**

   - Yahoo Finance may rate-limit requests
   - Try increasing `check_interval_minutes`

3. **SMS notifications not sending**

   - Verify AWS credentials are correct in `.env`
   - Check that your AWS account has SNS SMS permissions
   - Verify phone numbers are in E.164 format (e.g., `+14155551234`)
   - Check logs for AWS API errors

4. **Docker container exits immediately**

   - Check logs: `docker logs stockstalk`
   - Ensure `config.json` exists and is valid JSON

5. **"Database not initialized" error**
   - The database is auto-initialized on first run
   - Check write permissions in the app directory

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
