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
    """Read version from src/version.py."""
    version_file = os.path.join(ROOT, "src", "version.py")
    with open(version_file) as f:
        for line in f:
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip('"').strip("'")
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
        _prepare_installer(version)
        print("Run Inno Setup on installer.iss to create installer.")
    else:
        print(f"\nDone! Binary: dist/SoftSupport")
        _create_desktop_file()


def _prepare_installer(version):
    """Update installer.iss with current version from src/version.py."""
    iss_path = os.path.join(ROOT, "installer.iss")
    if not os.path.exists(iss_path):
        return
    with open(iss_path, "r", encoding="utf-8") as f:
        content = f.read()
    # Replace #define or add it at the top
    define_line = f'#define AppVer "{version}"'
    if content.startswith("#define AppVer"):
        lines = content.split("\n")
        lines[0] = define_line
        content = "\n".join(lines)
    else:
        content = define_line + "\n" + content
    with open(iss_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"installer.iss updated with version {version}")


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
