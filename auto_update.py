import subprocess
import sys
import os
from datetime import datetime

# Change working directory to script location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

def run_update():
    """DAILY runner: Batch 1 (indices) + Batch 2 (core 80 ETFs) only.
    The heavy Batch 3 (4000+ ETFs, data_engine_all.py) runs on its own WEEKLY
    schedule so it can never delay or block the daily indices/80-ETF refresh."""
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Starting daily auto-update (indices + 80 ETFs)...")
    try:
        print(f"[{datetime.now():%H:%M:%S}] Running data_engine.py...")
        subprocess.run([sys.executable, "data_engine.py"], check=True)

        # ETF detail-page analytics (Monthly Returns calendar + Risk Analysis for
        # QQQ/SMH...). Reads history.json, writes etf_analytics.json only.
        # NON-FATAL: a hiccup here (e.g. the ^IRX risk-free-rate fetch) must never
        # fail the core daily dashboard update — it just logs and moves on.
        print(f"[{datetime.now():%H:%M:%S}] Running etf_analytics_engine.py...")
        try:
            subprocess.run([sys.executable, "etf_analytics_engine.py"], check=True)
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] (non-fatal) etf_analytics_engine failed: {e}")

        print(f"[{datetime.now():%H:%M:%S}] Daily update complete. Data published to Supabase (no git push / no Netlify deploy).")

    except Exception as e:
        print(f"[{datetime.now():%H:%M:%S}] Error running update: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_update()
