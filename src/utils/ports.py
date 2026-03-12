import platform
import subprocess

import serial.tools.list_ports


def get_serial_ports():
    """Get list of COM/serial ports with status."""
    ports = []
    for port in serial.tools.list_ports.comports():
        ports.append({
            "device": port.device,
            "description": port.description,
            "hwid": port.hwid,
        })
    return ports


def get_usb_devices():
    """Get list of USB devices based on OS."""
    system = platform.system()
    devices = []

    try:
        if system == "Darwin":
            out = subprocess.check_output(
                ["system_profiler", "SPUSBDataType", "-detailLevel", "mini"],
                text=True, timeout=10
            )
            for line in out.splitlines():
                line = line.strip()
                if line and not line.startswith(("USB", "Location", "Host",
                                                  "Available", "Current")):
                    if ":" not in line and line:
                        devices.append(line.rstrip(":"))

        elif system == "Linux":
            out = subprocess.check_output(
                ["lsusb"], text=True, timeout=10
            )
            for line in out.splitlines():
                if line.strip():
                    # Format: Bus XXX Device XXX: ID xxxx:xxxx Name
                    parts = line.split("ID ")
                    name = parts[1].split(" ", 1)[1] if len(parts) > 1 else line
                    devices.append(name.strip())

        elif system == "Windows":
            out = subprocess.check_output(
                ["powershell", "-Command",
                 "Get-PnpDevice -Class USB -Status OK | Select-Object -ExpandProperty FriendlyName"],
                text=True, timeout=10
            )
            for line in out.splitlines():
                if line.strip():
                    devices.append(line.strip())

    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return devices
