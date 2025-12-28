"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def sample_symbols() -> list[str]:
    """Sample stock symbols for testing."""
    return ["AAPL", "MSFT", "GOOGL"]
