# ============================================================
#  modules/risk_manager.py — Shadow of the Dragon
#  Minimalist Risk Manager
# ============================================================

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Minimum acceptable Risk/Reward ratio. Trades below this are structurally unfavorable.
MIN_RR_RATIO = 1.5

@dataclass
class RiskResult:
    entry_price: float
    stop_loss: float
    take_profit: float
    rr_ratio: float
    direction: str

def calculate_trade_risk(
    entry_price: float,
    support: float,
    resistance: float,
    atr_14: float,
    ai_direction: str
) -> RiskResult:
    """
    Calculates Stop Loss, Take Profit and Risk:Reward ratio based on market structure.
    Enforces a minimum R/R of 1.5 by extending the TP target when structural levels are too close.
    """
    direction = ai_direction.upper()
    if direction not in ("LONG", "SHORT"):
        raise ValueError(f"Invalid direction: {direction}")

    atr_buffer = atr_14 * 1.5

    if direction == "LONG":
        stop_loss = support - atr_buffer
        if stop_loss >= entry_price:
            # Fallback if structure is invalid
            stop_loss = entry_price - atr_buffer
            
        actual_risk = entry_price - stop_loss
        take_profit = resistance
        
        if take_profit <= entry_price:
            take_profit = entry_price + (actual_risk * MIN_RR_RATIO)
            
        potential_reward = take_profit - entry_price
        rr_ratio = potential_reward / actual_risk if actual_risk > 0 else 0

        # Enforce minimum R/R by extending the TP if structural target is too close
        if rr_ratio < MIN_RR_RATIO and actual_risk > 0:
            original_tp = take_profit
            take_profit = entry_price + (actual_risk * MIN_RR_RATIO)
            potential_reward = take_profit - entry_price
            rr_ratio = MIN_RR_RATIO
            logger.warning(
                "LONG TP extended: %.4f -> %.4f (structural target too close, enforcing R/R >= %.1f)",
                original_tp, take_profit, MIN_RR_RATIO
            )

    else:  # SHORT
        stop_loss = resistance + atr_buffer
        if stop_loss <= entry_price:
            stop_loss = entry_price + atr_buffer
            
        actual_risk = stop_loss - entry_price
        take_profit = support
        
        if take_profit >= entry_price:
            take_profit = entry_price - (actual_risk * MIN_RR_RATIO)
            
        potential_reward = entry_price - take_profit
        rr_ratio = potential_reward / actual_risk if actual_risk > 0 else 0

        # Enforce minimum R/R by extending the TP if structural target is too close
        if rr_ratio < MIN_RR_RATIO and actual_risk > 0:
            original_tp = take_profit
            take_profit = entry_price - (actual_risk * MIN_RR_RATIO)
            potential_reward = entry_price - take_profit
            rr_ratio = MIN_RR_RATIO
            logger.warning(
                "SHORT TP extended: %.4f -> %.4f (structural target too close, enforcing R/R >= %.1f)",
                original_tp, take_profit, MIN_RR_RATIO
            )

    return RiskResult(
        entry_price=round(entry_price, 4),
        stop_loss=round(stop_loss, 4),
        take_profit=round(take_profit, 4),
        rr_ratio=round(rr_ratio, 2),
        direction=direction
    )


