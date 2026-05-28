"""
TradingReward — Full reward function with all penalties.

Reward = pnl_after_spread_commission_slippage
         - drawdown_penalty
         - overtrading_penalty
         - spread_penalty
         - risk_violation_penalty
         - excessive_hold_penalty

Rejects raw price_change as reward.

NEW (v5+): penalty_scale (default 1.0) multiplies all penalty terms for training stability via lighter early profiles
(controlled by AGI_PENALTY_SCALE / AGI_REWARD_PROFILE / config). Defaults preserve all hardened modeling.
"""
import numpy as np
from typing import Dict, Any


class TradingReward:
    """
    Computes trading reward with comprehensive penalty terms.
    """

    def __init__(
        self,
        commission_rate: float = 0.0002,
        spread_bps: float = 2.0,
        slippage_bps: float = 1.0,
        drawdown_penalty_coeff: float = 3.0,
        overtrading_penalty_coeff: float = 0.5,
        spread_penalty_coeff: float = 5.0,
        risk_violation_penalty_coeff: float = 10.0,
        excessive_hold_penalty_coeff: float = 0.1,
        max_hold_steps: int = 200,
        max_drawdown_threshold: float = 0.15,
        max_risk_per_trade: float = 0.02,
        penalty_scale: float = 1.0,  # NEW: Reward Scale & Signal Improvement (v5+): <1.0 for lighter early-training profiles; default preserves hardened
    ):
        self.commission_rate = float(commission_rate)
        self.spread_bps = float(spread_bps)
        self.slippage_bps = float(slippage_bps)
        self.drawdown_penalty_coeff = float(drawdown_penalty_coeff)
        self.overtrading_penalty_coeff = float(overtrading_penalty_coeff)
        self.spread_penalty_coeff = float(spread_penalty_coeff)
        self.risk_violation_penalty_coeff = float(risk_violation_penalty_coeff)
        self.excessive_hold_penalty_coeff = float(excessive_hold_penalty_coeff)
        self.max_hold_steps = int(max_hold_steps)
        self.max_drawdown_threshold = float(max_drawdown_threshold)
        self.max_risk_per_trade = float(max_risk_per_trade)
        self.penalty_scale = float(penalty_scale)

    def compute(
        self,
        prev_equity: float,
        current_equity: float,
        prev_position: float,
        current_position: float,
        current_price: float,
        prev_price: float,
        drawdown: float,
        hold_steps: int = 0,
        risk_used: float = 0.0,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Compute reward and return dict with components.
        """
        # Raw PnL before costs
        price_ret = (current_price - prev_price) / (prev_price + 1e-12)
        raw_pnl = prev_position * prev_equity * price_ret

        # Costs
        delta = current_position - prev_position
        traded_notional = abs(delta) * current_equity
        commission_cost = traded_notional * self.commission_rate
        spread_cost = traded_notional * (self.spread_bps / 10000.0)
        slippage_cost = traded_notional * (self.slippage_bps / 10000.0)
        total_cost = commission_cost + spread_cost + slippage_cost

        pnl_after_costs = raw_pnl - total_cost

        # Penalties
        drawdown_penalty = self.drawdown_penalty_coeff * max(0.0, drawdown - 0.06)
        overtrading_penalty = self.overtrading_penalty_coeff * abs(delta)
        spread_penalty = self.spread_penalty_coeff * (spread_cost / (prev_equity + 1e-12))
        risk_violation_penalty = self.risk_violation_penalty_coeff * max(0.0, risk_used - self.max_risk_per_trade)
        excessive_hold_penalty = self.excessive_hold_penalty_coeff * max(0.0, hold_steps - self.max_hold_steps) / max(1, self.max_hold_steps)

        # NEW (Reward Scale & Signal Improvement): apply penalty_scale for optional lighter profiles during early training (v5/v6)
        # Default=1.0 fully preserves hardened risk modeling (DD, costs, overtrading, risk violation).
        # Set <1.0 via AGI_PENALTY_SCALE or config only for training stability; evaluation gates unaffected.
        drawdown_penalty *= self.penalty_scale
        overtrading_penalty *= self.penalty_scale
        spread_penalty *= self.penalty_scale
        risk_violation_penalty *= self.penalty_scale
        excessive_hold_penalty *= self.penalty_scale

        # Total reward (core)
        reward = (
            pnl_after_costs / (prev_equity + 1e-12)
            - drawdown_penalty
            - overtrading_penalty
            - spread_penalty
            - risk_violation_penalty
            - excessive_hold_penalty
        )

        # ── Market Timing Awareness (user request: profitable timing + market open / news events) ──
        # These signals come from enriched observations (news_proximity, major_open_window, etc.)
        timing_bonus = 0.0
        news_proximity = float(kwargs.get("news_proximity", 0.0))
        in_open_window = float(kwargs.get("major_open_window", 0.0))
        news_avoidance = float(kwargs.get("news_avoidance_zone", 0.0))

        # Reward good behavior around news (avoiding high-impact windows when not in a strong position)
        if news_avoidance > 0 and current_position == 0:
            timing_bonus += 0.0008 * self.penalty_scale   # small positive for staying flat near news

        # Small bonus for participating in high-volatility open windows when conditions are good
        if in_open_window > 0 and abs(current_position) > 0:
            timing_bonus += 0.0005 * self.penalty_scale

        # Penalty for holding through very close high-impact news without justification
        if news_proximity > 0.7 and abs(current_position) > 0:
            timing_bonus -= 0.0015 * self.penalty_scale

        reward += timing_bonus

        # Reject raw price_change: if the reward is essentially just price_ret with no position scaling, zero it
        # This prevents the agent from getting rewarded for market movement without position
        if abs(prev_position) < 1e-6 and abs(delta) < 1e-6:
            reward = -excessive_hold_penalty - spread_penalty - drawdown_penalty

        return {
            "reward": float(np.clip(reward, -5.0, 5.0)),
            "components": {
                "pnl_after_spread_commission_slippage": float(pnl_after_costs / (prev_equity + 1e-12)),
                "drawdown_penalty": float(drawdown_penalty),
                "overtrading_penalty": float(overtrading_penalty),
                "spread_penalty": float(spread_penalty),
                "risk_violation_penalty": float(risk_violation_penalty),
                "excessive_hold_penalty": float(excessive_hold_penalty),
            },
            "costs": {
                "commission": float(commission_cost),
                "spread": float(spread_cost),
                "slippage": float(slippage_cost),
                "total": float(total_cost),
            },
        }

    @staticmethod
    def reject_raw_price_change(reward: float, position: float, delta: float) -> float:
        """
        Zero out rewards that are just raw price movement without meaningful position.
        """
        if abs(position) < 1e-6 and abs(delta) < 1e-6:
            return 0.0
        return float(reward)
