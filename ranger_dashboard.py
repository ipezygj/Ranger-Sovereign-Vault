""" Technical implementation for Hummingbot Gateway V2.1.
    MODULE: Ranger Sovereign Dashboard (TUI)
    PURPOSE: Visual command center for the Solana Vault.
"""
import os
import time
import json
from datetime import datetime

def clear_screen():
    os.system('clear')

def format_currency(value):
    return f"${value:,.2f}"

def get_latest_metrics():
    try:
        with open("vault_performance.jsonl", "r") as f:
            lines = f.readlines()
            if not lines:
                return None
            return json.loads(lines[-1])
    except:
        return None

def render_dashboard():
    while True:
        clear_screen()
        m = get_latest_metrics()
        
        print("=" * 60)
        print("      🦅 RANGER SOVEREIGN VAULT - COMMAND CENTER 🦅")
        print("=" * 60)
        
        if not m:
            print("\n   [WAITING FOR DATA] Start the engine to see metrics...")
        else:
            pnl_color = "\033[92m" if m['pnl_usd'] >= 0 else "\033[91m"
            reset = "\033[0m"
            
            print(f" LAST UPDATE: {m['timestamp']}")
            print("-" * 60)
            print(f" CURRENT EQUITY:  {format_currency(m['equity'])}")
            print(f" TOTAL PnL:       {pnl_color}{format_currency(m['pnl_usd'])}{reset}")
            print(f" ROI:             {pnl_color}{m['roi_pct']:+.4f}%{reset}")
            print(f" EST. APY:        {pnl_color}{m['estimated_apy']:+.2f}%{reset}")
            print("-" * 60)
            print(f" PEAK EQUITY:     {format_currency(m['peak_equity'])}")
            print(f" MAX DRAWDOWN:    \033[91m{m['drawdown_pct']:.4f}%\033[0m")
            print(f" RUNTIME:         {m['elapsed_days']} Days")
            print("-" * 60)
            
        print("\n [CTRL+C] TO EXIT | AUTO-REFRESH EVERY 5S")
        time.sleep(5)

if __name__ == "__main__":
    try:
        render_dashboard()
    except KeyboardInterrupt:
        print("\nDashboard closed. Systems still running in background.")
