"""
drift_basis_adapter.py â€” Production Drift Protocol v2 Adapter
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Ranger Sovereign Vault Â· Solana Build-a-Bear Hackathon (Main Track)

Replaces the mock adapter with real on-chain integration via `driftpy`.
Provides four capabilities consumed by the vault's execution layer:

  1. L2 Orderbook Reconstruction  â†’ liquidity_aware_twap.py
  2. Funding Rate Observation     â†’ adaptive_funding_strategy.py
  3. Delta-Neutral Positions      â†’ solana_execution_engine_integrated.py
  4. Account Health Telemetry     â†’ circuit_breakers.py

Dependencies:
  pip install driftpy solders anchorpy solana aiohttp

Architecture:

  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
  â”‚     run_ranger.py        â”‚  Production daemon
  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
               â”‚ await
  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
  â”‚   DriftBasisAdapter      â”‚  THIS MODULE
  â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â” â”‚
  â”‚  â”‚ DriftClient (driftpy)â”‚ â”‚  On-chain reads + order placement
  â”‚  â”‚ DLOB â†’ L2Snapshot    â”‚ â”‚  Orderbook reconstruction
  â”‚  â”‚ Retry + Backoff      â”‚ â”‚  RPC resilience layer
  â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜ â”‚
  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
               â”‚
  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
  â”‚  Drift v2 Program        â”‚  Solana Mainnet / Devnet
  â”‚  Pyth Oracle Network     â”‚
  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Drift Protocol v2 SDK (driftpy)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
from driftpy.drift_client import DriftClient
from driftpy.account_subscription_config import AccountSubscriptionConfig
from driftpy.types import (
    MarketType,
    OrderType,
    OrderParams,
    PositionDirection,
    OrderTriggerCondition,
)
from driftpy.constants.numeric_constants import (
    BASE_PRECISION,
    PRICE_PRECISION,
    QUOTE_PRECISION,
)
from driftpy.math.perp_position import calculate_entry_price
from driftpy.dlob.dlob_client import DLOBClient
from driftpy.keypair import load_keypair

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Solana
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed

logger = logging.getLogger("ranger.drift_adapter")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Section 1 â€” Data Models
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class Side(str, Enum):
    """Order side, used by TWAP engine for depth queries."""
    BID = "bid"
    ASK = "ask"


@dataclass(frozen=True)
class L2Level:
    """Single price/size level on one side of the book."""
    price: float   # USD
    size: float    # base asset units (e.g. SOL)


@dataclass(frozen=True)
class L2Snapshot:
    """
    Typed L2 orderbook snapshot reconstructed from Drift's DLOB.

    Consumed by liquidity_aware_twap.py to determine:
      - Per-slice size (fraction of available depth)
      - Whether spread is within tolerance
      - Whether sufficient depth exists to execute at all
    """
    bids: List[L2Level]          # Sorted descending by price
    asks: List[L2Level]          # Sorted ascending by price
    slot: int                    # Solana slot at observation time
    oracle_price: float          # Pyth oracle price at same slot
    timestamp_ms: int            # Unix ms for logging/staleness

    # â”€â”€ Derived properties consumed by TWAP + circuit breakers â”€â”€

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> Optional[float]:
        if self.best_bid is not None and self.best_ask is not None:
            return (self.best_bid + self.best_ask) / 2.0
        return None

    @property
    def spread_bps(self) -> Optional[float]:
        """Spread in basis points. Used by TWAP to gate slice execution."""
        mid = self.mid_price
        if mid and mid > 0 and self.best_bid and self.best_ask:
            return ((self.best_ask - self.best_bid) / mid) * 10_000
        return None

    def cumulative_depth(self, side: Side, max_bps_from_mid: float) -> float:
        """
        Total base asset available within `max_bps_from_mid` of mid price.

        This is the core method the TWAP engine uses to size each slice:
          available = snapshot.cumulative_depth(Side.ASK, slippage_budget_bps)
          slice_size = min(target_slice, available * 0.30)  # â‰¤30% of depth
        """
        mid = self.mid_price
        if mid is None or mid <= 0:
            return 0.0

        threshold = mid * (max_bps_from_mid / 10_000)
        levels = self.bids if side == Side.BID else self.asks
        total = 0.0
        for level in levels:
            if abs(level.price - mid) <= threshold:
                total += level.size
            else:
                break  # levels are sorted, no need to continue
        return total


@dataclass(frozen=True)
class FundingSnapshot:
    """
    Funding rate observation consumed by adaptive_funding_strategy.py.

    The 5-regime classifier uses current_rate_annualised and
    predicted_rate_annualised to determine regime transitions.
    """
    market_index: int
    current_rate_annualised: float      # Last settled, annualised %
    predicted_rate_annualised: float    # Predicted from TWAP spread
    twap_spread_bps: float             # Mark vs oracle TWAP in bps
    seconds_until_next: float          # Countdown to next settlement
    slot: int


@dataclass
class BasisPosition:
    """
    Tracks a live delta-neutral basis position (spot long + perp short).

    Created by open_basis_position(), consumed by close_basis_position()
    and by circuit_breakers.py for delta monitoring.
    """
    perp_market_index: int
    spot_market_index: int
    base_amount: float              # In base asset units
    spot_entry_price: float         # Effective fill price
    perp_entry_price: float         # Effective fill price
    direction: str = "short_perp"   # Cash-and-carry convention
    opened_at_ts: float = field(default_factory=time.time)
    spot_order_id: Optional[int] = None
    perp_order_id: Optional[int] = None

    @property
    def entry_basis_bps(self) -> float:
        """Basis captured at entry. Positive = profitable carry."""
        if self.spot_entry_price <= 0:
            return 0.0
        return (
            (self.perp_entry_price - self.spot_entry_price)
            / self.spot_entry_price
        ) * 10_000

    @property
    def hold_duration_s(self) -> float:
        return time.time() - self.opened_at_ts


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Section 2 â€” Configuration
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@dataclass
class DriftAdapterConfig:
    """
    Adapter configuration. Injected by run_ranger.py from env/config file.
    Every field has a safe default for devnet testing.
    """
    # â”€â”€ Connection â”€â”€
    rpc_url: str = "https://api.mainnet-beta.solana.com"
    drift_env: str = "mainnet-beta"       # "devnet" for testing
    subaccount_id: int = 0
    dlob_server_url: str = "https://dlob.drift.trade"

    # â”€â”€ Orderbook â”€â”€
    default_l2_depth: int = 20            # Levels per side
    max_slippage_bps: float = 15.0        # Per-slice hard limit
    min_depth_usd: float = 50_000.0       # L4 circuit breaker threshold

    # â”€â”€ Retry policy â”€â”€
    max_retries: int = 3
    base_retry_delay_s: float = 0.4       # Exponential backoff base

    # â”€â”€ Jito MEV protection (optional) â”€â”€
    jito_block_engine_url: Optional[str] = None
    jito_tip_lamports: int = 10_000


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Section 3 â€” DriftBasisAdapter (Core Class)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class DriftBasisAdapter:
    """
    Production bridge between Ranger Vault and Drift Protocol v2.

    Lifecycle (managed by run_ranger.py):
        adapter = DriftBasisAdapter(config, "/path/to/keypair.json")
        await adapter.initialize()
        # ... main loop ...
        await adapter.shutdown()

    Concurrency model:
        Single async event loop. All methods are coroutines.
        No internal locking â€” caller (run_ranger daemon) serialises access.
    """

    def __init__(self, config: DriftAdapterConfig, keypair_path: str) -> None:
        self._config = config
        self._keypair = load_keypair(keypair_path)
        self._rpc: Optional[AsyncClient] = None
        self._drift: Optional[DriftClient] = None
        self._dlob: Optional[DLOBClient] = None
        self._ready = False

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # 3.1 â€” Lifecycle
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def initialize(self) -> None:
        """
        Bootstrap sequence:
          1. Open Solana RPC connection
          2. Subscribe DriftClient via websocket (real-time account state)
          3. Connect DLOB client for L2 orderbook reconstruction
          4. Validate on-chain user account exists and has collateral
        """
        if self._ready:
            logger.warning("Already initialized, skipping")
            return

        logger.info("=" * 60)
        logger.info("  Drift Basis Adapter â€” Initializing")
        logger.info("=" * 60)

        # Step 1: Solana RPC
        self._rpc = AsyncClient(self._config.rpc_url, commitment=Confirmed)
        logger.info(f"  RPC endpoint : {self._config.rpc_url}")

        # Step 2: DriftClient with websocket subscription
        #   Websocket keeps local cache of all relevant Drift accounts
        #   in sync â€” no polling needed for reads.
        self._drift = DriftClient(
            self._rpc,
            self._keypair,
            env=self._config.drift_env,
            account_subscription=AccountSubscriptionConfig("websocket"),
        )
        await self._drift.subscribe()
        authority = self._drift.authority
        logger.info(f"  DriftClient  : subscribed (authority={authority})")

        # Step 3: DLOB client for orderbook
        self._dlob = DLOBClient(
            url=self._config.dlob_server_url,
            drift_client=self._drift,
        )
        logger.info(f"  DLOB server  : {self._config.dlob_server_url}")

        # Step 4: Validate account
        user = self._drift.get_user()
        collateral = float(user.get_total_collateral()) / QUOTE_PRECISION
        free = float(user.get_free_collateral()) / QUOTE_PRECISION
        logger.info(f"  Collateral   : ${collateral:,.2f} (free: ${free:,.2f})")
        logger.info(f"  Subaccount   : {self._config.subaccount_id}")
        logger.info("=" * 60)
        logger.info("  Adapter READY")
        logger.info("=" * 60)

        self._ready = True

    async def shutdown(self) -> None:
        """Graceful teardown: unsubscribe websocket, close RPC."""
        logger.info("Drift Adapter shutting down...")
        if self._drift:
            await self._drift.unsubscribe()
        if self._rpc:
            await self._rpc.close()
        self._ready = False
        logger.info("Drift Adapter shut down cleanly.")

    def _assert_ready(self) -> None:
        if not self._ready:
            raise RuntimeError(
                "DriftBasisAdapter not initialized. "
                "Call `await adapter.initialize()` first."
            )

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # 3.2 â€” L2 Orderbook (consumed by liquidity_aware_twap.py)
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def get_perp_l2(
        self,
        market_index: int,
        depth: Optional[int] = None,
    ) -> L2Snapshot:
        """
        Reconstruct the L2 limit-order book for a Drift perp market
        from on-chain DLOB state.

        The TWAP engine calls this before every slice to:
          1. Check spread is within tolerance
          2. Measure cumulative depth within slippage budget
          3. Size the slice as a fraction of available liquidity

        Args:
            market_index: Drift perp market index
                          (0 = SOL-PERP, 1 = BTC-PERP, 2 = ETH-PERP)
            depth: Number of levels per side (default: config value)

        Returns:
            L2Snapshot â€” typed, immutable orderbook with helper methods.
        """
        self._assert_ready()
        depth = depth or self._config.default_l2_depth

        # Fetch the full DLOB (decentralised limit-order book)
        dlob = await self._dlob.get_dlob()
        slot = self._drift.get_state_account().slot

        # Oracle price from Drift's cached Pyth feed
        oracle_data = self._drift.get_oracle_price_data_for_perp_market(
            market_index
        )
        oracle_price = float(oracle_data.price) / PRICE_PRECISION

        # Reconstruct L2 from DLOB
        raw_l2 = dlob.get_l2(
            market_index=market_index,
            market_type=MarketType.Perp(),
            slot=slot,
            oracle_price_data=oracle_data,
            depth=depth,
        )

        # Convert to typed L2Levels
        bids = [
            L2Level(
                price=float(lvl.price) / PRICE_PRECISION,
                size=float(lvl.size) / BASE_PRECISION,
            )
            for lvl in raw_l2.bids[:depth]
        ]
        asks = [
            L2Level(
                price=float(lvl.price) / PRICE_PRECISION,
                size=float(lvl.size) / BASE_PRECISION,
            )
            for lvl in raw_l2.asks[:depth]
        ]

        snapshot = L2Snapshot(
            bids=bids,
            asks=asks,
            slot=slot,
            oracle_price=oracle_price,
            timestamp_ms=int(time.time() * 1000),
        )

        logger.debug(
            f"L2 perp[{market_index}] | "
            f"bid={snapshot.best_bid} ask={snapshot.best_ask} "
            f"spread={snapshot.spread_bps:.1f}bps "
            f"oracle=${oracle_price:.4f} "
            f"levels={len(bids)}/{len(asks)}"
        )
        return snapshot

    async def get_spot_l2(
        self,
        market_index: int,
        depth: Optional[int] = None,
    ) -> L2Snapshot:
        """Same as get_perp_l2 but for Drift spot markets."""
        self._assert_ready()
        depth = depth or self._config.default_l2_depth

        dlob = await self._dlob.get_dlob()
        slot = self._drift.get_state_account().slot
        oracle_data = self._drift.get_oracle_price_data_for_spot_market(
            market_index
        )
        oracle_price = float(oracle_data.price) / PRICE_PRECISION

        raw_l2 = dlob.get_l2(
            market_index=market_index,
            market_type=MarketType.Spot(),
            slot=slot,
            oracle_price_data=oracle_data,
            depth=depth,
        )

        bids = [
            L2Level(
                price=float(lvl.price) / PRICE_PRECISION,
                size=float(lvl.size) / BASE_PRECISION,
            )
            for lvl in raw_l2.bids[:depth]
        ]
        asks = [
            L2Level(
                price=float(lvl.price) / PRICE_PRECISION,
                size=float(lvl.size) / BASE_PRECISION,
            )
            for lvl in raw_l2.asks[:depth]
        ]

        return L2Snapshot(
            bids=bids,
            asks=asks,
            slot=slot,
            oracle_price=oracle_price,
            timestamp_ms=int(time.time() * 1000),
        )

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # 3.3 â€” Funding Rate (consumed by adaptive_funding_strategy.py)
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def get_funding_snapshot(
        self,
        market_index: int,
    ) -> FundingSnapshot:
        """
        Observe current + predicted funding rate for the 5-regime classifier.

        The adaptive strategy uses:
          - current_rate_annualised:   regime classification
          - predicted_rate_annualised: anticipatory regime transitions
          - twap_spread_bps:           confirmation signal
          - seconds_until_next:        entry timing optimisation

        Drift settles funding every hour (3600s). Rates are stored as
        per-period values; we annualise by multiplying by 8760.
        """
        self._assert_ready()

        perp_market = self._drift.get_perp_market_account(market_index)
        slot = self._drift.get_state_account().slot
        amm = perp_market.amm

        # â”€â”€ Current (last settled) funding rate â”€â”€
        last_funding_raw = float(amm.last_funding_rate) / PRICE_PRECISION
        current_annualised = last_funding_raw * 8760  # hourly â†’ annual

        # â”€â”€ Predicted funding from mark-oracle TWAP divergence â”€â”€
        mark_twap = float(amm.last_mark_price_twap) / PRICE_PRECISION
        oracle_twap = float(
            amm.historical_oracle_data.last_oracle_price_twap
        ) / PRICE_PRECISION

        twap_spread = 0.0
        if oracle_twap > 0:
            twap_spread = (mark_twap - oracle_twap) / oracle_twap

        predicted_annualised = twap_spread * 8760

        # â”€â”€ Time until next settlement â”€â”€
        funding_period = int(amm.funding_period)  # seconds (typically 3600)
        last_ts = int(amm.last_funding_rate_ts)
        now_ts = int(time.time())
        secs_until_next = max(0, (last_ts + funding_period) - now_ts)

        snapshot = FundingSnapshot(
            market_index=market_index,
            current_rate_annualised=current_annualised,
            predicted_rate_annualised=predicted_annualised,
            twap_spread_bps=twap_spread * 10_000,
            seconds_until_next=float(secs_until_next),
            slot=slot,
        )

        logger.info(
            f"Funding[{market_index}] | "
            f"current={current_annualised:+.2f}% ann | "
            f"predicted={predicted_annualised:+.2f}% ann | "
            f"twap_spread={twap_spread * 10_000:+.1f}bps | "
            f"next_in={secs_until_next}s"
        )
        return snapshot

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # 3.4 â€” Delta-Neutral Position Lifecycle
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def open_basis_position(
        self,
        perp_market_index: int,
        spot_market_index: int,
        base_amount: float,
        max_slippage_bps: Optional[float] = None,
    ) -> BasisPosition:
        """
        Execute a delta-neutral basis trade:
          LEG 1: Buy spot   (go long underlying)
          LEG 2: Short perp (hedge delta, capture funding)
          â†’ Net delta â‰ˆ 0 | Captures: funding rate + basis spread

        The TWAP engine decomposes a large target into multiple slices.
        Each slice calls this method with a fractional base_amount.

        Both legs use Immediate-or-Cancel (IOC) limit orders to prevent
        stale resting exposure. If either leg fails, the caller
        (run_ranger.py) detects the delta imbalance within one cycle
        and the circuit breaker triggers rebalancing.

        Args:
            perp_market_index: e.g. 0 (SOL-PERP)
            spot_market_index: e.g. 1 (SOL)
            base_amount: Size in base units (e.g. 50.0 = 50 SOL)
            max_slippage_bps: Override per-slice slippage limit

        Returns:
            BasisPosition record tracking the opened position.

        Raises:
            ValueError: Insufficient L2 depth for requested size.
            RuntimeError: Both retry attempts exhausted on order placement.
        """
        self._assert_ready()
        slippage = max_slippage_bps or self._config.max_slippage_bps

        # â”€â”€ Pre-flight: verify depth â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        l2 = await self.get_perp_l2(perp_market_index)
        if l2.mid_price is None:
            raise ValueError(
                f"Perp market {perp_market_index}: orderbook empty, "
                f"cannot determine mid price"
            )

        ask_depth = l2.cumulative_depth(Side.ASK, slippage)
        if ask_depth < base_amount:
            raise ValueError(
                f"Insufficient ask-side depth: "
                f"need {base_amount:.4f}, "
                f"available {ask_depth:.4f} within {slippage}bps"
            )

        # â”€â”€ Compute limit prices â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        oracle = l2.oracle_price
        # Spot buy: accept up to oracle + slippage
        spot_limit = oracle * (1 + slippage / 10_000)
        # Perp short: accept down to oracle - slippage
        perp_limit = oracle * (1 - slippage / 10_000)

        base_raw = int(base_amount * BASE_PRECISION)

        # â”€â”€ LEG 1: Spot Buy â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        logger.info(
            f"BASIS OPEN leg1 | spot_buy "
            f"{base_amount:.4f} @ limit ${spot_limit:.4f}"
        )
        spot_params = OrderParams(
            order_type=OrderType.Limit(),
            market_index=spot_market_index,
            market_type=MarketType.Spot(),
            direction=PositionDirection.Long(),
            base_asset_amount=base_raw,
            price=int(spot_limit * PRICE_PRECISION),
            reduce_only=False,
            post_only=False,
            immediate_or_cancel=True,
            trigger_condition=OrderTriggerCondition.Above(),
            trigger_price=0,
        )
        spot_tx = await self._place_order_with_retry(spot_params)
        logger.info(f"  â†’ spot tx: {spot_tx}")

        # â”€â”€ LEG 2: Perp Short â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        logger.info(
            f"BASIS OPEN leg2 | perp_short "
            f"{base_amount:.4f} @ limit ${perp_limit:.4f}"
        )
        perp_params = OrderParams(
            order_type=OrderType.Limit(),
            market_index=perp_market_index,
            market_type=MarketType.Perp(),
            direction=PositionDirection.Short(),
            base_asset_amount=base_raw,
            price=int(perp_limit * PRICE_PRECISION),
            reduce_only=False,
            post_only=False,
            immediate_or_cancel=True,
            trigger_condition=OrderTriggerCondition.Above(),
            trigger_price=0,
        )
        perp_tx = await self._place_order_with_retry(perp_params)
        logger.info(f"  â†’ perp tx: {perp_tx}")

        # â”€â”€ Build position record â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        position = BasisPosition(
            perp_market_index=perp_market_index,
            spot_market_index=spot_market_index,
            base_amount=base_amount,
            spot_entry_price=spot_limit,
            perp_entry_price=perp_limit,
        )

        logger.info(
            f"BASIS OPENED | {base_amount:.4f} base | "
            f"entry_basis={position.entry_basis_bps:+.1f}bps | "
            f"oracle=${oracle:.4f}"
        )
        return position

    async def close_basis_position(
        self,
        position: BasisPosition,
        max_slippage_bps: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Unwind a delta-neutral position:
          LEG 1: Buy-to-cover perp short
          LEG 2: Sell spot long
          â†’ Returns capital to vault, realises PnL

        Returns:
            Dict with tx signatures, hold time, and PnL metadata.
        """
        self._assert_ready()
        slippage = max_slippage_bps or self._config.max_slippage_bps

        oracle_data = self._drift.get_oracle_price_data_for_perp_market(
            position.perp_market_index
        )
        oracle = float(oracle_data.price) / PRICE_PRECISION
        base_raw = int(position.base_amount * BASE_PRECISION)

        # â”€â”€ LEG 1: Close perp (buy to cover) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        perp_close_limit = oracle * (1 + slippage / 10_000)
        perp_params = OrderParams(
            order_type=OrderType.Limit(),
            market_index=position.perp_market_index,
            market_type=MarketType.Perp(),
            direction=PositionDirection.Long(),
            base_asset_amount=base_raw,
            price=int(perp_close_limit * PRICE_PRECISION),
            reduce_only=True,
            post_only=False,
            immediate_or_cancel=True,
            trigger_condition=OrderTriggerCondition.Above(),
            trigger_price=0,
        )
        perp_tx = await self._place_order_with_retry(perp_params)

        # â”€â”€ LEG 2: Sell spot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        spot_close_limit = oracle * (1 - slippage / 10_000)
        spot_params = OrderParams(
            order_type=OrderType.Limit(),
            market_index=position.spot_market_index,
            market_type=MarketType.Spot(),
            direction=PositionDirection.Short(),
            base_asset_amount=base_raw,
            price=int(spot_close_limit * PRICE_PRECISION),
            reduce_only=True,
            post_only=False,
            immediate_or_cancel=True,
            trigger_condition=OrderTriggerCondition.Above(),
            trigger_price=0,
        )
        spot_tx = await self._place_order_with_retry(spot_params)

        result = {
            "perp_tx": perp_tx,
            "spot_tx": spot_tx,
            "base_amount": position.base_amount,
            "hold_duration_s": position.hold_duration_s,
            "entry_basis_bps": position.entry_basis_bps,
            "exit_oracle_price": oracle,
        }

        logger.info(
            f"BASIS CLOSED | held {position.hold_duration_s:.0f}s | "
            f"entry_basis={position.entry_basis_bps:+.1f}bps"
        )
        return result

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # 3.5 â€” Collateral Management
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def deposit_usdc(self, amount: float) -> str:
        """Deposit USDC into Drift subaccount (spot market 0 = USDC)."""
        self._assert_ready()
        raw = int(amount * QUOTE_PRECISION)
        tx = await self._drift.deposit(amount=raw, spot_market_index=0)
        logger.info(f"Deposited ${amount:,.2f} USDC | tx={tx}")
        return str(tx)

    async def withdraw_usdc(self, amount: float) -> str:
        """Withdraw USDC from Drift subaccount."""
        self._assert_ready()
        raw = int(amount * QUOTE_PRECISION)
        tx = await self._drift.withdraw(amount=raw, spot_market_index=0)
        logger.info(f"Withdrew ${amount:,.2f} USDC | tx={tx}")
        return str(tx)

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # 3.6 â€” Account Health (consumed by circuit_breakers.py)
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def get_account_health(self) -> Dict[str, float]:
        """
        Snapshot of account-level risk metrics.

        circuit_breakers.py checks these every daemon cycle:
          - margin_ratio < threshold     â†’ Layer 2 (drawdown gate)
          - free_collateral â‰¤ 0          â†’ Layer 5 (emergency halt)
          - leverage > max               â†’ Layer 1 (position limit)
        """
        self._assert_ready()
        user = self._drift.get_user()

        total_collateral = float(user.get_total_collateral()) / QUOTE_PRECISION
        free_collateral = float(user.get_free_collateral()) / QUOTE_PRECISION
        margin_req = float(user.get_margin_requirement(None)) / QUOTE_PRECISION
        unrealised_pnl = float(user.get_unrealized_pnl(True)) / QUOTE_PRECISION
        leverage = float(user.get_leverage()) / 10_000

        return {
            "total_collateral_usd": total_collateral,
            "free_collateral_usd": free_collateral,
            "margin_requirement_usd": margin_req,
            "unrealised_pnl_usd": unrealised_pnl,
            "leverage_x": leverage,
            "margin_ratio": (
                total_collateral / margin_req if margin_req > 0 else float("inf")
            ),
        }

    async def get_perp_position(self, market_index: int) -> Optional[Dict]:
        """
        Current perp position for delta monitoring.

        Returns None if no open position. Used by circuit breakers
        to verify delta-neutrality invariant after each trade cycle.
        """
        self._assert_ready()
        user = self._drift.get_user()

        try:
            pos = user.get_perp_position(market_index)
        except Exception:
            return None

        if pos is None or pos.base_asset_amount == 0:
            return None

        base = float(pos.base_asset_amount) / BASE_PRECISION
        entry = float(calculate_entry_price(pos)) / PRICE_PRECISION

        return {
            "market_index": market_index,
            "base_amount": base,
            "side": "long" if base > 0 else "short",
            "entry_price": entry,
        }

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # 3.7 â€” Emergency Controls (consumed by circuit_breakers.py)
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def cancel_all_orders(
        self,
        market_index: Optional[int] = None,
        market_type: Optional[MarketType] = None,
    ) -> str:
        """
        Cancel all open orders. Called by Layer 5 emergency halt.

        If market_index and market_type are provided, cancels only
        for that specific market. Otherwise cancels everything.
        """
        self._assert_ready()

        if market_index is not None and market_type is not None:
            tx = await self._drift.cancel_orders(
                market_index=market_index,
                market_type=market_type,
            )
        else:
            tx = await self._drift.cancel_orders()

        logger.warning(f"CANCEL ALL ORDERS | tx={tx}")
        return str(tx)

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # 3.8 â€” Internal: Retry-Aware Order Placement
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _place_order_with_retry(self, params: OrderParams) -> str:
        """
        Place an order with exponential backoff for transient failures.

        Retryable conditions:
          - Blockhash expired (Solana slot advancement)
          - RPC rate limits (429)
          - Temporary unavailability (503)
          - Connection timeouts

        Non-retryable (raises immediately):
          - Insufficient margin
          - Invalid market index
          - Program errors
        """
        last_err: Optional[Exception] = None
        cfg = self._config

        for attempt in range(1, cfg.max_retries + 1):
            try:
                tx_sig = await self._drift.place_order(params)
                return str(tx_sig)

            except Exception as exc:
                last_err = exc
                msg = str(exc).lower()

                retryable_signals = [
                    "blockhash",
                    "timeout",
                    "429",
                    "503",
                    "rate limit",
                    "connection",
                    "slot",
                ]
                is_retryable = any(s in msg for s in retryable_signals)

                if is_retryable and attempt < cfg.max_retries:
                    delay = cfg.base_retry_delay_s * (2 ** (attempt - 1))
                    logger.warning(
                        f"Order attempt {attempt}/{cfg.max_retries} failed "
                        f"(retrying in {delay:.1f}s): {exc}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Order FAILED (non-retryable or attempts exhausted): "
                        f"{exc}"
                    )
                    break

        raise RuntimeError(
            f"Order placement failed after {cfg.max_retries} attempts: "
            f"{last_err}"
        )


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Section 4 â€” CLI Debug Tool
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def _cli_debug(rpc_url: str, keypair_path: str, market: int) -> None:
    """
    Standalone debug tool. Run directly:
      python drift_basis_adapter.py [RPC_URL] [KEYPAIR] [MARKET_INDEX]

    Prints the live L2 orderbook, funding rate, and account health.
    Useful for verifying adapter connectivity before running the vault.
    """
    config = DriftAdapterConfig(rpc_url=rpc_url)
    adapter = DriftBasisAdapter(config, keypair_path)

    try:
        await adapter.initialize()

        # â”€â”€ Orderbook â”€â”€
        l2 = await adapter.get_perp_l2(market, depth=10)
        header = f"  PERP MARKET {market} â€” L2 Orderbook  "
        print(f"\n{'â•' * 56}")
        print(f"{header:^56}")
        print(f"  Slot: {l2.slot}  |  Oracle: ${l2.oracle_price:.4f}")
        print(f"  Spread: {l2.spread_bps:.1f} bps")
        print(f"{'â•' * 56}")

        print(f"  {'ASKS (sell side)':^52}")
        print(f"  {'Price':>18}  {'Size':>14}  {'Cumulative':>14}")
        print(f"  {'â”€' * 50}")
        cum = 0.0
        for lvl in reversed(l2.asks[:10]):
            cum += lvl.size
            print(f"  ${lvl.price:>16.4f}  {lvl.size:>13.4f}  {cum:>13.4f}")

        print(f"  {'â”€â”€â”€ MID ' + f'${l2.mid_price:.4f} ':â”€<50}")

        cum = 0.0
        for lvl in l2.bids[:10]:
            cum += lvl.size
            print(f"  ${lvl.price:>16.4f}  {lvl.size:>13.4f}  {cum:>13.4f}")
        print(f"  {'â”€' * 50}")
        print(f"  {'BIDS (buy side)':^52}")

        # â”€â”€ Depth analysis â”€â”€
        for bps in [5, 10, 15, 25, 50]:
            bid_depth = l2.cumulative_depth(Side.BID, bps)
            ask_depth = l2.cumulative_depth(Side.ASK, bps)
            print(f"  Depth Â±{bps:>2}bps : "
                  f"bid={bid_depth:>10.2f}  ask={ask_depth:>10.2f}")

        # â”€â”€ Funding â”€â”€
        funding = await adapter.get_funding_snapshot(market)
        print(f"\n{'â”€' * 56}")
        print(f"  Funding Rate")
        print(f"  Current  : {funding.current_rate_annualised:+.4f}% ann")
        print(f"  Predicted: {funding.predicted_rate_annualised:+.4f}% ann")
        print(f"  TWAP sprd: {funding.twap_spread_bps:+.1f} bps")
        print(f"  Next in  : {funding.seconds_until_next:.0f}s")

        # â”€â”€ Account â”€â”€
        health = await adapter.get_account_health()
        print(f"\n{'â”€' * 56}")
        print(f"  Account Health")
        print(f"  Collateral  : ${health['total_collateral_usd']:>12,.2f}")
        print(f"  Free        : ${health['free_collateral_usd']:>12,.2f}")
        print(f"  Margin req  : ${health['margin_requirement_usd']:>12,.2f}")
        print(f"  Unrealised  : ${health['unrealised_pnl_usd']:>+12,.2f}")
        print(f"  Leverage    : {health['leverage_x']:>12.2f}x")
        print(f"  Margin ratio: {health['margin_ratio']:>12.2f}")
        print(f"{'â•' * 56}\n")

    finally:
        await adapter.shutdown()


if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )

    rpc = sys.argv[1] if len(sys.argv) > 1 else "https://api.mainnet-beta.solana.com"
    kp = sys.argv[2] if len(sys.argv) > 2 else "~/.config/solana/id.json"
    mkt = int(sys.argv[3]) if len(sys.argv) > 3 else 0  # SOL-PERP

    asyncio.run(_cli_debug(rpc, kp, mkt))
