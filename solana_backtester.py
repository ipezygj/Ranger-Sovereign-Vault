""" Technical implementation for Hummingbot Gateway V2.1. """

import json
import logging
import math
import itertools
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("solana_backtester")

VAULT_SIZE_USD: float = 1_000_000.0
DRIFT_FEE_TAKER: float = 0.0010
DRIFT_FEE_MAKER: float = 0.0002
SPOT_FEE: float = 0.0005
SLIPPAGE_BPS: float = 0.0003
FUNDING_PERIODS_PER_YEAR: int = 3 * 365
MAX_DRAWDOWN_LIMIT: float = 0.05

@dataclass
class VaultState:
    nav: float = VAULT_SIZE_USD
    peak_nav: float = VAULT_SIZE_USD
    in_position: bool = False
    cumulative_funding: float = 0.0
    cumulative_fees: float = 0.0
    nav_history: List[float] = field(default_factory=list)
    drawdown_history: List[float] = field(default_factory=list)

    def record_nav(self) -> None:
        self.nav_history.append(self.nav)
        if self.nav > self.peak_nav:
            self.peak_nav = self.nav
        dd = (self.peak_nav - self.nav) / self.peak_nav if self.peak_nav > 0 else 0.0
        self.drawdown_history.append(dd)

class CostModel:
    @staticmethod
    def calculate_trade_cost(notional: float) -> float:
        return notional * (SPOT_FEE + DRIFT_FEE_TAKER + SLIPPAGE_BPS)

class FastBacktester:
    def __init__(self):
        self.cost_model = CostModel()

    def run(self, df: pd.DataFrame, enter_thresh: float, exit_thresh: float) -> Dict:
        state = VaultState()
        notional = VAULT_SIZE_USD
        
        fr_values = df["funding_rate"].values
        fr_ma = df["funding_rate"].rolling(24, min_periods=1).mean().values

        for i in range(len(df)):
            fr_t = fr_values[i]
            ma_t = fr_ma[i]

            if not state.in_position:
                if fr_t > enter_thresh and ma_t > enter_thresh * 0.8:
                    cost = self.cost_model.calculate_trade_cost(notional)
                    state.nav -= cost
                    state.cumulative_fees += cost
                    state.in_position = True
            else:
                if fr_t < exit_thresh:
                    cost = self.cost_model.calculate_trade_cost(notional)
                    state.nav -= cost
                    state.cumulative_fees += cost
                    state.in_position = False
                
                current_dd = (state.peak_nav - state.nav) / state.peak_nav if state.peak_nav > 0 else 0
                if current_dd >= MAX_DRAWDOWN_LIMIT:
                    cost = self.cost_model.calculate_trade_cost(notional)
                    state.nav -= cost
                    state.cumulative_fees += cost
                    state.in_position = False

            if state.in_position:
                funding_pnl = fr_t * notional
                state.nav += funding_pnl
                state.cumulative_funding += funding_pnl

            state.record_nav()

        return self._compute_metrics(state, len(df))

    def _compute_metrics(self, state: VaultState, periods: int) -> Dict:
        nav = np.array(state.nav_history, dtype=float)
        if len(nav) < 2: return {"sharpe": 0.0, "apy": 0.0, "max_drawdown": 0.0}
        
        returns = np.diff(nav) / nav[:-1]
        total_return = (nav[-1] - VAULT_SIZE_USD) / VAULT_SIZE_USD
        apy = (1 + total_return) ** (FUNDING_PERIODS_PER_YEAR / max(1, periods)) - 1
        
        excess = returns - (0.05 / FUNDING_PERIODS_PER_YEAR)
        std_dev = excess.std() + 1e-10
        sharpe = (excess.mean() / std_dev) * math.sqrt(FUNDING_PERIODS_PER_YEAR)
        max_dd = max(state.drawdown_history) if state.drawdown_history else 0.0

        return {
            "sharpe": float(sharpe),
            "apy": float(apy),
            "max_drawdown": float(max_dd),
            "total_return": float(total_return),
            "cumulative_funding": state.cumulative_funding,
            "cumulative_fees": state.cumulative_fees,
            "nav_series": nav.tolist()
        }

def generate_synthetic_data(n_periods: int = 5000) -> pd.DataFrame:
    np.random.seed(42)
    timestamps = pd.date_range("2025-01-01", periods=n_periods, freq="8h")
    
    fr = np.zeros(n_periods)
    fr[0] = 0.0005
    for t in range(1, n_periods):
        fr[t] = fr[t-1] + 0.1 * (0.0008 - fr[t-1]) + 0.0004 * np.random.normal()
    
    return pd.DataFrame({"funding_rate": fr}, index=timestamps)

def optimize_strategy(df: pd.DataFrame) -> Tuple[Dict, Dict]:
    logger.info("Starting heuristic grid search optimization...")
    backtester = FastBacktester()
    
    enter_thresholds = [0.0003, 0.0005, 0.0007, 0.0009]
    exit_thresholds = [-0.0001, 0.0001, 0.0002]
    
    best_metrics = None
    best_params = {}
    best_score = -np.inf

    for ent, ext in itertools.product(enter_thresholds, exit_thresholds):
        if ent <= ext: continue
        
        metrics = backtester.run(df, ent, ext)
        score = metrics["sharpe"] + min(metrics["apy"], 0.50)
        
        if score > best_score and metrics["max_drawdown"] <= MAX_DRAWDOWN_LIMIT:
            best_score = score
            best_metrics = metrics
            best_params = {"enter": ent, "exit": ext}

    logger.info(f"Optimal Parameters found: Enter > {best_params.get('enter', 0)}, Exit < {best_params.get('exit', 0)}")
    return best_metrics, best_params

def export_jsonl(df: pd.DataFrame, nav_series: List[float]):
    logger.info("Exporting optimized vault data to vault_performance.jsonl...")
    with open("vault_performance.jsonl", "w") as f:
        peak = VAULT_SIZE_USD
        for i, nav in enumerate(nav_series):
            if i >= len(df): break
            peak = max(peak, nav)
            f.write(json.dumps({
                "timestamp": df.index[i].isoformat(),
                "equity": round(nav, 2),
                "pnl_usd": round(nav - VAULT_SIZE_USD, 2),
                "roi_pct": round((nav - VAULT_SIZE_USD) / VAULT_SIZE_USD * 100, 4),
                "estimated_apy": 0.0,
                "drawdown_pct": round(-((peak - nav) / peak) * 100, 4) if peak > 0 else 0.0,
                "peak_equity": round(peak, 2),
                "elapsed_days": round(i / 3.0, 2)
            }) + "\n")

def main():
    df = generate_synthetic_data(n_periods=5000)
    best_metrics, _ = optimize_strategy(df)
    
    if best_metrics:
        logger.info(f"Final APY: {best_metrics['apy']*100:.2f}% | MaxDD: {best_metrics['max_drawdown']*100:.2f}%")
        export_jsonl(df, best_metrics["nav_series"])
    else:
        logger.error("Optimization failed to find profitable constraints.")

if __name__ == "__main__":
    main()
