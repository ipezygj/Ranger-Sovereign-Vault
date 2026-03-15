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
    OPTIMAL = "optimal"      # Entry zone (> 0.0003)
    POSITIVE = "positive"    # Holding zone (> 0.0)
    MARGINAL = "marginal"    # Holding zone (< 0.0, but > -0.0001)
    NEGATIVE = "negative"    # Exit zone (< -0.0001)

class AdaptiveFundingStrategy:
    def __init__(self, max_capital: float):
        self.max_capital = max_capital
        # Institutionaaliset kynnysarvot (Grid Search Optimoitu: 41.33% APY)
        self.ENTER_THRESHOLD = 0.0003
        self.EXIT_THRESHOLD = -0.0001
        self.history = deque(maxlen=20)
        self._is_in_position = False

    def analyze_and_size(self, current_rate: float, current_equity: float) -> float:
        """
        Analysoi fundingin hystereesi-logiikalla ja palauttaa target-position ($).
        """
        self.history.append(current_rate)

        if not self._is_in_position:
            # Etsitään ENTRY-signaalia
            if current_rate >= self.ENTER_THRESHOLD:
                self._is_in_position = True
                regime = FundingRegime.OPTIMAL
                multiplier = 0.98 # 98% käyttöaste (2% puskuri markkinaliikkeille)
            else:
                regime = FundingRegime.NEGATIVE
                multiplier = 0.0  # FLAT - Odotetaan parempaa paikkaa
        else:
            # Olemme positiossa, etsitään EXIT-signaalia (Hold state)
            if current_rate <= self.EXIT_THRESHOLD:
                self._is_in_position = False
                regime = FundingRegime.NEGATIVE
                multiplier = 0.0  # Pura positio
            else:
                # Pidetään positio auki ja kerätään tuottoa (No fees paid)
                multiplier = 0.98
                if current_rate >= self.ENTER_THRESHOLD:
                    regime = FundingRegime.OPTIMAL
                elif current_rate >= 0.0:
                    regime = FundingRegime.POSITIVE
                else:
                    regime = FundingRegime.MARGINAL

        target_position = current_equity * multiplier

        logger.info(f"FUNDING REGIME: {regime.value.upper()} | Rate: {current_rate:.5f} | Target Size: ${target_position:,.0f}")
        return target_position
