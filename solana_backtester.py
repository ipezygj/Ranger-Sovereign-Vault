""" Technical implementation for Hummingbot Gateway V2.1.
    MODULE: Solana Basis Strategy Backtester (Production Grade)
    PURPOSE: Institutional-grade simulation with real Sharpe Ratio and state consistency.
"""
import json
import logging
import random
import math
import time
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Optional

# Käytetään parannettuja ja integroituja moduuleita
from solana_pnl_tracker_improved import SolanaPnLTracker
from solana_execution_engine_integrated import SolanaSovereignEngine

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger("Backtester")

@dataclass
class BacktestResult:
    scenario_name: str
    initial_capital: float
    final_equity: float
    total_pnl: float
    roi_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    cycles_completed: int
    successful: bool
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

class SolanaBacktester:
    def __init__(self, initial_capital: float = 1000000.0):
        self.initial_capital = initial_capital
        self.results_file = Path("backtest_results.jsonl")

    def calculate_sharpe(self, returns: List[float]) -> float:
        """Laskee annualisoidun Sharpe-luvun (3 sykliä/päivä)."""
        if len(returns) < 2:
            return 0.0
        avg_return = sum(returns) / len(returns)
        variance = sum((x - avg_return) ** 2 for x in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance)
        if std_dev == 0:
            return 0.0
        # Annualisointikerroin: sqrt(3 sykliä/pv * 365 pv)
        return (avg_return / std_dev) * math.sqrt(1095)

    def generate_scenario(self, days: int, mode: str = "bull") -> List[float]:
        """Generoi rahoitusmaksuja (8h välein)."""
        periods = days * 3
        if mode == "bull":
            return [random.uniform(0.0001, 0.0004) for _ in range(periods)]
        if mode == "crisis":
            return [random.uniform(-0.001, -0.0005) for _ in range(periods)]
        return [random.uniform(-0.0001, 0.0002) for _ in range(periods)]

    def run_backtest(self, funding_rates: List[float], scenario_name: str) -> BacktestResult:
        logger.info(f"--- Käynnistetään testi: {scenario_name} ---")
        
        # Luodaan tuore moottori testikohtaisesti
        engine = SolanaSovereignEngine(self.initial_capital)
        if not engine.initialize_vault_session():
            raise RuntimeError("Moottorin alustus epäonnistui.")

        # Simuloidaan ajan kuluminen APY-laskentaa varten
        # Jokainen sykli vastaa 8 tuntia
        simulated_days = len(funding_rates) / 3
        engine.tracker.start_time = time.time() - (simulated_days * 86400)

        periodic_returns = []
        peak_equity = self.initial_capital
        max_dd = 0.0

        for rate in funding_rates:
            prev_equity = engine.current_equity
            
            # Lasketaan uusi salkun arvo
            pnl = prev_equity * rate
            slippage = prev_equity * random.uniform(-0.00003, 0.00003)
            fee = prev_equity * -0.00001
            
            new_equity = prev_equity + pnl + slippage + fee
            
            # Päivitetään moottori absoluuttisella arvolla
            if not engine.execute_cycle(new_equity):
                logger.warning("Syklit keskeytyivät riskienhallinnan takia.")
                break
            
            # Kerätään dataa metriikoita varten
            current_ret = (engine.current_equity / prev_equity) - 1
            periodic_returns.append(current_ret)
            
            if engine.current_equity > peak_equity:
                peak_equity = engine.current_equity
            dd = ((engine.current_equity - peak_equity) / peak_equity) * 100
            max_dd = min(max_dd, dd)

        metrics = engine.tracker.calculate_metrics()
        result = BacktestResult(
            scenario_name=scenario_name,
            initial_capital=self.initial_capital,
            final_equity=metrics['equity'],
            total_pnl=metrics['pnl_usd'],
            roi_pct=metrics['roi_pct'],
            max_drawdown_pct=max_dd,
            sharpe_ratio=self.calculate_sharpe(periodic_returns),
            cycles_completed=len(periodic_returns),
            successful=engine.is_active
        )
        
        with open(self.results_file, "a") as f:
            f.write(json.dumps(asdict(result)) + "\n")
            
        return result

if __name__ == "__main__":
    tester = SolanaBacktester(1_000_000.0)
    
    # Suoritetaan 30 päivän bull-markkina
    bull_res = tester.run_backtest(tester.generate_scenario(30, "bull"), "Bull Market 30d")
    
    # Suoritetaan 7 päivän kriisi-skenaario
    crisis_res = tester.run_backtest(tester.generate_scenario(7, "crisis"), "Flash Crash 7d")
    
    print("\n" + "="*40)
    print(f"YHTEENVETO: {bull_res.scenario_name}")
    print(f"PnL: ${bull_res.total_pnl:,.2f} | ROI: {bull_res.roi_pct:.2f}% | Sharpe: {bull_res.sharpe_ratio:.2f}")
    print("="*40)
