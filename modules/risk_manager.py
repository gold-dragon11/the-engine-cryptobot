# ============================================================
#  modules/risk_manager.py — Dragon Crypto Oracle  (v3 – Dynamic)
#
#  Two position-sizing modes:
#
#  1. calculate_position()  — MANUAL mode
#     User provides explicit entry + stop-loss.
#     Original static math, kept for /risk command.
#
#  2. calculate_dynamic_position()  — MARKET STRUCTURE mode
#     Derives SL from Support – ATR×1.5 volatility buffer,
#     derives TP from Resistance (with 1:1.5 R:R floor).
#     Used by /analyze pipeline.
#
#  Both enforce:
#   • Risk in USD = Balance × Risk%  (constant)
#   • Position size = Risk USD / |Entry – SL|
#   • Leverage = round(notional / balance), integer, min 1×
# ============================================================

from dataclasses import dataclass
import math


@dataclass
class PositionResult:
    """Structured output of calculate_position()."""
    risk_amount_usd: float      # Dollar amount you are willing to lose
    risk_per_unit: float        # Dollar distance between entry and stop-loss
    position_size_units: float  # Number of units (e.g. BTC) to buy/sell
    position_value_usd: float   # Notional value of the full position
    recommended_leverage: int   # Rounded leverage (integer, minimum 1x)
    breakeven_fee_pct: float    # Approx. round-trip fee as % of position value
    take_profit_price: float    # TP at 1:2 Risk:Reward ratio


@dataclass
class DynamicPositionResult:
    """
    Structured output of calculate_dynamic_position().
    Extends the basic result with market-structure context fields.
    """
    # ── Risk constants ────────────────────────────────────────
    risk_amount_usd: float      # Balance × Risk%
    risk_per_unit: float        # |Entry – SL| (derived from market structure + ATR)

    # ── Position sizing ───────────────────────────────────────
    position_size_units: float  # risk_amount_usd / risk_per_unit
    position_value_usd: float   # position_size × entry_price
    recommended_leverage: int   # round(notional / balance), min 1

    # ── Market-structure-derived levels ────────────────────────
    stop_loss_price: float      # Support − ATR × 1.5
    take_profit_price: float    # Resistance or forced 1:1.5 R:R
    support: float              # 48 h lowest low
    resistance: float           # 48 h highest high
    atr_14: float               # ATR(14) value used for the buffer

    # ── Meta ──────────────────────────────────────────────────
    rr_ratio: float             # Actual Risk:Reward ratio achieved
    rr_forced: bool             # True if TP was recalculated to meet 1:1.5 floor
    direction: str              # "LONG" or "SHORT"
    margin_usd: float           # Notional Value / Leverage (actual collateral)
    margin_type: str            # "isolated" or "cross"
    breakeven_fee_pct: float


# ── Manual Position Sizing (for /risk) ───────────────────────

def calculate_position(
    balance: float,
    risk_percent: float,
    entry_price: float,
    stop_loss_price: float,
    fee_rate: float = 0.001,    # Binance taker fee: 0.1 % per leg → 0.2 % round-trip
    reward_ratio: float = 2.0,  # Risk:Reward ratio (default 1:2)
) -> PositionResult:
    """
    Calculate the recommended position size, leverage, and take-profit.

    Parameters
    ----------
    balance : float
        Available account balance in USD (or USDT).
    risk_percent : float
        Percentage of balance you are willing to risk on this trade.
    entry_price : float
        The price at which you plan to enter the trade (USD).
    stop_loss_price : float
        The price at which your stop-loss order will trigger (USD).
    fee_rate : float, optional
        Per-leg exchange fee as a decimal. Default: Binance taker (0.001).
    reward_ratio : float, optional
        The reward multiple of risk for Take Profit. Default: 2.0 (1:2 R:R).

    Returns
    -------
    PositionResult  — dataclass with all calculated metrics.

    Raises
    ------
    ValueError  — if entry equals stop-loss or inputs are non-positive.

    How the maths work
    ------------------
    1. risk_amount = balance × (risk_percent / 100)
          → The maximum USD loss you accept on this trade.

    2. risk_per_unit = |entry_price − stop_loss_price|
          → How many dollars you lose *per unit* if stop-loss is hit.

    3. position_size = risk_amount / risk_per_unit
          → Units to trade so a full move to stop-loss = exactly risk_amount.

    4. position_value = position_size × entry_price
          → Total notional value of the position in USD.

    5. leverage = round(max(1, position_value / balance))
          → Integer leverage needed (Binance only accepts whole numbers).
          A value of 1 means the trade fits within a spot/1x account.

    6. take_profit = entry + (entry − stop_loss) × reward_ratio
          → For LONG (entry > SL): TP is above entry.
          → For SHORT (entry < SL): TP is below entry.
          Both use the same formula because (entry − SL) is signed.

    7. breakeven_fee_pct = 2 × fee_rate × 100
          → Round-trip cost as a percentage. The position must move at
            least this much to break even after open + close fees.
    """
    # ── Input validation ─────────────────────────────────────
    if balance <= 0:
        raise ValueError("balance must be positive.")
    if not (0 < risk_percent <= 100):
        raise ValueError("risk_percent must be between 0 and 100.")
    if entry_price <= 0 or stop_loss_price <= 0:
        raise ValueError("Prices must be positive.")
    if entry_price == stop_loss_price:
        raise ValueError("entry_price and stop_loss_price must differ.")

    # ── Core calculations ────────────────────────────────────
    # Step 1 — Dollar amount risked
    risk_amount_usd = balance * (risk_percent / 100)

    # Step 2 — Dollar distance between entry and stop-loss (always positive)
    risk_per_unit = abs(entry_price - stop_loss_price)

    # Step 3 — Position size in base asset units (e.g. BTC)
    position_size_units = risk_amount_usd / risk_per_unit

    # Step 4 — Total notional value of the position
    position_value_usd = position_size_units * entry_price

    # Step 5 — Integer leverage (Binance constraint: whole numbers only, min 1×)
    raw_leverage = position_value_usd / balance
    recommended_leverage = max(1, math.ceil(raw_leverage))

    # Step 6 — Take-profit at the specified Risk:Reward ratio
    # Signed formula works for both LONG and SHORT automatically:
    #   LONG  (entry > SL): entry - SL > 0  →  TP above entry ✓
    #   SHORT (entry < SL): entry - SL < 0  →  TP below entry ✓
    take_profit_price = entry_price + (entry_price - stop_loss_price) * reward_ratio

    # Step 7 — Round-trip fee percentage (open + close)
    breakeven_fee_pct = 2 * fee_rate * 100

    return PositionResult(
        risk_amount_usd=round(risk_amount_usd, 2),
        risk_per_unit=round(risk_per_unit, 2),
        position_size_units=round(position_size_units, 6),
        position_value_usd=round(position_value_usd, 2),
        recommended_leverage=recommended_leverage,      # already an int from max(1, round(...))
        breakeven_fee_pct=round(breakeven_fee_pct, 3),
        take_profit_price=round(take_profit_price, 4),
    )


# ── Dynamic Position Sizing (Market Structure + ATR) ─────────

_MIN_RR_RATIO = 1.5   # Minimum acceptable Risk:Reward

def calculate_dynamic_position(
    balance: float,
    risk_percent: float,
    entry_price: float,
    support: float,
    resistance: float,
    atr_14: float,
    ai_direction: str,
    fee_rate: float = 0.001,
) -> DynamicPositionResult:
    """
    Quant-grade position sizing using market structure.

    This replaces the old "sentiment-adjusted 3% SL" approach with
    data-driven levels:

      SL = Support − (ATR × 1.5)     ← volatility buffer avoids noise wicks
      TP = Resistance                 ← initial target at structural high
           or Entry + risk × 1.5      ← forced if R:R < 1:1.5

    Parameters
    ----------
    balance       : float  — Account equity in USD
    risk_percent  : float  — % of balance to risk (e.g. 1.0 = 1 %)
    entry_price   : float  — Current market price (Entry)
    support       : float  — 48 h lowest low
    resistance    : float  — 48 h highest high
    atr_14        : float  — ATR(14) value in price units
    fee_rate      : float  — Per-leg fee (default: 0.001 = 0.1 %)

    Returns
    -------
    DynamicPositionResult  — Full position plan with market-context.

    Raises
    ------
    ValueError  — if inputs are invalid or SL/TP cannot be computed.
    """
    # ── Validation ───────────────────────────────────────────
    if balance <= 0:
        raise ValueError("balance must be positive.")
    if not (0 < risk_percent <= 100):
        raise ValueError("risk_percent must be between 0 and 100.")
    if entry_price <= 0:
        raise ValueError("entry_price must be positive.")
    if atr_14 <= 0:
        raise ValueError("ATR must be positive.")

    # ── Direction ──────────────────────────────────────────────
    # We strictly use the direction provided by the AI Analysis.
    direction = ai_direction.upper()
    if direction not in ("LONG", "SHORT"):
        raise ValueError(f"Invalid ai_direction: {direction}")

    # ── Dynamic Stop Loss ────────────────────────────────────
    atr_buffer = atr_14 * 1.5

    if direction == "LONG":
        stop_loss = support - atr_buffer
    else:
        # SHORT: SL above resistance + buffer
        stop_loss = resistance + atr_buffer

    # Safety: SL must be positive and different from entry
    if stop_loss <= 0:
        stop_loss = entry_price * 0.005  # fallback: 0.5 % from zero
    if abs(entry_price - stop_loss) < entry_price * 0.001:
        raise ValueError(
            "Entry and computed SL are too close "
            f"(entry={entry_price:.4f}, SL={stop_loss:.4f}, ATR={atr_14:.4f})."
        )

    # ── Risk amount (constant) ───────────────────────────────
    risk_amount_usd = balance * (risk_percent / 100)
    risk_per_unit = abs(entry_price - stop_loss)

    # ── Dynamic Take Profit ──────────────────────────────────
    rr_forced = False

    if direction == "LONG":
        initial_tp = resistance
        potential_reward = initial_tp - entry_price
        actual_risk      = entry_price - stop_loss

        if actual_risk <= 0:
            raise ValueError("Computed risk is non-positive for LONG direction.")

        rr_ratio = potential_reward / actual_risk

        if rr_ratio < _MIN_RR_RATIO:
            # Force TP to achieve the minimum 1:1.5 R:R
            take_profit = entry_price + (actual_risk * _MIN_RR_RATIO)
            rr_ratio = _MIN_RR_RATIO
            rr_forced = True
        else:
            take_profit = initial_tp

    else:  # SHORT
        initial_tp = support
        potential_reward = entry_price - initial_tp
        actual_risk      = stop_loss - entry_price

        if actual_risk <= 0:
            raise ValueError("Computed risk is non-positive for SHORT direction.")

        rr_ratio = potential_reward / actual_risk

        if rr_ratio < _MIN_RR_RATIO:
            take_profit = entry_price - (actual_risk * _MIN_RR_RATIO)
            rr_ratio = _MIN_RR_RATIO
            rr_forced = True
        else:
            take_profit = initial_tp

    # ── Position sizing ──────────────────────────────────────
    position_size_units = risk_amount_usd / risk_per_unit
    position_value_usd  = position_size_units * entry_price

    # ── Integer leverage (Binance constraint) ────────────────
    raw_leverage = position_value_usd / balance
    recommended_leverage = max(1, math.ceil(raw_leverage))
    
    margin_type = "isolated" if recommended_leverage > 2 else "isolated"  # Strict default safety

    # ── Margin (collateral required) ─────────────────────────
    margin_usd = position_value_usd / recommended_leverage

    # ── Round-trip breakeven fee ─────────────────────────────
    breakeven_fee_pct = 2 * fee_rate * 100

    return DynamicPositionResult(
        risk_amount_usd=round(risk_amount_usd, 2),
        risk_per_unit=round(risk_per_unit, 4),
        position_size_units=round(position_size_units, 6),
        position_value_usd=round(position_value_usd, 2),
        recommended_leverage=recommended_leverage,
        stop_loss_price=round(stop_loss, 4),
        take_profit_price=round(take_profit, 4),
        support=round(support, 4),
        resistance=round(resistance, 4),
        atr_14=round(atr_14, 4),
        rr_ratio=round(rr_ratio, 2),
        rr_forced=rr_forced,
        direction=direction,
        margin_usd=round(margin_usd, 2),
        margin_type=margin_type,
        breakeven_fee_pct=round(breakeven_fee_pct, 3),
    )
