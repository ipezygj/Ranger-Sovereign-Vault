""" Technical implementation for Hummingbot Gateway V2.1.
    MODULE: Circuit Breakers (Production Grade)
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger("CircuitBreaker")

class CircuitBreakerSystem:
    def __init__(self):
        self.max_drawdown_pct = -5.0       # -5% max drawdown
        self.min_funding_rate = -0.001     # -36% APY crisis
        self.max_rpc_failures = 5          # 5 peräkkäistä virhettä
        
        self.is_triggered = False
        self.trigger_reason = None
        
    def check_system_health(self, metrics: Dict) -> tuple[bool, Optional[str]]:
        if self.is_triggered:
            return False, f"BREAKER LOCKED: {self.trigger_reason}"
            
        if 'current_drawdown_pct' in metrics and metrics['current_drawdown_pct'] < self.max_drawdown_pct:
            return False, f"MAX DRAWDOWN BREACH: {metrics['current_drawdown_pct']:.2f}% < {self.max_drawdown_pct}%"
            
        if 'current_funding' in metrics and metrics['current_funding'] < self.min_funding_rate:
            return False, f"FUNDING CRISIS: {metrics['current_funding']:.5f} < {self.min_funding_rate}"
            
        if 'consecutive_rpc_failures' in metrics and metrics['consecutive_rpc_failures'] >= self.max_rpc_failures:
            return False, f"RPC FAILURE: {metrics['consecutive_rpc_failures']} failures"

        return True, None

    def trip_breaker(self, reason: str, engine):
        self.is_triggered = True
        self.trigger_reason = reason
        logger.critical("=" * 60)
        logger.critical("🚨🚨🚨 CIRCUIT BREAKER TRIGGERED 🚨🚨🚨")
        logger.critical(f"REASON: {reason}")
        logger.critical("=" * 60)
        
        try:
            engine.adapter.close_all_positions()
            engine.current_position_size = 0.0
            engine.is_active = False
            engine.tracker.log_snapshot()
            logger.critical("SYSTEM LOCKED - Manual intervention required.")
        except Exception as e:
            logger.critical(f"Emergency shutdown error: {e}")
            engine.is_active = False
