#!/usr/bin/env python3
"""LimanSoft Support — tech support utility.

Single-instance entry point with logging and cleanup.
Uses a localhost socket to signal the running instance to show its window.
"""
import sys
import platform
import tempfile
import os
import socket
import threading

IPC_PORT = 52184


def _signal_existing():
    """Try to signal an already-running instance to show its window.
    Returns True if signal was sent successfully."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.connect(("127.0.0.1", IPC_PORT))
        sock.sendall(b"show")
        sock.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


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
        # Another instance holds the lock — signal it to show
        if _signal_existing():
            sys.exit(0)
        # Lock held but no listener — stale lock, force exit
        sys.exit(0)
    return fd


def _start_ipc_listener(app):
    """Listen for 'show' commands from new instances."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("127.0.0.1", IPC_PORT))
    except OSError:
        return
    server.listen(1)
    server.settimeout(1)

    while True:
        try:
            conn, _ = server.accept()
            data = conn.recv(16)
            conn.close()
            if data == b"show":
                app.after(0, app._show_window)
        except socket.timeout:
            continue
        except OSError:
            break


def main():
    lock = _acquire_lock()  # noqa: F841 — prevent GC

    from src.utils.logging import log_startup, cleanup_old_logs
    log_startup()
    cleanup_old_logs()

    from src.ui.app import SoftSupportApp
    app = SoftSupportApp()

    ipc_thread = threading.Thread(target=_start_ipc_listener, args=(app,),
                                  daemon=True)
    ipc_thread.start()

    app.run()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
