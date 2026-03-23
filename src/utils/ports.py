import platform
import re
import subprocess

import serial
import serial.tools.list_ports

from src.utils.logging import log
from src.utils.platform_utils import SUBPROCESS_KWARGS as _SUBPROCESS_KWARGS


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
        if any(kw in lower for kw in INTERNAL_SERIAL_KEYWORDS):
            continue

        status = _check_port_status(port.device)

        # Log only on first scan or status change
        prev = _prev_com_status.get(port.device)
        if prev != status:
            log(f"COM {port.device}: {status} | {port.description} | {port.hwid}")
            _prev_com_status[port.device] = status

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
]


def _is_external(name: str) -> bool:
    """Filter out internal USB controllers/hubs, keep external devices."""
    lower = name.lower()
    return not any(kw in lower for kw in INTERNAL_USB_KEYWORDS)


def get_usb_devices():
    """Get list of external USB devices based on OS."""
    system = platform.system()
    devices = []

    try:
        if system == "Darwin":
            out = subprocess.check_output(
                ["system_profiler", "SPUSBDataType", "-detailLevel", "mini"],
                text=True, timeout=10, **_SUBPROCESS_KWARGS
            )
            current_device = None
            is_internal = False
            for line in out.splitlines():
                stripped = line.strip()
                indent = len(line) - len(line.lstrip())
                # Top-level entries (Bus, Host Controller) at indent <= 4
                # Device names at indent 8-12, ending with ":"
                if stripped.endswith(":") and not stripped.startswith("Host Controller"):
                    name = stripped.rstrip(":")
                    if indent <= 4:
                        # USB Bus header — skip
                        current_device = None
                        is_internal = False
                    else:
                        # Save previous device if external
                        if current_device and not is_internal:
                            if _is_external(current_device):
                                devices.append(current_device)
                        current_device = name
                        is_internal = False
                elif current_device:
                    if "Built-In" in stripped:
                        is_internal = True
                    elif "Location ID:" in stripped:
                        if "built" in stripped.lower() or "internal" in stripped.lower():
                            is_internal = True
            # Last device
            if current_device and not is_internal:
                if _is_external(current_device):
                    devices.append(current_device)

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
                        if _is_external(name):
                            devices.append(name.strip())

        elif system == "Windows":
            import pythoncom
            import wmi
            pythoncom.CoInitialize()
            try:
                c = wmi.WMI()
                exclude = re.compile(
                    r"root hub|host controller|generic hub|usb hub"
                    r"|composite|fingerprint|internal|integrated|biometric",
                    re.IGNORECASE)
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
                log(f"USB connected IDs: {len(connected_ids)} devices")
                for dev in c.Win32_PnPEntity():
                    pnp_id = dev.PNPDeviceID or ""
                    if not pnp_id.startswith("USB\\VID_"):
                        continue
                    if pnp_id.upper() not in connected_ids:
                        continue
                    name = dev.Name or ""
                    if not name:
                        continue
                    if exclude.search(name):
                        continue
                    devices.append(name)
            finally:
                pythoncom.CoUninitialize()

    except Exception as e:
        log(f"USB помилка: {e}", "WARN")

    return devices
