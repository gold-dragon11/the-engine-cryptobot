# ============================================================
#  modules/reporter.py — Dragon Crypto Oracle
#
#  Daily Report Engine (fires at 23:59 local time every day).
#
#  Collects from engine.db:
#   • Gemini API calls in the last 24 h
#   • Signals generated in the last 24 h
#   • Top rejection reasons (ranked by frequency)
#   • Open positions summary
#
#  Runs as an independent asyncio task alongside all other loops.
#  Zero interference with scanning — uses its own DB connection.
# ============================================================

import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Fire the report at this local time each day (HH, MM).
_REPORT_HOUR   = 23
_REPORT_MINUTE = 59


def _seconds_until_report() -> float:
    """
    Calculate how many seconds remain until the next 23:59 local time.
    Always returns a positive value so the task never fires immediately.
    """
    now = datetime.now()
    target = now.replace(hour=_REPORT_HOUR, minute=_REPORT_MINUTE, second=0, microsecond=0)
    if now >= target:
        # Already past 23:59 today — aim for tomorrow
        target += timedelta(days=1)
    delta = (target - now).total_seconds()
    return delta


def collect_daily_stats(db) -> dict:
    """
    Query engine.db and return a stats dict for the last 24 hours.

    Returns
    -------
    {
        "gemini_calls":  int,
        "signals_total": int,
        "signals": [{"ticker": str, "type": str, "timestamp": str}, ...],
        "rejections": [{"reason": str, "count": int}, ...],   # top-5, ranked
        "open_signals": int,
    }
    """
    cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db._connect()
    cursor = conn.cursor()

    # ── Gemini call count ────────────────────────────────────────────────────
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM gemini_calls WHERE called_at >= ?", (cutoff,)
        )
        gemini_calls = cursor.fetchone()[0]
    except Exception:
        gemini_calls = 0   # table may not exist yet on first run

    # ── Signals generated today ──────────────────────────────────────────────
    try:
        cursor.execute(
            "SELECT ticker, type, timestamp FROM signals WHERE timestamp >= ? ORDER BY timestamp DESC",
            (cutoff,),
        )
        signal_rows = cursor.fetchall()
        signals_total = len(signal_rows)
        signals = [{"ticker": r[0], "type": r[1], "timestamp": r[2]} for r in signal_rows]
    except Exception:
        signals_total, signals = 0, []

    # ── Rejection reasons ────────────────────────────────────────────────────
    try:
        cursor.execute(
            """
            SELECT reason, COUNT(*) as cnt
            FROM rejection_log
            WHERE logged_at >= ?
            GROUP BY reason
            ORDER BY cnt DESC
            LIMIT 5
            """,
            (cutoff,),
        )
        rejections = [{"reason": r[0], "count": r[1]} for r in cursor.fetchall()]
    except Exception:
        rejections = []

    # ── Currently open signals ───────────────────────────────────────────────
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM signals WHERE status IN ('PENDING', 'ACTIVE')"
        )
        open_signals = cursor.fetchone()[0]
    except Exception:
        open_signals = 0

    conn.close()

    return {
        "gemini_calls":  gemini_calls,
        "signals_total": signals_total,
        "signals":       signals,
        "rejections":    rejections,
        "open_signals":  open_signals,
    }


def _format_report(stats: dict) -> str:
    """Build the HTML Telegram message from the stats dict."""
    now_str = datetime.now().strftime("%d.%m.%Y")

    lines = [
        f"🐉 <b>Dragon Oracle — Щоденний звіт</b> 🐉",
        f"📅 <b>Дата:</b> {now_str}",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # ── API usage ────────────────────────────────────────────────────────────
    lines.append(f"\n🤖 <b>Gemini API:</b>")
    lines.append(f"   • Запитів за 24 год: <code>{stats['gemini_calls']}</code>")

    # ── Signals ─────────────────────────────────────────────────────────────
    lines.append(f"\n📡 <b>Торгові сигнали:</b>")
    lines.append(f"   • Згенеровано: <code>{stats['signals_total']}</code>")
    lines.append(f"   • Відкритих позицій: <code>{stats['open_signals']}/3</code>")

    if stats["signals"]:
        lines.append("   • <i>Деталі:</i>")
        for s in stats["signals"][:5]:   # cap at 5 to keep message short
            icon = "🟢" if s["type"] == "LONG" else "🔴"
            ts   = s["timestamp"][:16] if s["timestamp"] else "?"
            lines.append(f"      {icon} <code>{s['ticker']}</code> — {s['type']} [{ts}]")

    # ── Rejection breakdown ──────────────────────────────────────────────────
    lines.append(f"\n🚫 <b>Причини відхилень (топ-5):</b>")
    if stats["rejections"]:
        for r in stats["rejections"]:
            # Truncate long reasons so the message stays readable
            reason_short = r["reason"][:60] + "…" if len(r["reason"]) > 60 else r["reason"]
            lines.append(f"   • <code>{reason_short}</code> — {r['count']}×")
    else:
        lines.append("   • Даних немає (перший запуск або відсутні відхилення)")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🔋 <i>Система продовжує роботу. Наступний звіт — завтра о 23:59.</i>")

    return "\n".join(lines)


async def run_daily_reporter(db) -> None:
    """
    Async background task.
    Sleeps until 23:59 local time, then fires the daily Telegram report.
    Loops forever — one report per day.

    Designed to be registered with application.create_task() in main.py.
    """
    logger.info(
        "📊 Daily Reporter: active. Next report in %.0f minutes.",
        _seconds_until_report() / 60,
    )

    while True:
        try:
            wait_sec = _seconds_until_report()
            logger.debug("📊 Daily Reporter: sleeping %.0f s until 23:59.", wait_sec)
            await asyncio.sleep(wait_sec)

            # Collect & send
            stats   = collect_daily_stats(db)
            message = _format_report(stats)

            from modules.notifier import _send_telegram_message
            _send_telegram_message(message)

            logger.info(
                "📊 Daily Reporter: report sent. "
                "Gemini calls=%d  Signals=%d  Open=%d",
                stats["gemini_calls"], stats["signals_total"], stats["open_signals"],
            )

            # Sleep a short buffer so we don't fire twice on the same minute
            await asyncio.sleep(90)

        except asyncio.CancelledError:
            logger.info("📊 Daily Reporter: shutdown signal received.")
            return
        except Exception as exc:
            logger.error("📊 Daily Reporter: error — %s", exc)
            await asyncio.sleep(60)   # back-off and retry
