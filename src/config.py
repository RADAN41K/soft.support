import json
import os
import sys


def get_base_path():
    """Get base path for config file (works with PyInstaller)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    """Load config.json from base path."""
    path = os.path.join(get_base_path(), "config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
