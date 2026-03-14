""" Technical implementation for Hummingbot Gateway V2.1.
    MODULE: Adaptive Funding Strategy (Ranger Protocol)
    PURPOSE: Dynamic position sizing based on funding regime.
"""
import logging
from enum import Enum
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger("AdaptiveFunding")

class FundingRegime(Enum):
    OPTIMAL = "optimal"      # >15 bps/8h (~20% APY)
    POSITIVE = "positive"    # 5-15 bps
    MARGINAL = "marginal"    # 1-5 bps (Cover costs only)
    NEGATIVE = "negative"    # <1 bps (Exit)

class AdaptiveFundingStrategy:
    def __init__(self, max_capital: float):
        self.max_capital = max_capital
        self.TOTAL_COST_DECIMAL = 0.00004 # 4 bps round-trip cost
        self.history = deque(maxlen=20)
        
    def analyze_and_size(self, current_rate: float, current_equity: float) -> float:
        """ 
        Analysoi fundingin ja palauttaa optimaalisen target-position ($).
        """
        self.history.append(current_rate)
        
        # 1. Regiimin tunnistus
        if current_rate >= 0.00015:
            regime = FundingRegime.OPTIMAL
            multiplier = 0.98 # 98% käyttöaste
        elif current_rate >= 0.00005:
            regime = FundingRegime.POSITIVE
            multiplier = 0.75 # 75% käyttöaste
        elif current_rate > self.TOTAL_COST_DECIMAL:
            regime = FundingRegime.MARGINAL
            multiplier = 0.30 # 30% käyttöaste (minimoi riski, kata kulut)
        else:
            regime = FundingRegime.NEGATIVE
            multiplier = 0.0  # FLAT - Ei kannata treidata
            
        target_position = current_equity * multiplier
        
        logger.info(f"FUNDING REGIME: {regime.value.upper()} | Rate: {current_rate:.5f} | Target Size: ${target_position:,.0f}")
        return target_position
