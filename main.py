#!/usr/bin/env python3
"""Soft Support — LimanSoft tech support utility.

Single-instance entry point with logging and cleanup.
"""
import sys
import platform
import tempfile
import os


def _acquire_lock():
    """Ensure only one instance runs (cross-platform)."""
    lock_path = os.path.join(tempfile.gettempdir(), "softsupport.lock")
    fd = open(lock_path, "w")
    try:
        if platform.system() == "Windows":
            import msvcrt
            msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, IOError):
        sys.exit(0)
    return fd


def main():
    lock = _acquire_lock()  # noqa: F841 — prevent GC

    from src.utils.logging import log_startup, cleanup_old_logs
    log_startup()
    cleanup_old_logs()

    from src.ui.app import SoftSupportApp
    app = SoftSupportApp()
    app.run()


if __name__ == "__main__":
    main()
