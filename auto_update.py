import subprocess
import sys
import os
from datetime import datetime

# Change working directory to script location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

def run_update():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Starting scheduled auto-update...")
    try:
        # 1. Run standard data engine (80 ETFs)
        print(f"[{datetime.now():%H:%M:%S}] Running data_engine.py...")
        subprocess.run([sys.executable, "data_engine.py"], check=True)

        # 2. Run large data engine (all ETFs universe)
        print(f"[{datetime.now():%H:%M:%S}] Running data_engine_all.py...")
        subprocess.run([sys.executable, "data_engine_all.py"], check=True)

        print(f"[{datetime.now():%H:%M:%S}] Auto-update complete. GitHub Action will commit and push the new data files.")

    except Exception as e:
        print(f"[{datetime.now():%H:%M:%S}] Error running update: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_update()
