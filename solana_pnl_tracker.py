""" Technical implementation for Hummingbot Gateway V2.1.
    MODULE: Solana PnL & Performance Tracker
    PURPOSE: Institutional-grade tracking for Ranger Earn Vault.
"""
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path

logger = logging.getLogger("PnLTracker")

class SolanaPnLTracker:
    SECONDS_PER_DAY = 86400
    MIN_DAYS_FOR_APY = 0.01  # ~15 minuutin minimidata
    
    def __init__(self, initial_equity: float = 1000000.0):
        if initial_equity <= 0:
            raise ValueError(f"Initial equity must be positive, got {initial_equity}")
            
        self.initial_equity = initial_equity
        self.current_equity = initial_equity
        self.peak_equity = initial_equity 
        self.start_time = time.time()
        self.history_file = Path("vault_performance.jsonl") 
        self.equity_history: List[Dict[str, float]] = []
        
        logger.info(f"PnL Tracker initialized with ${initial_equity:,.2f}")
        
    def calculate_metrics(self) -> Dict[str, Any]:
        total_pnl = self.current_equity - self.initial_equity
        roi_pct = (total_pnl / self.initial_equity) * 100
        elapsed_days = (time.time() - self.start_time) / self.SECONDS_PER_DAY
        
        if elapsed_days >= self.MIN_DAYS_FOR_APY:
            growth_factor = 1 + (roi_pct / 100)
            annualization_factor = 365 / elapsed_days
            apy = (growth_factor ** annualization_factor - 1) * 100
            apy = max(min(apy, 999999.99), -999999.99)
        else:
            apy = 0.0 
        
        return {
            "timestamp": datetime.now().isoformat(),
            "equity": round(self.current_equity, 2),
            "pnl_usd": round(total_pnl, 2),
            "roi_pct": round(roi_pct, 4),
            "estimated_apy": round(apy, 2),
            "drawdown_pct": round(self._calculate_drawdown(), 4),
            "peak_equity": round(self.peak_equity, 2),
            "elapsed_days": round(elapsed_days, 2)
        }
    
    def _calculate_drawdown(self) -> float:
        if self.peak_equity <= 0: return 0.0
        drawdown = ((self.current_equity - self.peak_equity) / self.peak_equity) * 100
        return min(drawdown, 0.0)
    
    def log_snapshot(self):
        metrics = self.calculate_metrics()
        logger.info(f"PERFORMANCE: ${metrics['equity']:,.2f} | APY: {metrics['estimated_apy']:+.2f}%")
        try:
            with open(self.history_file, "a") as f:
                f.write(json.dumps(metrics) + "\n")
        except IOError as e:
            logger.error(f"Failed to write log: {e}")
    
    def update_equity(self, new_equity: float):
        if new_equity < 0: raise ValueError("Equity cannot be negative")
        if new_equity > self.peak_equity:
            self.peak_equity = new_equity
        self.current_equity = new_equity
        self.equity_history.append({"timestamp": time.time(), "equity": new_equity})
        self.log_snapshot()

    def get_summary(self) -> str:
        m = self.calculate_metrics()
        return f"--- VAULT SUMMARY ---\nEquity: ${m['equity']}\nROI: {m['roi_pct']}%\nAPY: {m['estimated_apy']}%\nMaxDD: {m['drawdown_pct']}%"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tracker = SolanaPnLTracker(1_000_000.0)
    tracker.update_equity(1_000_500.0)
    print(tracker.get_summary())
