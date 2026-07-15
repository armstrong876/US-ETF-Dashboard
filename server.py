import os
import json
import subprocess
import zipfile
import io
import requests
from datetime import datetime
from flask import Flask, send_from_directory, jsonify, request

app = Flask(__name__, static_folder='.')

# --- Configuration ---
NETLIFY_TOKEN = os.environ.get("NETLIFY_AUTH_TOKEN", "nfp_8f2UiPxVQUbcTNbxGU8GqdbAVDLf2jnd6936")
NETLIFY_SITE_ID = os.environ.get("NETLIFY_SITE_ID", "1efbdd84-2440-4715-aa74-52baf24c3b8f")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_JSON = os.path.join(BASE_DIR, "dashboard.json")

def get_last_updated_date():
    if not os.path.exists(DASHBOARD_JSON):
        return None
    try:
        with open(DASHBOARD_JSON, 'r') as f:
            data = json.load(f)
            return data.get('as_of_date')
    except:
        return None

def deploy_to_netlify():
    print(f"[{datetime.now():%H:%M:%S}] Preparing cloud deployment...")
    
    # Files to include in the deployment
    include_files = [
        'index.html', 'dashboard.js', 'style.css', 'auth.js',
        'dashboard.json', 'dashboard_all.json', 'history.json', 'login.html',
        'netlify.toml', 'armstrong_vibrant_hero.png', 'armstrong_logo.jpg'
    ]
    
    # Create in-memory zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file in include_files:
            file_path = os.path.join(BASE_DIR, file)
            if os.path.exists(file_path):
                zip_file.write(file_path, file)
            else:
                print(f"  Warning: {file} not found, skipping.")

    zip_buffer.seek(0)
    
    # Push to Netlify API
    url = f"https://api.netlify.com/api/v1/sites/{NETLIFY_SITE_ID}/deploys"
    headers = {
        "Authorization": f"Bearer {NETLIFY_TOKEN}",
        "Content-Type": "application/zip"
    }
    
    print(f"[{datetime.now():%H:%M:%S}] Uploading to Netlify...")
    response = requests.post(url, data=zip_buffer, headers=headers)
    
    if response.status_code in [200, 201]:
        print(f"[{datetime.now():%H:%M:%S}] Cloud deployment SUCCESS!")
        return True, "Cloud site updated successfully!"
    else:
        error_msg = response.json().get('message', response.text)
        print(f"[{datetime.now():%H:%M:%S}] Cloud deployment FAILED: {error_msg}")
        return False, f"Netlify Deploy Error: {error_msg}"

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

@app.route('/api/refresh', methods=['POST'])
def refresh():
    data = request.json or {}
    force = data.get('force', False)
    include_all = data.get('include_all', False)
    
    print(f"[{datetime.now():%H:%M:%S}] Refresh request: Force={force}, IncludeAll={include_all}")

    try:
        # 1. Run Data Engine
        print(f"[{datetime.now():%H:%M:%S}] Running data_engine.py...")
        subprocess.run(["python", "data_engine.py"], check=True)
        
        if include_all:
            print(f"[{datetime.now():%H:%M:%S}] Running data_engine_all.py...")
            subprocess.run(["python", "data_engine_all.py"], check=True)

        # 2. Deploy to Netlify
        print(f"[{datetime.now():%H:%M:%S}] Refresh successful. Now pushing to Cloud...")
        success, cloud_msg = deploy_to_netlify()
        
        if success:
            return jsonify({
                "status": "success",
                "message": f"Updated & Cloud Synced!",
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        else:
            return jsonify({
                "status": "partial_success",
                "message": f"Local OK, but Cloud ERROR: {cloud_msg}",
                "error_detail": cloud_msg,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }), 200 # Return 200 so UI doesn't treat as total failure

    except subprocess.CalledProcessError as e:
        print(f"  ERROR: subprocess failed: {e}")
        return jsonify({
            "status": "error",
            "message": f"Data Engine Error: {str(e)}"
        }), 500
    except Exception as e:
        print(f"  CRITICAL ERROR: {e}")
        return jsonify({
            "status": "error",
            "message": f"System Error: {str(e)}"
        }), 500

@app.route('/api/refresh-etf-details', methods=['POST'])
def refresh_etf_details():
    """Manual-only trigger for QQQ/SMH (and later, all 80) ETF composition &
    holdings data. Not on any automatic schedule — only runs when called here."""
    print(f"[{datetime.now():%H:%M:%S}] ETF composition refresh requested...")
    try:
        result = subprocess.run(
            ["python", "etf_composition_engine.py"],
            check=True, capture_output=True, text=True
        )
        print(result.stdout)
        return jsonify({
            "status": "success",
            "message": "ETF composition & holdings data refreshed.",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except subprocess.CalledProcessError as e:
        print(f"  ERROR: {e.stderr}")
        return jsonify({"status": "error", "message": f"Composition engine failed: {e.stderr}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    print("====================================================")
    print("   Armstrong Capital — ETF Dashboard Server")
    print("   Access at: http://localhost:5000")
    print("====================================================")
    app.run(port=5000, debug=True)
