import os
import subprocess
from datetime import datetime
import sys

# Change working directory to the script's directory to ensure paths work
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from server import deploy_to_netlify

def run_update():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Starting scheduled auto-update...")
    try:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Running data_engine.py...")
        subprocess.run([sys.executable, "data_engine.py"], check=True)
        
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Running data_engine_all.py...")
        subprocess.run([sys.executable, "data_engine_all.py"], check=True)
        
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Refresh successful. Now pushing to Cloud...")
        success, cloud_msg = deploy_to_netlify()
        
        if success:
            print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Auto-update and deployment completed successfully.")
        else:
            print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Auto-update local successful, but cloud deployment failed: {cloud_msg}")

    except subprocess.CalledProcessError as e:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] ERROR: subprocess failed: {e}")
    except Exception as e:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] CRITICAL ERROR: {e}")

if __name__ == "__main__":
    run_update()
