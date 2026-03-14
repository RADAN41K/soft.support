import json
import os
import sys
import urllib.request
import urllib.error

API_URL = "https://limansoft.com/api/v1/pos/"


def get_base_path():
    """Get base path for config file (works with PyInstaller).

    On macOS .app bundle, executable is inside
    SoftSupport.app/Contents/MacOS/ — config.json should be
    next to the .app bundle, not inside it.
    """
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        # macOS .app bundle: go up from Contents/MacOS to .app parent
        if exe_dir.endswith("Contents/MacOS"):
            return os.path.dirname(os.path.dirname(os.path.dirname(exe_dir)))
        return exe_dir
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_config_path():
    """Get full path to config.json."""
    return os.path.join(get_base_path(), "config.json")


def load_config():
    """Load config.json from base path."""
    path = get_config_path()
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(data):
    """Save config data to config.json."""
    path = get_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def fetch_from_api(code):
    """Fetch POS data from API by code. Returns dict or None."""
    try:
        url = API_URL + code
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "code": code,
                    "pos_id": data.get("pos_id"),
                    "shop_name": data.get("shop_name", ""),
                    "telegram_link": data.get("telegram_link", ""),
                    "support_phone": data.get("support_phone", ""),
                }
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, OSError):
        pass
    return None


def load_or_fetch_config():
    """Load config: try API refresh first, fallback to cached file.

    Returns (config_dict, is_new) — is_new=True if no config existed.
    """
    config = load_config()

    if config and config.get("code"):
        # Try refreshing from API
        api_data = fetch_from_api(config["code"])
        if api_data:
            save_config(api_data)
            return api_data, False
        # API failed — use cached data
        return config, False

    # No config — need code input
    return None, True
