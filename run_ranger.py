"""
Ranger Sovereign Vault -- Delta-Neutral Funding Arbitrage Paper Engine v2
=========================================================================
Simulates cash-and-carry funding-rate arbitrage (spot long + perp short).
Assumes perfect hedge: PnL is purely f(funding_collected) - fees.

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

# -- Terminal colours --------------------------------------------------------
G, Y, R, W, C = "\033[92m", "\033[93m", "\033[91m", "\033[0m", "\033[96m"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("RangerDaemon")


# ===========================================================================
#  CORE ENGINE
# ===========================================================================
class L2PaperArbitrageEngine:
    """Delta-neutral funding harvester with whipsaw protection."""

    def __init__(
        self,
        # -- Capital ----------------------------------------------------
        initial_capital: float = 1_000_000.0,
        max_allocation_per_asset: float = 100_000.0,
        max_concurrent_positions: int = 5,
        # -- Fee model (per leg; applied x2 for spot+perp) -------------
        taker_fee: float = 0.000_35,          # 3.5 bps
        # -- Funding thresholds (8 h decimal) --------------------------
        min_funding_entry: float = 0.001_5,   # 15 bps / 8 h
        min_funding_exit: float = 0.000_5,    #  5 bps / 8 h
        # -- Anti-whipsaw ----------------------------------------------
        min_hold_seconds: float = 4 * 3600,   # 4 hours
        emergency_funding_threshold: float = -0.000_5,  # force-close below
        # -- Persistence -----------------------------------------------
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

    # -- Fee helpers --------------------------------------------------------
    def _single_side_fee(self, size: float) -> float:
        """Fee for one side (entry OR exit) across both legs."""
        return size * self.taker_fee * 2

    # -- Persistence --------------------------------------------------------
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
            msg = "Vault restored -- PnL ${:+,.2f} | Fees ${:,.2f} | Yield ${:,.2f}".format(self.pnl, self.total_fees_paid, self.total_yield_earned)
            logger.info(G + msg + W)
        except Exception as exc:
            logger.error(R + "State corruption, cold start: " + str(exc) + W)

    def save_state(self, current_time: float) -> None:
        state = {
            "pnl": self.pnl,
            "equity": self.equity,
            "total_fees_paid": self.total_fees_paid,
            "total_yield_earned": self.total_yield_earned,
            "positions": self.positions,
            "last_tick": current_time,
        }
        tmp = self.state_file + ".tmp"
        try:
            with open(tmp, "w") as fh:
                json.dump(state, fh)
            os.replace(tmp, self.state_file)
        except Exception as exc:
            logger.error("Persist failed: " + str(exc))

    # -- Exit eligibility (anti-whipsaw core) -------------------------------
    def _may_exit(self, pos, current_rate_8h, now):
        """Evaluate whether a position is allowed to close.

        Priority order:
        1. EMERGENCY -- funding deeply negative -> always allow.
        2. BREAKEVEN LOCK -- yield < round-trip fees -> block.
        3. MIN HOLD -- age < min_hold_seconds -> block.
        4. NORMAL -- rate < exit threshold, locks clear -> allow.
        """
        # (1) Emergency override: heavily negative funding burns capital fast
        if current_rate_8h < self.emergency_funding_threshold:
            return True, "EMERGENCY"

        age_s = now - pos["entry_time"]
        round_trip_cost = pos["entry_fee"] + self._single_side_fee(pos["size"])

        # (2) Breakeven lock
        if pos["earned"] < round_trip_cost:
            shortfall = round_trip_cost - pos["earned"]
            return False, "BREAKEVEN_LOCK (${:.2f} to go)".format(shortfall)

        # (3) Minimum hold time
        if age_s < self.min_hold_seconds:
            remaining_h = (self.min_hold_seconds - age_s) / 3600
            return False, "MIN_HOLD ({:.1f}h left)".format(remaining_h)

        # (4) Normal exit signal
        if current_rate_8h < self.min_funding_exit:
            return True, "RATE_DECAY"

        return False, "RATE_ABOVE_EXIT"

    # -- Main tick ----------------------------------------------------------
    def update_positions_and_pnl(self, live_rates_decimal, elapsed_seconds):
        now = time.time()
        rates_dict = dict(live_rates_decimal)

        # -- 1. Accrue yield & evaluate exits on existing book ----------
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
                logger.info("[X] %sCLOSE %s%s [%s] | Hold %.1fh | Yield $%.2f | Fees $%.2f | Net $%+.2f" % (Y, coin, W, reason, hold_h, pos["earned"], pos["entry_fee"] + exit_fee, net))
                del self.positions[coin]

            elif not may_close and rate_8h < self.min_funding_exit:
                # Would have exited in v1 -- log the block for observability
                logger.info("[S]  %sWHIPSAW BLOCK %s%s [%s] | Rate %+.4f%%" % (C, coin, W, reason, rate_8h * 100))

        # -- 2. Scan for new entries ------------------------------------
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
            logger.info("[+] %sOPEN  %s%s | Rate %+.4f%% | Fee -$%.2f | BE ~%.1fh" % (G, coin, W, rate_8h * 100, entry_fee, be_hours))

        self.equity = self.initial_capital + self.pnl


# ===========================================================================
#  DAEMON
# ===========================================================================
class RangerVaultDaemon:
    """Top-level process: fetch -> tick -> persist -> sleep."""

    def __init__(self):
        self.engine = L2PaperArbitrageEngine()
        self.shutdown_requested = False
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, _signum, _frame):
        self.shutdown_requested = True
        logger.info(R + "Shutdown intercepted. Vault locked." + W)

    @staticmethod
    def fetch_hyperliquid_rates():
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
            rates = []
            for i, asset in enumerate(universe):
                funding_8h = float(ctxs[i].get("funding", 0)) * 8
                rates.append((asset.get("name", "UNKNOWN"), funding_8h))
            rates.sort(key=lambda x: x[1], reverse=True)
            return rates
        except Exception as exc:
            logger.error("L2 Desync: " + str(exc))
            return []

    def run(self):
        logger.info(G + ">>> RANGER SOVEREIGN VAULT v2 -- ANTI-WHIPSAW ENGINE" + W)
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
                logger.info("[=] VAULT: %sEq $%s%s | PnL $%+.2f | Yield $%.2f | Fees -$%.2f" % (G, "{:,.2f}".format(e.equity), W, e.pnl, e.total_yield_earned, e.total_fees_paid))

                if e.positions:
                    parts = []
                    for coin, p in e.positions.items():
                        age_h = (now - p["entry_time"]) / 3600
                        parts.append("%s: $%.2f (%.1fh)" % (coin, p["earned"], age_h))
                    logger.info("[B] BOOK: %s%s%s" % (C, " | ".join(parts), W))

                self.engine.save_state(now)
                time.sleep(5)
        finally:
            self.engine.save_state(time.time())
            logger.info("Ranger hibernating. State saved atomically.")


if __name__ == "__main__":
    RangerVaultDaemon().run()
