import json
import os
import sys


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


def load_config():
    """Load config.json from base path."""
    path = os.path.join(get_base_path(), "config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
