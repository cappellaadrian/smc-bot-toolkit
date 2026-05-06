"""
Risk gate. Every order goes through check_order() before submission.

Tracks intraday PnL, position count, and a kill-switch flag. The kill-switch
is sticky: once tripped, only manual reset clears it.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from typing import Optional
from loguru import logger


@dataclass
class RiskState:
    starting_equity_today: float
    current_equity: float
    open_positions_count: int = 0
    today: date = field(default_factory=lambda: datetime.now(timezone.utc).date())
    kill_switch_tripped: bool = False
    kill_switch_reason: str = ""

    def daily_pnl_pct(self) -> float:
        if self.starting_equity_today <= 0:
            return 0.0
        return (self.current_equity / self.starting_equity_today) - 1


class RiskManager:
    def __init__(self, initial_equity: float, max_daily_loss_pct: float = 0.05,
                 max_positions: int = 1):
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_positions = max_positions
        self.state = RiskState(
            starting_equity_today=initial_equity,
            current_equity=initial_equity,
        )

    def update_equity(self, equity: float) -> None:
        self.state.current_equity = equity
        # Check daily loss
        loss_pct = -self.state.daily_pnl_pct()
        if loss_pct >= self.max_daily_loss_pct and not self.state.kill_switch_tripped:
            self.trip_kill_switch(f"daily loss {loss_pct*100:.2f}% exceeds limit "
                                 f"{self.max_daily_loss_pct*100:.2f}%")

    def update_position_count(self, count: int) -> None:
        self.state.open_positions_count = count

    def maybe_reset_for_new_day(self) -> bool:
        today = datetime.now(timezone.utc).date()
        if today != self.state.today:
            logger.info(f"new day {today}, resetting daily risk anchor "
                       f"(equity={self.state.current_equity:.2f})")
            self.state.today = today
            self.state.starting_equity_today = self.state.current_equity
            return True
        return False

    def trip_kill_switch(self, reason: str) -> None:
        self.state.kill_switch_tripped = True
        self.state.kill_switch_reason = reason
        logger.error(f"KILL SWITCH TRIPPED: {reason}")

    def reset_kill_switch(self) -> None:
        """Manual reset only. Engine should not call this."""
        self.state.kill_switch_tripped = False
        self.state.kill_switch_reason = ""
        logger.warning("Kill switch manually reset")

    def check_order(self, side: str, size_usd: float) -> tuple[bool, Optional[str]]:
        """Return (allowed, reason_if_blocked)."""
        if self.state.kill_switch_tripped:
            return False, f"kill switch tripped: {self.state.kill_switch_reason}"
        if self.state.open_positions_count >= self.max_positions:
            return False, f"max positions reached ({self.max_positions})"
        if size_usd <= 0:
            return False, "size_usd must be positive"
        if size_usd > self.state.current_equity * 20:
            return False, f"size_usd {size_usd:.0f} exceeds 20x equity"
        return True, None
