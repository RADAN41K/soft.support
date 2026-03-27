import platform
import re
import subprocess

import serial
import serial.tools.list_ports

from src.utils.logging import log
from src.utils.platform_utils import SUBPROCESS_KWARGS as _SUBPROCESS_KWARGS


def _get_device_address(instance_id):
    """Get USB device address (port number) via cfgmgr32 API.

    Returns port number as string, or empty string on failure.
    Windows only.
    """
    try:
        import ctypes
        from ctypes import wintypes

        cfgmgr = ctypes.windll.CfgMgr32

        class DEVPROPKEY(ctypes.Structure):
            _fields_ = [("fmtid", ctypes.c_byte * 16), ("pid", wintypes.ULONG)]

        key = DEVPROPKEY()
        # GUID {a45c254e-df1c-4efd-8020-67d146a850e0}
        guid_bytes = (
            b'\x4e\x25\x5c\xa4\x1c\xdf\xfd\x4e'
            b'\x80\x20\x67\xd1\x46\xa8\x50\xe0')
        ctypes.memmove(key.fmtid, guid_bytes, 16)
        key.pid = 30  # DEVPKEY_Device_Address

        # Locate device node
        dev_inst = wintypes.DWORD()
        ret = cfgmgr.CM_Locate_DevNodeW(
            ctypes.byref(dev_inst), instance_id, 0)
        if ret != 0:
            return ""

        # Get property
        prop_type = wintypes.ULONG()
        buf_size = wintypes.ULONG(0)
        # First call to get required buffer size
        cfgmgr.CM_Get_DevNode_PropertyW(
            dev_inst, ctypes.byref(key),
            ctypes.byref(prop_type), None,
            ctypes.byref(buf_size), 0)
        if buf_size.value == 0:
            return ""
        buf = (ctypes.c_byte * buf_size.value)()
        ret = cfgmgr.CM_Get_DevNode_PropertyW(
            dev_inst, ctypes.byref(key),
            ctypes.byref(prop_type), buf,
            ctypes.byref(buf_size), 0)
        if ret != 0:
            return ""
        # DEVPROP_TYPE_UINT32 = 7
        if prop_type.value == 7 and buf_size.value >= 4:
            addr = ctypes.c_uint32.from_buffer(buf).value
            return str(addr)
        return ""
    except Exception:
        return ""


def _check_port_status(device):
    """Check COM port status: 'busy', 'ready', or 'empty'.

    busy  — port is in use by another program (device connected & working)
    ready — port can be opened and has data (device found but not in use)
    empty — port can be opened but no data (nothing connected)
    """
    try:
        ser = serial.Serial(device, baudrate=9600, timeout=0.3)
        try:
            data = ser.read(64)
            if data:
                return "ready"
            return "empty"
        finally:
            ser.close()
    except serial.SerialException as e:
        err_msg = str(e).lower()
        # "Access is denied" / "PermissionError" = another program holds the port
        if "access" in err_msg or "permission" in err_msg or "in use" in err_msg:
            return "busy"
        # Other errors (device removed, port doesn't exist)
        return "disconnected"


_prev_com_status = {}


def get_serial_ports():
    """Get list of physical COM/serial ports with connection status."""
    global _prev_com_status
    ports = []
    for port in serial.tools.list_ports.comports():
        lower = f"{port.device} {port.description}".lower()
        filtered = any(kw in lower for kw in INTERNAL_SERIAL_KEYWORDS)

        status = _check_port_status(port.device)

        # Log only on first scan or status change
        prev = _prev_com_status.get(port.device)
        if prev != status:
            log(f"[COM] {port.device}: {status} | {port.description} | {port.hwid}"
                f"{' (filtered)' if filtered else ''}")
            _prev_com_status[port.device] = status

        if filtered:
            continue

        ports.append({
            "device": port.device,
            "description": port.description,
            "hwid": port.hwid,
            "status": status,
        })
    return ports


INTERNAL_SERIAL_KEYWORDS = [
    "debug-console", "bluetooth", "wlan", "internal",
    "built-in", "btusb", "bthusb",
]

INTERNAL_USB_KEYWORDS = [
    "hub", "host controller", "root hub", "usb bus", "hsic",
    "internal", "built-in", "bluetooth", "bthusb", "btusb",
    "isp", "xhci", "ehci", "ohci", "uhci", "chipset",
    "smbus", "thunderbolt", "pci", "controller",
    "apple t2", "apple internal", "fingerprint",
    "ir receiver", "ambient light", "facetime",
    "generic hub", "usb3.0 hub", "usb2.0 hub",
    "keyboard", "mouse", "wi-fi", "wifi", "wireless adapter",
    "bluecore",
]


def _is_external(name: str) -> bool:
    """Filter out internal USB controllers/hubs, keep external devices."""
    lower = name.lower()
    return not any(kw in lower for kw in INTERNAL_USB_KEYWORDS)


_prev_usb_result = ([], [])


def get_usb_devices():
    """Get list of external USB devices based on OS.

    Returns (visible, all_found) where visible is filtered for UI
    and all_found includes everything for logging.
    On error returns last successful result.
    """
    global _prev_usb_result
    system = platform.system()
    devices = []
    all_devices = []

    try:
        if system == "Darwin":
            out = subprocess.check_output(
                ["system_profiler", "SPUSBDataType", "-detailLevel", "mini"],
                text=True, timeout=10, **_SUBPROCESS_KWARGS
            )
            current_device = None
            is_internal = False

            def _save_device():
                if current_device and not is_internal:
                    all_devices.append(current_device)
                    if _is_external(current_device):
                        devices.append(current_device)

            for line in out.splitlines():
                stripped = line.strip()
                indent = len(line) - len(line.lstrip())
                if stripped.endswith(":") and not stripped.startswith("Host Controller"):
                    name = stripped.rstrip(":")
                    if indent <= 4:
                        _save_device()
                        current_device = None
                        is_internal = False
                    else:
                        _save_device()
                        current_device = name
                        is_internal = False
                elif current_device:
                    if "Built-In" in stripped:
                        is_internal = True
                    elif "Location ID:" in stripped:
                        if "built" in stripped.lower() or "internal" in stripped.lower():
                            is_internal = True
            _save_device()

        elif system == "Linux":
            out = subprocess.check_output(
                ["lsusb"], text=True, timeout=10, **_SUBPROCESS_KWARGS
            )
            for line in out.splitlines():
                if line.strip():
                    parts = line.split("ID ")
                    if len(parts) > 1:
                        vid_pid_name = parts[1]
                        vid_pid = vid_pid_name.split(" ", 1)[0]
                        name = vid_pid_name.split(" ", 1)[1] if " " in vid_pid_name else vid_pid
                        # Skip 1d6b:xxxx (Linux Foundation root hubs)
                        if vid_pid.startswith("1d6b:"):
                            continue
                        all_devices.append(name.strip())
                        if _is_external(name):
                            devices.append(name.strip())

        elif system == "Windows":
            import pythoncom
            import wmi
            pythoncom.CoInitialize()
            try:
                c = wmi.WMI()
                # Infrastructure - skip entirely (no log, no UI)
                skip = re.compile(
                    r"root hub|host controller|generic hub|usb hub"
                    r"|internal|integrated",
                    re.IGNORECASE)
                # Peripherals - log but hide from UI
                hide = re.compile(
                    r"fingerprint|biometric"
                    r"|keyboard|mouse|bluetooth|wi-fi|wifi|wireless adapter"
                    r"|bluecore",
                    re.IGNORECASE)
                # usbccgp = composite device wrapper (language-independent)
                exclude_services = {"usbccgp"}
                # Get physically connected USB device IDs
                connected_ids = set()
                for assoc in c.Win32_USBControllerDevice():
                    dep = assoc.Dependent
                    # dep is a WMI object reference — get its DeviceID
                    dep_id = dep.DeviceID if hasattr(dep, 'DeviceID') else ""
                    if not dep_id:
                        # Fallback: parse string representation
                        dep_str = str(dep)
                        if 'DeviceID="' in dep_str:
                            dep_id = dep_str.split('DeviceID="')[1].rstrip('"')
                            dep_id = dep_id.replace("\\\\", "\\")
                    if dep_id:
                        connected_ids.add(dep_id.upper())
                # First pass: collect port numbers for all USB VID devices
                vidpid_port = {}
                all_usb_devs = []
                for dev in c.Win32_PnPEntity():
                    try:
                        pnp_id = dev.PNPDeviceID or ""
                        if not pnp_id.startswith("USB\\VID_"):
                            continue
                        vp = re.search(r'VID_([0-9A-Fa-f]+)&PID_([0-9A-Fa-f]+)', pnp_id)
                        vid_pid = f"{vp.group(1)}:{vp.group(2)}" if vp else ""
                        # Get port number: LocationInfo > cfgmgr32 > &0&N
                        port = ""
                        try:
                            loc = dev.LocationInformation or ""
                        except Exception:
                            loc = ""
                        m = re.search(r'Port_#(\d+)', loc)
                        if m:
                            port = str(int(m.group(1)))
                        # Fallback: cfgmgr32 DEVPKEY_Device_Address
                        if not port:
                            port = _get_device_address(pnp_id)
                        # Fallback: &0&N from PNPDeviceID
                        if not port and "&MI_" not in pnp_id.upper():
                            m2 = re.search(r'&0&(\d+)$', pnp_id)
                            if m2:
                                port = m2.group(1)
                        if vid_pid and port and vid_pid not in vidpid_port:
                            vidpid_port[vid_pid] = port
                        all_usb_devs.append(dev)
                    except Exception:
                        continue
                # Second pass: group devices by physical port
                port_devices = {}  # port_num -> list of (name, vid_pid, filtered)
                seen_vidpid = set()
                for dev in all_usb_devs:
                    try:
                        pnp_id = dev.PNPDeviceID or ""
                        if pnp_id.upper() not in connected_ids:
                            continue
                        name = dev.Name or ""
                        if not name:
                            continue
                        if skip.search(name):
                            continue
                        service = getattr(dev, 'Service', '') or ""
                        if service.lower() in exclude_services:
                            continue
                        filtered = bool(hide.search(name))
                        vp = re.search(
                            r'VID_([0-9A-Fa-f]+)&PID_([0-9A-Fa-f]+)', pnp_id)
                        vid_pid = f"{vp.group(1)}:{vp.group(2)}" if vp else ""
                        if vid_pid and vid_pid in seen_vidpid:
                            continue
                        if vid_pid:
                            seen_vidpid.add(vid_pid)
                        port_num = vidpid_port.get(vid_pid, "")
                        key = port_num or f"_no_port_{len(port_devices)}"
                        if port_num and port_num in port_devices:
                            port_devices[port_num].append((name, vid_pid, filtered))
                        else:
                            port_devices[key] = [(name, vid_pid, filtered)]
                    except Exception:
                        continue
                # Build labels: group by port
                all_devices = []
                for port_key, devs in port_devices.items():
                    port = port_key if not port_key.startswith("_") else ""
                    prefix = f"USB{port}" if port else "USB"
                    # All devices for logging
                    for d in devs:
                        names_all = d[0]
                        vids_all = d[1] or ""
                        lbl = f"{prefix}: {names_all}"
                        if vids_all:
                            lbl += f" [{vids_all}]"
                        all_devices.append(lbl)
                    # Only show non-filtered in UI
                    visible = [d for d in devs if not d[2]]
                    if not visible:
                        continue
                    names = ", ".join(d[0] for d in visible)
                    vids = ", ".join(d[1] for d in visible if d[1])
                    label = f"{prefix}: {names}"
                    if vids:
                        label += f" [{vids}]"
                    devices.append(label)
            finally:
                pythoncom.CoUninitialize()

    except Exception as e:
        log(f"USB помилка: {e}", "WARN")
        return _prev_usb_result

    _prev_usb_result = (devices, all_devices)
    return devices, all_devices
