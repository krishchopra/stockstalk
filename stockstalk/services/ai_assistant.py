"""AI-powered investment assistant using OpenAI gpt-5-nano with function calling."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from openai import OpenAI

from stockstalk.models import WatchlistItem
from stockstalk.services.analyzer import IndicatorRegistry
from stockstalk.services.data_fetcher import StockDataFetcher
from stockstalk.services.etf_holdings import ETFHoldingsFetcher
from stockstalk.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class StockInsight:
    """Analysis insight for a single stock."""

    symbol: str
    price: float
    change_percent: float
    composite_score: float
    triggered_signals: list[str]
    key_metrics: dict[str, Any]
    recommendation: str  # "bullish", "bearish", "neutral", "hold"


@dataclass
class DigestData:
    """Data for generating a daily digest."""

    watchlist_insights: list[StockInsight]
    discovery_insights: list[StockInsight]  # From VTI scanning
    market_summary: str
    generated_at: datetime


# =============================================================================
# Tool Definitions - These are the functions the AI can call
# =============================================================================

TOOLS = [
    {
        "type": "function",
        "name": "get_stock_quote",
        "description": "Get the current price and basic info for a stock. Use this for quick price checks.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)",
                }
            },
            "required": ["symbol"],
        },
    },
    {
        "type": "function",
        "name": "analyze_stock",
        "description": "Get comprehensive analysis for a stock including technical indicators, fundamentals, and a recommendation. Use this when the user wants detailed analysis or asks if they should buy/sell.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)",
                }
            },
            "required": ["symbol"],
        },
    },
    {
        "type": "function",
        "name": "get_watchlist",
        "description": "Get the user's current watchlist of stocks they're tracking.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "add_to_watchlist",
        "description": "Add a stock to the user's watchlist so they receive alerts about it.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock ticker symbol to add (e.g., AAPL)",
                }
            },
            "required": ["symbol"],
        },
    },
    {
        "type": "function",
        "name": "remove_from_watchlist",
        "description": "Remove a stock from the user's watchlist.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock ticker symbol to remove",
                }
            },
            "required": ["symbol"],
        },
    },
    {
        "type": "function",
        "name": "scan_opportunities",
        "description": "Scan the market (VTI holdings) for investment opportunities based on technical and fundamental analysis. Returns top stocks with strong signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of opportunities to return (default: 3, max: 5)",
                }
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "get_market_overview",
        "description": "Get an overview of the overall market using major indices (SPY, QQQ, VTI).",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "get_watchlist_summary",
        "description": "Get a summary of the user's watchlist with current prices, daily changes, scores, and recommendations for each stock they're tracking. This is NOT their actual brokerage portfolio - just the stocks they're monitoring.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "compare_stocks",
        "description": "Compare two or more stocks side by side on key metrics.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of stock symbols to compare (e.g., ['AAPL', 'MSFT'])",
                }
            },
            "required": ["symbols"],
        },
    },
    {
        "type": "function",
        "name": "web_search",
        "description": "Search the web for current news, information, or anything else. Use this when the user asks about recent events, news, or anything you don't have data for.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query (e.g., 'AAPL earnings news', 'tech sector outlook 2024')",
                }
            },
            "required": ["query"],
        },
    },
]

SYSTEM_PROMPT = """you're a chill friend who knows a lot about stocks and investing. you text like a normal person - all lowercase, casual, helpful.

you have tools to look up real stock data. use them when needed, but you can also just chat!

you ARE allowed to give financial advice. you're their investing buddy - tell them what you'd do, what looks good, what to avoid. be opinionated and helpful.

important:
- users have a WATCHLIST (stocks they're tracking) - NOT an actual brokerage portfolio
- when they say "my stocks" they mean their watchlist
- we don't know their real holdings or cost basis
- don't treat casual greetings or words like "hey", "hi", "what's up" as stock symbols
- only use stock tools when the user is actually asking about stocks or investing
- if someone's just chatting (like "hey what's up" or "how are you"), just respond naturally without tools
- you have conversation context from previous messages, so you can reference things you talked about before
- use web_search for news, recent events, or anything you need to look up

CRITICAL: when tools return results, they may include a "message" field with formatted text. ALWAYS extract and use the "message" field from tool results - never output raw JSON. if a tool returns {"message": "some text"}, you should respond with "some text" (formatted nicely), not the JSON itself.

your vibe:
- ALL LOWERCASE always. never capitalize anything except stock symbols like AAPL
- sound like you're texting a friend, not writing a formal report
- keep it short - this is SMS, not an essay
- use casual language: "looks good", "not great tbh", "i'd keep an eye on it"
- throw in some personality: "nice!", "ooh", "hmm", "honestly..."
- be direct and helpful, skip the fluff
- include actual numbers - don't be vague
- give real opinions: "i'd buy this", "i'd wait", "looks risky tbh"
- if you're not sure, just say so

examples of your tone:
- "aapl's at $195.50, up 1.2% today. looking solid with a score of 67/100. i'd buy 📈"
- "hmm nvda's been on a tear lately. score's 72/100 which is strong. definitely add this one"
- "your watchlist is doing okay - average +0.8% today. msft's your top performer"
- "added tsla to your list ✓"
- "honestly the market's pretty flat today, nothing too exciting"
- "i'd stay away from that one tbh, fundamentals look weak"

important scoring:
- composite_score is always "X/100" (overall stock score)
- fundamental_score in key_metrics is "X/7" (fundamental analysis only)
- always include the scale so it's clear: "score 72/100" not just "score 72"

remember: you're helpful, opinionated, and knowledgeable. text like a real person who genuinely wants to help their friend make money."""


class AIAssistant:
    """AI-powered assistant with function calling for investment insights."""

    def __init__(self) -> None:
        """Initialize the AI assistant."""
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.OPENAI_MODEL
        self.data_fetcher = StockDataFetcher()

        # Initialize OpenAI client
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
        else:
            self.client = None
            logger.warning(
                "OpenAI API key not configured. Set OPENAI_API_KEY environment variable."
            )

        # These get set per-request for tool execution
        self._current_user_phone: str | None = None
        self._current_user_watchlist: list[WatchlistItem] = []
        self._db = None

    def is_configured(self) -> bool:
        """Check if OpenAI is properly configured."""
        return bool(self.api_key)

    # =========================================================================
    # Tool Implementations
    # =========================================================================

    async def _tool_get_stock_quote(self, symbol: str) -> dict[str, Any]:
        """Get quick quote for a stock."""
        try:
            stock_data = await self.data_fetcher.get_current_data(symbol.upper())
            change_pct = 0.0
            if stock_data.previous_close > 0:
                change_pct = (
                    (stock_data.current_price - stock_data.previous_close)
                    / stock_data.previous_close
                    * 100
                )
            return {
                "symbol": symbol.upper(),
                "price": round(stock_data.current_price, 2),
                "change_percent": round(change_pct, 2),
                "volume": stock_data.volume,
                "high": round(stock_data.high_price, 2),
                "low": round(stock_data.low_price, 2),
            }
        except Exception as e:
            return {"error": f"Could not find stock {symbol}: {str(e)}"}

    async def _tool_analyze_stock(self, symbol: str) -> dict[str, Any]:
        """Get comprehensive stock analysis."""
        try:
            insight = await self.analyze_stock_full(symbol)
            return {
                "symbol": insight.symbol,
                "price": insight.price,
                "change_percent": insight.change_percent,
                "composite_score": f"{insight.composite_score}/100",  # Always show as X/100
                "recommendation": insight.recommendation,
                "triggered_signals": insight.triggered_signals,
                "key_metrics": insight.key_metrics,
            }
        except Exception as e:
            return {"error": f"Could not analyze {symbol}: {str(e)}"}

    async def _tool_get_watchlist(self) -> dict[str, Any]:
        """Get user's watchlist."""
        if not self._current_user_watchlist:
            return {
                "message": "your watchlist is empty - add some stocks! text 'add aapl' to get started"
            }

        symbols = [item.symbol.upper() for item in self._current_user_watchlist]
        if len(symbols) == 1:
            return {"message": f"you're tracking: {symbols[0]}"}
        else:
            symbols_str = ", ".join(symbols[:-1]) + f" and {symbols[-1]}"
            return {
                "message": f"you're tracking {len(symbols)} stocks: {symbols_str}",
                "symbols": symbols,  # Keep for reference if needed
            }

    async def _tool_add_to_watchlist(self, symbol: str) -> dict[str, Any]:
        """Add stock to watchlist."""
        symbol = symbol.upper()

        if not self._db or not self._current_user_phone:
            return {"error": "Database not available"}

        try:
            # Check if already exists
            if any(
                item.symbol.upper() == symbol for item in self._current_user_watchlist
            ):
                return {
                    "success": False,
                    "message": f"{symbol} is already in your watchlist",
                }

            await self._db.add_to_user_watchlist(
                self._current_user_phone,
                symbol,
                enabled_indicators=settings.DEFAULT_INDICATORS,
            )
            return {"success": True, "message": f"Added {symbol} to your watchlist"}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_remove_from_watchlist(self, symbol: str) -> dict[str, Any]:
        """Remove stock from watchlist."""
        symbol = symbol.upper()

        if not self._db or not self._current_user_phone:
            return {"error": "Database not available"}

        try:
            removed = await self._db.remove_from_user_watchlist(
                self._current_user_phone, symbol
            )
            if removed:
                return {
                    "success": True,
                    "message": f"Removed {symbol} from your watchlist",
                }
            else:
                return {
                    "success": False,
                    "message": f"{symbol} was not in your watchlist",
                }
        except Exception as e:
            return {"error": str(e)}

    async def _tool_scan_opportunities(self, count: int = 3) -> dict[str, Any]:
        """Scan for investment opportunities."""
        count = min(count or 3, 5)

        try:
            opportunities = await self.scan_for_opportunities(
                top_n=50,
                min_score=50.0,
                max_results=count,
            )

            # Filter out stocks already in watchlist
            watchlist_symbols = {
                item.symbol.upper() for item in self._current_user_watchlist
            }
            new_opps = [o for o in opportunities if o.symbol not in watchlist_symbols]

            return {
                "opportunities": [
                    {
                        "symbol": o.symbol,
                        "price": o.price,
                        "score": f"{o.composite_score:.0f}/100",  # Composite score out of 100
                        "recommendation": o.recommendation,
                        "signals": o.triggered_signals[:3],
                    }
                    for o in new_opps[:count]
                ],
                "count": len(new_opps[:count]),
            }
        except Exception as e:
            return {"error": str(e)}

    async def _tool_get_market_overview(self) -> dict[str, Any]:
        """Get market overview."""
        try:
            symbols = ["SPY", "QQQ", "VTI"]
            results = []

            for symbol in symbols:
                try:
                    insight = await self.analyze_stock_full(symbol)
                    results.append(
                        {
                            "symbol": symbol,
                            "price": insight.price,
                            "change_percent": insight.change_percent,
                            "trend": "up"
                            if insight.change_percent > 0
                            else "down"
                            if insight.change_percent < 0
                            else "flat",
                        }
                    )
                except Exception:
                    pass

            return {"indices": results}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_get_watchlist_summary(self) -> dict[str, Any]:
        """Get watchlist summary with analysis for each tracked stock."""
        if not self._current_user_watchlist:
            return {
                "message": "your watchlist is empty! text 'add aapl' to start tracking stocks"
            }

        try:
            insights = []
            for item in self._current_user_watchlist:
                try:
                    insight = await self.analyze_stock_full(item.symbol)
                    insights.append(insight)
                except Exception:
                    pass

            if not insights:
                return {"error": "Could not analyze watchlist stocks"}

            total_change = sum(i.change_percent for i in insights) / len(insights)
            bullish = [i for i in insights if i.recommendation == "bullish"]
            bearish = [i for i in insights if i.recommendation == "bearish"]

            return {
                "stocks": [
                    {
                        "symbol": i.symbol,
                        "price": i.price,
                        "change_percent": i.change_percent,
                        "score": f"{i.composite_score:.0f}/100",  # Composite score out of 100
                        "recommendation": i.recommendation,
                    }
                    for i in insights
                ],
                "summary": {
                    "total_stocks": len(insights),
                    "average_change": round(total_change, 2),
                    "bullish_count": len(bullish),
                    "bearish_count": len(bearish),
                },
            }
        except Exception as e:
            return {"error": str(e)}

    async def _tool_compare_stocks(self, symbols: list[str]) -> dict[str, Any]:
        """Compare multiple stocks."""
        if len(symbols) < 2:
            return {"error": "Need at least 2 symbols to compare"}

        symbols = [s.upper() for s in symbols[:4]]  # Max 4 stocks

        try:
            comparisons = []
            for symbol in symbols:
                try:
                    insight = await self.analyze_stock_full(symbol)
                    comparisons.append(
                        {
                            "symbol": insight.symbol,
                            "price": insight.price,
                            "change_percent": insight.change_percent,
                            "score": f"{insight.composite_score:.0f}/100",  # Composite score out of 100
                            "recommendation": insight.recommendation,
                            "key_metrics": insight.key_metrics,  # May contain fundamental_score X/7
                        }
                    )
                except Exception as e:
                    comparisons.append({"symbol": symbol, "error": str(e)})

            # Find the best one
            valid = [c for c in comparisons if "error" not in c]
            best = max(valid, key=lambda x: x["score"]) if valid else None

            return {
                "comparisons": comparisons,
                "best_pick": best["symbol"] if best else None,
            }
        except Exception as e:
            return {"error": str(e)}

    async def _tool_web_search(self, query: str) -> dict[str, Any]:
        """Search the web using DuckDuckGo."""
        try:
            # Use DuckDuckGo's HTML search (no API key needed)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (compatible; StockStalk/1.0)"},
                )

                if response.status_code != 200:
                    return {"error": "Search failed", "results": []}

                # Parse the HTML response for search results
                html = response.text
                results = []

                # Extract result snippets using simple parsing
                # DuckDuckGo HTML results are in <a class="result__a"> and <a class="result__snippet">
                # Find all result blocks
                result_pattern = re.compile(
                    r'class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>.*?'
                    r'class="result__snippet"[^>]*>([^<]*)',
                    re.DOTALL,
                )

                matches = result_pattern.findall(html)
                for match in matches[:5]:  # Top 5 results
                    url, title, snippet = match
                    if title.strip() and snippet.strip():
                        results.append(
                            {
                                "title": title.strip(),
                                "snippet": snippet.strip()[:200],
                                "url": url,
                            }
                        )

                # If regex didn't work well, try a simpler approach
                if not results:
                    # Look for result__snippet divs
                    snippet_pattern = re.compile(
                        r"result__snippet[^>]*>([^<]+)<", re.DOTALL
                    )
                    snippets = snippet_pattern.findall(html)
                    for i, snippet in enumerate(snippets[:5]):
                        if snippet.strip():
                            results.append(
                                {
                                    "title": f"Result {i + 1}",
                                    "snippet": snippet.strip()[:200],
                                }
                            )

                if results:
                    # Format results into a readable message
                    lines = [f"found {len(results)} results for '{query}':"]
                    for i, result in enumerate(results, 1):
                        title = result.get("title", "Result")
                        snippet = result.get("snippet", "")
                        url = result.get("url", "")
                        lines.append(f"\n{i}. {title}")
                        if snippet:
                            lines.append(f"   {snippet}")
                        if url:
                            lines.append(f"   {url}")

                    return {
                        "message": "\n".join(lines),
                        "results": results,  # Keep structured data for reference
                    }
                else:
                    return {
                        "message": f"no results found for '{query}'. try a different search.",
                    }

        except Exception as e:
            logger.error(f"Web search error: {e}")
            return {
                "message": f"search failed: {str(e)}. try again or rephrase your query."
            }

    # =========================================================================
    # Tool Execution Engine
    # =========================================================================

    async def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool and return the result as a string."""
        logger.info(f"Executing tool: {tool_name} with args: {arguments}")

        tool_map = {
            "get_stock_quote": lambda: self._tool_get_stock_quote(
                arguments.get("symbol", "")
            ),
            "analyze_stock": lambda: self._tool_analyze_stock(
                arguments.get("symbol", "")
            ),
            "get_watchlist": lambda: self._tool_get_watchlist(),
            "add_to_watchlist": lambda: self._tool_add_to_watchlist(
                arguments.get("symbol", "")
            ),
            "remove_from_watchlist": lambda: self._tool_remove_from_watchlist(
                arguments.get("symbol", "")
            ),
            "scan_opportunities": lambda: self._tool_scan_opportunities(
                arguments.get("count", 3)
            ),
            "get_market_overview": lambda: self._tool_get_market_overview(),
            "get_watchlist_summary": lambda: self._tool_get_watchlist_summary(),
            "compare_stocks": lambda: self._tool_compare_stocks(
                arguments.get("symbols", [])
            ),
            "web_search": lambda: self._tool_web_search(arguments.get("query", "")),
        }

        if tool_name not in tool_map:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        try:
            result = await tool_map[tool_name]()
            return json.dumps(result)
        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return json.dumps({"error": str(e)})

    # =========================================================================
    # Agentic Conversation Loop
    # =========================================================================

    async def chat(
        self,
        user_message: str,
        user_phone: str,
        user_watchlist: list[WatchlistItem],
        db: Any = None,
    ) -> str:
        """
        Process a natural language message using AI with function calling.

        This is the main entry point for the agentic assistant.

        Args:
            user_message: The user's text message
            user_phone: User's phone number
            user_watchlist: User's current watchlist
            db: Database instance for modifications

        Returns:
            Response text to send back
        """
        if not self.is_configured():
            return await self._fallback_response(user_message, user_watchlist)

        # Set context for tool execution
        self._current_user_phone = user_phone
        self._current_user_watchlist = user_watchlist
        self._db = db

        try:
            # Get conversation history (last 10 messages)
            conversation_history = []
            if db:
                try:
                    conversation_history = await db.get_conversation_history(
                        user_phone, limit=10
                    )
                except Exception as e:
                    logger.debug(f"Could not fetch conversation history: {e}")

            # Build initial request with context
            watchlist_context = ""
            if user_watchlist:
                symbols = [item.symbol for item in user_watchlist[:10]]
                watchlist_context = (
                    f"\n\nUser's current watchlist: {', '.join(symbols)}"
                )

            # Build conversation context
            history_text = ""
            if conversation_history:
                history_lines = []
                for msg in conversation_history[-10:]:  # Last 10 messages
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role == "user":
                        history_lines.append(f"user: {content}")
                    else:
                        history_lines.append(f"you: {content}")
                if history_lines:
                    history_text = "\n\nrecent conversation:\n" + "\n".join(
                        history_lines
                    )

            input_text = f"{SYSTEM_PROMPT}{watchlist_context}{history_text}\n\nUser message: {user_message}"

            # Make the API call with tools using OpenAI client
            if not self.client:
                return await self._fallback_response(user_message, user_watchlist)

            try:
                logger.debug(f"Calling OpenAI API with model {self.model}")
                # Run synchronous OpenAI call in thread pool
                response = await asyncio.to_thread(
                    self.client.responses.create,
                    model=self.model,
                    input=input_text,
                    tools=TOOLS,
                )
                logger.debug("OpenAI API response received")

                # Extract response data
                data = {
                    "id": response.id if hasattr(response, "id") else None,
                    "output": response.output if hasattr(response, "output") else [],
                    "output_text": response.output_text
                    if hasattr(response, "output_text")
                    else "",
                }
            except Exception as e:
                logger.error(f"OpenAI API request error: {e}", exc_info=True)
                return await self._fallback_response(user_message, user_watchlist)

            # Process the response - handle tool calls in a loop
            max_iterations = 5
            iteration = 0

            while iteration < max_iterations:
                iteration += 1

                # Check for output_text first (primary response format from OpenAI)
                output_text = data.get("output_text", "")
                if output_text and not data.get(
                    "output"
                ):  # If we have output_text and no tool calls
                    response_text = str(output_text).lower()
                    # Save conversation
                    if db:
                        try:
                            await db.add_conversation_message(
                                user_phone, "user", user_message
                            )
                            await db.add_conversation_message(
                                user_phone, "assistant", response_text
                            )
                        except Exception as e:
                            logger.debug(f"Could not save conversation: {e}")
                    return response_text

                # Check if there are tool calls to process
                output = data.get("output", [])

                # Handle different response formats
                if isinstance(output, str):
                    # Direct text response
                    response_text = output.lower()
                    # Save conversation
                    if db:
                        try:
                            await db.add_conversation_message(
                                user_phone, "user", user_message
                            )
                            await db.add_conversation_message(
                                user_phone, "assistant", response_text
                            )
                        except Exception as e:
                            logger.debug(f"Could not save conversation: {e}")
                    return response_text

                if isinstance(output, list):
                    tool_calls = [
                        item
                        for item in output
                        if isinstance(item, dict)
                        and item.get("type") == "function_call"
                    ]
                    text_outputs = [
                        item
                        for item in output
                        if isinstance(item, dict) and item.get("type") == "message"
                    ]

                    if not tool_calls:
                        # No more tool calls, return the text
                        if text_outputs:
                            last_output = text_outputs[-1]
                            # Handle different content formats from OpenAI API
                            content = ""
                            if isinstance(last_output, dict):
                                raw_content = last_output.get("content", "")
                                # Content can be a string or a list of content blocks
                                if isinstance(raw_content, str):
                                    content = raw_content
                                elif isinstance(raw_content, list):
                                    # Extract text from content blocks
                                    text_parts = []
                                    for block in raw_content:
                                        if isinstance(block, str):
                                            text_parts.append(block)
                                        elif isinstance(block, dict):
                                            # Handle {"type": "text", "text": "..."} format
                                            if block.get("type") == "text":
                                                text_parts.append(block.get("text", ""))
                                            elif "text" in block:
                                                text_parts.append(block.get("text", ""))
                                    content = " ".join(text_parts)
                                else:
                                    content = str(raw_content)
                            elif isinstance(last_output, str):
                                content = last_output
                            else:
                                content = str(last_output)
                            response_text = (
                                content.lower()
                                if content
                                else "i couldn't process that. try again."
                            )
                            # Save conversation
                            if db:
                                try:
                                    await db.add_conversation_message(
                                        user_phone, "user", user_message
                                    )
                                    await db.add_conversation_message(
                                        user_phone, "assistant", response_text
                                    )
                                except Exception as e:
                                    logger.debug(f"Could not save conversation: {e}")
                            return response_text
                        # Try output_text as fallback
                        output_text = data.get("output_text", "")
                        if output_text:
                            response_text = str(output_text).lower()
                            # Save conversation
                            if db:
                                try:
                                    await db.add_conversation_message(
                                        user_phone, "user", user_message
                                    )
                                    await db.add_conversation_message(
                                        user_phone, "assistant", response_text
                                    )
                                except Exception as e:
                                    logger.debug(f"Could not save conversation: {e}")
                            return response_text
                        return "i couldn't process that. try again."

                    # Execute all tool calls
                    tool_results = []
                    for tool_call in tool_calls:
                        func_name = tool_call.get("name", "")
                        func_args = tool_call.get("arguments", {})

                        # Parse arguments if they're a string
                        if isinstance(func_args, str):
                            try:
                                func_args = json.loads(func_args)
                            except json.JSONDecodeError:
                                func_args = {}

                        result = await self._execute_tool(func_name, func_args)

                        # Extract "message" field if it exists (for formatted responses)
                        try:
                            result_data = json.loads(result)
                            if "message" in result_data:
                                # Use the formatted message instead of raw JSON
                                result = json.dumps({"message": result_data["message"]})
                        except (json.JSONDecodeError, TypeError):
                            pass  # Keep original result if parsing fails

                        tool_results.append(
                            {
                                "type": "function_call_output",
                                "call_id": tool_call.get("call_id", ""),
                                "output": result,
                            }
                        )

                    # Continue the conversation with tool results
                    try:
                        # Format tool results for OpenAI API
                        # OpenAI expects tool results in a specific format
                        tool_input = (
                            json.dumps(tool_results)
                            if isinstance(tool_results, list)
                            else str(tool_results)
                        )

                        response = await asyncio.to_thread(
                            self.client.responses.create,
                            model=self.model,
                            input=tool_input,
                            previous_response_id=data.get("id"),
                        )

                        # Extract response data
                        data = {
                            "id": response.id if hasattr(response, "id") else None,
                            "output": response.output
                            if hasattr(response, "output")
                            else [],
                            "output_text": response.output_text
                            if hasattr(response, "output_text")
                            else "",
                        }
                    except Exception as e:
                        logger.error(
                            f"OpenAI API continuation error: {e}", exc_info=True
                        )
                        response_text = self._format_tool_results(tool_results)
                        if db:
                            try:
                                await db.add_conversation_message(
                                    user_phone, "user", user_message
                                )
                                await db.add_conversation_message(
                                    user_phone, "assistant", response_text
                                )
                            except Exception:
                                pass
                        return response_text
                else:
                    # Unknown format, try output_text
                    output_text = data.get("output_text", "")
                    if output_text:
                        response_text = str(output_text).lower()
                        # Save conversation at the end
                        if db:
                            try:
                                await db.add_conversation_message(
                                    user_phone, "user", user_message
                                )
                                await db.add_conversation_message(
                                    user_phone, "assistant", response_text
                                )
                            except Exception as e:
                                logger.debug(f"Could not save conversation: {e}")
                        return response_text
                    # Last resort: try to extract any text from output
                    if isinstance(output, list) and output:
                        # If output is a list of strings, join them
                        if all(isinstance(item, str) for item in output):
                            response_text = " ".join(output).lower()
                            # Save conversation
                            if db:
                                try:
                                    await db.add_conversation_message(
                                        user_phone, "user", user_message
                                    )
                                    await db.add_conversation_message(
                                        user_phone, "assistant", response_text
                                    )
                                except Exception as e:
                                    logger.debug(f"Could not save conversation: {e}")
                            return response_text
                    return "i couldn't process that. try again."

            # Max iterations reached - save what we have
            logger.warning(
                f"Max iterations ({max_iterations}) reached for query: {user_message[:50]}"
            )
            response_text = "i'm still thinking about that. try a simpler question."
            if db:
                try:
                    await db.add_conversation_message(user_phone, "user", user_message)
                    await db.add_conversation_message(
                        user_phone, "assistant", response_text
                    )
                except Exception as e:
                    logger.debug(f"Could not save conversation: {e}")
            return response_text

        except Exception as e:
            logger.error(f"Error in chat: {e}", exc_info=True)
            fallback_response = await self._fallback_response(
                user_message, user_watchlist
            )
            # Save conversation even on error
            if db:
                try:
                    await db.add_conversation_message(user_phone, "user", user_message)
                    await db.add_conversation_message(
                        user_phone, "assistant", fallback_response
                    )
                except Exception:
                    pass
            return fallback_response
        finally:
            # Clear context
            self._current_user_phone = None
            self._current_user_watchlist = []
            self._db = None

    def _format_tool_results(self, tool_results: list[dict]) -> str:
        """Format tool results as a readable response."""
        lines = []
        for result in tool_results:
            try:
                data = json.loads(result.get("output", "{}"))
                if "error" in data:
                    lines.append(f"error: {data['error']}")
                elif "symbol" in data:
                    lines.append(f"{data['symbol']}: ${data.get('price', 'N/A')}")
                elif "symbols" in data:
                    lines.append(f"watchlist: {', '.join(data['symbols'])}")
                elif "opportunities" in data:
                    for opp in data["opportunities"]:
                        lines.append(f"{opp['symbol']}: score {opp['score']}")
            except Exception:
                pass

        return "\n".join(lines) if lines else "here's what i found."

    async def _fallback_response(
        self, user_message: str, user_watchlist: list[WatchlistItem]
    ) -> str:
        """Fallback when AI is not available - use pattern matching."""
        message_lower = user_message.lower().strip()

        # Try to extract stock symbols
        potential_symbols = re.findall(r"\b[A-Z]{1,5}\b", user_message.upper())
        common_words = {
            # Common English words
            "I",
            "A",
            "THE",
            "IS",
            "IT",
            "TO",
            "FOR",
            "AND",
            "OR",
            "MY",
            "ME",
            "AM",
            "DO",
            "IN",
            "ON",
            "AT",
            "BY",
            "UP",
            "SO",
            "IF",
            "AS",
            "OF",
            "BE",
            "WE",
            "AN",
            "NO",
            "YES",
            "NOT",
            "BUT",
            "HOW",
            "WHY",
            "WHAT",
            "WHEN",
            "WHO",
            "CAN",
            "ALL",
            "GET",
            "GOT",
            "HAS",
            "HAD",
            "WAS",
            "ARE",
            "BEEN",
            "HAVE",
            "WILL",
            "FROM",
            "WITH",
            "THAT",
            "THIS",
            "THEN",
            "THAN",
            "SOME",
            "JUST",
            "ALSO",
            "ONLY",
            "YOUR",
            "THEM",
            # Greetings and casual words - these are NOT stock symbols!
            "HEY",
            "HI",
            "HELLO",
            "YO",
            "SUP",
            "BYE",
            "OK",
            "OKAY",
            "YEAH",
            "YEP",
            "NAH",
            "WHATS",
            "THANKS",
            "THANK",
            "PLEASE",
            "PLS",
            "LOL",
            "OMG",
            "WOW",
            "COOL",
            "NICE",
            "GOOD",
            "BAD",
            "HELP",
            "GREAT",
            "SURE",
            "FINE",
        }
        symbols = [s for s in potential_symbols if s not in common_words]

        # If the message looks like a greeting, just respond friendly
        greetings = {
            "hey",
            "hi",
            "hello",
            "yo",
            "sup",
            "whats up",
            "what's up",
            "howdy",
        }
        if any(g in message_lower for g in greetings) and not symbols:
            return "hey! what can i help you with? ask me about stocks or your watchlist 📈"

        # Check for specific commands
        if any(word in message_lower for word in ["list", "watchlist", "watching"]):
            if user_watchlist:
                syms = [item.symbol.lower() for item in user_watchlist]
                return f"your watchlist: {', '.join(syms)}"
            return "your watchlist is empty. text 'add aapl' to add stocks."

        if any(
            word in message_lower
            for word in ["opportunities", "suggest", "find", "discover"]
        ):
            try:
                opps = await self.scan_for_opportunities(
                    top_n=30, min_score=50, max_results=3
                )
                if opps:
                    lines = ["opportunities:"]
                    for o in opps:
                        lines.append(
                            f"{o.symbol.lower()}: score {o.composite_score:.0f}"
                        )
                    return "\n".join(lines)
            except Exception:
                pass
            return "couldn't find opportunities right now."

        if any(word in message_lower for word in ["market", "overall", "indices"]):
            try:
                return await self._handle_market_query_fallback()
            except Exception:
                return "couldn't get market data."

        if symbols:
            # Analyze first symbol found
            try:
                insight = await self.analyze_stock_full(symbols[0])
                return (
                    f"{insight.symbol.lower()}: ${insight.price:.2f} "
                    f"({insight.change_percent:+.1f}%)\n"
                    f"score: {insight.composite_score:.0f}/100\n"
                    f"outlook: {insight.recommendation}"
                )
            except Exception:
                return f"couldn't find {symbols[0].lower()}"

        return (
            "hey! i can help with:\n"
            "• just text a symbol like 'aapl' for info\n"
            "• 'opportunities' to find good stocks\n"
            "• 'market' to see how things are going\n"
            "• 'add aapl' or 'remove aapl' for your watchlist\n"
            "or just ask me anything about stocks!"
        )

    async def _handle_market_query_fallback(self) -> str:
        """Fallback market query handler."""
        symbols = ["SPY", "QQQ", "VTI"]
        lines = ["market overview:"]

        for symbol in symbols:
            try:
                insight = await self.analyze_stock_full(symbol)
                emoji = (
                    "🟢"
                    if insight.change_percent > 0
                    else "🔴"
                    if insight.change_percent < 0
                    else "⚪"
                )
                lines.append(
                    f"{symbol.lower()}: ${insight.price:.2f} ({insight.change_percent:+.1f}%) {emoji}"
                )
            except Exception:
                pass

        return "\n".join(lines)

    # =========================================================================
    # Stock Analysis (used by tools)
    # =========================================================================

    async def analyze_stock_full(self, symbol: str) -> StockInsight:
        """Get comprehensive analysis for a stock."""
        try:
            stock_data, historical_data = await self.data_fetcher.get_stock_data(
                symbol.upper(), days=30
            )

            price = stock_data.current_price
            prev_close = stock_data.previous_close
            change_percent = (
                ((price - prev_close) / prev_close) * 100 if prev_close else 0
            )

            # Run all indicators
            all_indicators = IndicatorRegistry.list_indicators()
            triggered_signals = []
            key_metrics: dict[str, Any] = {}
            all_results = []
            fundamental_score = 0
            fundamental_max = 7

            for indicator_name in all_indicators:
                try:
                    indicator = IndicatorRegistry.get_indicator(indicator_name)
                    result = indicator.analyze(stock_data, historical_data)
                    all_results.append(result)

                    if result.is_triggered:
                        triggered_signals.append(
                            indicator_name.lower().replace("_", " ")
                        )

                    # Extract metrics
                    meta = result.metadata
                    if "rsi" in meta and meta["rsi"]:
                        key_metrics["rsi"] = round(meta["rsi"], 1)
                    if "volume_ratio" in meta and meta["volume_ratio"]:
                        key_metrics["volume_ratio"] = round(meta["volume_ratio"], 1)
                    if "score" in meta and indicator_name == "Fundamental_Score":
                        fundamental_score = meta.get("score", 0)
                        fundamental_max = meta.get("max_score", 7)
                        key_metrics["fundamental_score"] = (
                            f"{fundamental_score}/{fundamental_max}"
                        )
                    if "debt_to_equity" in meta and meta["debt_to_equity"]:
                        key_metrics["debt_to_equity"] = round(meta["debt_to_equity"], 2)
                    if "revenue_growth" in meta and meta["revenue_growth"]:
                        key_metrics["revenue_growth"] = f"{meta['revenue_growth']:.1f}%"
                    if "peg_ratio" in meta and meta["peg_ratio"]:
                        key_metrics["peg_ratio"] = round(meta["peg_ratio"], 2)

                except Exception as e:
                    logger.debug(f"Indicator {indicator_name} failed for {symbol}: {e}")

            # Calculate composite score
            total_indicators = len(all_results)
            triggered_count = len(triggered_signals)
            avg_signal_strength = (
                sum(r.signal_strength for r in all_results) / total_indicators
                if total_indicators > 0
                else 0
            )

            signal_component = (triggered_count / max(total_indicators, 1)) * 40
            strength_component = avg_signal_strength * 30
            fundamental_component = (
                (fundamental_score / fundamental_max) * 30 if fundamental_max > 0 else 0
            )
            composite_score = (
                signal_component + strength_component + fundamental_component
            )

            # Determine recommendation
            bullish_signals = [
                "rsi",
                "macd",
                "volume spike",
                "revenue growth",
                "earnings growth",
            ]
            bullish_count = sum(
                1 for s in triggered_signals if any(b in s for b in bullish_signals)
            )

            if composite_score >= 60 and bullish_count >= 2:
                recommendation = "bullish"
            elif composite_score >= 40:
                recommendation = "neutral"
            elif composite_score < 30:
                recommendation = "bearish"
            else:
                recommendation = "hold"

            return StockInsight(
                symbol=symbol.upper(),
                price=price,
                change_percent=round(change_percent, 2),
                composite_score=round(composite_score, 1),
                triggered_signals=triggered_signals,
                key_metrics=key_metrics,
                recommendation=recommendation,
            )

        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            raise

    async def scan_for_opportunities(
        self,
        top_n: int = 50,
        min_score: float = 50.0,
        max_results: int = 5,
    ) -> list[StockInsight]:
        """Scan VTI holdings for investment opportunities."""
        logger.info(f"Scanning top {top_n} VTI holdings for opportunities...")

        etf_fetcher = ETFHoldingsFetcher("VTI")
        holdings = await etf_fetcher.fetch_holdings(top_n)

        opportunities: list[StockInsight] = []

        for holding in holdings:
            symbol = holding["symbol"]
            try:
                insight = await self.analyze_stock_full(symbol)

                if insight.composite_score >= min_score and insight.recommendation in (
                    "bullish",
                    "neutral",
                ):
                    opportunities.append(insight)
                    logger.debug(
                        f"Found opportunity: {symbol} (score: {insight.composite_score})"
                    )

                if len(opportunities) >= max_results:
                    break

            except Exception as e:
                logger.debug(f"Error analyzing {symbol}: {e}")
                continue

        opportunities.sort(key=lambda x: x.composite_score, reverse=True)
        return opportunities[:max_results]

    async def generate_daily_digest(
        self,
        user_watchlist: list[WatchlistItem],
        include_discoveries: bool = True,
        max_discoveries: int = 3,
    ) -> DigestData:
        """Generate a comprehensive daily digest for a user."""
        logger.info(
            f"Generating daily digest for {len(user_watchlist)} watchlist items..."
        )

        # Analyze user's watchlist
        watchlist_insights: list[StockInsight] = []
        for item in user_watchlist:
            try:
                insight = await self.analyze_stock_full(item.symbol)
                watchlist_insights.append(insight)
            except Exception as e:
                logger.error(f"Error analyzing watchlist item {item.symbol}: {e}")

        # Scan for new opportunities if enabled
        discovery_insights: list[StockInsight] = []
        if include_discoveries:
            watchlist_symbols = {item.symbol.upper() for item in user_watchlist}
            all_discoveries = await self.scan_for_opportunities(
                top_n=100,
                min_score=55.0,
                max_results=max_discoveries * 2,
            )
            discovery_insights = [
                d for d in all_discoveries if d.symbol not in watchlist_symbols
            ][:max_discoveries]

        # Generate market summary
        market_summary = self._generate_summary(watchlist_insights, discovery_insights)

        return DigestData(
            watchlist_insights=watchlist_insights,
            discovery_insights=discovery_insights,
            market_summary=market_summary,
            generated_at=datetime.now(),
        )

    def _generate_summary(
        self,
        watchlist_insights: list[StockInsight],
        discovery_insights: list[StockInsight],
    ) -> str:
        """Generate a summary without AI."""
        lines = []

        if watchlist_insights:
            sorted_by_change = sorted(
                watchlist_insights, key=lambda x: x.change_percent, reverse=True
            )
            best = sorted_by_change[0] if sorted_by_change else None
            worst = sorted_by_change[-1] if sorted_by_change else None

            if best and best.change_percent > 0:
                lines.append(
                    f"nice! {best.symbol.lower()} is up {best.change_percent:.1f}%"
                )
            if worst and worst.change_percent < 0:
                lines.append(
                    f"hmm {worst.symbol.lower()} is down {abs(worst.change_percent):.1f}%"
                )

            high_scorers = [i for i in watchlist_insights if i.composite_score >= 60]
            if high_scorers:
                symbols = [i.symbol.lower() for i in high_scorers[:3]]
                lines.append(f"looking strong: {', '.join(symbols)}")

        if discovery_insights:
            symbols = [i.symbol.lower() for i in discovery_insights]
            lines.append(f"worth checking out: {', '.join(symbols)}")

        return (
            "\n".join(lines) if lines else "pretty quiet day, nothing major happening"
        )

    def format_digest_sms(self, digest: DigestData) -> str:
        """Format a digest into an SMS-friendly message."""
        lines = ["hey! here's your daily update 📊\n"]

        if digest.watchlist_insights:
            bullish = [
                i for i in digest.watchlist_insights if i.recommendation == "bullish"
            ]
            bearish = [
                i for i in digest.watchlist_insights if i.recommendation == "bearish"
            ]

            if bullish:
                symbols = [
                    f"{i.symbol.lower()} +{i.change_percent:.1f}%" for i in bullish[:3]
                ]
                lines.append(f"📈 looking good: {', '.join(symbols)}")

            if bearish:
                symbols = [
                    f"{i.symbol.lower()} {i.change_percent:.1f}%" for i in bearish[:2]
                ]
                lines.append(f"📉 keep an eye on: {', '.join(symbols)}")

            avg_change = sum(i.change_percent for i in digest.watchlist_insights) / len(
                digest.watchlist_insights
            )
            lines.append(f"watchlist avg: {avg_change:+.1f}%")

        if digest.discovery_insights:
            lines.append("\n💡 you might like:")
            for insight in digest.discovery_insights[:2]:
                lines.append(
                    f"  {insight.symbol.lower()} (score {insight.composite_score:.0f})"
                )

        if digest.market_summary:
            summary = digest.market_summary[:200]
            if len(digest.market_summary) > 200:
                summary = summary.rsplit(" ", 1)[0] + "..."
            lines.append(f"\n{summary}")

        lines.append("\njust text me a symbol for more details!")
        return "\n".join(lines)


# Backwards compatibility - keep old method name
AIAssistant.process_natural_language = AIAssistant.chat
