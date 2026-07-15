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

        print(f"[{datetime.now():%H:%M:%S}] Daily update complete. GitHub Action will commit and push the new data files.")

    except Exception as e:
        print(f"[{datetime.now():%H:%M:%S}] Error running update: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_update()
