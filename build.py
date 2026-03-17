#!/usr/bin/env python3
"""Cross-platform build script for LimanSoft Support.

Usage:
    python build.py          # Build for current platform
    python build.py --clean  # Clean build artifacts first
"""
import os
import platform
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")


def _read_version():
    """Read version from VERSION file."""
    version_file = os.path.join(ROOT, "VERSION")
    with open(version_file) as f:
        return f.read().strip()
    return "0.0.0"


def clean():
    for d in [DIST, BUILD]:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"Removed {d}")


def build():
    system = platform.system()
    print(f"Building for {system}...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        os.path.join(ROOT, "soft_support.spec"),
    ]

    subprocess.run(cmd, check=True, cwd=ROOT)

    version = _read_version()
    print(f"Version: {version}")

    if system == "Darwin":
        print(f"\nDone! App bundle: dist/SoftSupport.app")
        _create_dmg()
    elif system == "Windows":
        print(f"\nDone! Executable: dist/SoftSupport.exe")
        print("Run Inno Setup on installer.iss to create installer.")
    else:
        print(f"\nDone! Binary: dist/SoftSupport")
        _create_desktop_file()




def _create_dmg():
    """Create DMG for macOS distribution."""
    app_path = os.path.join(DIST, "SoftSupport.app")
    dmg_path = os.path.join(DIST, "SoftSupport.dmg")

    if not os.path.exists(app_path):
        return

    if shutil.which("create-dmg"):
        subprocess.run([
            "create-dmg",
            "--volname", "LimanSoft Support",
            "--window-size", "500", "350",
            "--icon-size", "80",
            "--icon", "SoftSupport.app", "125", "175",
            "--app-drop-link", "375", "175",
            dmg_path, app_path,
        ], cwd=DIST)
    else:
        subprocess.run([
            "hdiutil", "create", "-volname", "SoftSupport",
            "-srcfolder", app_path,
            "-ov", "-format", "UDZO",
            dmg_path,
        ], check=True)
    print(f"DMG created: {dmg_path}")


def _create_desktop_file():
    """Create .desktop shortcut for Linux."""
    desktop = os.path.expanduser("~/Desktop")
    if not os.path.isdir(desktop):
        desktop = os.path.expanduser("~/Рабочий стол")
    if not os.path.isdir(desktop):
        print("Desktop folder not found, skipping shortcut.")
        return

    binary = os.path.join(DIST, "SoftSupport")
    icon = os.path.join(ROOT, "assets", "icon.png")

    content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=LimanSoft Support
Comment=LimanSoft Tech Support Utility
Exec={binary}
Icon={icon}
Terminal=false
Categories=Utility;
"""
    path = os.path.join(desktop, "SoftSupport.desktop")
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, 0o755)
    print(f"Desktop shortcut created: {path}")


if __name__ == "__main__":
    if "--clean" in sys.argv:
        clean()
    build()
