# Contributing to StockStalk

Thank you for your interest in contributing to StockStalk! This document provides guidelines and instructions for contributing.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/stockstalk.git`
3. Create a new branch: `git checkout -b feature/your-feature-name`

## Development Setup

```bash
# Install UV package manager
pip install uv

# Install dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Check code formatting
black --check stockstalk/ tests/

# Format code
black stockstalk/ tests/
```

## Code Style

- We use [Black](https://black.readthedocs.io/) for code formatting
- Line length: 100 characters
- Use type hints for all functions
- Follow PEP 8 guidelines

## Testing

- Write tests for all new features
- Ensure all tests pass before submitting a PR
- Aim for at least 80% code coverage
- Use descriptive test names

```bash
# Run tests with coverage
pytest --cov=stockstalk --cov-report=html
```

## Creating a New Indicator

To add a custom stock indicator:

1. Create a new file in `stockstalk/indicators/`
2. Extend the `BaseIndicator` class
3. Implement the `name` property and `analyze` method
4. Add your indicator to `stockstalk/indicators/__init__.py`
5. Write tests in `tests/test_indicators.py`

Example:

```python
from stockstalk.indicators.base import BaseIndicator
from stockstalk.models import IndicatorResult, StockData, HistoricalData, AlertPriority

class MyIndicator(BaseIndicator):
    @property
    def name(self) -> str:
        return "My_Indicator"
    
    def analyze(self, current_data: StockData, historical_data: HistoricalData) -> IndicatorResult:
        # Your logic here
        return IndicatorResult(
            indicator_name=self.name,
            symbol=current_data.symbol,
            is_triggered=False,
            priority=AlertPriority.MEDIUM,
            signal_strength=0.5,
            message="Analysis result",
        )
```

## Pull Request Process

1. Update documentation for any new features
2. Add tests for your changes
3. Ensure all tests pass: `pytest`
4. Format your code: `black stockstalk/ tests/`
5. Update the README if needed
6. Create a pull request with a clear description

## Commit Messages

- Use clear, descriptive commit messages
- Start with a verb (Add, Fix, Update, etc.)
- Keep the first line under 72 characters
- Add details in the body if needed

Examples:
- `Add Bollinger Bands indicator`
- `Fix RSI calculation for edge cases`
- `Update documentation for API endpoints`

## Reporting Issues

When reporting issues, please include:

- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Error messages or logs

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Accept constructive criticism
- Focus on what's best for the project

## Questions?

Feel free to open an issue for questions or discussions!

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
