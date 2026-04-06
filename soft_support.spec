# -*- mode: python ; coding: utf-8 -*-
import platform

import glob

block_cipher = None
system = platform.system()

# Linux: bundle GObject Introspection typelibs for pystray tray icon
linux_datas = []
linux_binaries = []
linux_hiddenimports = []
if system == "Linux":
    linux_hiddenimports = [
        "gi",
        "gi.repository.Gtk",
        "gi.repository.GLib",
        "gi.repository.GObject",
        "gi.repository.GdkPixbuf",
        "gi.repository.AyatanaAppIndicator3",
        "pystray._appindicator",
    ]
    # Typelib files
    typelib_dir = "/usr/lib/x86_64-linux-gnu/girepository-1.0"
    for typelib in ["Gtk-3.0", "Gdk-3.0", "GLib-2.0", "GObject-2.0",
                    "GdkPixbuf-2.0", "Gio-2.0", "AyatanaAppIndicator3-0.1",
                    "Atk-1.0", "Pango-1.0", "cairo-1.0", "HarfBuzz-0.0"]:
        path = f"{typelib_dir}/{typelib}.typelib"
        if glob.glob(path):
            linux_datas.append((path, "gi_typelibs"))
    # GI shared lib
    for so in glob.glob("/usr/lib/python3/dist-packages/gi/*.so"):
        linux_binaries.append((so, "gi"))

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
    binaries=linux_binaries,
    datas=[
        ("assets", "assets"),
        ("VERSION", "."),
    ] + linux_datas,
    hiddenimports=[
        "customtkinter",
        "PIL",
        "PIL._tkinter_finder",
        "serial",
        "serial.tools",
        "serial.tools.list_ports",
        "psutil",
        "pystray",
    ] + linux_hiddenimports + [
        "pip_system_certs",
        "truststore",
        "certifi",
        "wmi",
        "pythoncom",
        "win32com",
        "win32com.client",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["hooks/gi_hook.py"] if system == "Linux" else [],
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
