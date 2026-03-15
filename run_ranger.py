""" Technical implementation for Hummingbot Gateway V2.1.
    MODULE: Ranger Vault Daemon (Production Paper Trading w/ Fees & Persistence)
"""
import json
import logging
import os
import signal
import time
from typing import Dict, List, Tuple

import requests

# UI Colors for Stealth Terminal
G, Y, R, W, C = "\033[92m", "\033[93m", "\033[91m", "\033[0m", "\033[96m"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("RangerDaemon")

STATE_FILE = "vault_state.json"
TAKER_FEE = 0.00035  # 3.5 bps per leg
MIN_FUNDING_ENTRY = 0.0005  # 0.05% per 8h
MIN_FUNDING_EXIT = 0.00025  # 0.025% per 8h

class L2PaperArbitrageEngine:
    def __init__(self, initial_capital: float = 1000000.0):
        self.initial_capital = initial_capital
        self.equity = initial_capital
        self.pnl = 0.0
        self.positions: Dict[str, dict] = {}
        self.max_allocation_per_asset = 100000.0
        self.load_state()

    def load_state(self):
        """Loads vault state to survive Termux reboots."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
                    self.pnl = state.get("pnl", 0.0)
                    self.equity = state.get("equity", self.initial_capital)
                    self.positions = state.get("positions", {})
                logger.info(f"{G}Vault state restored from disk.{W}")
            except Exception as e:
                logger.error(f"State corruption, starting fresh: {e}")

    def save_state(self):
        """Persists vault state to disk."""
        state = {
            "pnl": self.pnl,
            "equity": self.equity,
            "positions": self.positions
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)

    def update_positions_and_pnl(self, live_rates_decimal: List[Tuple[str, float]], elapsed_seconds: float):
        rates_dict = {coin: rate for coin, rate in live_rates_decimal}
        
        # 1. Harvest yield & check exits
        for coin in list(self.positions.keys()):
            pos = self.positions[coin]
            current_rate_8h_dec = rates_dict.get(coin, 0.0)
            
            # EXIT LOGIC: Close if rate drops too low or flips negative
            if current_rate_8h_dec < MIN_FUNDING_EXIT:
                # Pay exit fees (Spot sell + Perp buy)
                exit_fee = pos["size"] * TAKER_FEE * 2
                self.pnl -= exit_fee
                logger.info(f"🔒 {Y}Closing {coin}{W} (Rate: {current_rate_8h_dec * 100:+.4f}%) | Fee: -${exit_fee:.2f}")
                del self.positions[coin]
                continue
                
            # YIELD CALCULATION (Pure decimals)
            rate_per_second = current_rate_8h_dec / (8 * 3600)
            yield_earned = pos["size"] * rate_per_second * elapsed_seconds
            
            self.pnl += yield_earned
            self.positions[coin]["earned"] += yield_earned

        # 2. Open new positions
        active_coins = set(self.positions.keys())
        for coin, rate_8h_dec in live_rates_decimal:
            if len(self.positions) >= 5:
                break
            if coin not in active_coins and rate_8h_dec >= MIN_FUNDING_ENTRY:
                # Pay entry fees (Spot buy + Perp short)
                entry_fee = self.max_allocation_per_asset * TAKER_FEE * 2
                self.pnl -= entry_fee
                logger.info(f"⚡ {G}Opening {coin}{W} (Rate: {rate_8h_dec * 100:+.4f}%) | Fee: -${entry_fee:.2f}")
                self.positions[coin] = {
                    "size": self.max_allocation_per_asset, 
                    "earned": 0.0, 
                    "entry_rate": rate_8h_dec
                }
        
        self.equity = self.initial_capital + self.pnl
        self.save_state()

class RangerVaultDaemon:
    def __init__(self):
        self.paper_engine = L2PaperArbitrageEngine()
        self.shutdown_requested = False
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        self.shutdown_requested = True
        logger.info(f"{R}Shutdown intercepted. Vault locked.{W}")

    def fetch_hyperliquid_rates(self) -> List[Tuple[str, float]]:
        """Extracts pure decimal 8h rates."""
        try:
            response = requests.post("https://api.hyperliquid.xyz/info", json={"type": "metaAndAssetCtxs"}, timeout=5)
            if response.status_code == 200:
                data = response.json()
                universe, ctxs = data[0].get("universe", []), data[1]
                
                rates_decimal = []
                for i, asset in enumerate(universe):
                    # Natively hourly decimal -> multiply by 8 for 8h decimal
                    funding_8h_dec = float(ctxs[i].get("funding", 0)) * 8
                    rates_decimal.append((asset.get("name", "UNKNOWN"), funding_8h_dec))
                
                rates_decimal.sort(key=lambda x: x[1], reverse=True) # Sort by most positive
                return rates_decimal
        except Exception as e:
            logger.error(f"L2 Desync: {e}")
        return []

    def run(self):
        logger.info(f"{G}🦅 RANGER SOVEREIGN VAULT - HARDENED LIVE PAPER ENGINE{W}")
        last_tick = time.time()
        
        try:
            while not self.shutdown_requested:
                current_time = time.time()
                elapsed = current_time - last_tick
                last_tick = current_time

                live_rates_decimal = self.fetch_hyperliquid_rates()
                if live_rates_decimal:
                    self.paper_engine.update_positions_and_pnl(live_rates_decimal, elapsed)
                
                # Terminal UI
                eq, pnl = self.paper_engine.equity, self.paper_engine.pnl
                logger.info(f"📊 VAULT: {G}Equity ${eq:,.2f}{W} | PnL ${pnl:+,.4f}")
                
                if self.paper_engine.positions:
                    pos_str = " | ".join([f"{c}: ${p['earned']:.4f}" for c, p in self.paper_engine.positions.items()])
                    logger.info(f"🏦 ACTIVE YIELD: {C}{pos_str}{W}")
                
                time.sleep(5)
        finally:
            self.paper_engine.save_state()
            logger.info("Ranger hibernating. State saved.")

if __name__ == "__main__":
    RangerVaultDaemon().run()
