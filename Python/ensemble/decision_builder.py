"""DecisionBuilder — converts raw model votes into trade intents."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

try:
    from loguru import logger
except ImportError:
    import logging as _logging
    logger = _logging.getLogger("decision_builder")  # type: ignore


@dataclass
class TradeIntent:
    """Structured trade intent emitted by DecisionBuilder."""

    intent_id: str
    decision_id: str
    symbol: str
    side: str  # LONG / SHORT / FLAT
    target_exposure_pct: float
    stop_atr: float
    take_profit_atr: float
    max_hold_bars: int
    confidence: float
    source_bundle_id: str
    metadata: dict = field(default_factory=dict)


class DecisionBuilder:
    """Converts raw ensemble votes into a concrete trade intent."""

    # Default intent sizing parameters
    DEFAULT_STOP_ATR = 2.0
    DEFAULT_TAKE_PROFIT_ATR = 3.0
    DEFAULT_MAX_HOLD_BARS = 48
    MAX_EXPOSURE_PCT = 0.35

    def __init__(
        self,
        stop_atr: float = DEFAULT_STOP_ATR,
        take_profit_atr: float = DEFAULT_TAKE_PROFIT_ATR,
        max_hold_bars: int = DEFAULT_MAX_HOLD_BARS,
    ):
        self.stop_atr = stop_atr
        self.take_profit_atr = take_profit_atr
        self.max_hold_bars = max_hold_bars

    def build_intent(
        self,
        raw_votes: dict,
        decision_id: str,
        symbol: str,
        source_bundle_id: str,
        regime: str = "ranging",
    ) -> Optional[TradeIntent]:
        """Build a TradeIntent from raw model votes.

        Raw vote object:
          {
            lstm: {vote, confidence, expected_return},
            rainforest: {regime, vote, confidence},
            dreamer: {vote, expected_reward, ruin_probability, confidence},
            ppo: {vote, target_exposure, confidence}
          }
        """
        ppo_vote = self._extract_vote(raw_votes.get("ppo", {}))
        lstm_vote = self._extract_vote(raw_votes.get("lstm", {}))
        dreamer_vote = self._extract_vote(raw_votes.get("dreamer", {}))
        rainforest_vote = self._extract_vote(raw_votes.get("rainforest", {}))

        # Determine side via weighted consensus
        side, confidence = self._resolve_side(
            lstm=lstm_vote,
            ppo=ppo_vote,
            dreamer=dreamer_vote,
            rainforest=rainforest_vote,
            raw=raw_votes,
        )

        if side == "NO_TRADE":
            return None

        target_exposure = self._resolve_target_exposure(raw_votes, side)

        # Adjust sizing by regime risk
        if regime in ("ranging", "reversal_up", "reversal_down"):
            target_exposure *= 0.5
        elif regime in ("breakout_up", "breakout_down"):
            target_exposure *= 0.8

        # Clamp exposure
        target_exposure = max(0.0, min(target_exposure, self.MAX_EXPOSURE_PCT))

        if target_exposure <= 0.0:
            return None

        intent = TradeIntent(
            intent_id=f"intent_{uuid.uuid4().hex[:12]}",
            decision_id=decision_id,
            symbol=symbol,
            side=side,
            target_exposure_pct=round(target_exposure, 4),
            stop_atr=self.stop_atr,
            take_profit_atr=self.take_profit_atr,
            max_hold_bars=self.max_hold_bars,
            confidence=round(confidence, 4),
            source_bundle_id=source_bundle_id,
            metadata={
                "votes": {
                    "lstm": lstm_vote,
                    "ppo": ppo_vote,
                    "dreamer": dreamer_vote,
                    "rainforest": rainforest_vote,
                },
                "regime": regime,
            },
        )
        logger.debug(f"DecisionBuilder emitted intent {intent.intent_id} side={intent.side} exp={intent.target_exposure_pct}")
        return intent

    @staticmethod
    def _extract_vote(vote_payload: dict) -> dict:
        return {
            "vote": str(vote_payload.get("vote", "FLAT")).upper(),
            "confidence": float(vote_payload.get("confidence", 0.0)),
            "expected_return": float(vote_payload.get("expected_return", 0.0)),
            "expected_reward": float(vote_payload.get("expected_reward", 0.0)),
            "ruin_probability": float(vote_payload.get("ruin_probability", 0.0)),
            "target_exposure": float(vote_payload.get("target_exposure", 0.0)),
        }

    def _resolve_side(self, lstm: dict, ppo: dict, dreamer: dict, rainforest: dict, raw: dict) -> tuple[str, float]:
        """Resolve final side and confidence from votes."""
        votes = [lstm["vote"], ppo["vote"], dreamer["vote"], rainforest["vote"]]
        confidences = [lstm["confidence"], ppo["confidence"], dreamer["confidence"], rainforest["confidence"]]

        # Count weighted votes
        long_score = 0.0
        short_score = 0.0
        flat_score = 0.0
        for v, c in zip(votes, confidences):
            weight = max(0.0, min(1.0, c))
            if v == "LONG":
                long_score += weight
            elif v == "SHORT":
                short_score += weight
            else:
                flat_score += weight

        # Dreamer ruin penalty: if ruin prob high, suppress trade
        if dreamer["ruin_probability"] > 0.30:
            long_score *= 0.5
            short_score *= 0.5

        max_score = max(long_score, short_score, flat_score)
        total_score = long_score + short_score + flat_score + 1e-8
        agreement = max_score / total_score

        # Need at least 2 models agreeing with non-trivial confidence
        if agreement < 0.40 or max_score < 0.30:
            return "NO_TRADE", round(agreement, 4)

        if long_score == max_score:
            return "LONG", round(agreement, 4)
        if short_score == max_score:
            return "SHORT", round(agreement, 4)
        return "FLAT", round(agreement, 4)

    def _resolve_target_exposure(self, raw_votes: dict, side: str) -> float:
        """Determine target exposure percentage from votes."""
        ppo = raw_votes.get("ppo", {})
        lstm = raw_votes.get("lstm", {})

        # Start from PPO target exposure if available and aligned
        ppo_target = float(ppo.get("target_exposure", 0.0))
        ppo_vote = str(ppo.get("vote", "FLAT")).upper()

        if ppo_vote == side and ppo_target > 0:
            return ppo_target

        # Default sizing based on LSTM confidence
        lstm_conf = float(lstm.get("confidence", 0.0))
        if lstm_conf >= 0.75:
            return 0.20
        if lstm_conf >= 0.60:
            return 0.15
        if lstm_conf >= 0.50:
            return 0.10
        return 0.05
