# ============================================================
#  modules/news_utils.py — Dragon Crypto Oracle
#
#  Advanced News Engine v2:
#  - Strict 24-hour freshness filter (compares to system time UTC)
#  - Stream A (Micro): coin-specific news using regex word boundaries
#  - Stream B (Macro): global market triggers (Fed, CPI, SEC, ETF, etc.)
#  - Merge → deduplicate → sort newest-first → top 4
#  - Zero API keys required; uses requests + browser UA to bypass blockers.
# ============================================================

import feedparser
import logging
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from config import RSS_FEEDS

logger = logging.getLogger(__name__)

# ── Browser-like request headers ─────────────────────────────
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

_REQUEST_TIMEOUT = 12   # seconds per feed
_MAX_AGE_HOURS   = 24   # strict freshness window
_TOP_N_TOTAL     = 4    # max headlines in the final merged result

# ── Macro market trigger keywords ────────────────────────────
# Stream B: global catalyst words that affect the whole crypto market.
_MACRO_KEYWORDS: list[str] = [
    "fed", "federal reserve", "fomc",
    "cpi", "inflation", "interest rate", "interest rates",
    "sec", "etf", "trump", "tariff", "bitcoin",
    "treasury", "recession", "gdp", "jobs report",
]

# ── Coin alias map ────────────────────────────────────────────
COIN_ALIASES: dict[str, list[str]] = {
    "BTC":   ["bitcoin", "btc"],
    "ETH":   ["ethereum", "eth", "ether"],
    "SOL":   ["solana", "sol"],
    "BNB":   ["binance coin", "bnb", "binance smart chain"],
    "XRP":   ["xrp", "ripple"],
    "ADA":   ["cardano", "ada"],
    "DOGE":  ["dogecoin", "doge"],
    "AVAX":  ["avalanche", "avax"],
    "DOT":   ["polkadot", "dot"],
    "MATIC": ["polygon", "matic", "pol"],
    "LINK":  ["chainlink", "link"],
    "LTC":   ["litecoin", "ltc"],
    "UNI":   ["uniswap", "uni"],
    "ATOM":  ["cosmos", "atom"],
    "NEAR":  ["near protocol", "near"],
    "ARB":   ["arbitrum", "arb"],
    "OP":    ["optimism", "op"],
    "SUI":   ["sui network", "sui"],
    "APT":   ["aptos", "apt"],
    "INJ":   ["injective", "inj"],
    "FIL":   ["filecoin", "fil"],
    "AAVE":  ["aave"],
    "MKR":   ["maker", "mkr"],
    "PEPE":  ["pepe", "pepecoin"],
    "SHIB":  ["shiba inu", "shib"],
}


@dataclass
class NewsItem:
    title:          str         # Clean headline text
    summary:        str         # Truncated to 200 chars for readability
    source:         str         # Feed display title
    published:      str         # Raw publication string from the feed
    published_fmt:  str         # Clean formatted timestamp, e.g. "14 Apr, 10:30"
    published_dt:   datetime    # UTC datetime (for sorting and age filter)
    stream:         str         # "micro" | "macro" — origin stream tag


# ── Helpers ───────────────────────────────────────────────────

def _parse_datetime(pub_str: str) -> datetime | None:
    """
    Parse an RSS publication string to a timezone-aware UTC datetime.
    Supports RFC 2822 and ISO 8601. Returns None on failure.
    """
    if not pub_str or pub_str == "Unknown date":
        return None
    try:
        dt = parsedate_to_datetime(pub_str)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    return None


def _format_dt(dt: datetime) -> str:
    """Format a UTC datetime to '16 Apr, 10:30'."""
    return dt.strftime("%d %b, %H:%M")


def _clean_html(text: str) -> str:
    """Strip HTML tags and normalise whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()


def _build_micro_keywords(coin_name: str) -> list[str]:
    """
    Return lowercase search terms for a coin ticker.
    "SOL" → ["solana", "sol"]  |  "BTC" → ["bitcoin", "btc"]
    Unknown tickers fall back to [ticker.lower()].
    """
    upper = coin_name.strip().upper()
    return COIN_ALIASES.get(upper, [coin_name.lower()])


def _match_micro(text: str, keywords: list[str]) -> bool:
    """
    Stream A relevance check.
    ALL keywords use strict regex word-boundary matching (\\b…\\b),
    which prevents "sol" from matching inside "resolution" etc.
    """
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE):
            return True
    return False


def _match_macro(text: str) -> bool:
    """
    Stream B relevance check.
    Any macro trigger keyword (whole-word) fires a match.
    """
    for kw in _MACRO_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE):
            return True
    return False


def _is_fresh(dt: datetime | None) -> bool:
    """Return True iff the item's publication datetime is within the last 24 hours."""
    if dt is None:
        return False   # No parseable date → treat as stale
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_MAX_AGE_HOURS)
    return dt >= cutoff


# ── Feed fetcher ──────────────────────────────────────────────

def _fetch_feed_dual(
    url: str,
    micro_keywords: list[str],
) -> tuple[list[NewsItem], list[NewsItem]]:
    """
    Fetch one RSS feed and classify entries into two streams:
      • micro_items — entries matching the coin's keywords (Stream A)
      • macro_items — entries matching global trigger words (Stream B)

    Only items passing the strict 24-hour freshness filter are retained.
    Items can appear in BOTH streams (they will be deduplicated later).
    """
    micro_items: list[NewsItem] = []
    macro_items: list[NewsItem] = []

    try:
        resp = requests.get(url, headers=_BROWSER_HEADERS, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()

        feed = feedparser.parse(resp.content)
        source = feed.feed.get("title", url)

        for entry in feed.entries:
            pub_raw = entry.get("published", "")
            pub_dt  = _parse_datetime(pub_raw)

            # ── 24h freshness gate ────────────────────────────
            if not _is_fresh(pub_dt):
                continue

            title_raw   = _clean_html(entry.get("title", "Untitled"))
            raw_summary = entry.get("summary", "No summary available.")
            clean_sum   = _clean_html(raw_summary)
            if len(clean_sum) > 200:
                clean_sum = clean_sum[:200].strip() + "…"

            search_text = f"{title_raw} {clean_sum}".lower()

            item = NewsItem(
                title         = title_raw,
                summary       = clean_sum,
                source        = source,
                published     = pub_raw,
                published_fmt = _format_dt(pub_dt),
                published_dt  = pub_dt,
                stream        = "",   # will be set below
            )

            if _match_micro(search_text, micro_keywords):
                micro_items.append(NewsItem(**{**item.__dict__, "stream": "micro"}))

            if _match_macro(search_text):
                macro_items.append(NewsItem(**{**item.__dict__, "stream": "macro"}))

        logger.debug(
            "Feed %s → %d micro / %d macro (fresh)",
            url, len(micro_items), len(macro_items),
        )

    except requests.exceptions.HTTPError as e:
        logger.warning("HTTP error fetching %s: %s", url, e)
    except Exception as exc:
        logger.warning("Failed to parse feed %s: %s", url, exc)

    return micro_items, macro_items


# ── Public API ────────────────────────────────────────────────

def get_latest_news(
    coin_name: str,
    top_n: int = _TOP_N_TOTAL,
) -> tuple[list[NewsItem], str, list[NewsItem], list[NewsItem]]:
    """
    Fetch, filter, merge, and rank news for a given coin.

    Returns
    -------
    (merged_top, formatted_text_for_llm, micro_items, macro_items)

    merged_top : list[NewsItem]
        Top `top_n` fresh headlines, sorted newest-first.
        Micro items are prioritised (listed first) before macro-only items.

    formatted_text_for_llm : str
        Plain-text block for the Gemini prompt.

    micro_items : list[NewsItem]
        All fresh coin-specific items (pre-merge, pre-limit).

    macro_items : list[NewsItem]
        All fresh macro items (pre-merge, pre-limit).
    """
    keywords = _build_micro_keywords(coin_name)

    all_micro: list[NewsItem] = []
    all_macro: list[NewsItem] = []

    # Fetch all feeds concurrently
    with ThreadPoolExecutor(max_workers=len(RSS_FEEDS)) as executor:
        futures = {
            executor.submit(_fetch_feed_dual, url, keywords): url
            for url in RSS_FEEDS
        }
        for future in as_completed(futures, timeout=25):
            try:
                m, M = future.result()
                all_micro.extend(m)
                all_macro.extend(M)
            except Exception as exc:
                logger.warning("Feed thread error: %s", exc)

    # ── Deduplicate each stream individually ──────────────────
    def _dedup(items: list[NewsItem]) -> list[NewsItem]:
        seen: set[str] = set()
        out:  list[NewsItem] = []
        for item in items:
            key = item.title.lower().strip()
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out

    micro_dedup = _dedup(all_micro)
    macro_dedup = _dedup(all_macro)

    # Sort each stream newest-first
    micro_dedup.sort(key=lambda x: x.published_dt, reverse=True)
    macro_dedup.sort(key=lambda x: x.published_dt, reverse=True)

    # ── Merge: micro first, then add macro-only items ─────────
    merged_keys: set[str] = set()
    merged: list[NewsItem] = []

    for item in micro_dedup:
        key = item.title.lower().strip()
        if key not in merged_keys:
            merged_keys.add(key)
            merged.append(item)

    for item in macro_dedup:
        key = item.title.lower().strip()
        if key not in merged_keys:
            merged_keys.add(key)
            item = NewsItem(**{**item.__dict__, "stream": "macro"})
            merged.append(item)

    # Final sort by publish time (newest first) and limit
    merged.sort(key=lambda x: x.published_dt, reverse=True)
    top_items = merged[:top_n]

    # ── Format plain-text block for the LLM ──────────────────
    if not top_items:
        formatted_text = (
            f"No fresh news found for {coin_name.upper()} in the last 24 hours. "
            "Sentiment analysis will be based on technical data and general market context."
        )
    else:
        lines: list[str] = []
        for i, item in enumerate(top_items, 1):
            tag = "[MICRO]" if item.stream == "micro" else "[MACRO]"
            lines.append(
                f"{i}. {tag} [{item.source}] {item.title} ({item.published_fmt})\n"
                f"   {item.summary}"
            )
        formatted_text = "\n\n".join(lines)

    logger.info(
        "News result for %s: %d micro, %d macro → %d merged (top %d)",
        coin_name, len(micro_dedup), len(macro_dedup), len(merged), len(top_items),
    )

    return top_items, formatted_text, micro_dedup, macro_dedup
