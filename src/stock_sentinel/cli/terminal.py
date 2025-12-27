"""Terminal CLI for Stock Sentinel configuration and management."""

import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from stock_sentinel import __version__
from stock_sentinel.config.settings import get_settings
from stock_sentinel.data.providers.yahoo import YahooFinanceProvider
from stock_sentinel.indicators import indicator_registry
from stock_sentinel.scheduler.jobs import run_scheduler
from stock_sentinel.storage.database import get_database, init_database

app = typer.Typer(
    name="stock-sentinel",
    help="Stock Sentinel - Real-time stock monitoring with SMS alerts",
    add_completion=False,
)

console = Console()


def run_async(coro):
    """Helper to run async functions."""
    return asyncio.get_event_loop().run_until_complete(coro)


@app.command()
def version():
    """Show version information."""
    console.print(f"[bold blue]Stock Sentinel[/bold blue] v{__version__}")


@app.command()
def start(
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Run as daemon"),
):
    """Start the stock monitoring scheduler."""
    console.print(
        Panel.fit(
            "[bold green]Starting Stock Sentinel[/bold green]\n" "Press Ctrl+C to stop",
            title="🚀 Stock Sentinel",
        )
    )

    async def _start():
        await init_database()
        await run_scheduler()

    try:
        run_async(_start())
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")


@app.command()
def check(
    symbols: Annotated[
        list[str] | None,
        typer.Argument(help="Stock symbols to check (e.g., AAPL GOOGL)"),
    ] = None,
):
    """Run a one-time check on specified stocks or watchlist."""
    settings = get_settings()

    async def _check():
        await init_database()
        provider = YahooFinanceProvider()

        check_symbols = symbols if symbols else settings.watchlist

        console.print(f"[bold]Checking {len(check_symbols)} stocks...[/bold]\n")

        for symbol in check_symbols:
            try:
                stock_data = await provider.get_stock_data(symbol)

                console.print(
                    f"[bold cyan]{symbol}[/bold cyan] - ${stock_data.quote.price:.2f} "
                    f"({stock_data.quote.change_percent:+.2f}%)"
                )

                results = await indicator_registry.analyze_all(stock_data)

                for result in results:
                    color = (
                        "green"
                        if result.signal.is_bullish
                        else "red" if result.signal.is_bearish else "yellow"
                    )
                    alert_marker = "🔔" if result.should_alert else ""
                    console.print(
                        f"  [{color}]{result.signal.emoji} {result.indicator_name}:[/{color}] "
                        f"{result.message} {alert_marker}"
                    )

                console.print()

            except Exception as e:
                console.print(f"[red]Error checking {symbol}: {e}[/red]")

    run_async(_check())


@app.command()
def watchlist():
    """Manage the stock watchlist."""

    async def _watchlist():
        await init_database()
        db = get_database()

        while True:
            console.clear()
            console.print(Panel.fit("[bold]Stock Watchlist[/bold]", title="📋 Watchlist"))

            items = await db.get_watchlist(enabled_only=False)

            if items:
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Symbol", style="cyan")
                table.add_column("Status")
                table.add_column("Notes")
                table.add_column("Added")

                for item in items:
                    status = "✅ Active" if item.enabled else "❌ Disabled"
                    table.add_row(
                        item.symbol,
                        status,
                        item.notes or "-",
                        item.added_at.strftime("%Y-%m-%d"),
                    )

                console.print(table)
            else:
                console.print("[yellow]Watchlist is empty[/yellow]")

            console.print("\n[bold]Options:[/bold]")
            console.print("  [a] Add symbol")
            console.print("  [r] Remove symbol")
            console.print("  [q] Quit")

            choice = Prompt.ask("Choose an option", choices=["a", "r", "q"], default="q")

            if choice == "q":
                break
            elif choice == "a":
                symbol = Prompt.ask("Enter stock symbol").upper()
                notes = Prompt.ask("Add notes (optional)", default="")
                await db.add_to_watchlist(symbol, notes if notes else None)
                console.print(f"[green]Added {symbol} to watchlist[/green]")
                await asyncio.sleep(1)
            elif choice == "r":
                symbol = Prompt.ask("Enter symbol to remove").upper()
                if await db.remove_from_watchlist(symbol):
                    console.print(f"[yellow]Removed {symbol} from watchlist[/yellow]")
                else:
                    console.print(f"[red]Symbol {symbol} not found[/red]")
                await asyncio.sleep(1)

    run_async(_watchlist())


@app.command()
def phones():
    """Manage phone numbers for notifications."""

    async def _phones():
        await init_database()
        db = get_database()

        while True:
            console.clear()
            console.print(Panel.fit("[bold]Phone Numbers[/bold]", title="📱 Notifications"))

            numbers = await db.get_phone_numbers(enabled_only=False)

            if numbers:
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Phone Number", style="cyan")
                table.add_column("Label")
                table.add_column("Status")
                table.add_column("Added")

                for num in numbers:
                    status = "✅ Active" if num.enabled else "❌ Disabled"
                    table.add_row(
                        num.phone_number,
                        num.label or "-",
                        status,
                        num.added_at.strftime("%Y-%m-%d"),
                    )

                console.print(table)
            else:
                console.print("[yellow]No phone numbers configured[/yellow]")

            console.print("\n[bold]Options:[/bold]")
            console.print("  [a] Add phone number")
            console.print("  [r] Remove phone number")
            console.print("  [q] Quit")

            choice = Prompt.ask("Choose an option", choices=["a", "r", "q"], default="q")

            if choice == "q":
                break
            elif choice == "a":
                phone = Prompt.ask("Enter phone number (with country code, e.g., +1234567890)")
                label = Prompt.ask("Add label (optional)", default="")
                await db.add_phone_number(phone, label if label else None)
                console.print(f"[green]Added {phone}[/green]")
                await asyncio.sleep(1)
            elif choice == "r":
                phone = Prompt.ask("Enter phone number to remove")
                if await db.remove_phone_number(phone):
                    console.print(f"[yellow]Removed {phone}[/yellow]")
                else:
                    console.print("[red]Phone number not found[/red]")
                await asyncio.sleep(1)

    run_async(_phones())


@app.command()
def indicators():
    """List all available indicators."""
    console.print(Panel.fit("[bold]Available Indicators[/bold]", title="📊 Indicators"))

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("History Required")

    for name in indicator_registry.list_indicators():
        indicator = indicator_registry.get(name)
        table.add_row(
            indicator.name,
            indicator.description,
            f"{indicator.required_history_days} days",
        )

    console.print(table)


@app.command()
def config():
    """Show current configuration."""
    settings = get_settings()

    console.print(Panel.fit("[bold]Current Configuration[/bold]", title="⚙️ Config"))

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    table.add_row("Check Interval", f"{settings.check_interval_minutes} minutes")
    table.add_row("Market Hours Only", str(settings.market_hours_only))
    table.add_row("Cooldown Period", f"{settings.cooldown_minutes} minutes")
    table.add_row("Max Alerts/Hour", str(settings.max_alerts_per_hour))
    table.add_row("RSI Oversold", str(settings.rsi_oversold))
    table.add_row("RSI Overbought", str(settings.rsi_overbought))
    table.add_row("Volume Spike Multiplier", f"{settings.volume_spike_multiplier}x")
    table.add_row("Price Change Threshold", f"{settings.price_change_threshold}%")
    table.add_row("Default Watchlist", ", ".join(settings.watchlist))

    console.print(table)

    console.print("\n[dim]Configuration is loaded from environment variables.[/dim]")
    console.print("[dim]Prefix: STOCK_SENTINEL_[/dim]")


@app.command()
def quote(symbol: str = typer.Argument(..., help="Stock symbol")):
    """Get a quick quote for a stock."""

    async def _quote():
        provider = YahooFinanceProvider()

        try:
            stock_data = await provider.get_stock_data(symbol.upper())
            quote = stock_data.quote

            console.print(
                Panel.fit(
                    f"[bold cyan]{symbol.upper()}[/bold cyan]\n\n"
                    f"Price: [bold]${quote.price:.2f}[/bold]\n"
                    f"Change: [{('green' if quote.change >= 0 else 'red')}]"
                    f"${quote.change:+.2f} ({quote.change_percent:+.2f}%)[/]\n"
                    f"Volume: {quote.volume:,}\n"
                    f"52W Range: ${quote.week_52_low:.2f} - ${quote.week_52_high:.2f}",
                    title="📈 Quote",
                )
            )

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    run_async(_quote())


if __name__ == "__main__":
    app()
