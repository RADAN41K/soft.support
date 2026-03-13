import platform
import subprocess

import serial.tools.list_ports


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
                text=True, timeout=10
            )
            current_device = None
            is_internal = False
            for line in out.splitlines():
                stripped = line.strip()
                indent = len(line) - len(line.lstrip())
                # Device names are at specific indent levels, no colon in name
                if indent <= 12 and stripped and ":" not in stripped:
                    # Save previous device if external
                    if current_device and not is_internal:
                        if _is_external(current_device):
                            devices.append(current_device)
                    current_device = stripped.rstrip(":")
                    is_internal = False
                elif current_device and "Built-In" in stripped:
                    is_internal = True
                elif current_device and "Location ID:" in stripped:
                    # Internal devices often have specific location patterns
                    if "built" in stripped.lower() or "internal" in stripped.lower():
                        is_internal = True
            # Last device
            if current_device and not is_internal:
                if _is_external(current_device):
                    devices.append(current_device)

        elif system == "Linux":
            out = subprocess.check_output(
                ["lsusb"], text=True, timeout=10
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
                ["powershell", "-Command",
                 "Get-PnpDevice -Class USB -Status OK "
                 "| Where-Object { $_.FriendlyName -notmatch "
                 "'Hub|Host Controller|Root|Composite' } "
                 "| Select-Object -ExpandProperty FriendlyName"],
                text=True, timeout=10
            )
            for line in out.splitlines():
                name = line.strip()
                if name and _is_external(name):
                    devices.append(name)

    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return devices
