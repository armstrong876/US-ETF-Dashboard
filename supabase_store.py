"""
Supabase Storage helper — download/upload data files for the ETF engine.

Credentials come from environment variables (GitHub Actions secrets) OR a local
`.env` file in this folder. Real environment variables win over `.env`.

If credentials are absent/placeholder, `enabled()` returns False and every call
is a no-op that returns False — so a plain local run (no .env) still works exactly
as before, falling back to the local files. Nothing breaks without Supabase.

Layout used in the bucket:
    nav/   -> private engine cache (parquet, yf_profiles.json)
    site/  -> website-facing JSON (public bucket, added in Phase 2)
"""
import os
import urllib.parse
import requests

_BASE = os.path.dirname(os.path.abspath(__file__))


def _load_env():
    vals = {}
    envf = os.path.join(_BASE, ".env")
    if os.path.exists(envf):
        try:
            with open(envf, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        vals[k.strip()] = v.strip()
        except Exception:
            pass
    # real environment variables take precedence (GitHub Actions secrets)
    for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_BUCKET"):
        if os.environ.get(k):
            vals[k] = os.environ[k]
    return vals


_ENV = _load_env()
URL = (_ENV.get("SUPABASE_URL") or "").rstrip("/")
KEY = _ENV.get("SUPABASE_SERVICE_KEY") or ""
BUCKET = _ENV.get("SUPABASE_BUCKET") or "ETF Data"          # private engine cache
SITE_BUCKET = _ENV.get("SUPABASE_SITE_BUCKET") or "site-data"  # public website JSON


def enabled():
    """True only when real, non-placeholder credentials are present."""
    return bool(URL and KEY and "PASTE" not in KEY)


def _headers(extra=None):
    h = {"apikey": KEY, "Authorization": "Bearer " + KEY}
    if extra:
        h.update(extra)
    return h


def _object_url(remote_path, bucket=None):
    eb = urllib.parse.quote(bucket or BUCKET)
    ep = "/".join(urllib.parse.quote(seg) for seg in remote_path.split("/"))
    return f"{URL}/storage/v1/object/{eb}/{ep}"


def download_file(remote_path, local_path, bucket=None, timeout=120):
    """Download bucket:remote_path -> local_path. Returns True on success."""
    if not enabled():
        return False
    try:
        r = requests.get(_object_url(remote_path, bucket), headers=_headers(), timeout=timeout)
        if r.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(r.content)
            return True
        return False
    except Exception:
        return False


def upload_file(local_path, remote_path, bucket=None, content_type=None, cache_control=None, timeout=180):
    """Upload local_path -> bucket:remote_path (overwrites). Returns True on success."""
    if not enabled():
        return False
    if content_type is None:
        content_type = "application/json" if local_path.endswith(".json") else "application/octet-stream"
    try:
        with open(local_path, "rb") as f:
            body = f.read()
        extra = {"x-upsert": "true", "Content-Type": content_type}
        if cache_control:
            extra["cache-control"] = cache_control
        r = requests.post(
            _object_url(remote_path, bucket),
            headers=_headers(extra),
            data=body,
            timeout=timeout,
        )
        return r.status_code in (200, 201)
    except Exception:
        return False


def upload_site(local_path, remote_name=None, timeout=180):
    """Upload a website-facing JSON to the PUBLIC site bucket (short cache window
    so daily updates propagate fast). remote_name defaults to the file's basename."""
    remote = remote_name or os.path.basename(local_path)
    return upload_file(local_path, remote, bucket=SITE_BUCKET,
                       content_type="application/json", cache_control="max-age=300", timeout=timeout)
