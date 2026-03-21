"""
Ranger Sovereign Vault â€” Delta-Neutral Funding Arbitrage Paper Engine v2
=========================================================================
Simulates cash-and-carry funding-rate arbitrage (spot long + perp short).
Assumes perfect hedge: PnL is purely f(funding_collected) âˆ’ fees.

v2 patch notes (anti-whipsaw hardening)
----------------------------------------
- Breakeven lock: position cannot exit until accrued yield >= round-trip fees.
- Minimum hold time: 4 h floor regardless of yield (configurable).
- Emergency override: force-close if funding turns heavily negative (< threshold).
- Granular accounting: yield_earned / total_fees_paid tracked separately on
  both per-position and engine-wide level.
- All tunables surfaced as __init__ kwargs for institutional configurability.
"""

import json
import logging
import os
import signal
import time
from typing import Dict, List, Tuple

import requests

# â”€â”€ Terminal colours â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
G, Y, R, W, C = "\033[92m", "\033[93m", "\033[91m", "\033[0m", "\033[96m"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("RangerDaemon")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  CORE ENGINE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
class L2PaperArbitrageEngine:
    """Delta-neutral funding harvester with whipsaw protection."""

    def __init__(
        self,
        # â”€â”€ Capital â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        initial_capital: float = 1_000_000.0,
        max_allocation_per_asset: float = 100_000.0,
        max_concurrent_positions: int = 5,
        # â”€â”€ Fee model (per leg; applied Ã—2 for spot+perp) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        taker_fee: float = 0.000_35,          # 3.5 bps
        # â”€â”€ Funding thresholds (8 h decimal) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        min_funding_entry: float = 0.001_5,   # 15 bps / 8 h
        min_funding_exit: float = 0.000_5,    #  5 bps / 8 h
        # â”€â”€ Anti-whipsaw â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        min_hold_seconds: float = 4 * 3600,   # 4 hours
        emergency_funding_threshold: float = -0.000_5,  # force-close below
        # â”€â”€ Persistence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        state_file: str = "vault_state.json",
    ) -> None:
        # Tunables (frozen after init for auditability)
        self.initial_capital = initial_capital
        self.max_allocation_per_asset = max_allocation_per_asset
        self.max_concurrent_positions = max_concurrent_positions
        self.taker_fee = taker_fee
        self.min_funding_entry = min_funding_entry
        self.min_funding_exit = min_funding_exit
        self.min_hold_seconds = min_hold_seconds
        self.emergency_funding_threshold = emergency_funding_threshold
        self.state_file = state_file

        # Accounting
        self.equity: float = initial_capital
        self.pnl: float = 0.0
        self.total_fees_paid: float = 0.0
        self.total_yield_earned: float = 0.0
        self.positions: Dict[str, dict] = {}
        self.last_tick: float = time.time()

        self._load_state()

    # â”€â”€ Fee helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _single_side_fee(self, size: float) -> float:
        """Fee for one side (entry OR exit) across both legs."""
        return size * self.taker_fee * 2

    # â”€â”€ Persistence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _load_state(self) -> None:
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, "r") as fh:
                state = json.load(fh)
            self.pnl = state.get("pnl", 0.0)
            self.equity = state.get("equity", self.initial_capital)
            self.total_fees_paid = state.get("total_fees_paid", 0.0)
            self.total_yield_earned = state.get("total_yield_earned", 0.0)
            self.positions = state.get("positions", {})
            self.last_tick = state.get("last_tick", time.time())
            logger.info(
                f"{G}Vault restored â€” PnL ${self.pnl:+,.2f} | "
                f"Fees ${self.total_fees_paid:,.2f} | "
                f"Yield ${self.total_yield_earned:,.2f}{W}"
            )
        except Exception as exc:
            logger.error(f"{R}State corruption, cold start: {exc}{W}")

    def save_state(self, current_time: float) -> None:
        state = {
            "pnl": self.pnl,
            "equity": self.equity,
            "total_fees_paid": self.total_fees_paid,
            "total_yield_earned": self.total_yield_earned,
            "positions": self.positions,
            "last_tick": current_time,
        }
        tmp = f"{self.state_file}.tmp"
        try:
            with open(tmp, "w") as fh:
                json.dump(state, fh)
            os.replace(tmp, self.state_file)
        except Exception as exc:
            logger.error(f"Persist failed: {exc}")

    # â”€â”€ Exit eligibility (anti-whipsaw core) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _may_exit(
        self,
        pos: dict,
        current_rate_8h: float,
        now: float,
    ) -> Tuple[bool, str]:
        """Evaluate whether a position is allowed to close.

        Priority order:
        1. EMERGENCY â€” funding deeply negative â†’ always allow.
        2. BREAKEVEN LOCK â€” yield < round-trip fees â†’ block.
        3. MIN HOLD â€” age < min_hold_seconds â†’ block.
        4. NORMAL â€” rate < exit threshold, locks clear â†’ allow.
        """
        # â‘  Emergency override: heavily negative funding burns capital fast
        if current_rate_8h < self.emergency_funding_threshold:
            return True, "EMERGENCY"

        age_s = now - pos["entry_time"]
        round_trip_cost = pos["entry_fee"] + self._single_side_fee(pos["size"])

        # â‘¡ Breakeven lock
        if pos["earned"] < round_trip_cost:
            shortfall = round_trip_cost - pos["earned"]
            return False, f"BREAKEVEN_LOCK (${shortfall:.2f} to go)"

        # â‘¢ Minimum hold time
        if age_s < self.min_hold_seconds:
            remaining_h = (self.min_hold_seconds - age_s) / 3600
            return False, f"MIN_HOLD ({remaining_h:.1f}h left)"

        # â‘£ Normal exit signal
        if current_rate_8h < self.min_funding_exit:
            return True, "RATE_DECAY"

        return False, "RATE_ABOVE_EXIT"

    # â”€â”€ Main tick â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def update_positions_and_pnl(
        self,
        live_rates_decimal: List[Tuple[str, float]],
        elapsed_seconds: float,
    ) -> None:
        now = time.time()
        rates_dict = dict(live_rates_decimal)

        # â”€â”€ 1. Accrue yield & evaluate exits on existing book â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        for coin in list(self.positions):
            pos = self.positions[coin]
            rate_8h = rates_dict.get(coin, 0.0)

            # Accrue funding yield
            rate_per_sec = rate_8h / (8 * 3600)
            tick_yield = pos["size"] * rate_per_sec * elapsed_seconds
            pos["earned"] += tick_yield
            self.total_yield_earned += tick_yield
            self.pnl += tick_yield

            # Exit decision
            may_close, reason = self._may_exit(pos, rate_8h, now)

            if may_close and reason != "RATE_ABOVE_EXIT":
                exit_fee = self._single_side_fee(pos["size"])
                self.pnl -= exit_fee
                self.total_fees_paid += exit_fee
                hold_h = (now - pos["entry_time"]) / 3600
                net = pos["earned"] - pos["entry_fee"] - exit_fee
                logger.info(
                    f"ðŸ”’ {Y}CLOSE {coin}{W} [{reason}] | "
                    f"Hold {hold_h:.1f}h | Yield ${pos['earned']:.2f} | "
                    f"Fees ${pos['entry_fee'] + exit_fee:.2f} | "
                    f"Net ${net:+.2f}"
                )
                del self.positions[coin]

            elif not may_close and rate_8h < self.min_funding_exit:
                # Would have exited in v1 â€” log the block for observability
                logger.info(
                    f"ðŸ›¡ï¸  {C}WHIPSAW BLOCK {coin}{W} [{reason}] | "
                    f"Rate {rate_8h * 100:+.4f}%"
                )

        # â”€â”€ 2. Scan for new entries â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        active = set(self.positions)
        for coin, rate_8h in live_rates_decimal:
            if len(self.positions) >= self.max_concurrent_positions:
                break
            if coin in active:
                continue
            if rate_8h < self.min_funding_entry:
                continue

            entry_fee = self._single_side_fee(self.max_allocation_per_asset)
            self.pnl -= entry_fee
            self.total_fees_paid += entry_fee

            # Estimate time to breakeven (entry + future exit fees)
            projected_rt = entry_fee * 2  # entry now + exit later
            yield_per_sec = self.max_allocation_per_asset * rate_8h / (8 * 3600)
            be_hours = (projected_rt / yield_per_sec / 3600) if yield_per_sec > 0 else float("inf")

            self.positions[coin] = {
                "size": self.max_allocation_per_asset,
                "earned": 0.0,
                "entry_rate": rate_8h,
                "entry_fee": entry_fee,
                "entry_time": now,
            }
            logger.info(
                f"âš¡ {G}OPEN  {coin}{W} | Rate {rate_8h * 100:+.4f}% | "
                f"Fee âˆ’${entry_fee:.2f} | BE ~{be_hours:.1f}h"
            )

        self.equity = self.initial_capital + self.pnl


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  DAEMON
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
class RangerVaultDaemon:
    """Top-level process: fetch â†’ tick â†’ persist â†’ sleep."""

    def __init__(self) -> None:
        self.engine = L2PaperArbitrageEngine()
        self.shutdown_requested = False
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, _signum: int, _frame) -> None:
        self.shutdown_requested = True
        logger.info(f"{R}Shutdown intercepted. Vault locked.{W}")

    @staticmethod
    def fetch_hyperliquid_rates() -> List[Tuple[str, float]]:
        try:
            resp = requests.post(
                "https://api.hyperliquid.xyz/info",
                json={"type": "metaAndAssetCtxs"},
                timeout=5,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            universe = data[0].get("universe", [])
            ctxs = data[1]
            rates = [
                (asset.get("name", "UNKNOWN"), float(ctxs[i].get("funding", 0)) * 8)
                for i, asset in enumerate(universe)
            ]
            rates.sort(key=lambda x: x[1], reverse=True)
            return rates
        except Exception as exc:
            logger.error(f"L2 Desync: {exc}")
            return []

    def run(self) -> None:
        logger.info(f"{G}ðŸ¦… RANGER SOVEREIGN VAULT v2 â€” ANTI-WHIPSAW ENGINE{W}")
        last_tick = self.engine.last_tick

        try:
            while not self.shutdown_requested:
                now = time.time()
                elapsed = now - last_tick
                last_tick = now

                rates = self.fetch_hyperliquid_rates()
                if rates:
                    self.engine.update_positions_and_pnl(rates, elapsed)

                e = self.engine
                logger.info(
                    f"ðŸ“Š VAULT: {G}Eq ${e.equity:,.2f}{W} | "
                    f"PnL ${e.pnl:+,.2f} | "
                    f"Yield ${e.total_yield_earned:,.2f} | "
                    f"Fees âˆ’${e.total_fees_paid:,.2f}"
                )
                if e.positions:
                    parts = []
                    for coin, p in e.positions.items():
                        age_h = (now - p["entry_time"]) / 3600
                        parts.append(f"{coin}: ${p['earned']:.2f} ({age_h:.1f}h)")
                    logger.info(f"ðŸ¦ BOOK: {C}{' | '.join(parts)}{W}")

                self.engine.save_state(now)
                time.sleep(5)
        finally:
            self.engine.save_state(time.time())
            logger.info("Ranger hibernating. State saved atomically.")


if __name__ == "__main__":
    RangerVaultDaemon().run()
