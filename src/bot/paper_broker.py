"""
Paper broker. In-memory simulation of order placement, fills, and PnL.

Honors the same SL/TP/partial logic as the backtest engine. Designed to be
swappable with live_broker.py through the Broker protocol.
"""
from dataclasses import dataclass
from typing import Optional, Literal, Protocol
from datetime import datetime, timezone
import uuid
from loguru import logger


@dataclass
class Position:
    id: str
    symbol: str
    side: Literal["long", "short"]
    entry_price: float
    size_usd: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_usd: float
    opened_at: datetime
    partial_closed: bool = False
    realized_pnl_usd: float = 0.0
    closed_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    outcome: Optional[Literal["tp1", "tp2", "sl", "be", "manual"]] = None
    notes: str = ""


class Broker(Protocol):
    """Common interface for paper and live brokers."""
    async def open_position(self, symbol: str, side: str, size_usd: float,
                            entry_price: float, stop_loss: float,
                            tp1: float, tp2: float, notes: str = "") -> Position: ...
    async def close_position(self, position_id: str, exit_price: float,
                             reason: str = "manual") -> Position: ...
    async def get_open_positions(self) -> list[Position]: ...
    def equity(self) -> float: ...


class PaperBroker:
    """In-memory paper broker. State lives in self.positions; persistence is
    the caller's job (state.py mirrors to Supabase)."""

    def __init__(self, initial_equity: float, fee_pct: float = 0.0006,
                 slippage_pct: float = 0.0005):
        self.cash = initial_equity
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct
        self.positions: dict[str, Position] = {}
        self.closed_positions: list[Position] = []

    def equity(self) -> float:
        """Cash + unrealized PnL for open positions (mark-to-market)."""
        return self.cash  # paper broker MTM updates happen on tick via mark()

    async def open_position(self, symbol: str, side: str, size_usd: float,
                            entry_price: float, stop_loss: float,
                            tp1: float, tp2: float, notes: str = "") -> Position:
        if side not in ("long", "short"):
            raise ValueError(f"side must be long or short, got {side}")
        # apply slippage on entry
        slipped = entry_price * (1 + self.slippage_pct) if side == "long" \
                  else entry_price * (1 - self.slippage_pct)
        risk_usd = abs(slipped - stop_loss) / slipped * size_usd
        fee = size_usd * self.fee_pct
        self.cash -= fee
        pos = Position(
            id=str(uuid.uuid4()),
            symbol=symbol,
            side=side,  # type: ignore
            entry_price=slipped,
            size_usd=size_usd,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            risk_usd=risk_usd,
            opened_at=datetime.now(timezone.utc),
            notes=notes,
        )
        self.positions[pos.id] = pos
        logger.info(f"[paper] OPEN {side} {symbol} @ {slipped:.2f} size=${size_usd:.0f} "
                   f"sl={stop_loss:.2f} tp1={tp1:.2f} tp2={tp2:.2f}")
        return pos

    async def close_position(self, position_id: str, exit_price: float,
                             reason: str = "manual") -> Position:
        pos = self.positions.pop(position_id, None)
        if pos is None:
            raise KeyError(f"no open position {position_id}")
        # determine remaining size
        remaining_frac = 0.5 if pos.partial_closed else 1.0
        remaining_usd = pos.size_usd * remaining_frac
        slipped = exit_price * (1 - self.slippage_pct) if pos.side == "long" \
                  else exit_price * (1 + self.slippage_pct)
        sign = 1 if pos.side == "long" else -1
        pnl = sign * (slipped - pos.entry_price) / pos.entry_price * remaining_usd
        fee = remaining_usd * self.fee_pct
        net = pnl - fee
        pos.realized_pnl_usd += net
        self.cash += net
        pos.closed_at = datetime.now(timezone.utc)
        pos.exit_price = slipped
        pos.outcome = reason  # type: ignore
        self.closed_positions.append(pos)
        logger.info(f"[paper] CLOSE {pos.side} {pos.symbol} @ {slipped:.2f} "
                   f"reason={reason} pnl=${pos.realized_pnl_usd:+.2f}")
        return pos

    async def partial_close(self, position_id: str, exit_price: float, fraction: float = 0.5):
        """Used when TP1 hits. Closes `fraction` of the position and moves SL to BE."""
        pos = self.positions.get(position_id)
        if pos is None or pos.partial_closed:
            return
        slipped = exit_price * (1 - self.slippage_pct) if pos.side == "long" \
                  else exit_price * (1 + self.slippage_pct)
        portion_usd = pos.size_usd * fraction
        sign = 1 if pos.side == "long" else -1
        pnl = sign * (slipped - pos.entry_price) / pos.entry_price * portion_usd
        fee = portion_usd * self.fee_pct
        net = pnl - fee
        pos.realized_pnl_usd += net
        self.cash += net
        pos.partial_closed = True
        pos.stop_loss = pos.entry_price  # move to BE
        logger.info(f"[paper] TP1 {pos.side} {pos.symbol} @ {slipped:.2f} "
                   f"partial=${net:+.2f} sl->BE")

    async def get_open_positions(self) -> list[Position]:
        return list(self.positions.values())

    def check_exits(self, symbol: str, high: float, low: float):
        """Called on every new bar/tick. Returns list of (position_id, action) tuples
        for the engine to execute. Action is one of 'sl', 'tp1', 'tp2'."""
        actions = []
        for pos in self.positions.values():
            if pos.symbol != symbol:
                continue
            if pos.side == "long":
                if low <= pos.stop_loss:
                    outcome = "be" if abs(pos.stop_loss - pos.entry_price) / pos.entry_price < 0.001 else "sl"
                    actions.append((pos.id, outcome, pos.stop_loss))
                elif high >= pos.take_profit_2:
                    actions.append((pos.id, "tp2", pos.take_profit_2))
                elif (not pos.partial_closed) and high >= pos.take_profit_1:
                    actions.append((pos.id, "tp1", pos.take_profit_1))
            else:  # short
                if high >= pos.stop_loss:
                    outcome = "be" if abs(pos.stop_loss - pos.entry_price) / pos.entry_price < 0.001 else "sl"
                    actions.append((pos.id, outcome, pos.stop_loss))
                elif low <= pos.take_profit_2:
                    actions.append((pos.id, "tp2", pos.take_profit_2))
                elif (not pos.partial_closed) and low <= pos.take_profit_1:
                    actions.append((pos.id, "tp1", pos.take_profit_1))
        return actions
