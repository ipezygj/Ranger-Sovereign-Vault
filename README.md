<p align="center">
  <img src="https://img.shields.io/badge/Solana-Build--a--Bear-9945FF?style=for-the-badge&logo=solana&logoColor=white" />
  <img src="https://img.shields.io/badge/Drift_v2-Protocol-5B6CF0?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Track-Main-FF6B35?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Audit-Ready-00C853?style=for-the-badge" />
</p>

<h1 align="center">ðŸ° Ranger Sovereign Vault</h1>

<p align="center">
  <strong>Institutional-Grade Delta-Neutral Basis Engine on Drift v2</strong><br/>
  <em>Systematic funding capture with 5-regime adaptive strategy, liquidity-aware TWAP execution, and 5-layer circuit breaker protection.</em>
</p>

<p align="center">
  <a href="#architecture">Architecture</a> Â·
  <a href="#our-alpha--the-three-pillars">Our Alpha</a> Â·
  <a href="#risk-framework">Risk Framework</a> Â·
  <a href="#quickstart">Quickstart</a> Â·
  <a href="#audit-notes-for-presto-labs">Audit Notes</a>
</p>

---

## Executive Summary

Ranger Sovereign Vault is a **fully automated delta-neutral basis trading vault** built on [Drift Protocol v2](https://www.drift.trade/). It captures the funding rate premium between Drift perpetual markets and their spot underlyings while maintaining near-zero directional exposure.

Most basis bots use static parameters: enter when funding is positive, exit when it's not. They work until they don't. Ranger takes a fundamentally different approach â€” a **regime-aware execution framework** that classifies the funding environment into five distinct states, adapts every parameter in real-time, executes through a **liquidity-sensing TWAP engine** that reads the on-chain DLOB before every order slice, and wraps the entire system in a **5-layer progressive circuit breaker shield** capable of halting within a single Solana slot.

**This is not a strategy pitch. This is production infrastructure.**

---

## Architecture

```
                          â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                          â”‚            run_ranger.py                 â”‚
                          â”‚         Production Daemon                â”‚
                          â”‚   â€¢ Async event loop (no time.sleep)     â”‚
                          â”‚   â€¢ Cron-style scheduling                â”‚
                          â”‚   â€¢ Health telemetry + Prometheus        â”‚
                          â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                             â”‚
              â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
              â”‚                              â”‚                              â”‚
   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
   â”‚  Adaptive Funding     â”‚   â”‚  Liquidity-Aware        â”‚   â”‚   Circuit Breakers      â”‚
   â”‚  Strategy             â”‚   â”‚  TWAP Engine             â”‚   â”‚   (5-Layer Shield)      â”‚
   â”‚                       â”‚   â”‚                          â”‚   â”‚                         â”‚
   â”‚  â€¢ 5-regime model     â”‚   â”‚  â€¢ DLOB L2 depth sensing â”‚   â”‚  L1: Position limits    â”‚
   â”‚  â€¢ Hysteresis guards  â”‚   â”‚  â€¢ Adaptive slice sizing â”‚   â”‚  L2: Drawdown gates     â”‚
   â”‚  â€¢ Dynamic sizing     â”‚   â”‚  â€¢ Kyle-Î» impact model   â”‚   â”‚  L3: Funding reversal   â”‚
   â”‚  â€¢ Predictive entry   â”‚   â”‚  â€¢ Spread guards         â”‚   â”‚  L4: Liquidity drought  â”‚
   â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜   â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜   â”‚  L5: Emergency halt     â”‚
              â”‚                              â”‚                â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
              â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                             â”‚
                          â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                          â”‚      Solana Execution Engine              â”‚
                          â”‚   â€¢ Versioned transaction building        â”‚
                          â”‚   â€¢ Dynamic priority fee estimation       â”‚
                          â”‚   â€¢ Optional Jito bundle submission       â”‚
                          â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                             â”‚
                          â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                          â”‚      Drift Basis Adapter (driftpy)       â”‚
                          â”‚   â€¢ DriftClient websocket subscription   â”‚
                          â”‚   â€¢ DLOB â†’ typed L2Snapshot              â”‚
                          â”‚   â€¢ Funding rate observation              â”‚
                          â”‚   â€¢ Delta-neutral order lifecycle         â”‚
                          â”‚   â€¢ Retry-aware RPC (exp. backoff)       â”‚
                          â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

### Module Map

| Module | File | Responsibility |
|--------|------|----------------|
| **Execution Core** | `solana_execution_engine_integrated.py` | Transaction building, signing, compute budget, Jito bundles |
| **Adaptive Strategy** | `adaptive_funding_strategy.py` | 5-regime funding classifier, dynamic position sizing, entry timing |
| **TWAP Engine** | `liquidity_aware_twap.py` | L2-depth-aware order slicing, spread guards, impact estimation |
| **Circuit Breakers** | `circuit_breakers.py` | 5-layer progressive risk containment, independent evaluation |
| **Drift Adapter** | `drift_basis_adapter.py` | On-chain integration via driftpy â€” L2, funding, orders, health |
| **Production Daemon** | `run_ranger.py` | Async main loop, cron scheduling, health reporting |

---

## Our Alpha â€” The Three Pillars

### Pillar 1: Adaptive Funding Strategy (5-Regime Model)

Most basis vaults treat funding as a binary signal. Ranger classifies the funding environment into **five market regimes** and applies distinct logic at every decision point:

| Regime | Condition | Vault Behaviour |
|--------|-----------|-----------------|
| **R1 â€” High Contango** | Funding > 20 bps/8h, sustained | Maximum allocation. Aggressive entry via TWAP. |
| **R2 â€” Moderate Contango** | Funding 5â€“20 bps/8h | Standard allocation. Selective entry on confirmation. |
| **R3 â€” Flat / Noise** | Funding Â±5 bps/8h | Minimal exposure. Harvest only confirmed carry. |
| **R4 â€” Backwardation** | Funding âˆ’5 to âˆ’20 bps/8h | Orderly unwind via TWAP. Preserve capital. |
| **R5 â€” Crisis** | Funding < âˆ’20 bps/8h or vol spike | Full exit. Circuit breakers active. Cash position. |

**Regime transitions use hysteresis thresholds** to prevent whipsawing between states. The classifier consumes both the last settled funding rate and the predicted next-period rate (derived from Drift's mark vs oracle TWAP divergence) to anticipate transitions before they confirm on-chain.

**Why this matters:** Static strategies leave alpha on the table in moderate regimes and bleed capital in adverse ones. The 5-regime model is the difference between a vault that performs in Q1 and one that survives a full market cycle.

### Pillar 2: Liquidity-Aware TWAP Execution

Ranger never sends a single market order for the full position. Every entry and exit is decomposed into **adaptive TWAP slices** parameterised by real-time L2 orderbook state:

**How slicing works:**

The TWAP engine calls `adapter.get_perp_l2()` before every slice. This reconstructs the Drift DLOB into a typed `L2Snapshot` with helper methods the engine consumes directly:

```python
# Before each slice, the TWAP engine measures available liquidity
l2 = await adapter.get_perp_l2(market_index=0, depth=20)

# Size slice as â‰¤30% of available depth within slippage budget
available = l2.cumulative_depth(Side.ASK, max_bps=15.0)
slice_size = min(target_per_slice, available * 0.30)

# Abort if spread has blown out
if l2.spread_bps > 2 * historical_median_spread:
    pause_and_reassess()
```

**Impact estimation:** Before committing each slice, the engine estimates market impact using the Kyle lambda model against observed depth. If estimated impact for the remaining size exceeds the per-session budget, the sequence pauses.

**No external dependencies:** The entire L2 reconstruction pipeline runs against Drift's on-chain DLOB state via the adapter's `DLOBClient`. No third-party data feeds required.

### Pillar 3: 5-Layer Circuit Breaker Shield

Risk management is not a feature bolted on at the end. **It is the architecture.** Five independent, progressively escalating protection layers:

| Layer | Trigger | Response | Recovery |
|-------|---------|----------|----------|
| **L1 â€” Position Limits** | Single position exceeds max notional | Block new entries | Automatic on reduction |
| **L2 â€” Drawdown Gate** | Unrealised PnL breaches threshold | Reduce position 50% | Manual review required |
| **L3 â€” Funding Reversal** | Regime transitions to R4 or R5 | Begin orderly TWAP unwind | Auto-resume on regime recovery |
| **L4 â€” Liquidity Drought** | L2 depth < minimum threshold | Halt all new entries | Auto-resume when depth recovers |
| **L5 â€” Emergency Halt** | Margin ratio critical OR oracle stale | Cancel ALL orders. Flatten. | **Manual restart only.** |

Each layer evaluates independently every daemon cycle. **Layer 5 can fire even if Layers 1â€“4 are green.** The system is designed to **fail safe** â€” if the daemon process crashes, no new orders are placed. All orders use IOC (Immediate-or-Cancel) semantics, so no stale resting orders can persist on-chain.

---

## Risk Framework

### Delta-Neutrality Invariant

The vault's core invariant: **net delta remains within Â±2% of zero at all times.**

Enforcement mechanism:

1. Every `open_basis_position()` places a spot buy and perp short as IOC limit orders with matching base amounts and slippage guards.
2. If one leg fills and the other fails (partial fill, slippage rejection), the daemon's next cycle detects the delta imbalance.
3. The circuit breaker (Layer 2) triggers automatic rebalancing â€” either completing the missing leg or unwinding the filled leg.
4. Delta is verified every cycle via `adapter.get_perp_position()` against spot balance.

### Slippage Budget (3-Tier)

| Scope | Limit | Enforced By |
|-------|-------|-------------|
| Per-slice | 15 bps | IOC limit price = oracle Â± slippage |
| Per-position (all slices) | 30 bps | Cumulative tracking in TWAP engine |
| Per-session | 50 bps | Circuit breaker L4 trigger |

If any tier is breached, the TWAP engine halts and the circuit breaker activates.

### Oracle Model

All price data is sourced from **Drift's cached Pyth oracle** â€” no external oracle calls. The adapter reads oracle price data directly from the Drift program's on-chain state for:

- Limit price computation (oracle Â± slippage band)
- Funding rate prediction (mark TWAP vs oracle TWAP divergence)
- Circuit breaker L5 (stale oracle detection via slot age)

---

## Drift Adapter â€” Technical Reference

The `drift_basis_adapter.py` module is the production bridge between Ranger's strategy layer and Drift Protocol v2. It replaces the previous mock implementation entirely.

### L2 Orderbook Reconstruction

```python
adapter = DriftBasisAdapter(config, keypair_path)
await adapter.initialize()

# Reconstruct 20-level L2 from Drift's on-chain DLOB
l2 = await adapter.get_perp_l2(market_index=0, depth=20)

l2.best_bid          # â†’ $142.3500
l2.best_ask          # â†’ $142.3800
l2.spread_bps        # â†’ 2.1
l2.oracle_price      # â†’ $142.3650  (Pyth via Drift)
l2.cumulative_depth(Side.ASK, 10.0)  # â†’ 450.0 SOL within 10bps
```

### Delta-Neutral Position Lifecycle

```python
# OPEN: spot buy + perp short (both IOC, slippage-guarded)
position = await adapter.open_basis_position(
    perp_market_index=0,   # SOL-PERP
    spot_market_index=1,   # SOL
    base_amount=50.0,      # 50 SOL
    max_slippage_bps=15.0,
)
# position.entry_basis_bps â†’ +8.3 bps captured

# MONITOR
health  = await adapter.get_account_health()
funding = await adapter.get_funding_snapshot(market_index=0)

# CLOSE: sell spot + buy-to-cover perp
result = await adapter.close_basis_position(position)
# result["hold_duration_s"] â†’ 3847.0
# result["entry_basis_bps"] â†’ +8.3
```

### Funding Rate Observation

```python
snap = await adapter.get_funding_snapshot(market_index=0)
snap.current_rate_annualised     # â†’ +12.45% (last settled, annualised)
snap.predicted_rate_annualised   # â†’ +14.20% (from TWAP divergence)
snap.twap_spread_bps             # â†’ +3.2 bps (mark above oracle)
snap.seconds_until_next          # â†’ 1847 (until next settlement)
```

### Emergency Controls

```python
# Called by circuit breaker Layer 5
await adapter.cancel_all_orders()  # Cancel everything, all markets

# Or scoped to a specific market
await adapter.cancel_all_orders(
    market_index=0,
    market_type=MarketType.Perp(),
)
```

---

## Quickstart

### Prerequisites

```
Python 3.10+
Solana CLI (keypair management)
Funded Drift v2 account (mainnet-beta or devnet)
```

### Install

```bash
git clone https://github.com/ranger-vault/ranger-sovereign-vault.git
cd ranger-sovereign-vault
pip install driftpy solders anchorpy solana aiohttp
```

### Verify Connectivity

```bash
# Print live L2 orderbook, funding rate, and account health
python drift_basis_adapter.py <RPC_URL> <KEYPAIR_PATH> 0
```

### Configure

```bash
export RANGER_RPC_URL="https://your-rpc-endpoint.com"
export RANGER_KEYPAIR_PATH="~/.config/solana/id.json"
export RANGER_ENV="mainnet-beta"
export RANGER_DLOB_URL="https://dlob.drift.trade"
export RANGER_MAX_SLIPPAGE_BPS="15"
export RANGER_MIN_L2_DEPTH_USD="50000"
```

### Run

```bash
# Production
python run_ranger.py

# Dry run (full logging, no orders)
python run_ranger.py --dry-run
```

---

## Project Structure

```
ranger-sovereign-vault/
â”œâ”€â”€ solana_execution_engine_integrated.py   # Solana tx lifecycle
â”œâ”€â”€ adaptive_funding_strategy.py            # 5-regime classifier + sizer
â”œâ”€â”€ liquidity_aware_twap.py                 # L2-aware order slicing
â”œâ”€â”€ circuit_breakers.py                     # 5-layer risk shield
â”œâ”€â”€ drift_basis_adapter.py                  # Drift v2 on-chain adapter
â”œâ”€â”€ run_ranger.py                           # Async production daemon
â”œâ”€â”€ README.md
â”œâ”€â”€ requirements.txt
â””â”€â”€ tests/
    â”œâ”€â”€ test_strategy.py                    # Regime transition + hysteresis
    â”œâ”€â”€ test_twap.py                        # Slice sizing + abort logic
    â”œâ”€â”€ test_circuit_breakers.py            # Layer trigger + recovery paths
    â””â”€â”€ test_adapter_integration.py         # Devnet end-to-end
```

---

## Audit Notes for Presto Labs

This section is written specifically for the technical audit team.

### 1. Regime Classifier Correctness

**File:** `adaptive_funding_strategy.py`

Verify that hysteresis thresholds prevent rapid regime oscillation. The critical edge case: funding oscillating at exactly a regime boundary should not cause position churn. The classifier requires N consecutive observations in the new regime before transitioning.

### 2. TWAP Slice Safety

**File:** `liquidity_aware_twap.py`

Each slice is IOC with a per-slice slippage limit. Verify that a partial fill on one leg (spot fills, perp rejects) triggers the delta-rebalance path in the next daemon cycle, not a silent imbalance accumulation. The cumulative slippage tracker should trigger L4 (liquidity drought) before the session budget is breached.

### 3. Circuit Breaker Independence

**File:** `circuit_breakers.py`

All five layers are evaluated independently every cycle. Layer 5 (emergency halt) cannot be masked by green status on Layers 1â€“4. Verify that `cancel_all_orders()` reaches the adapter and executes even under high event-loop load. The adapter's retry logic must not delay emergency cancellation.

### 4. Adapter Leg Atomicity

**File:** `drift_basis_adapter.py`

The two-leg basis trade (spot buy + perp short) is submitted as **two separate Solana transactions**. Atomicity is enforced at the application layer: IOC semantics prevent stale resting orders, and the daemon detects delta imbalance within one cycle. This is documented as a known limitation. A future version could use Drift's composite order instructions for transaction-level atomicity.

### 5. No Blocking Calls

Zero `time.sleep()` calls in any production path. All timing is `asyncio.sleep()` in the daemon loop. The adapter uses Solana slot timestamps as ground truth.

### Known Limitations (Documented Transparently)

| Limitation | Mitigation | Future Path |
|------------|------------|-------------|
| Two-leg trades are not Solana-atomic | IOC + per-cycle delta monitoring | Drift composite order CPI |
| DLOB depends on `dlob.drift.trade` server | Adapter raises â†’ circuit breaker halts | Self-hosted DLOB node |
| Jito bundles are optional | Fallback to priority fees | Always-on MEV protection |
| Funding prediction is simplified | TWAP spread Ã— 8760 | ML model on historical curves |

### Dependency Versions

| Package | Min Version | Purpose |
|---------|-------------|---------|
| `driftpy` | â‰¥ 0.7.0 | Drift Protocol v2 SDK |
| `solders` | â‰¥ 0.20.0 | Solana types (Pubkey, Keypair, Transaction) |
| `anchorpy` | â‰¥ 0.18.0 | Anchor framework bindings |
| `solana` | â‰¥ 0.32.0 | Solana async RPC client |
| `aiohttp` | â‰¥ 3.9.0 | Async HTTP for DLOB server |

---

## Hackathon Context

| | |
|---|---|
| **Hackathon** | Solana Build-a-Bear |
| **Track** | Main |
| **Bounty** | Presto Labs |
| **Protocol** | Drift v2 (Solana) |
| **Language** | Python 3.10+ (fully async) |
| **Network** | Mainnet-Beta / Devnet |

---

<p align="center">
  <strong>Built for the audit. Built for production. Built to win.</strong><br/>
  <em>Ranger Sovereign Vault â€” Superteam Hackathon 2025</em>
</p>
