""" Technical implementation for Hummingbot Gateway V2.1.
    MODULE: Solana Sovereign Engine (Integrated & TWAP Ready)
"""
import logging
from typing import Optional

from adaptive_funding_strategy import AdaptiveFundingStrategy
from risk_manager import RiskManager
from solana_pnl_tracker_improved import SolanaPnLTracker
from drift_basis_adapter import DriftBasisAdapter
from liquidity_aware_twap import LiquidityAwareTWAP

logger = logging.getLogger("SovereignEngine")

class SolanaSovereignEngine:
    def __init__(self, initial_capital: float = 1000000.0):
        self.tracker = SolanaPnLTracker(initial_capital)
        self.risk_mgr = RiskManager()
        self.funding_strategy = AdaptiveFundingStrategy(initial_capital)
        self.adapter = DriftBasisAdapter()
        self.twap_executor = LiquidityAwareTWAP(self.adapter)
        
        self.is_active = False
        self.current_position_size = 0.0
        self.TWAP_THRESHOLD_USD = 100000.0 # Yli 00k muutokset TWAPilla

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

        is_safe, reason = self.risk_mgr.check_trade_safety(
            capital=self.current_equity,
            current_exposure=self.current_position_size,
            predicted_funding=current_funding_rate
        )

        if not is_safe:
            logger.warning(f"Safety Halt: {reason}")
            return False

        target_position = self.funding_strategy.analyze_and_size(
            current_rate=current_funding_rate,
            current_equity=self.current_equity
        )

        # Suoritetaan position muutos, jos tarpeen
        if target_position != self.current_position_size:
            delta = abs(target_position - self.current_position_size)
            
            if delta > self.TWAP_THRESHOLD_USD:
                logger.info(f"Large adjustment (${delta:,.0f}). Routing to TWAP Executor.")
                self.twap_executor.execute_twap_sync(
                    target_size=target_position, 
                    current_size=self.current_position_size
                )
            else:
                logger.debug(f"Small adjustment (${delta:,.0f}). Direct execution.")
                self.adapter.execute_delta_neutral_open(target_position)
                
            self.current_position_size = target_position

        return True
