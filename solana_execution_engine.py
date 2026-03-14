""" Technical implementation for Hummingbot Gateway V2.1.
    MODULE: Solana Sovereign Execution Engine (Ranger Protocol)
    INTEGRATION: Risk Manager + PnL Tracker + Drift Adapter
    STATUS: Production Ready | Fixed State Consistency
"""
import logging
import time
from typing import Optional, Dict, Any
import solana_config as cfg
from risk_manager import RiskManager
from drift_basis_adapter import DriftBasisAdapter
from solana_pnl_tracker import SolanaPnLTracker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SovereignEngine")

class SolanaSovereignEngine:
    EXPOSURE_BUFFER = 0.02  # 2% turvamarginaali
    MAX_ALLOWED_DRAWDOWN = -5.0  # Hätäpysäytys -5% kohdalla
    DEFAULT_SLIPPAGE = 0.05
    CYCLE_INTERVAL = 300  # 5 minuuttia syklien välillä

    def __init__(self, initial_capital: float = 1000000.0):
        if initial_capital <= 0:
            raise ValueError(f"Initial capital must be positive, got {initial_capital}")
        
        self.risk_mgr = RiskManager()
        self.adapter = DriftBasisAdapter()
        self.tracker = SolanaPnLTracker(initial_capital)
        
        self.is_active = False
        self.cycle_count = 0
        self.last_cycle_time = 0.0
        
        logger.info(f"Engine initialized with ${initial_capital:,.2f}")

    @property
    def current_equity(self) -> float:
        """ Single Source of Truth: Pääoma haetaan aina träkkeriltä. """
        return self.tracker.current_equity

    def initialize_vault_session(self) -> bool:
        """ Alustaa istunnon ja suorittaa turvatarkistukset. """
        try:
            safe, message = self.risk_mgr.check_trade_safety(self.current_equity, 0, self.DEFAULT_SLIPPAGE)
            if not safe:
                logger.critical(f"INITIALIZATION ABORTED: {message}")
                return False
            
            self.is_active = True
            self.last_cycle_time = time.time()
            logger.info(f"SESSION START: {cfg.DEX_PROTOCOL} | Equity: ${self.current_equity:,.2f}")
            self.tracker.log_snapshot()
            return True
        except Exception as e:
            logger.exception(f"Session initialization failed: {e}")
            return False

    def execute_cycle(self, new_equity: Optional[float] = None) -> bool:
        """ Suorittaa yhden kaupankäyntisyklin: päivitys, analyysi, rebalance. """
        if not self.is_active:
            return False
        
        self.cycle_count += 1
        cycle_start = time.time()
        
        try:
            # 1. PÄIVITETÄÄN PÄÄOMA (Fetch from Drift in production)
            if new_equity is not None:
                self.tracker.update_equity(new_equity)
            
            metrics = self.tracker.calculate_metrics()
            
            # 2. RISKIANALYYSI - Drawdown Guardian
            if metrics['drawdown_pct'] < self.MAX_ALLOWED_DRAWDOWN:
                logger.error(f"CRITICAL DRAWDOWN: {metrics['drawdown_pct']}%")
                self.emergency_shutdown()
                return False
            
            # 3. POSITIOIDEN TASAPAINOTUS
            target_size = self.current_equity * (1 - self.EXPOSURE_BUFFER)
            self.adapter.execute_delta_neutral_open(target_size)
            
            self.last_cycle_time = cycle_start
            logger.info(f"Cycle {self.cycle_count} Complete | APY: {metrics['estimated_apy']}%")
            return True
            
        except Exception as e:
            logger.exception(f"Execution cycle failed: {e}")
            return False

    def emergency_shutdown(self):
        """ Sulkee kaikki positiot ja lukitsee järjestelmän. """
        logger.critical("EMERGENCY SHUTDOWN INITIATED")
        try:
            self.adapter.execute_delta_neutral_open(0)
            self.is_active = False
            print(self.tracker.get_summary())
            logger.info("System locked for safety.")
        except Exception as e:
            logger.exception(f"Shutdown error: {e}")
            self.is_active = False

if __name__ == "__main__":
    engine = SolanaSovereignEngine(1_000_000.0)
    if engine.initialize_vault_session():
        # Simuloitu ajo
        engine.execute_cycle(1_000_250.0)
        engine.execute_cycle(1_000_500.0)
