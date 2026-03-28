"""Event-driven device and network change watcher.

Replaces 3-second polling with OS-level event listeners:
- macOS/Linux: watchdog on /dev for USB/COM changes
- Windows: WMI Win32_DeviceChangeEvent subscription
- Linux network: netlink socket (RTMGRP_IPV4_IFADDR)
- Windows network: NotifyAddrChange (iphlpapi.dll)
- macOS network: lightweight IP polling (no subprocess)
- Fallback: 10-second timeout on all platforms
"""
import platform
import socket
import threading

from src.utils.logging import log

_DEBOUNCE_SEC = 1.5
_FALLBACK_TIMEOUT = 10
_NET_POLL_INTERVAL = 15


class DeviceWatcher:
    """Cross-platform event-driven watcher for device and network changes."""

    def __init__(self, on_change):
        self._on_change = on_change
        self._event = threading.Event()
        self._stop = threading.Event()

    def start(self):
        system = platform.system()

        if system in ("Darwin", "Linux"):
            self._start_dev_watcher()
        elif system == "Windows":
            self._start_wmi_watcher()

        self._start_network_watcher()

        threading.Thread(
            target=self._dispatch_loop, daemon=True
        ).start()

    def trigger(self):
        """Manually trigger a rescan."""
        self._event.set()

    def stop(self):
        self._stop.set()
        self._event.set()

    def _dispatch_loop(self):
        while not self._stop.is_set():
            triggered = self._event.wait(timeout=_FALLBACK_TIMEOUT)
            if self._stop.is_set():
                break
            self._event.clear()
            # Debounce: let rapid events settle (e.g. USB plug fires many /dev changes)
            if triggered:
                self._stop.wait(_DEBOUNCE_SEC)
                self._event.clear()
            self._on_change()

    # --- Device watchers ---

    def _start_dev_watcher(self):
        """macOS/Linux: watch /dev for device file changes."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            parent = self

            class _DevHandler(FileSystemEventHandler):
                def on_created(self, event):
                    parent._event.set()

                def on_deleted(self, event):
                    parent._event.set()

            observer = Observer()
            observer.schedule(_DevHandler(), "/dev", recursive=False)
            observer.daemon = True
            observer.start()
            log("[WATCHER] /dev listener started")
        except Exception as e:
            log(f"[WATCHER] /dev watcher failed: {e}", "WARN")

    def _start_wmi_watcher(self):
        """Windows: WMI event subscription for USB device changes."""
        def _watch():
            import pythoncom
            import wmi as wmi_mod
            pythoncom.CoInitialize()
            try:
                w = wmi_mod.WMI()
                watcher = w.Win32_DeviceChangeEvent.watch_for()
                log("[WATCHER] WMI device listener started")
                while not self._stop.is_set():
                    try:
                        watcher(timeout_ms=2000)
                        self._event.set()
                    except wmi_mod.x_wmi_timed_out:
                        continue
            except Exception as e:
                log(f"[WATCHER] WMI watcher failed: {e}", "WARN")
            finally:
                pythoncom.CoUninitialize()

        threading.Thread(target=_watch, daemon=True).start()

    # --- Network watchers ---

    def _start_network_watcher(self):
        system = platform.system()
        targets = {
            "Linux": self._watch_network_linux,
            "Windows": self._watch_network_windows,
        }
        target = targets.get(system, self._poll_network)

        threading.Thread(target=target, daemon=True).start()

    def _watch_network_linux(self):
        """Linux: netlink socket for IP address change events."""
        try:
            # AF_NETLINK=16, NETLINK_ROUTE=0, RTMGRP_IPV4_IFADDR=0x10
            sock = socket.socket(16, socket.SOCK_DGRAM, 0)
            sock.bind((0, 0x10))
            sock.settimeout(2)
            log("[WATCHER] Netlink network listener started")
            while not self._stop.is_set():
                try:
                    data = sock.recv(4096)
                    if data:
                        self._event.set()
                except socket.timeout:
                    continue
        except Exception as e:
            log(f"[WATCHER] Netlink failed: {e}, fallback to polling", "WARN")
            self._poll_network()

    def _watch_network_windows(self):
        """Windows: NotifyAddrChange blocks until network address changes."""
        try:
            import ctypes
            from ctypes import wintypes
            iphlpapi = ctypes.windll.iphlpapi
            log("[WATCHER] NotifyAddrChange network listener started")
            while not self._stop.is_set():
                handle = wintypes.HANDLE()
                ret = iphlpapi.NotifyAddrChange(
                    ctypes.byref(handle), None)
                if ret == 0:
                    self._event.set()
                else:
                    self._stop.wait(30)
        except Exception as e:
            log(f"[WATCHER] NotifyAddrChange failed: {e}", "WARN")
            self._poll_network()

    def _poll_network(self):
        """Fallback: lightweight IP check without subprocesses."""
        last_ip = None
        log("[WATCHER] Network polling started "
            f"(interval {_NET_POLL_INTERVAL}s)")
        while not self._stop.is_set():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
            except OSError:
                ip = None
            if ip != last_ip and last_ip is not None:
                self._event.set()
            last_ip = ip
            self._stop.wait(_NET_POLL_INTERVAL)