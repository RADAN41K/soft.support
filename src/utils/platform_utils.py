"""Platform-aware helpers shared across utility modules."""
import platform
import subprocess

# Kwargs to hide console window on Windows subprocess calls
SUBPROCESS_KWARGS = {}
if platform.system() == "Windows":
    SUBPROCESS_KWARGS["creationflags"] = (
        subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW")
        else 0x08000000
    )
