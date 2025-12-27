"""Tests for the indicator registry."""

import pytest

from stock_sentinel.data.models import StockData
from stock_sentinel.indicators.base import Indicator, IndicatorConfig, IndicatorResult, SignalType
from stock_sentinel.indicators.registry import IndicatorRegistry


class TestIndicatorRegistry:
    """Test suite for the indicator registry."""

    @pytest.fixture
    def empty_registry(self):
        """Create an empty registry for testing."""
        return IndicatorRegistry()

    @pytest.fixture
    def sample_indicator_class(self):
        """Create a sample indicator class for testing."""

        class SampleIndicator(Indicator):
            @property
            def name(self) -> str:
                return "sample"

            @property
            def description(self) -> str:
                return "A sample indicator"

            async def analyze(self, stock_data: StockData) -> IndicatorResult | None:
                return self._create_result(
                    symbol=stock_data.symbol,
                    signal=SignalType.NEUTRAL,
                    value=0.0,
                    message="Sample result",
                )

        return SampleIndicator

    def test_register_decorator(self, empty_registry, sample_indicator_class):
        """Test registering an indicator using the decorator."""
        empty_registry.register(sample_indicator_class)

        assert "sample" in empty_registry
        assert len(empty_registry) == 1

    def test_register_class_method(self, empty_registry, sample_indicator_class):
        """Test registering an indicator using register_class method."""
        empty_registry.register_class(sample_indicator_class)

        assert empty_registry.has("sample")

    def test_get_indicator(self, empty_registry, sample_indicator_class):
        """Test getting an indicator by name."""
        empty_registry.register(sample_indicator_class)

        indicator = empty_registry.get("sample")

        assert indicator is not None
        assert indicator.name == "sample"
        assert isinstance(indicator, Indicator)

    def test_get_nonexistent_indicator(self, empty_registry):
        """Test getting a non-existent indicator raises KeyError."""
        with pytest.raises(KeyError):
            empty_registry.get("nonexistent")

    def test_get_with_config(self, empty_registry, sample_indicator_class):
        """Test getting an indicator with custom config."""
        empty_registry.register(sample_indicator_class)

        config = IndicatorConfig(enabled=False, alert_on_buy=False)
        indicator = empty_registry.get("sample", config=config)

        assert indicator.config.enabled is False
        assert indicator.config.alert_on_buy is False

    def test_list_indicators(self, empty_registry, sample_indicator_class):
        """Test listing all registered indicators."""
        empty_registry.register(sample_indicator_class)

        indicators = empty_registry.list_indicators()

        assert "sample" in indicators

    def test_unregister(self, empty_registry, sample_indicator_class):
        """Test unregistering an indicator."""
        empty_registry.register(sample_indicator_class)
        assert "sample" in empty_registry

        result = empty_registry.unregister("sample")

        assert result is True
        assert "sample" not in empty_registry

    def test_unregister_nonexistent(self, empty_registry):
        """Test unregistering a non-existent indicator."""
        result = empty_registry.unregister("nonexistent")

        assert result is False

    def test_get_all(self, empty_registry, sample_indicator_class):
        """Test getting all indicators."""
        empty_registry.register(sample_indicator_class)

        indicators = empty_registry.get_all()

        assert len(indicators) == 1
        assert indicators[0].name == "sample"

    def test_get_enabled_only(self, empty_registry, sample_indicator_class):
        """Test getting only enabled indicators."""
        empty_registry.register(sample_indicator_class)

        # Get enabled (default)
        enabled = empty_registry.get_enabled()
        assert len(enabled) == 1

        # Get with disabled config
        configs = {"sample": IndicatorConfig(enabled=False)}
        enabled = empty_registry.get_enabled(configs)
        assert len(enabled) == 0

    async def test_analyze_all(self, empty_registry, sample_indicator_class, sample_stock_data):
        """Test running all indicators on stock data."""
        empty_registry.register(sample_indicator_class)

        results = await empty_registry.analyze_all(sample_stock_data)

        assert len(results) == 1
        assert results[0].indicator_name == "sample"


class TestGlobalRegistry:
    """Test the global indicator registry."""

    def test_global_registry_has_builtin_indicators(self):
        """Test that the global registry has built-in indicators."""
        from stock_sentinel.indicators import indicator_registry

        # Check that our built-in indicators are registered
        assert "rsi" in indicator_registry
        assert "macd" in indicator_registry
        assert "volume_spike" in indicator_registry
        assert "golden_cross" in indicator_registry
        assert "bollinger_bands" in indicator_registry
        assert "price_change" in indicator_registry

    def test_global_registry_indicator_count(self):
        """Test the global registry has expected number of indicators."""
        from stock_sentinel.indicators import indicator_registry

        assert len(indicator_registry) >= 6
