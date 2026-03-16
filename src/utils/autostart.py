"""Cross-platform autostart management."""
import os
import platform
import sys


APP_NAME = "SoftSupport"


def _get_exe_path():
    """Get path to the running executable."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def is_autostart_enabled():
    """Check if autostart is enabled."""
    system = platform.system()

    if system == "Windows":
        import winreg
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_READ)
            winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return True
        except (FileNotFoundError, OSError):
            return False

    elif system == "Darwin":
        plist = os.path.expanduser(
            f"~/Library/LaunchAgents/com.limansoft.{APP_NAME.lower()}.plist")
        return os.path.exists(plist)

    else:  # Linux
        autostart_dir = os.path.expanduser("~/.config/autostart")
        desktop_file = os.path.join(autostart_dir, f"{APP_NAME}.desktop")
        return os.path.exists(desktop_file)


def set_autostart(enabled):
    """Enable or disable autostart."""
    system = platform.system()

    if system == "Windows":
        _set_autostart_windows(enabled)
    elif system == "Darwin":
        _set_autostart_macos(enabled)
    else:
        _set_autostart_linux(enabled)


def _set_autostart_windows(enabled):
    import winreg
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE)
    if enabled:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _get_exe_path())
    else:
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
    winreg.CloseKey(key)


def _set_autostart_macos(enabled):
    plist_path = os.path.expanduser(
        f"~/Library/LaunchAgents/com.limansoft.{APP_NAME.lower()}.plist")

    if enabled:
        exe = _get_exe_path()
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.limansoft.{APP_NAME.lower()}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
        os.makedirs(os.path.dirname(plist_path), exist_ok=True)
        with open(plist_path, "w") as f:
            f.write(plist_content)
    else:
        if os.path.exists(plist_path):
            os.remove(plist_path)


def _set_autostart_linux(enabled):
    autostart_dir = os.path.expanduser("~/.config/autostart")
    desktop_file = os.path.join(autostart_dir, f"{APP_NAME}.desktop")

    if enabled:
        exe = _get_exe_path()
        content = f"""[Desktop Entry]
Type=Application
Name=LimanSoft Support
Exec={exe}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
        os.makedirs(autostart_dir, exist_ok=True)
        with open(desktop_file, "w") as f:
            f.write(content)
    else:
        if os.path.exists(desktop_file):
            os.remove(desktop_file)
