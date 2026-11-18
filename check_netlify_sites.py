import os
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Token comes from the environment or the local .env file (never hard-code it here).
def _load_env():
    vals = {}
    envf = os.path.join(BASE_DIR, ".env")
    if os.path.exists(envf):
        with open(envf, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip()
    return vals

token = os.environ.get("NETLIFY_AUTH_TOKEN") or _load_env().get("NETLIFY_AUTH_TOKEN", "")
if not token:
    raise SystemExit("NETLIFY_AUTH_TOKEN not set (add it to .env).")
headers = {"Authorization": f"Bearer {token}"}

response = requests.get("https://api.netlify.com/api/v1/sites", headers=headers)
if response.status_code == 200:
    sites = response.json()
    for site in sites:
        print(f"Name: {site['name']}, ID: {site['id']}, URL: {site['url']}")
else:
    print(f"Error: {response.status_code} - {response.text}")
