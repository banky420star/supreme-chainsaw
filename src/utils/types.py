"""Shared type definitions for chain_gambler.

Central place for dataclasses, enums, and type aliases used across modules.
"""
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Optional, Dict, List, Any


class TradeAction(IntEnum):
    """Trading action from the model."""
    HOLD = 0
    BUY = 1
    SELL = 2
    CLOSE = 3


class Regime(Enum):
    """Market regime classification."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    LOW_VOLATILITY = "low_volatility"
    UNKNOWN = "unknown"


class PositionSide(Enum):
    """Position direction."""
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class ModelType(Enum):
    """Types of models in the registry."""
    CHAMPION = "champion"
    CANARY = "canary"
    CANDIDATE = "candidate"


@dataclass
class TradingSignal:
    """A trading signal from the model."""
    action: TradeAction
    symbol: str
    confidence: float = 0.0
    regime: Regime = Regime.UNKNOWN
    raw_action: float = 0.0
    bias: float = 0.0
    threshold: float = 0.0
    reason: str = ""
    timestamp: Optional[str] = None


@dataclass
class OrderResult:
    """Result of an order attempt."""
    success: bool = False
    ticket: int = 0
    symbol: str = ""
    side: str = ""
    lots: float = 0.0
    price: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    comment: str = ""
    error: str = ""


@dataclass
class ManagedPosition:
    """A position being tracked for SL/TP/trailing management."""
    ticket: int
    symbol: str
    side: str  # "BUY" or "SELL"
    lots: float = 0.0
    open_price: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    atr_at_open: float = 0.0
    open_time: str = ""
    breakeven_triggered: bool = False
    scale_out_level: int = 0
    scale_out_1_done: bool = False
    scale_out_2_done: bool = False
    peak_profit: float = 0.0
    trailing_active: bool = False
    magic: int = 0


@dataclass
class DecisionRecord:
    """Complete decision record for audit logging."""
    timestamp: str = ""
    symbol: str = ""
    raw_action: float = 0.0
    corrected_action: str = ""
    bias: float = 0.0
    regime: str = ""
    confidence: float = 0.0
    threshold: float = 0.0
    reason: str = ""
    target_exposure: float = 0.0
    model_path: str = ""
    model_version: str = ""
    is_canary: bool = False
    lot_size: float = 0.0
    sl: float = 0.0
    tp: float = 0.0


@dataclass
class CanaryMetrics:
    """Metrics for evaluating a canary model."""
    total_trades: int = 0
    winning_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    avg_trade_pnl: float = 0.0


@dataclass
class ModelInfo:
    """Information about a model in the registry."""
    name: str = ""
    path: str = ""
    model_type: ModelType = ModelType.CANDIDATE
    symbol: str = ""
    version: str = ""
    created_at: str = ""
    metrics: Optional[CanaryMetrics] = None


@dataclass
class TradeReview:
    """Review of a completed trade with outcome tags."""
    ticket: int = 0
    symbol: str = ""
    side: str = ""
    open_time: str = ""
    close_time: str = ""
    open_price: float = 0.0
    close_price: float = 0.0
    lots: float = 0.0
    profit: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    duration_minutes: float = 0.0
    outcome_tags: List[str] = field(default_factory=list)
    decision: Optional[DecisionRecord] = None


# Type aliases
SymbolConfig = Dict[str, Any]
FeatureVector = List[float]
PriceData = Dict[str, List[float]]