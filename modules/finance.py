# ============================================================
#  modules/finance.py — Dragon Crypto Oracle  (v3 – Market Structure)
#
#  Live market data from Binance via ccxt:
#   • Ticker (price, volume, 24h change)
#   • OHLCV candles → Market Structure analysis:
#       – Support  = lowest low   of last 48 h
#       – Resistance = highest high of last 48 h
#       – ATR(14)  via `ta` library
#       – RSI(14)  via `ta` library
#   • Fear & Greed Index  (alternative.me — free, no key)
# ============================================================

import logging
import requests
import ccxt
import pandas as pd

try:
    from ta.momentum import RSIIndicator as _RSIIndicator
    from ta.volatility import AverageTrueRange as _ATRIndicator
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False

from typing import Optional
from dataclasses import dataclass
from config import BINANCE_API_KEY, BINANCE_API_SECRET

logger = logging.getLogger(__name__)

# Values that clearly indicate placeholder / unconfigured keys
_PLACEHOLDER_VALUES = {
    "", "your_binance_api_key_here", "your_api_key_here",
    "your_binance_api_secret_here", "your_api_secret_here",
}

_FNG_URL     = "https://api.alternative.me/fng/"
_FNG_TIMEOUT = 8   # seconds


# ── Exchange helpers ─────────────────────────────────────────

def _looks_like_real_key(value: str) -> bool:
    """
    Heuristic: a real Binance API key is 64 hex chars,
    and a secret is also 64 chars. Reject anything shorter
    or that matches known placeholder strings.
    """
    v = value.strip()
    return len(v) >= 20 and v not in _PLACEHOLDER_VALUES


def _make_public_exchange() -> ccxt.binance:
    """Return a Binance exchange instance with NO credentials (public mode)."""
    return ccxt.binance({"enableRateLimit": True})


def _make_auth_exchange() -> ccxt.binance:
    """Return a Binance exchange instance with API key + secret."""
    return ccxt.binance(
        {
            "apiKey": BINANCE_API_KEY,
            "secret": BINANCE_API_SECRET,
            "enableRateLimit": True,
        }
    )


def _get_exchange() -> ccxt.binance:
    """
    Return a ccxt Binance instance, choosing auth vs. public mode.

    Public-data mode (prices, tickers) requires NO credentials.
    We only pass API keys when both look like real values (length ≥ 20,
    not a known placeholder string). If they look fake, we skip them.

    Even if keys pass this check but Binance still rejects them with
    an auth error (-2008 / -2015), the caller (`_fetch_ticker_safe`)
    automatically retries in public mode.
    """
    if _looks_like_real_key(BINANCE_API_KEY) and _looks_like_real_key(BINANCE_API_SECRET):
        logger.debug("Binance: using authenticated mode.")
        return _make_auth_exchange()
    else:
        logger.debug("Binance: keys look like placeholders — using public mode.")
        return _make_public_exchange()


def _fetch_ticker_safe(symbol: str) -> dict:
    """
    Fetch a ticker, with automatic fallback to public mode if Binance
    returns an authentication error (-2008 Invalid Api-Key, -2015 etc.).

    This handles the case where a user has partial / wrong keys in .env
    that pass the heuristic check but are rejected by Binance.
    """
    exchange = _get_exchange()
    try:
        return exchange.fetch_ticker(symbol)
    except ccxt.AuthenticationError as auth_err:
        logger.warning(
            "Binance auth failed (%s). Retrying in public (no-key) mode.", auth_err
        )
        public_exchange = _make_public_exchange()
        return public_exchange.fetch_ticker(symbol)


# ── Simple ticker fetchers ───────────────────────────────────

def fetch_btc_price() -> dict:
    """
    Fetch the current BTC/USDT ticker from Binance.

    Returns
    -------
    dict with keys: symbol, last, bid, ask, change_pct,
                    volume_24h, high_24h, low_24h.

    Raises
    ------
    ccxt.NetworkError  — connectivity failure.
    ccxt.ExchangeError — Binance returned a non-auth error.
    """
    ticker = _fetch_ticker_safe("BTC/USDT")
    return {
        "symbol":     ticker["symbol"],
        "last":       ticker["last"],
        "bid":        ticker["bid"],
        "ask":        ticker["ask"],
        "change_pct": ticker["percentage"],
        "volume_24h": ticker["baseVolume"],
        "high_24h":   ticker["high"],
        "low_24h":    ticker["low"],
    }


def fetch_fear_and_greed() -> dict:
    """
    Fetch the current Crypto Fear & Greed Index from alternative.me.

    Returns
    -------
    dict with keys:
        value       (int)   — 0–100 index value
        label       (str)   — e.g. "Extreme Greed", "Fear"
        timestamp   (str)   — Unix timestamp string from the API
        display     (str)   — formatted string, e.g. "72 — Greed"

    On any network / parse error returns a safe fallback dict with
    value=None so callers can detect the absence gracefully.
    """
    fallback = {"value": None, "label": "N/A", "timestamp": "", "display": "N/A"}
    try:
        resp = requests.get(_FNG_URL, timeout=_FNG_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        item = data["data"][0]
        value = int(item["value"])
        label = item["value_classification"]
        display = f"{value} — {label}"
        return {
            "value":     value,
            "label":     label,
            "timestamp": item.get("timestamp", ""),
            "display":   display,
        }
    except Exception as exc:
        logger.warning("Fear & Greed fetch failed: %s", exc)
        return fallback


# ── Market Structure Analysis ────────────────────────────────

@dataclass
class MarketStructure:
    """Result of full market-structure analysis on OHLCV candles."""
    support:    float          # Lowest low of the look-back window (48 h)
    resistance: float          # Highest high of the look-back window (48 h)
    atr_14:     Optional[float] # Average True Range (14-period) on 1h candles
    rsi_14:     Optional[float] # RSI(14) on 1h candles
    candles:    int            # Number of candles used in the analysis


def fetch_market_structure(
    symbol:    str,
    timeframe: str = "1h",
    limit:     int = 100,
) -> Optional[MarketStructure]:
    """
    Fetch 1-hour OHLCV candles from Binance and derive market structure.

    The analysis uses the last `limit` candles (default 100 × 1 h ≈ 4 days),
    but Support/Resistance are specifically computed over the most recent
    48 candles (= 48 hours on 1 h timeframe) as per the quant spec.

    ATR(14) and RSI(14) are computed over the full dataset for stability
    of the indicator warm-up period.

    Parameters
    ----------
    symbol    : str  — e.g. "BTC/USDT"
    timeframe : str  — ccxt timeframe, default "1h"
    limit     : int  — number of candles to fetch (must be ≥ 48)

    Returns
    -------
    MarketStructure or None on any error.
    """
    try:
        exchange = _make_public_exchange()
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

        if not ohlcv or len(ohlcv) < 15:
            logger.warning(
                "Not enough OHLCV data for %s (%d candles)", symbol, len(ohlcv or [])
            )
            return None

        # Build DataFrame: columns = [timestamp, open, high, low, close, volume]
        df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])

        # ── Support & Resistance (last 48 candles = 48 hours) ─────
        lookback = min(48, len(df))
        recent   = df.tail(lookback)
        support    = float(recent["low"].min())
        resistance = float(recent["high"].max())

        # ── ATR(14) & RSI(14) via `ta` library ───────────────────
        atr_value = None
        rsi_value = None

        if _TA_AVAILABLE and len(df) >= 15:
            try:
                atr_series = _ATRIndicator(
                    high=df["high"], low=df["low"], close=df["close"], window=14
                ).average_true_range()
                atr_value = round(float(atr_series.iloc[-1]), 4)
            except Exception as exc:
                logger.warning("ATR calculation failed: %s", exc)

            try:
                rsi_series = _RSIIndicator(close=df["close"], window=14).rsi()
                rsi_value = round(float(rsi_series.iloc[-1]), 2)
            except Exception as exc:
                logger.warning("RSI calculation failed: %s", exc)
        elif not _TA_AVAILABLE:
            logger.warning("'ta' library not installed — ATR/RSI unavailable.")

        result = MarketStructure(
            support=round(support, 4),
            resistance=round(resistance, 4),
            atr_14=atr_value,
            rsi_14=rsi_value,
            candles=len(df),
        )
        logger.info(
            "Market structure for %s: S=%.4f  R=%.4f  ATR=%.4f  RSI=%.2f  (%d candles)",
            symbol, result.support, result.resistance,
            atr_value or 0, rsi_value or 0, result.candles,
        )
        return result

    except Exception as exc:
        logger.error("Market structure fetch failed for %s: %s", symbol, exc)
        return None
