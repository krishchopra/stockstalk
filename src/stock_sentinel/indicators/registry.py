"""Indicator registry for plugin-based indicator management."""

from typing import TypeVar

from stock_sentinel.data.models import StockData
from stock_sentinel.indicators.base import Indicator, IndicatorConfig, IndicatorResult

T = TypeVar("T", bound=Indicator)


class IndicatorRegistry:
    """
    Registry for managing stock indicators.

    This provides a plugin-like system where indicators can be registered
    and later instantiated by name. Supports both decorator-based and
    manual registration.

    Example usage:
        # Decorator registration
        @indicator_registry.register
        class RSIIndicator(Indicator):
            ...

        # Manual registration
        indicator_registry.register_class(MyIndicator)

        # Get indicator by name
        rsi = indicator_registry.get("rsi")

        # List all registered indicators
        for name in indicator_registry.list_indicators():
            print(name)
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._indicators: dict[str, type[Indicator]] = {}
        self._instances: dict[str, Indicator] = {}

    def register(self, cls: type[T]) -> type[T]:
        """
        Register an indicator class (decorator).

        Args:
            cls: Indicator class to register

        Returns:
            The same class (for decorator chaining)
        """
        # Create temporary instance to get name
        temp_instance = cls.__new__(cls)
        temp_instance.config = IndicatorConfig()

        name = temp_instance.name
        self._indicators[name] = cls
        return cls

    def register_class(self, cls: type[Indicator]) -> None:
        """
        Register an indicator class (manual registration).

        Args:
            cls: Indicator class to register
        """
        self.register(cls)

    def unregister(self, name: str) -> bool:
        """
        Unregister an indicator by name.

        Args:
            name: Indicator name to unregister

        Returns:
            True if indicator was unregistered, False if not found
        """
        if name in self._indicators:
            del self._indicators[name]
            if name in self._instances:
                del self._instances[name]
            return True
        return False

    def get(self, name: str, config: IndicatorConfig | None = None) -> Indicator:
        """
        Get an indicator instance by name.

        Args:
            name: Registered indicator name
            config: Optional configuration for the indicator

        Returns:
            Indicator instance

        Raises:
            KeyError: If indicator name is not registered
        """
        if name not in self._indicators:
            available = ", ".join(self._indicators.keys())
            raise KeyError(f"Indicator '{name}' not found. Available: {available}")

        # Return cached instance if no custom config and already instantiated
        if config is None and name in self._instances:
            return self._instances[name]

        # Create new instance
        indicator_cls = self._indicators[name]
        instance = indicator_cls(config=config)

        # Cache if using default config
        if config is None:
            self._instances[name] = instance

        return instance

    def get_all(self, configs: dict[str, IndicatorConfig] | None = None) -> list[Indicator]:
        """
        Get all registered indicator instances.

        Args:
            configs: Optional dict mapping indicator names to configurations

        Returns:
            List of all indicator instances
        """
        configs = configs or {}
        return [self.get(name, configs.get(name)) for name in self._indicators]

    def get_enabled(self, configs: dict[str, IndicatorConfig] | None = None) -> list[Indicator]:
        """
        Get all enabled indicator instances.

        Args:
            configs: Optional dict mapping indicator names to configurations

        Returns:
            List of enabled indicator instances
        """
        return [ind for ind in self.get_all(configs) if ind.config.enabled]

    def list_indicators(self) -> list[str]:
        """
        List all registered indicator names.

        Returns:
            List of indicator names
        """
        return list(self._indicators.keys())

    def has(self, name: str) -> bool:
        """
        Check if an indicator is registered.

        Args:
            name: Indicator name to check

        Returns:
            True if registered, False otherwise
        """
        return name in self._indicators

    async def analyze_all(
        self,
        stock_data: StockData,
        configs: dict[str, IndicatorConfig] | None = None,
    ) -> list[IndicatorResult]:
        """
        Run all enabled indicators on stock data.

        Args:
            stock_data: Stock data to analyze
            configs: Optional indicator configurations

        Returns:
            List of results from all indicators that produced signals
        """
        results: list[IndicatorResult] = []
        for indicator in self.get_enabled(configs):
            try:
                result = await indicator.analyze(stock_data)
                if result is not None:
                    results.append(result)
            except Exception as e:
                # Log error but continue with other indicators
                print(f"Error in {indicator.name}: {e}")
        return results

    def __len__(self) -> int:
        """Get number of registered indicators."""
        return len(self._indicators)

    def __contains__(self, name: str) -> bool:
        """Check if indicator is registered."""
        return self.has(name)


# Global registry instance
indicator_registry = IndicatorRegistry()
