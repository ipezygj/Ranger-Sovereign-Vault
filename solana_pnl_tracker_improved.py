import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("PnLTracker")

class SolanaPnLTracker:
    def __init__(self, initial_equity: float = 1000000.0):
        self.initial_equity = initial_equity
        self.current_equity = initial_equity
        self.peak_equity = initial_equity
        self.start_time = time.time()
        self.history_file = Path("vault_performance.jsonl")
        
    def calculate_metrics(self) -> Dict[str, Any]:
        total_pnl = self.current_equity - self.initial_equity
        roi_pct = (total_pnl / self.initial_equity) * 100
        return {
            "equity": self.current_equity,
            "pnl_usd": total_pnl,
            "roi_pct": roi_pct,
            "drawdown_pct": ((self.current_equity - self.peak_equity) / self.peak_equity) * 100 if self.peak_equity > 0 else 0
        }

    def update_equity(self, new_equity: float):
        self.current_equity = new_equity
        if new_equity > self.peak_equity:
            self.peak_equity = new_equity

    def log_snapshot(self):
        metrics = self.calculate_metrics()
        with open(self.history_file, "a") as f:
            f.write(json.dumps(metrics) + "\n")
