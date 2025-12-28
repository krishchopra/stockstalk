"""Fundamental analysis indicators for long-term stock evaluation."""

import logging
from typing import Any

import yfinance as yf

from stockstalk.indicators.base import BaseIndicator
from stockstalk.models import AlertPriority, HistoricalData, IndicatorResult, StockData

logger = logging.getLogger(__name__)


class FundamentalAnalyzer:
    """Helper class to fetch and cache fundamental data from Yahoo Finance."""

    _cache: dict[str, dict[str, Any]] = {}

    @classmethod
    def get_fundamentals(cls, symbol: str) -> dict[str, Any]:
        """Fetch fundamental data for a symbol (cached)."""
        if symbol in cls._cache:
            return cls._cache[symbol]

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Get financial statements
            financials = ticker.financials
            balance_sheet = ticker.balance_sheet
            cash_flow = ticker.cashflow

            data = {
                "info": info,
                "financials": financials,
                "balance_sheet": balance_sheet,
                "cash_flow": cash_flow,
                # Pre-extracted common metrics
                "peg_ratio": info.get("pegRatio"),
                "debt_to_equity": info.get("debtToEquity"),
                "operating_margins": info.get("operatingMargins"),
                "profit_margins": info.get("profitMargins"),
                "return_on_equity": info.get("returnOnEquity"),
                "return_on_assets": info.get("returnOnAssets"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "free_cash_flow": info.get("freeCashflow"),
                "shares_outstanding": info.get("sharesOutstanding"),
                "market_cap": info.get("marketCap"),
                "enterprise_value": info.get("enterpriseValue"),
                "trailing_eps": info.get("trailingEps"),
                "forward_eps": info.get("forwardEps"),
            }

            cls._cache[symbol] = data
            return data

        except Exception as e:
            logger.error(f"Error fetching fundamentals for {symbol}: {e}")
            return {}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the fundamentals cache."""
        cls._cache.clear()


class PEGRatioIndicator(BaseIndicator):
    """
    PEG Ratio indicator.

    PEG < 1.0 is considered undervalued
    PEG < 1.5 is considered fairly valued with growth
    PEG > 2.0 may be overvalued
    """

    @property
    def name(self) -> str:
        return "PEG_Ratio"

    def analyze(self, current_data: StockData, historical_data: HistoricalData) -> IndicatorResult:
        threshold = self.get_param("threshold", 1.5)

        fundamentals = FundamentalAnalyzer.get_fundamentals(current_data.symbol)
        peg = fundamentals.get("peg_ratio")

        if peg is None:
            return IndicatorResult(
                indicator_name=self.name,
                symbol=current_data.symbol,
                is_triggered=False,
                signal_strength=0.0,
                message=f"{current_data.symbol}: PEG ratio not available",
                metadata={"peg_ratio": None},
            )

        is_triggered = peg < threshold and peg > 0
        
        if peg < 1.0:
            priority = AlertPriority.HIGH
            message = f"{current_data.symbol} PEG={peg:.2f} - Potentially undervalued with strong growth"
        elif peg < threshold:
            priority = AlertPriority.MEDIUM
            message = f"{current_data.symbol} PEG={peg:.2f} - Fairly valued with growth potential"
        else:
            priority = AlertPriority.LOW
            message = f"{current_data.symbol} PEG={peg:.2f} - Above threshold ({threshold})"

        # Signal strength: lower PEG = stronger signal (inverted, capped)
        signal_strength = max(0, min(1, (threshold - peg) / threshold)) if peg > 0 else 0

        return IndicatorResult(
            indicator_name=self.name,
            symbol=current_data.symbol,
            is_triggered=is_triggered,
            priority=priority,
            signal_strength=signal_strength,
            message=message,
            metadata={"peg_ratio": peg, "threshold": threshold},
        )


class DebtToEquityIndicator(BaseIndicator):
    """
    Debt-to-Equity ratio indicator.

    D/E < 0.6 is considered healthy
    D/E > 1.0 indicates high leverage
    """

    @property
    def name(self) -> str:
        return "Debt_To_Equity"

    def analyze(self, current_data: StockData, historical_data: HistoricalData) -> IndicatorResult:
        threshold = self.get_param("threshold", 0.6)

        fundamentals = FundamentalAnalyzer.get_fundamentals(current_data.symbol)
        de_ratio = fundamentals.get("debt_to_equity")

        if de_ratio is None:
            return IndicatorResult(
                indicator_name=self.name,
                symbol=current_data.symbol,
                is_triggered=False,
                signal_strength=0.0,
                message=f"{current_data.symbol}: Debt-to-equity not available",
                metadata={"debt_to_equity": None},
            )

        # Convert from percentage if needed (yfinance returns as percentage sometimes)
        if de_ratio > 10:
            de_ratio = de_ratio / 100

        is_triggered = de_ratio < threshold

        if de_ratio < 0.3:
            priority = AlertPriority.HIGH
            message = f"{current_data.symbol} D/E={de_ratio:.2f} - Very low debt, strong balance sheet"
        elif de_ratio < threshold:
            priority = AlertPriority.MEDIUM
            message = f"{current_data.symbol} D/E={de_ratio:.2f} - Healthy debt levels"
        else:
            priority = AlertPriority.LOW
            message = f"{current_data.symbol} D/E={de_ratio:.2f} - Above threshold ({threshold})"

        signal_strength = max(0, min(1, (threshold - de_ratio) / threshold)) if de_ratio >= 0 else 0

        return IndicatorResult(
            indicator_name=self.name,
            symbol=current_data.symbol,
            is_triggered=is_triggered,
            priority=priority,
            signal_strength=signal_strength,
            message=message,
            metadata={"debt_to_equity": de_ratio, "threshold": threshold},
        )


class OperatingMarginsIndicator(BaseIndicator):
    """
    Operating Margins indicator.

    Looks for expanding/healthy operating margins.
    """

    @property
    def name(self) -> str:
        return "Operating_Margins"

    def analyze(self, current_data: StockData, historical_data: HistoricalData) -> IndicatorResult:
        min_margin = self.get_param("min_margin", 0.15)  # 15% minimum

        fundamentals = FundamentalAnalyzer.get_fundamentals(current_data.symbol)
        op_margin = fundamentals.get("operating_margins")

        if op_margin is None:
            return IndicatorResult(
                indicator_name=self.name,
                symbol=current_data.symbol,
                is_triggered=False,
                signal_strength=0.0,
                message=f"{current_data.symbol}: Operating margins not available",
                metadata={"operating_margins": None},
            )

        is_triggered = op_margin >= min_margin
        margin_pct = op_margin * 100

        if op_margin >= 0.25:
            priority = AlertPriority.HIGH
            message = f"{current_data.symbol} Operating margin {margin_pct:.1f}% - Excellent profitability"
        elif op_margin >= min_margin:
            priority = AlertPriority.MEDIUM
            message = f"{current_data.symbol} Operating margin {margin_pct:.1f}% - Healthy margins"
        else:
            priority = AlertPriority.LOW
            message = f"{current_data.symbol} Operating margin {margin_pct:.1f}% - Below threshold ({min_margin*100:.0f}%)"

        signal_strength = min(1, op_margin / 0.3) if op_margin > 0 else 0

        return IndicatorResult(
            indicator_name=self.name,
            symbol=current_data.symbol,
            is_triggered=is_triggered,
            priority=priority,
            signal_strength=signal_strength,
            message=message,
            metadata={"operating_margins": op_margin, "min_margin": min_margin},
        )


class ROICIndicator(BaseIndicator):
    """
    Return on Invested Capital (ROIC) indicator.

    ROIC > 15% indicates efficient capital allocation.
    Uses ROE as a proxy when ROIC isn't directly available.
    """

    @property
    def name(self) -> str:
        return "ROIC"

    def analyze(self, current_data: StockData, historical_data: HistoricalData) -> IndicatorResult:
        threshold = self.get_param("threshold", 0.15)  # 15%

        fundamentals = FundamentalAnalyzer.get_fundamentals(current_data.symbol)
        
        # Try ROE as proxy (ROIC often not directly available)
        roe = fundamentals.get("return_on_equity")
        roa = fundamentals.get("return_on_assets")

        # Estimate ROIC from available data
        roic = roe  # Use ROE as primary proxy

        if roic is None:
            return IndicatorResult(
                indicator_name=self.name,
                symbol=current_data.symbol,
                is_triggered=False,
                signal_strength=0.0,
                message=f"{current_data.symbol}: ROIC/ROE not available",
                metadata={"roic": None, "roe": None, "roa": roa},
            )

        is_triggered = roic >= threshold
        roic_pct = roic * 100

        if roic >= 0.25:
            priority = AlertPriority.HIGH
            message = f"{current_data.symbol} ROIC≈{roic_pct:.1f}% - Exceptional capital efficiency"
        elif roic >= threshold:
            priority = AlertPriority.MEDIUM
            message = f"{current_data.symbol} ROIC≈{roic_pct:.1f}% - Strong returns on capital"
        else:
            priority = AlertPriority.LOW
            message = f"{current_data.symbol} ROIC≈{roic_pct:.1f}% - Below threshold ({threshold*100:.0f}%)"

        signal_strength = min(1, roic / 0.3) if roic > 0 else 0

        return IndicatorResult(
            indicator_name=self.name,
            symbol=current_data.symbol,
            is_triggered=is_triggered,
            priority=priority,
            signal_strength=signal_strength,
            message=message,
            metadata={"roic_estimate": roic, "roe": roe, "roa": roa, "threshold": threshold},
        )


class FreeCashFlowIndicator(BaseIndicator):
    """
    Free Cash Flow indicator.

    Looks for positive and growing FCF.
    """

    @property
    def name(self) -> str:
        return "Free_Cash_Flow"

    def analyze(self, current_data: StockData, historical_data: HistoricalData) -> IndicatorResult:
        fundamentals = FundamentalAnalyzer.get_fundamentals(current_data.symbol)
        fcf = fundamentals.get("free_cash_flow")
        market_cap = fundamentals.get("market_cap")

        if fcf is None:
            return IndicatorResult(
                indicator_name=self.name,
                symbol=current_data.symbol,
                is_triggered=False,
                signal_strength=0.0,
                message=f"{current_data.symbol}: Free cash flow not available",
                metadata={"fcf": None},
            )

        # Calculate FCF yield if market cap available
        fcf_yield = (fcf / market_cap) if market_cap and market_cap > 0 else None

        is_triggered = fcf > 0
        fcf_billions = fcf / 1e9

        if fcf > 0 and fcf_yield and fcf_yield > 0.05:
            priority = AlertPriority.HIGH
            message = f"{current_data.symbol} FCF ${fcf_billions:.2f}B, Yield {fcf_yield*100:.1f}% - Strong cash generation"
        elif fcf > 0:
            priority = AlertPriority.MEDIUM
            yield_str = f", Yield {fcf_yield*100:.1f}%" if fcf_yield else ""
            message = f"{current_data.symbol} FCF ${fcf_billions:.2f}B{yield_str} - Positive cash flow"
        else:
            priority = AlertPriority.LOW
            message = f"{current_data.symbol} FCF ${fcf_billions:.2f}B - Negative free cash flow"

        signal_strength = min(1, fcf_yield * 10) if fcf_yield and fcf_yield > 0 else (0.5 if fcf > 0 else 0)

        return IndicatorResult(
            indicator_name=self.name,
            symbol=current_data.symbol,
            is_triggered=is_triggered,
            priority=priority,
            signal_strength=signal_strength,
            message=message,
            metadata={"fcf": fcf, "fcf_yield": fcf_yield, "market_cap": market_cap},
        )


class RevenueGrowthIndicator(BaseIndicator):
    """
    Revenue Growth indicator.

    Revenue CAGR > 12% indicates strong growth.
    """

    @property
    def name(self) -> str:
        return "Revenue_Growth"

    def analyze(self, current_data: StockData, historical_data: HistoricalData) -> IndicatorResult:
        threshold = self.get_param("threshold", 0.12)  # 12%

        fundamentals = FundamentalAnalyzer.get_fundamentals(current_data.symbol)
        rev_growth = fundamentals.get("revenue_growth")

        if rev_growth is None:
            return IndicatorResult(
                indicator_name=self.name,
                symbol=current_data.symbol,
                is_triggered=False,
                signal_strength=0.0,
                message=f"{current_data.symbol}: Revenue growth not available",
                metadata={"revenue_growth": None},
            )

        is_triggered = rev_growth >= threshold
        growth_pct = rev_growth * 100

        if rev_growth >= 0.20:
            priority = AlertPriority.HIGH
            message = f"{current_data.symbol} Revenue growth {growth_pct:.1f}% - Exceptional growth"
        elif rev_growth >= threshold:
            priority = AlertPriority.MEDIUM
            message = f"{current_data.symbol} Revenue growth {growth_pct:.1f}% - Strong growth"
        else:
            priority = AlertPriority.LOW
            message = f"{current_data.symbol} Revenue growth {growth_pct:.1f}% - Below threshold ({threshold*100:.0f}%)"

        signal_strength = min(1, rev_growth / 0.25) if rev_growth > 0 else 0

        return IndicatorResult(
            indicator_name=self.name,
            symbol=current_data.symbol,
            is_triggered=is_triggered,
            priority=priority,
            signal_strength=signal_strength,
            message=message,
            metadata={"revenue_growth": rev_growth, "threshold": threshold},
        )


class EarningsGrowthIndicator(BaseIndicator):
    """
    Earnings/EPS Growth indicator.

    EPS CAGR > 15% indicates strong earnings growth.
    """

    @property
    def name(self) -> str:
        return "Earnings_Growth"

    def analyze(self, current_data: StockData, historical_data: HistoricalData) -> IndicatorResult:
        threshold = self.get_param("threshold", 0.15)  # 15%

        fundamentals = FundamentalAnalyzer.get_fundamentals(current_data.symbol)
        earnings_growth = fundamentals.get("earnings_growth")

        if earnings_growth is None:
            return IndicatorResult(
                indicator_name=self.name,
                symbol=current_data.symbol,
                is_triggered=False,
                signal_strength=0.0,
                message=f"{current_data.symbol}: Earnings growth not available",
                metadata={"earnings_growth": None},
            )

        is_triggered = earnings_growth >= threshold
        growth_pct = earnings_growth * 100

        if earnings_growth >= 0.25:
            priority = AlertPriority.HIGH
            message = f"{current_data.symbol} EPS growth {growth_pct:.1f}% - Exceptional earnings growth"
        elif earnings_growth >= threshold:
            priority = AlertPriority.MEDIUM
            message = f"{current_data.symbol} EPS growth {growth_pct:.1f}% - Strong earnings growth"
        else:
            priority = AlertPriority.LOW
            message = f"{current_data.symbol} EPS growth {growth_pct:.1f}% - Below threshold ({threshold*100:.0f}%)"

        signal_strength = min(1, earnings_growth / 0.30) if earnings_growth > 0 else 0

        return IndicatorResult(
            indicator_name=self.name,
            symbol=current_data.symbol,
            is_triggered=is_triggered,
            priority=priority,
            signal_strength=signal_strength,
            message=message,
            metadata={"earnings_growth": earnings_growth, "threshold": threshold},
        )


class FundamentalScoreIndicator(BaseIndicator):
    """
    Composite Fundamental Score indicator.

    Checks how many of the key fundamental criteria a stock meets:
    - PEG < 1.5
    - Debt-to-Equity < 0.6
    - Operating Margins > 15%
    - ROIC > 15%
    - Positive FCF
    - Revenue Growth > 12%
    - EPS Growth > 15%

    Triggers when 5+ criteria are met (configurable).
    """

    @property
    def name(self) -> str:
        return "Fundamental_Score"

    def analyze(self, current_data: StockData, historical_data: HistoricalData) -> IndicatorResult:
        min_score = self.get_param("min_score", 5)

        fundamentals = FundamentalAnalyzer.get_fundamentals(current_data.symbol)

        checks = {
            "PEG < 1.5": False,
            "D/E < 0.6": False,
            "Op Margin > 15%": False,
            "ROIC > 15%": False,
            "Positive FCF": False,
            "Rev Growth > 12%": False,
            "EPS Growth > 15%": False,
        }

        # PEG ratio
        peg = fundamentals.get("peg_ratio")
        if peg and 0 < peg < 1.5:
            checks["PEG < 1.5"] = True

        # Debt to Equity
        de = fundamentals.get("debt_to_equity")
        if de is not None:
            de = de / 100 if de > 10 else de  # Normalize
            if de < 0.6:
                checks["D/E < 0.6"] = True

        # Operating Margins
        op_margin = fundamentals.get("operating_margins")
        if op_margin and op_margin > 0.15:
            checks["Op Margin > 15%"] = True

        # ROIC (using ROE as proxy)
        roe = fundamentals.get("return_on_equity")
        if roe and roe > 0.15:
            checks["ROIC > 15%"] = True

        # Free Cash Flow
        fcf = fundamentals.get("free_cash_flow")
        if fcf and fcf > 0:
            checks["Positive FCF"] = True

        # Revenue Growth
        rev_growth = fundamentals.get("revenue_growth")
        if rev_growth and rev_growth > 0.12:
            checks["Rev Growth > 12%"] = True

        # Earnings Growth
        eps_growth = fundamentals.get("earnings_growth")
        if eps_growth and eps_growth > 0.15:
            checks["EPS Growth > 15%"] = True

        score = sum(1 for v in checks.values() if v)
        is_triggered = score >= min_score

        passed = [k for k, v in checks.items() if v]
        failed = [k for k, v in checks.items() if not v]

        if score >= 6:
            priority = AlertPriority.HIGH
            message = f"{current_data.symbol} Fundamental Score {score}/7 - Excellent fundamentals! Passed: {', '.join(passed)}"
        elif score >= min_score:
            priority = AlertPriority.MEDIUM
            message = f"{current_data.symbol} Fundamental Score {score}/7 - Strong fundamentals. Passed: {', '.join(passed)}"
        else:
            priority = AlertPriority.LOW
            message = f"{current_data.symbol} Fundamental Score {score}/7 - Below threshold. Missing: {', '.join(failed)}"

        signal_strength = score / 7

        return IndicatorResult(
            indicator_name=self.name,
            symbol=current_data.symbol,
            is_triggered=is_triggered,
            priority=priority,
            signal_strength=signal_strength,
            message=message,
            metadata={
                "score": score,
                "max_score": 7,
                "min_score": min_score,
                "checks": checks,
                "passed": passed,
                "failed": failed,
            },
        )

