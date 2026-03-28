"""Event-driven device and network change watcher.

Replaces 3-second polling with OS-level event listeners:
- macOS: IOKit USB notifications (instant) via ctypes
- Linux: watchdog on /dev for USB/COM changes
- Windows: WMI Win32_DeviceChangeEvent subscription
- Linux network: netlink socket (RTMGRP_IPV4_IFADDR)
- Windows network: NotifyAddrChange (iphlpapi.dll)
- macOS network: lightweight IP polling (no subprocess)
- Fallback: 30-second full scan on all platforms
"""
import platform
import socket
import threading

from src.utils.logging import log

_DEBOUNCE_SEC = 1.5
_FALLBACK_TIMEOUT = 60
_NET_POLL_INTERVAL = 15


class DeviceWatcher:
    """Cross-platform event-driven watcher for device and network changes.

    Fires separate callbacks for device vs network events so the app
    can run only the relevant scan instead of a full rescan.
    """

    def __init__(self, on_device_change, on_network_change, on_full_scan):
        self._on_device = on_device_change
        self._on_network = on_network_change
        self._on_full = on_full_scan
        self._dev_event = threading.Event()
        self._net_event = threading.Event()
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
            target=self._device_dispatch, daemon=True
        ).start()
        threading.Thread(
            target=self._network_dispatch, daemon=True
        ).start()
        threading.Thread(
            target=self._fallback_loop, daemon=True
        ).start()

    def trigger(self):
        """Manually trigger a full rescan."""
        self._dev_event.set()
        self._net_event.set()

    def stop(self):
        self._stop.set()
        self._dev_event.set()
        self._net_event.set()
        if self._iokit_runloop:
            import ctypes
            cf = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/"
                "CoreFoundation.framework/CoreFoundation")
            cf.CFRunLoopStop.argtypes = [ctypes.c_void_p]
            cf.CFRunLoopStop(self._iokit_runloop)

    # --- Dispatch loops ---

    def _device_dispatch(self):
        while not self._stop.is_set():
            self._dev_event.wait()
            if self._stop.is_set():
                break
            self._dev_event.clear()
            self._stop.wait(_DEBOUNCE_SEC)
            self._dev_event.clear()
            self._on_device()

    def _network_dispatch(self):
        while not self._stop.is_set():
            self._net_event.wait()
            if self._stop.is_set():
                break
            self._net_event.clear()
            self._stop.wait(_DEBOUNCE_SEC)
            self._net_event.clear()
            self._on_network()

    def _fallback_loop(self):
        while not self._stop.is_set():
            self._stop.wait(_FALLBACK_TIMEOUT)
            if self._stop.is_set():
                break
            self._on_full()

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
                while True:
                    obj = iokit.IOIteratorNext(iterator)
                    if not obj:
                        break
                    iokit.IOObjectRelease(obj)
                self._dev_event.set()

            self._iokit_callback = CALLBACK(_on_usb_event)

            port = iokit.IONotificationPortCreate(None)
            if not port:
                raise RuntimeError("IONotificationPortCreate failed")

            source = iokit.IONotificationPortGetRunLoopSource(port)
            run_loop = cf.CFRunLoopGetCurrent()
            self._iokit_runloop = run_loop

            cf.CFRunLoopAddSource(run_loop, source,
                                  ctypes.c_void_p.in_dll(
                                      cf, "kCFRunLoopDefaultMode"))

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
                        while True:
                            obj = iokit.IOIteratorNext(iterator)
                            if not obj:
                                break
                            iokit.IOObjectRelease(obj)

            log("[WATCHER] IOKit USB listener started")
            cf.CFRunLoopRun()

        except Exception as e:
            log(f"[WATCHER] IOKit failed: {e}, fallback to /dev", "WARN")
            self._start_dev_watcher()

    def _start_dev_watcher(self):
        """Linux: watch /dev for device file changes."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            parent = self

            class _DevHandler(FileSystemEventHandler):
                def on_created(self, event):
                    parent._dev_event.set()

                def on_deleted(self, event):
                    parent._dev_event.set()

            observer = Observer()
            observer.schedule(_DevHandler(), "/dev", recursive=False)
            observer.daemon = True
            observer.start()
            log("[WATCHER] /dev listener started")
        except Exception as e:
            log(f"[WATCHER] /dev watcher failed: {e}", "WARN")

    def _start_wmi_watcher(self):
        """Windows: WMI subscription for USB connect/disconnect only."""
        def _watch():
            import pythoncom
            import wmi as wmi_mod
            pythoncom.CoInitialize()
            try:
                w = wmi_mod.WMI()
                # Watch USB controller-device associations only;
                # fires on real USB plug/unplug, ignores HID/power noise
                wql = ("SELECT * FROM __InstanceOperationEvent WITHIN 3 "
                       "WHERE TargetInstance ISA 'Win32_USBControllerDevice'")
                watcher = w.watch_for(raw_wql=wql)
                log("[WATCHER] WMI USB listener started")
                while not self._stop.is_set():
                    try:
                        watcher(timeout_ms=5000)
                        self._dev_event.set()
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
            sock = socket.socket(16, socket.SOCK_DGRAM, 0)
            sock.bind((0, 0x10))
            sock.settimeout(2)
            log("[WATCHER] Netlink network listener started")
            while not self._stop.is_set():
                try:
                    data = sock.recv(4096)
                    if data:
                        self._net_event.set()
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
                    self._net_event.set()
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
                self._net_event.set()
            last_ip = ip
            self._stop.wait(_NET_POLL_INTERVAL)
