"""Runtime hook: set GI_TYPELIB_PATH so pystray finds typelibs in bundle."""
import os
import sys

typelib_dir = os.path.join(getattr(sys, "_MEIPASS", ""), "gi_typelibs")
if os.path.isdir(typelib_dir):
    os.environ["GI_TYPELIB_PATH"] = typelib_dir
