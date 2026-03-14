import logging
from typing import Optional
from solana_pnl_tracker_improved import SolanaPnLTracker
from risk_manager import RiskManager
from adaptive_funding_strategy import AdaptiveFundingStrategy

logger = logging.getLogger("SovereignEngine")

class SolanaSovereignEngine:
    def __init__(self, initial_capital: float = 1000000.0):
        self.tracker = SolanaPnLTracker(initial_capital)
        self.risk_mgr = RiskManager()
        self.funding_strategy = AdaptiveFundingStrategy(initial_capital)
        self.is_active = False

    @property
    def current_equity(self) -> float:
        return self.tracker.current_equity

    def initialize_vault_session(self) -> bool:
        self.is_active = True
        return True

    def execute_cycle(self, new_equity: float) -> bool:
        if not self.is_active:
            return False
        self.tracker.update_equity(new_equity)
        return True
