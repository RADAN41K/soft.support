"""File-based logging for LimanSoft tech support.

Logs are stored in platform-specific directories:
- Windows: %APPDATA%/LimanSoft/logs
- macOS: ~/Library/Logs/LimanSoft
- Linux: ~/.local/share/LimanSoft/logs

Auto-cleanup removes logs older than 30 days.
"""
import os
import glob
import platform
from datetime import datetime, timedelta


def get_log_dir():
    """Public accessor for log directory path."""
    return _log_dir()


def _log_dir():
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "LimanSoft", "logs")
    elif system == "Darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Logs", "LimanSoft")
    else:
        return os.path.join(os.path.expanduser("~"), ".local", "share", "LimanSoft", "logs")


def _ensure_dir():
    d = _log_dir()
    os.makedirs(d, exist_ok=True)
    return d


def _write(filename_prefix, message, level=None):
    try:
        d = _ensure_dir()
        date_str = datetime.now().strftime("%Y-%m-%d")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        path = os.path.join(d, f"{filename_prefix}_{date_str}.log")
        prefix = f"[{ts}] [{level}] " if level else f"[{ts}] "
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{prefix}{message}\n")
    except Exception:
        pass


def log(message, level="INFO"):
    _write("limansoft", message, level)


def log_device(message):
    _write("devices", message)


def log_startup():
    log("==============================================")
    log("=== ЗАПУСК LimanSoft Технічна підтримка ===")
    log("==============================================")
    log(f"Python: {platform.python_version()} | "
        f"Користувач: {os.environ.get('USERNAME', os.environ.get('USER', '?'))} | "
        f"Комп'ютер: {platform.node()}")
    log(f"ОС: {platform.system()} {platform.release()}")
    log_device(f"[ПК] Запуск | Користувач: {os.environ.get('USERNAME', os.environ.get('USER', '?'))} | "
               f"Комп'ютер: {platform.node()}")


def cleanup_old_logs(days=30):
    try:
        d = _log_dir()
        if not os.path.isdir(d):
            return
        cutoff = datetime.now() - timedelta(days=days)
        for f in glob.glob(os.path.join(d, "*.log")):
            mtime = datetime.fromtimestamp(os.path.getmtime(f))
            if mtime < cutoff:
                os.remove(f)
    except Exception:
        pass
