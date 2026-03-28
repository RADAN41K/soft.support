"""Event-driven device and network change watcher.

Replaces 3-second polling with OS-level event listeners:
- macOS: IOKit USB notifications (instant) via ctypes
- Linux: watchdog on /dev for USB/COM changes
- Windows: WMI Win32_DeviceChangeEvent subscription
- Linux network: netlink socket (RTMGRP_IPV4_IFADDR)
- Windows network: NotifyAddrChange (iphlpapi.dll)
- macOS network: lightweight IP polling (no subprocess)
- Fallback: 30-second timeout on all platforms
"""
import platform
import socket
import threading

from src.utils.logging import log

_DEBOUNCE_SEC = 1.5
_FALLBACK_TIMEOUT = 30
_NET_POLL_INTERVAL = 15


class DeviceWatcher:
    """Cross-platform event-driven watcher for device and network changes."""

    def __init__(self, on_change):
        self._on_change = on_change
        self._event = threading.Event()
        self._stop = threading.Event()
        self._iokit_runloop = None

    def start(self):
        system = platform.system()

        if system == "Darwin":
            self._start_iokit_watcher()
        elif system == "Linux":
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
        if self._iokit_runloop:
            import ctypes
            cf = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/"
                "CoreFoundation.framework/CoreFoundation")
            cf.CFRunLoopStop.argtypes = [ctypes.c_void_p]
            cf.CFRunLoopStop(self._iokit_runloop)

    def _dispatch_loop(self):
        while not self._stop.is_set():
            triggered = self._event.wait(timeout=_FALLBACK_TIMEOUT)
            if self._stop.is_set():
                break
            self._event.clear()
            # Debounce: let rapid events settle
            if triggered:
                self._stop.wait(_DEBOUNCE_SEC)
                self._event.clear()
            self._on_change()

    # --- Device watchers ---

    def _start_iokit_watcher(self):
        """macOS: IOKit USB notifications via ctypes. Instant detection."""
        threading.Thread(
            target=self._run_iokit, daemon=True
        ).start()

    def _run_iokit(self):
        try:
            import ctypes
            from ctypes import c_void_p, c_char_p, c_int32, byref, CFUNCTYPE

            iokit = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/"
                "IOKit.framework/IOKit")
            cf = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/"
                "CoreFoundation.framework/CoreFoundation")

            # Function signatures
            iokit.IONotificationPortCreate.restype = c_void_p
            iokit.IONotificationPortCreate.argtypes = [c_void_p]
            iokit.IOServiceMatching.restype = c_void_p
            iokit.IOServiceMatching.argtypes = [c_char_p]
            iokit.IONotificationPortGetRunLoopSource.restype = c_void_p
            iokit.IONotificationPortGetRunLoopSource.argtypes = [c_void_p]
            iokit.IOIteratorNext.restype = c_void_p
            iokit.IOIteratorNext.argtypes = [c_void_p]
            iokit.IOObjectRelease.restype = c_int32
            iokit.IOObjectRelease.argtypes = [c_void_p]

            CALLBACK = CFUNCTYPE(None, c_void_p, c_void_p)
            iokit.IOServiceAddMatchingNotification.restype = c_int32
            iokit.IOServiceAddMatchingNotification.argtypes = [
                c_void_p, c_char_p, c_void_p, CALLBACK, c_void_p, c_void_p
            ]

            cf.CFRunLoopGetCurrent.restype = c_void_p
            cf.CFRunLoopAddSource.argtypes = [c_void_p, c_void_p, c_void_p]
            cf.CFRunLoopRun.restype = None

            # Keep strong reference to prevent GC crash
            def _on_usb_event(_refcon, iterator):
                # Drain iterator to arm next notification
                while True:
                    obj = iokit.IOIteratorNext(iterator)
                    if not obj:
                        break
                    iokit.IOObjectRelease(obj)
                self._event.set()

            self._iokit_callback = CALLBACK(_on_usb_event)

            port = iokit.IONotificationPortCreate(None)
            if not port:
                raise RuntimeError("IONotificationPortCreate failed")

            source = iokit.IONotificationPortGetRunLoopSource(port)
            run_loop = cf.CFRunLoopGetCurrent()
            self._iokit_runloop = run_loop

            # kCFRunLoopDefaultMode
            mode = cf.CFStringCreateWithCString(
                None, b"kCFRunLoopDefaultMode", 0
            ) if hasattr(cf, "CFStringCreateWithCString") else None

            # Use raw pointer for default mode
            cf.CFRunLoopAddSource(run_loop, source,
                                  ctypes.c_void_p.in_dll(
                                      cf, "kCFRunLoopDefaultMode"))

            # Register for matched + terminated on IOUSBHostDevice
            for service_class in [b"IOUSBHostDevice", b"IOUSBDevice"]:
                for notif_type in [b"IOServiceMatched",
                                   b"IOServiceTerminate"]:
                    matching = iokit.IOServiceMatching(service_class)
                    if not matching:
                        continue
                    iterator = c_void_p()
                    kr = iokit.IOServiceAddMatchingNotification(
                        port, notif_type, matching,
                        self._iokit_callback, None, byref(iterator))
                    if kr == 0:
                        # Drain iterator to arm notification
                        while True:
                            obj = iokit.IOIteratorNext(iterator)
                            if not obj:
                                break
                            iokit.IOObjectRelease(obj)

            log("[WATCHER] IOKit USB listener started")
            cf.CFRunLoopRun()

        except Exception as e:
            log(f"[WATCHER] IOKit failed: {e}, fallback to /dev", "WARN")
            self._start_dev_watcher_sync()

    def _start_dev_watcher(self):
        """Linux: watch /dev for device file changes."""
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

    def _start_dev_watcher_sync(self):
        """Fallback /dev watcher (called from IOKit thread on failure)."""
        self._start_dev_watcher()

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
