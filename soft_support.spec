# -*- mode: python ; coding: utf-8 -*-
import platform

block_cipher = None
system = platform.system()

# Platform-specific icon
if system == "Windows":
    icon_file = "assets/icon.ico"
elif system == "Darwin":
    icon_file = "assets/icon.icns"
else:
    icon_file = "assets/icon.png"

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets", "assets"),
        ("VERSION", "."),
    ],
    hiddenimports=[
        "customtkinter",
        "PIL",
        "serial",
        "serial.tools",
        "serial.tools.list_ports",
        "psutil",
        "pystray",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SoftSupport",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

# macOS .app bundle
if system == "Darwin":
    with open("VERSION", "r", encoding="utf-8") as f:
        app_version = f.read().strip()

    app = BUNDLE(
        exe,
        name="SoftSupport.app",
        icon=icon_file,
        bundle_identifier="com.limansoft.softsupport",
        info_plist={
            "CFBundleShortVersionString": app_version,
            "CFBundleName": "LimanSoft Support",
            "NSHighResolutionCapable": True,
        },
    )
