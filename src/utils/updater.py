"""Silent auto-updater for LimanSoft Support.

Checks API for new version, downloads installer, verifies SHA256,
runs silent install and restarts.
"""
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import urllib.request
import urllib.error

from src.version import __version__
from src.utils.logging import log

UPDATE_API = "https://limansoft.com/api/v1/update"


def _get_platform():
    """Return platform name for API query."""
    s = platform.system()
    if s == "Windows":
        return "windows"
    if s == "Darwin":
        return "macos"
    return "linux"


def check_update():
    """Check API for available update. Returns update dict or None."""
    try:
        url = f"{UPDATE_API}?name=limansoft-support&platform={_get_platform()}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                remote_version = data.get("version", "")
                if remote_version and remote_version != __version__:
                    log(f"Доступне оновлення: {__version__} -> {remote_version}")
                    return data
                log(f"Версія актуальна: {__version__}")
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, OSError) as e:
        log(f"Помилка перевірки оновлень: {e}", "WARN")
    return None


def _download_file(url, dest):
    """Download file from url to dest path."""
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=120) as resp:
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                f.write(chunk)


def _verify_sha256(file_path, expected_hash):
    """Verify file SHA256 hash."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha256.update(chunk)
    actual = sha256.hexdigest()
    return actual == expected_hash


def apply_update(update_info, on_progress=None):
    """Download and apply update. Returns True on success."""
    download_url = update_info.get("download_url", "")
    expected_sha = update_info.get("sha256", "")
    new_version = update_info.get("version", "?")

    if not download_url:
        log("Немає URL для завантаження", "ERROR")
        return False

    if not getattr(sys, "frozen", False):
        log("Оновлення доступне лише для зібраного додатку")
        return False

    try:
        tmp_dir = tempfile.gettempdir()

        if platform.system() == "Windows":
            tmp_file = os.path.join(tmp_dir, "LimanSoftSupport_Setup.exe")
        else:
            tmp_file = os.path.join(tmp_dir, "LimanSoftSupport_update")

        # Download
        if on_progress:
            on_progress("Завантаження оновлення...")
        log(f"Завантаження: {download_url}")
        _download_file(download_url, tmp_file)

        # Verify SHA256
        if expected_sha:
            if on_progress:
                on_progress("Перевірка цілісності...")
            if not _verify_sha256(tmp_file, expected_sha):
                log("SHA256 не збігається — оновлення скасовано", "ERROR")
                os.remove(tmp_file)
                return False
            log("SHA256 перевірено")

        # Apply update
        if platform.system() == "Windows":
            _apply_windows(tmp_file)
        else:
            _apply_unix(sys.executable, tmp_file)

        log(f"Оновлення до v{new_version} застосовано, перезапуск...")
        return True

    except Exception as e:
        log(f"Помилка оновлення: {e}", "ERROR")
        return False


def _apply_windows(setup_exe):
    """Run Inno Setup installer silently and exit current process."""
    log("Запуск тихої установки...")
    subprocess.Popen(
        [setup_exe, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
         "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
        creationflags=0x08000000 | 0x00000200,
        close_fds=True
    )
    sys.exit(0)


def _apply_unix(current_exe, new_exe):
    """Replace binary and restart on macOS/Linux."""
    os.chmod(new_exe, 0o755)
    sh_path = os.path.join(tempfile.gettempdir(), "limansoft_update.sh")
    sh_content = f"""#!/bin/bash
sleep 2
cp -f "{new_exe}" "{current_exe}"
chmod +x "{current_exe}"
"{current_exe}" &
rm -f "{new_exe}" "{sh_path}"
"""
    with open(sh_path, "w") as f:
        f.write(sh_content)
    os.chmod(sh_path, 0o755)

    subprocess.Popen(["bash", sh_path])
    sys.exit(0)


def check_and_apply_silently():
    """Check for updates in background thread and apply silently if available."""
    def _check():
        info = check_update()
        if info:
            log(f"Тихе оновлення до v{info.get('version', '?')}...")
            success = apply_update(info)
            if not success:
                log("Тихе оновлення не вдалося", "WARN")

    threading.Thread(target=_check, daemon=True).start()
