import os
import sys


def _read_version():
    """Read version from VERSION file."""
    if getattr(sys, "frozen", False):
        # PyInstaller: VERSION is next to the exe (inside _MEIPASS)
        base = sys._MEIPASS
    else:
        # Development: VERSION is in project root
        base = os.path.join(os.path.dirname(__file__), "..")
    try:
        with open(os.path.join(base, "VERSION")) as f:
            return f.read().strip()
    except FileNotFoundError:
        return "0.0.0"


__version__ = _read_version()
