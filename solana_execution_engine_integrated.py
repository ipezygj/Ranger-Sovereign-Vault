""" Technical implementation for Hummingbot Gateway V2.1.
    MODULE: Solana Sovereign Engine (PRODUCTION 9.0/10)
"""
import logging
import time
from adaptive_funding_strategy import AdaptiveFundingStrategy
from risk_manager import RiskManager
from solana_pnl_tracker_improved import SolanaPnLTracker
from drift_basis_adapter import DriftBasisAdapter
from liquidity_aware_twap import LiquidityAwareTWAP
from circuit_breakers import CircuitBreakerSystem

logger = logging.getLogger("SovereignEngine")

class SolanaSovereignEngine:
    def __init__(self, initial_capital: float = 1000000.0):
        self.tracker = SolanaPnLTracker(initial_capital)
        self.risk_mgr = RiskManager()
        self.funding_strategy = AdaptiveFundingStrategy(initial_capital)
        self.adapter = DriftBasisAdapter()
        self.twap_executor = LiquidityAwareTWAP(self.adapter)
        self.circuit_breaker = CircuitBreakerSystem()
        
        self.is_active = False
        self.current_position_size = 0.0
        self.TWAP_THRESHOLD_USD = 100000.0
        self.consecutive_rpc_failures = 0

    @property
    def current_equity(self) -> float:
        return self.tracker.current_equity

    def initialize_vault_session(self) -> bool:
        self.is_active = True
        logger.info(f"SESSION START: Drift-V2 | Equity: ${self.current_equity:,.2f}")
        return True

    def execute_cycle(self, new_equity: float, current_funding_rate: float = 0.0001) -> bool:
        if not self.is_active: return False

        self.tracker.update_equity(new_equity)
        metrics = self.tracker.calculate_metrics()

        # 1. CIRCUIT BREAKER
        breaker_metrics = {
            'current_drawdown_pct': metrics['drawdown_pct'],
            'current_funding': current_funding_rate,
            'consecutive_rpc_failures': self.consecutive_rpc_failures
        }
        is_healthy, breaker_reason = self.circuit_breaker.check_system_health(breaker_metrics)
        
        if not is_healthy:
            self.circuit_breaker.trip_breaker(breaker_reason, self)
            return False

        # 2. RISK MANAGER
        is_safe, reason = self.risk_mgr.check_trade_safety(
            capital=self.current_equity,
            current_exposure=self.current_position_size,
            predicted_funding=current_funding_rate
        )
        if not is_safe:
            logger.warning(f"Safety Pause: {reason}")
            return True

        # 3. ADAPTIVE SIZING & EXECUTION
        target_position = self.funding_strategy.analyze_and_size(current_funding_rate, self.current_equity)
        
        if target_position != self.current_position_size:
            delta = abs(target_position - self.current_position_size)
            if delta > self.TWAP_THRESHOLD_USD:
                logger.info(f"Large Adjustment (${delta:,.0f}) -> Routing to TWAP")
                self.twap_executor.execute_twap_sync(target_position, self.current_position_size)
            else:
                self.adapter.execute_delta_neutral_open(target_position)
            
            self.current_position_size = target_position
            self.consecutive_rpc_failures = 0

        return True

    def emergency_shutdown(self, reason: str = "Manual"):
        """ Hätäpysäytys. Suoritetaan kun Circuit Breaker laukeaa tai käyttäjä keskeyttää. """
        logger.critical(f"EMERGENCY SHUTDOWN INITIATED. Reason: {reason}")
        try:
            self.adapter.close_all_positions()
            self.current_position_size = 0.0
            self.is_active = False
            self.tracker.log_snapshot()
        except Exception as e:
            logger.critical(f"Shutdown error: {e}")
            self.is_active = False

    def get_status(self) -> dict:
        """ Palauttaa täyden tilannekuvan Daemonia ja raportointia varten. """
        m = self.tracker.calculate_metrics()
        return {
            'equity': m['equity'],
            'pnl': m['pnl_usd'],
            'roi_pct': m['roi_pct'],
            'drawdown_pct': m['drawdown_pct'],
            'position_size': self.current_position_size,
            'position_pct': (self.current_position_size / self.current_equity) * 100 if self.current_equity > 0 else 0
        }
