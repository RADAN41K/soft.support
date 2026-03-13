import platform
import subprocess
import sys

import serial.tools.list_ports

# Hide console window on Windows
_SUBPROCESS_KWARGS = {}
if platform.system() == "Windows":
    _SUBPROCESS_KWARGS["creationflags"] = (
        subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW")
        else 0x08000000
    )


def get_serial_ports():
    """Get list of physical COM/serial ports (filter out internal)."""
    ports = []
    for port in serial.tools.list_ports.comports():
        lower = f"{port.device} {port.description}".lower()
        if any(kw in lower for kw in INTERNAL_SERIAL_KEYWORDS):
            continue
        ports.append({
            "device": port.device,
            "description": port.description,
            "hwid": port.hwid,
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
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command",
                 "Get-PnpDevice -Class USB,USBSTOR,DiskDrive,WPD -Status OK "
                 "| Where-Object { $_.FriendlyName -notmatch "
                 "'Hub|Host Controller|Root|Composite|Input Device|Keyboard|Mouse|HID' } "
                 "| Select-Object -ExpandProperty FriendlyName"],
                text=True, timeout=10, **_SUBPROCESS_KWARGS
            )
            for line in out.splitlines():
                name = line.strip()
                if name and _is_external(name):
                    devices.append(name)

    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return devices
