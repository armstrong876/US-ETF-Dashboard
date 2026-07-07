import os
import subprocess
import sys
from datetime import datetime

# Change working directory to script location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# Import Netlify deploy functionality from server
from server import deploy_to_netlify

def run_update():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Starting scheduled auto-update...")
    try:
        # 1. Run standard data engine
        print(f"[{datetime.now():%H:%M:%S}] Running data_engine.py...")
        subprocess.run([sys.executable, "data_engine.py"], check=True)
        
        # 2. Run large data engine (all ETFs)
        print(f"[{datetime.now():%H:%M:%S}] Running data_engine_all.py...")
        subprocess.run([sys.executable, "data_engine_all.py"], check=True)
        
        # 3. Deploy to Netlify (Disabled as requested to keep updates local/GitHub only)
        # print(f"[{datetime.now():%H:%M:%S}] Deploying updated data to Netlify...")
        # success, cloud_msg = deploy_to_netlify()
        # if success:
        #     print(f"[{datetime.now():%H:%M:%S}] Cloud deployment succeeded: {cloud_msg}")
        # else:
        #     print(f"[{datetime.now():%H:%M:%S}] Cloud deployment FAILED: {cloud_msg}")
        #     sys.exit(1)
        pass
            
    except Exception as e:
        print(f"[{datetime.now():%H:%M:%S}] Error running update: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_update()
