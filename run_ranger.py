""" Technical implementation for Hummingbot Gateway V2.1.
    MODULE: Ranger Vault Daemon (Production)
"""
import time
import logging
import random
import signal
from datetime import datetime
import argparse
from solana_execution_engine_integrated import SolanaSovereignEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
logger = logging.getLogger("RangerDaemon")

class RangerVaultDaemon:
    def __init__(self, initial_capital=1000000.0, mode='simulation', interval=10.0, max_cycles=None):
        self.engine = SolanaSovereignEngine(initial_capital)
        self.mode = mode
        self.interval = interval
        self.max_cycles = max_cycles
        self.cycles = 0
        self.start_time = None
        self.shutdown_requested = False
        
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        logger.warning("\n⚠️ Shutdown signal received.")
        self.shutdown_requested = True

    def run(self):
        logger.info("=" * 60)
        logger.info("🦅 RANGER SOVEREIGN VAULT - AWAKENING")
        logger.info("=" * 60)
        
        if not self.engine.initialize_vault_session():
            return

        self.start_time = time.time()
        
        try:
            while not self.shutdown_requested and self.engine.is_active:
                if self.max_cycles and self.cycles >= self.max_cycles:
                    logger.info("🎯 Max cycles reached.")
                    break
                    
                self._execute_sim_cycle()
                self.cycles += 1
                
                if self.cycles % 10 == 0:
                    self._print_status()
                    
                time.sleep(self.interval)
                
        except Exception as e:
            logger.exception(f"Fatal error: {e}")
            self.engine.emergency_shutdown("Fatal error")
        finally:
            self._print_final_report()

    def _execute_sim_cycle(self):
        base_funding = 0.00015
        current_funding = base_funding * random.uniform(0.6, 1.4)
        if random.random() < 0.1: current_funding *= -0.5 # 10% mahdollisuus negatiiviseen
        
        pnl = self.engine.current_equity * current_funding * (self.interval / 28800)
        noise = self.engine.current_equity * random.uniform(-0.00002, 0.00002)
        new_equity = self.engine.current_equity + pnl + noise
        
        self.engine.execute_cycle(new_equity, current_funding)

    def _print_status(self):
        s = self.engine.get_status()
        logger.info(f"📊 STATUS [Cycle {self.cycles}]: Equity ${s['equity']:,.2f} | PnL ${s['pnl']:+,.2f} | DD {s['drawdown_pct']:.2f}% | Position {s['position_pct']:.1f}%")

    def _print_final_report(self):
        s = self.engine.get_status()
        logger.info("=" * 60)
        logger.info("📋 FINAL PERFORMANCE REPORT")
        logger.info(f"Cycles: {self.cycles} | Final Equity: ${s['equity']:,.2f} | ROI: {s['roi_pct']:+.2f}%")
        logger.info("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--cycles', type=int, default=100)
    parser.add_argument('--interval', type=float, default=0.5)
    args = parser.parse_args()
    
    daemon = RangerVaultDaemon(max_cycles=args.cycles, interval=args.interval)
    daemon.run()
