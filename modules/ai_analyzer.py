# ============================================================
#  modules/ai_analyzer.py — Dragon Crypto Oracle  (v3)
#
#  Sends a rich market-context prompt to Google Gemini for
#  sentiment scoring. Context includes:
#   • Current price & 24h volume
#   • Fear & Greed Index
#   • Technical indicators: ATR(14), RSI(14), Support, Resistance
#   • Macro news + Micro news
#   • User's selected language → Gemini replies in that language
#
#  Retry logic: 3 attempts with exponential back-off on 429 errors.
#
#  Uses the `google-genai` SDK.
#  Free key: https://aistudio.google.com/app/apikey
# ============================================================

import json
import logging
import re
import time
from dataclasses import dataclass

from typing import Optional

from google import genai

from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

# The new google-genai SDK requires the full "models/" prefix.
_GEMINI_MODEL = f"models/{GEMINI_MODEL}" if not GEMINI_MODEL.startswith("models/") else GEMINI_MODEL

# Retry configuration for 429 / quota errors
_MAX_RETRIES    = 3
_RETRY_BASE_SEC = 2     # first wait = 2 s, then 4 s, then 8 s

# Friendly message shown to the user when AI is unavailable.
_RESTING_MSG = "AI currently resting. Using neutral market context."

# Language code → full language name for the Gemini instruction
_LANG_FULL_NAME: dict[str, str] = {
    "en": "English",
    "uk": "Ukrainian",
    "es": "Spanish",
    "de": "German",
    "ru": "Russian",
    "fr": "French",
    "pl": "Polish",
}


@dataclass
class SentimentResult:
    direction:  str     # "LONG", "SHORT", or "WAIT"
    confidence: int     # 1-10
    reasoning:  str     # Concise explanation from the LLM
    leverage:   int     # Recommended leverage (2-12)
    model_used: str     # Which model produced the result


def _neutral(reason: str, model: str = _GEMINI_MODEL) -> SentimentResult:
    """Return a pre-built neutral/wait result with a friendly reason string."""
    return SentimentResult(
        direction="WAIT",
        confidence=0,
        reasoning=reason,
        leverage=1,
        model_used=model,
    )


def _parse_ai_json(text: str) -> SentimentResult:
    """
    Safely parse the JSON block returned by the LLM.
    Handles partial markdown wrappers (```json ... ```).
    """
    clean_text = text.strip()
    if clean_text.startswith("```"):
        start_idx = clean_text.find('{')
        end_idx = clean_text.rfind('}')
        if start_idx != -1 and end_idx != -1:
            clean_text = clean_text[start_idx:end_idx+1]
            
    try:
        data = json.loads(clean_text)
        direction = str(data.get("direction", "WAIT")).upper()
        if direction not in ["LONG", "SHORT", "WAIT"]:
            direction = "WAIT"
            
        try:
            confidence = int(data.get("confidence", 0))
        except (ValueError, TypeError):
            confidence = 0
            
        reasoning = str(data.get("reasoning", ""))
        try:
            leverage = int(data.get("leverage", 1))
        except (ValueError, TypeError):
            leverage = 1
            
        return SentimentResult(
            direction=direction,
            confidence=max(1, min(10, confidence)) if direction != "WAIT" else confidence,
            reasoning=reasoning,
            leverage=leverage,
            model_used=_GEMINI_MODEL,
        )
    except Exception as exc:
        logger.error(f"Failed to parse AI JSON: {exc}. Raw text: {clean_text}")
        return SentimentResult(
            direction="WAIT",
            confidence=0,
            reasoning="AI returned malformed data. Waiting for clearer conditions.",
            leverage=1,
            model_used=_GEMINI_MODEL,
        )


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True if the exception looks like a 429 / quota error."""
    err_str = str(exc).lower()
    return any(kw in err_str for kw in ("429", "resource_exhausted", "quota", "rate"))


def analyze_sentiment(
    coin_name:   str,
    news_text:   str            = "",     # Micro news (coin-specific)
    price:       Optional[float] = None,
    volume_24h:  Optional[float] = None,
    fng_display: str            = "N/A",
    macro_text:  str            = "",     # Macro news (global triggers)
    atr_14:      Optional[float] = None,
    rsi_14:      Optional[float] = None,
    support:     Optional[float] = None,
    resistance:  Optional[float] = None,
    lang:        str            = "en",   # User's selected language code
) -> SentimentResult:
    """
    Ask Gemini to score the sentiment of the provided market context.

    The prompt includes the full technical picture:
    • Price, Volume, Fear & Greed
    • Market Structure: Support, Resistance, ATR(14), RSI(14)
    • Macro and Micro news
    • Instructions to respond in the user's chosen language

    Retry logic: up to 3 attempts with exponential back-off on 429 errors.
    Any other error fails fast with a neutral fallback.

    Returns
    -------
    SentimentResult  — parsed JSON response returning direction, confidence, and reasoning.
    """
    # ── No key configured ────────────────────────────────────────────
    if not GEMINI_API_KEY or GEMINI_API_KEY.strip() in (
        "", "your_gemini_api_key_here"
    ):
        logger.warning("GEMINI_API_KEY not set — skipping AI sentiment.")
        return _neutral(
            "Set GEMINI_API_KEY in .env to enable AI sentiment "
            "(free at aistudio.google.com).",
            model="none",
        )

    # ── Build rich market context ─────────────────────────────────────
    ctx: list[str] = []
    if price is not None:
        ctx.append(f"• Current Price:       ${price:,.4f}")
    if volume_24h is not None:
        ctx.append(f"• 24h Volume:          {volume_24h:,.2f} {coin_name.upper()}")
    ctx.append(f"• Fear & Greed Index:  {fng_display}")
    if support is not None:
        ctx.append(f"• Support  (48h Low):  ${support:,.4f}")
    if resistance is not None:
        ctx.append(f"• Resistance (48h Hi): ${resistance:,.4f}")
    if atr_14 is not None:
        ctx.append(f"• ATR(14):             ${atr_14:,.4f}")
    if rsi_14 is not None:
        ctx.append(f"• RSI(14):             {rsi_14:.1f}")

    market_context = "\n".join(ctx)

    # ── News sections ─────────────────────────────────────────────────
    macro_section = (
        f"\n\nMACRO NEWS (global market catalysts):\n{macro_text}"
        if macro_text.strip()
        else ""
    )
    micro_section = (
        f"\n\nMICRO NEWS (coin-specific headlines):\n{news_text}"
        if news_text.strip()
        else ""
    )

    # ── Language instruction ──────────────────────────────────────────
    lang_name = _LANG_FULL_NAME.get(lang, "English")

    sys_instruction = (
        f"ТИ — ПРОФЕСІЙНИЙ КРИПТО-АНАЛІТИК. ТВОЯ ЄДИНА МОВА СПІЛКУВАННЯ — УКРАЇНСЬКА. "
        f"ВСІ ПОЛЯ В JSON, ВКЛЮЧАЮЧИ 'reasoning', МАЮТЬ БУТИ НАПИСАНІ ВИКЛЮЧНО УКРАЇНСЬКОЮ. "
        f"Не використовуй англійські або французькі терміни в описі, якщо є українські відповідники.\n\n"
        f"УВАГА ДО ТЕХНІЧНИХ ДАНИХ (Precision Tuning):\n"
        f"Звертай особливу увагу на значення RSI та ATR. "
        f"Якщо RSI < 35, обов'язково підкресли, що ринок перебуває в зоні 'Перепроданості' (Oversold). "
        f"Якщо RSI > 65, підкресли ризик 'Перекупленості' (Overbought).\n\n"
    )

    prompt = (
        f"{sys_instruction}"
        f"Analyze the overall sentiment for {coin_name.upper()} "
        f"and decide whether to go LONG, SHORT, or WAIT based on the provided context.\n\n"
        f"MARKET CONTEXT:\n{market_context}"
        f"{macro_section}"
        f"{micro_section}\n\n"
        f"Weigh all data: price action, RSI, ATR volatility, Fear & Greed, "
        f"support/resistance levels, macro catalysts, and coin-specific news.\n"
        f"EVALUATE if fundamental news supports or contradicts the technical structure (e.g., if price is near resistance but news is extremely bullish, consider LONG for a breakout, or WAIT, but never blindly SHORT).\n"
        f"Evaluate market volatility, news context, and distance to Stop Loss to determine a 'Professional Recommended Leverage'. Leverage must be conservative. Range: 2x to 10x. Never exceed 12x even in high-confidence setups.\n\n"
        f"Provide your response STRICTLY as a parseable JSON object:\n"
        f"{{\n"
        f'  "direction": "LONG" | "SHORT" | "WAIT",\n'
        f'  "confidence": <integer between 1 and 10>,\n'
        f'  "reasoning": "<2-3 concise sentences in Ukrainian>",\n'
        f'  "leverage": <integer between 2 and 12>\n'
        f"}}"
    )

    # ── Retry loop (up to 3 attempts on 429) ──────────────────────────
    client = genai.Client(api_key=GEMINI_API_KEY)
    last_exc: Optional[Exception] = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=_GEMINI_MODEL,
                contents=prompt,
            )
            raw_text = response.text.strip()
            logger.info("Gemini response (attempt %d): %s", attempt, raw_text[:200])

            result = _parse_ai_json(raw_text)
            
            # If validly parsed, return it
            if result.reasoning: 
                return result

        except Exception as exc:
            print(f"Gemini Error: {exc}")
            last_exc = exc
            if _is_rate_limit_error(exc) and attempt < _MAX_RETRIES:
                wait = _RETRY_BASE_SEC * (2 ** (attempt - 1))
                logger.warning(
                    "Gemini 429 (attempt %d/%d). Retrying in %d s…",
                    attempt, _MAX_RETRIES, wait,
                )
                time.sleep(wait)
                continue
            else:
                # Non-retryable error or final attempt — break out
                break

    # ── All retries exhausted or non-retryable error ─────────────────
    if last_exc:
        if _is_rate_limit_error(last_exc):
            logger.warning("Gemini quota exhausted after %d attempts: %s", _MAX_RETRIES, last_exc)
        else:
            logger.error("Gemini API error: %s", last_exc)

    return _neutral(_RESTING_MSG)


def parse_strategy_json(text: str) -> dict:
    """Safely parse the strategy JSON block."""
    clean_text = text.strip()
    if clean_text.startswith("```"):
        start_idx = clean_text.find('{')
        end_idx = clean_text.rfind('}')
        if start_idx != -1 and end_idx != -1:
            clean_text = clean_text[start_idx:end_idx+1]
    
    try:
        return json.loads(clean_text)
    except Exception as exc:
        logger.error(f"Failed to parse strategy JSON: {exc}. Raw text: {clean_text}")
        return {"decision": "WAIT", "type": "NONE", "tp": 0.0, "sl": 0.0, "leverage": 1, "comment": "Parse error"}


def analyze_strategy(ticker: str, price: float, btc_trend: str, support: float, resistance: float, atr: float, rsi: float) -> dict:
    """
    Called by Strategy Engine to execute the final technical audit of a setup.
    Enforces a strict JSON return schema: {"decision": "GO/WAIT", "type": "LONG/SHORT", "tp": value, "sl": value, "comment": "..."}
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY.strip() in ("", "your_gemini_api_key_here"):
        return {"decision": "WAIT", "type": "NONE", "tp": 0.0, "sl": 0.0, "comment": "No Gemini API key"}

    sys_instruction = (
        f"ТИ — ПРОФЕСІЙНИЙ КРИПТО-АНАЛІТИК. ТВОЯ ЄДИНА МОВА СПІЛКУВАННЯ — УКРАЇНСЬКА. "
        f"ВСІ ПОЛЯ В JSON, ВКЛЮЧАЮЧИ 'comment', МАЮТЬ БУТИ НАПИСАНІ ВИКЛЮЧНО УКРАЇНСЬКОЮ. "
        f"Не використовуй англійські або французькі терміни в описі, якщо є українські відповідники.\n\n"
        f"УВАГА ДО ТЕХНІЧНИХ ДАНИХ (Precision Tuning):\n"
        f"Звертай особливу увагу на значення RSI та ATR. "
        f"Якщо RSI < 35, обов'язково підкресли, що ринок перебуває в зоні 'Перепроданості'. "
        f"Якщо RSI > 65, підкресли ризик 'Перекупленості'.\n\n"
    )

    prompt = (
        f"{sys_instruction}"
        f"Evaluate the following setup and provide a final trade decision.\n\n"
        f"CONTEXT PACKAGE:\n"
        f"• Ticker: {ticker}\n"
        f"• Current Price: ${price:,.4f}\n"
        f"• BTC Trend Guard: {btc_trend}\n"
        f"• 48h Support: ${support:,.4f}\n"
        f"• 48h Resistance: ${resistance:,.4f}\n"
        f"• ATR(14): ${atr:,.4f}\n"
        f"• RSI(14): {rsi:.1f}\n\n"
        f"RULES:\n"
        f"1. You are a professional risk manager. If the calculated Take Profit is too close to the Entry price, resulting in a poor Risk/Reward ratio, you MUST set the 'decision' to 'WAIT' and explain that the setup is mathematically unfavorable.\n"
        f"2. If RSI is neutral and there's no clear structural edge, return WAIT.\n"
        f"3. If going LONG, set SL slightly below Support, and TP near Resistance or at least 1:1.5 offset.\n"
        f"4. Evaluate market volatility, news context, and distance to Stop Loss to determine a 'Professional Recommended Leverage'. Leverage must be conservative. Range: 2x to 10x. Never exceed 12x even in high-confidence setups.\n"
        f"5. Return strictly a raw JSON object (no markdown, no extra text).\n\n"
        f"OUTPUT FORMAT:\n"
        f"{{\n"
        f'  "decision": "GO" | "WAIT",\n'
        f'  "type": "LONG" | "SHORT",\n'
        f'  "tp": <float>,\n'
        f'  "sl": <float>,\n'
        f'  "leverage": <integer between 2 and 12>,\n'
        f'  "comment": "<1 short sentence explanation in Ukrainian>"\n'
        f"}}"
    )

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=_GEMINI_MODEL,
                contents=prompt,
            )
            raw_text = response.text.strip()
            logger.info("Strategy Gemini response (attempt %d): %s", attempt, raw_text[:200])
            
            return parse_strategy_json(raw_text)
            
        except Exception as exc:
            if _is_rate_limit_error(exc) and attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BASE_SEC * (2 ** (attempt - 1)))
            else:
                break

    return {"decision": "WAIT", "type": "NONE", "tp": 0.0, "sl": 0.0, "comment": "API Error"}


def analyze_performance(stats_data: dict, lang: str = "en") -> str:
    """
    Asks Gemini to provide a 1-sentence tip based on virtual trade stats.
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY.strip() in ("", "your_gemini_api_key_here"):
        return "AI analysis unavailable."

    lang_name = _LANG_FULL_NAME.get(lang.lower(), "English")
    
    prompt = (
        f"You are a Senior Quantitative Chief Investment Officer. Analyze the following trading performance statistics:\n"
        f"- Strategy Win Rate: {stats_data['win_rate']}%\n"
        f"- Virtual Balance Change: {stats_data['total_pnl']}%\n"
        f"- Best Performing Coin: {stats_data['best_coin']}\n\n"
        f"Utilizing your enhanced Gemini 3 analytical capabilities, provide exactly one sophisticated, professional sentence in {lang_name} giving a deep tactical tip or observing a subtle market correlation pattern based on these results. Be punchy and direct."
    )

    client = genai.Client(api_key=GEMINI_API_KEY)
    try:
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
        )
        return response.text.strip().replace('"', '').replace('*', '')
    except Exception as e:
        logger.error(f"Failed to generate performance tip: {e}")
        return "Зберігайте дисципліну та слідкуйте за трендом BTC."
